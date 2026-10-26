"""주간 운영 작업과 닫힌 고리 모의 실행.

주간 작업(run_week, 주 w가 끝난 뒤 한 번):
  1) 데이터 확인: w주까지의 기록만 쓴다(미래 주 차단), 이미 결정한 주는 다시 결정하지 않는다(--force 제외).
  2) 재학습: w−1주·w주 스냅샷의 특징·신호를 새 기록으로 다시 만든다.
  3) 재선정: 후보 정책(현재 정책, 선언 정책, 가중치 변형, 자격 있는 기존 설정)을 w−1주 NDCG@K로 비교해 도전 정책 1개를 고른다.
  4) 되돌리기 판정: 직전 주에 교체했다면 w주 자료로 새 정책과 이전 정책을 다시 비교한다.
  5) 검증 게이트: 선정에 쓰지 않은 w주 자료로 현재 정책과 도전 정책을 비교하고, w주 탐색 기록으로 OPE를 계산한다.
  6) 결정·이력: 게이트를 모두 통과할 때만 교체한다. 결정과 근거를 해시 사슬 이력과 주간 보고서에 남긴다.
  7) 서빙 갱신: (선택) w주 기록까지 반영한 w+1주 서빙 번들을 만든다.

모의 실행(simulate): 합성 세계에서 매주 현재 정책 + 탐색으로 활동 학습자에게 목록을 보이고(노출 확률 기록),
그 주의 실제 퀴즈 통과를 반응으로 기록한 뒤 run_week를 돌린다. 합성 세계의 행동은 추천과 무관하게 생성되므로
반응은 "보인 단원을 그 주에 통과했는가"이며, 추천이 행동을 바꾸는 효과는 모의 범위 밖이다.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import pickle
import shutil
import time
from dataclasses import asdict, dataclass, field

import numpy as np

from .. import __version__
from ..catalog import RADIX, Catalog
from ..config import K, N_CPU, SEED, GuardrailConfig, TrainConfig
from ..data import Dataset
from ..evaluation import candidate_items, choose_items, evaluate_zoo, make_select, primary_eval
from ..features import feature_store
from ..privacy import generalize_profiles, minimize_log
from ..signals import CandidateBatch, LearnerBatch, ModelStore, Reference, SignalBank, build_signals, supervised_from_log
from ..util import get_logger, json_safe
from ..zoo import score_algo
from . import metrics as M
from .exploration import ExplorationConfig, explore_slate
from .gate import GateConfig, evaluate_gate, rollback_check
from .logstore import OpsLog
from .ope import attach_rewards, logged_value, paired_difference, policy_value
from .policies import DEFAULT_GRID, algo_from_spec, candidate_pool, declared_spec, eligibility, public_spec
from .registry import PolicyRegistry

SERVICE_GUARD = GuardrailConfig(block_gap=2, plus_one_max=1, exclude_passed=True, prereq_block=True)   # 서비스와 같은 필수 가드레일


@dataclass
class LoopConfig:
    k: int = K
    exploration: ExplorationConfig = field(default_factory=ExplorationConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    grid: dict = field(default_factory=lambda: dict(DEFAULT_GRID))
    include_zoo: bool = True                 # 기존 설정 가운데 목적·로드맵 항이 있는 것도 후보로
    reward_event: str = "quiz_pass"          # OPE 보상: 같은 주 안 퀴즈 통과
    refresh_serving: bool = True             # 결정 뒤 다음 주 서빙 번들을 만든다
    full_retrain: bool = False               # 전체 학습 파이프라인(train)으로 기준 번들도 새로 학습(후보 설정·신호 설명 갱신, 느림)
    keep_serving: int = 2                    # 남길 서빙 번들 수
    n_workers: int = N_CPU
    seed: int = SEED

    def as_dict(self) -> dict:
        d = asdict(self)
        d["grid"] = {k: list(v) for k, v in self.grid.items()}
        return d

    @classmethod
    def from_settings(cls, settings: dict, **overrides) -> "LoopConfig":
        s = dict(settings or {})
        exp = ExplorationConfig(**s.get("exploration", {})) if s.get("exploration") else ExplorationConfig()
        gate = GateConfig(**s.get("gate", {})) if s.get("gate") else GateConfig()
        grid = {k: tuple(v) for k, v in s["grid"].items()} if s.get("grid") else dict(DEFAULT_GRID)
        kw = dict(k=s.get("k", K), exploration=exp, gate=gate, grid=grid, include_zoo=s.get("include_zoo", True),
                  reward_event=s.get("reward_event", "quiz_pass"))
        kw.update(overrides)
        return cls(**kw)


def default_settings(cfg: LoopConfig = None) -> dict:
    cfg = cfg or LoopConfig()
    return dict(k=cfg.k, exploration=cfg.exploration.as_dict(), gate=cfg.gate.as_dict(), grid={k: list(v) for k, v in cfg.grid.items()},
                include_zoo=cfg.include_zoo, reward_event=cfg.reward_event)


# ---------- 공통 계산 ----------
def _rows_candidates(F, users, catalog) -> CandidateBatch:
    lists = [candidate_items(F.und[u], F.level[u], catalog, SERVICE_GUARD) for u in users]
    L = max([len(x) for x in lists] + [1])
    C = np.full((len(users), L), -1, dtype=int)
    for r, ca in enumerate(lists):
        C[r, :len(ca)] = ca
    return CandidateBatch(np.asarray(users, dtype=np.int64), C)


def _bank(cands, ref, lb, catalog, models, needed) -> SignalBank:
    bank = SignalBank(cands)
    build_signals(bank, ref, lb, catalog, models, needed=set(needed))
    return bank


def ranked_orders(algo, bank, lb, catalog, cands):
    """행마다 가드레일·한 단계 위 상한을 통과한 후보의 전체 순서(열 번호)와 점수."""
    S = score_algo(algo, bank, lb.nu)
    cols = choose_items(cands, lb, catalog, S, k=max(cands.L, 1), guard=SERVICE_GUARD)
    return cols, S


def impression_record(slate: dict, week: int, user_ref, spec: dict, k: int, n_candidates: int, source: str) -> dict:
    return dict(request_id=slate["request_id"], week=int(week), user_ref=None if user_ref is None else int(user_ref),
                policy=dict(key=spec["key"], version=spec["version"], hash=spec["hash"]), k=int(k),
                items=[int(x) for x in slate["items"]], propensity=[float(p) for p in slate["propensity"]],
                explored=bool(slate["explored"]), slot=slate["slot"], exploit_item=slate["exploit_item"],
                prefix=[int(x) for x in slate["prefix"]], pool=[int(x) for x in slate["pool"]], pool_prob=slate["pool_prob"],
                epsilon=float(slate["epsilon"]), method=slate["method"], n_candidates=int(n_candidates), source=source)


def serve_batch(profiles, log_before, catalog, week: int, spec: dict, cfg: LoopConfig, users, source: str = "simulation") -> list:
    """현재 정책 + 탐색으로 학습자 묶음에 목록을 만들고 노출 기록을 돌려준다(모의 서빙·일괄 서빙)."""
    users = np.asarray(sorted(set(int(u) for u in users)), dtype=np.int64)
    if len(users) == 0:
        return []
    F = feature_store(profiles, log_before, catalog, week)
    lb = LearnerBatch.from_store(F, users)
    cands = _rows_candidates(F, users, catalog)
    algo = algo_from_spec(spec)
    bank = _bank(cands, Reference.from_store(F, catalog, RADIX, None), lb, catalog, ModelStore(False, seed=cfg.seed), algo.signals)
    cols, S = ranked_orders(algo, bank, lb, catalog, cands)
    out = []
    for r, u in enumerate(users):
        c = cols[r][cols[r] >= 0]
        slate = explore_slate(cands.cand[r, c], S[r, c], cfg.k, cfg.exploration, f"{source[:3]}-w{week}-u{int(u)}")
        if slate["items"]:
            out.append(impression_record(slate, week, int(u), spec, cfg.k, len(c), source))
    return out


def policy_lists(profiles, log_before, catalog, week: int, specs: list, users, k: int, seed: int = SEED) -> dict:
    """정책별 Top-K 단원 목록(행 = users 순서). OPE 목표 목록과 모의 실행의 실제 성과 계산에 쓴다."""
    users = np.asarray(users, dtype=np.int64)
    F = feature_store(profiles, log_before, catalog, week)
    lb = LearnerBatch.from_store(F, users)
    cands = _rows_candidates(F, users, catalog)
    algos = [algo_from_spec(s) for s in specs]
    bank = _bank(cands, Reference.from_store(F, catalog, RADIX, None), lb, catalog, ModelStore(False, seed=seed),
                 {sig for a in algos for sig in a.signals})
    out = {}
    for s, a in zip(specs, algos):
        S = score_algo(a, bank, lb.nu)
        out[s["hash"]] = M.cols_to_items(choose_items(cands, lb, catalog, S, k=k, guard=SERVICE_GUARD), cands)
    return out


def _context(profiles, log_df, catalog, week: int, needed, seed: int) -> dict:
    F = feature_store(profiles, log_df, catalog, week)
    cands, lb = primary_eval(week, F, log_df, catalog, SERVICE_GUARD)
    bank = _bank(cands, Reference.from_store(F, catalog, RADIX, None), lb, catalog, ModelStore(False, seed=seed), needed)
    return dict(F=F, cands=cands, lb=lb, bank=bank)


def _summary(m: dict) -> dict:
    return dict(ndcg=m["ndcg"], hit=m["hit"], diversity=m["diversity"], alignment=m["alignment"], prereq_violation=m["prereq_violation"],
                exposure_max_gap=m["exposure"]["max_gap"], exposure={k: v for k, v in m["exposure"].items() if k != "max_gap"}, users=m["users"])


def _data_hash(log_df) -> str:
    cols = [c for c in ("user", "item", "week", "complete", "quiz", "quiz_pass", "save", "drop", "replay", "source") if c in log_df.columns]
    body = log_df[cols].sort_values(cols, kind="stable").to_csv(index=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


@contextlib.contextmanager
def _lock(root: str):
    path = os.path.join(root, ".lock")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"다른 주간 작업이 실행 중입니다({path}). 실행 중인 작업이 없다면 이 파일을 지우고 다시 실행하세요")
    try:
        os.write(fd, f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S')}".encode()); os.close(fd)
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)


# ---------- 주간 작업 ----------
def run_week(ops_dir: str, dataset: Dataset, week: int, cfg: LoopConfig = None, base_bundle=None, force: bool = False,
             truth: dict = None, log=None) -> dict:
    """주 w가 끝난 뒤의 재학습·재선정·게이트·결정. 반환값은 이력에 남긴 기록(보고서 경로 포함)."""
    logger = log or get_logger().info
    reg = PolicyRegistry(ops_dir)
    cfg = cfg or LoopConfig.from_settings(reg.settings)
    week = int(week)
    if week < 2:
        raise ValueError("선정 주(w−1)와 확인 주(w)가 모두 필요하므로 week는 2 이상이어야 합니다")
    if week in reg.decided_weeks() and not force:
        raise RuntimeError(f"{week}주 결정이 이미 이력에 있습니다(같은 주를 다시 판정하려면 --force)")
    with _lock(ops_dir):
        t0 = time.time()
        catalog, profiles = dataset.catalog, dataset.profiles
        log_df = dataset.log[dataset.log.week <= week]              # 미래 주 기록은 쓰지 않는다
        if log_df.empty or int(log_df.week.max()) < week:
            raise ValueError(f"{week}주 학습 기록이 없습니다")
        act = log_df if "source" not in log_df.columns else log_df[log_df["source"] != "diagnosis"]     # 진단 인정만 있는 학습자는 활동이 아니다
        data = dict(through_week=week, rows=int(len(log_df)), active_users_week=int(act[act.week == week].user.nunique()),
                    active_users_selection_week=int(act[act.week == week - 1].user.nunique()), sha256=_data_hash(log_df))
        if data["active_users_week"] < cfg.gate.min_users or data["active_users_selection_week"] < cfg.gate.min_users:
            rec = reg.append_history(dict(event="skipped", week=week, reason="활동 학습자가 최소 표본보다 적음", data=data,
                                          champion_after=public_spec(reg.champion), code_version=__version__))
            return _write_report(ops_dir, rec, {})
        base = base_bundle if base_bundle is not None else (_load_pickle(reg.state["base_bundle"]) if reg.state.get("base_bundle") else None)
        if cfg.full_retrain and base is not None:
            base = _full_retrain(ops_dir, reg, dataset, log_df, week, base)
            data["full_retrain"] = reg.state["base_bundle"]
        info = dict(base.signal_meta) if base is not None else {}
        champion = reg.champion
        pool = candidate_pool(champion, base.algos if (base is not None and cfg.include_zoo) else None, info, cfg.grid, cfg.include_zoo)
        # 1) 재학습 + 재선정(w−1주)
        needed = {sig for s in pool for sig, _ in s["terms"]
                  if s["hash"] == champion["hash"] or s["source"] != "zoo"
                  or not eligibility(s, info, cfg.gate.min_goal_weight, cfg.gate.min_roadmap_weight)}
        val = _context(profiles, log_df, catalog, week - 1, needed, cfg.seed)
        info.update(val["bank"].info)
        elig = {s["hash"]: eligibility(s, info, cfg.gate.min_goal_weight, cfg.gate.min_roadmap_weight) for s in pool}
        specs = [s for s in pool if all(sig in val["bank"] for sig, _ in s["terms"]) and (not elig[s["hash"]] or s["hash"] == champion["hash"])]
        algos = [algo_from_spec(s) for s in specs]
        _, _, jobs = evaluate_zoo(algos, val["bank"], val["lb"].nu, make_select(val["cands"], val["lb"], catalog, cfg.k, SERVICE_GUARD),
                                  catalog.item_topic, cfg.n_workers)
        jobs = jobs.sort_values("job_id").reset_index(drop=True)
        jobs["hash"] = [s["hash"] for s in specs]
        champ_val = float(jobs.loc[jobs.hash == champion["hash"], "ndcg"].iloc[0]) if (jobs.hash == champion["hash"]).any() else None
        ranked = jobs[jobs.hash != champion["hash"]].sort_values("ndcg", ascending=False, kind="mergesort")
        selection = dict(candidates=len(pool), evaluated=len(specs), ineligible=int(sum(bool(v) for v in elig.values())),
                         champion_validation_ndcg=champ_val, selection_week=week - 1,
                         top=[dict(name=r.name, hash=r.hash, ndcg=float(r.ndcg)) for r in ranked.head(5).itertuples()])
        challenger = None
        if len(ranked) and (champ_val is None or float(ranked.iloc[0].ndcg) > champ_val):
            challenger = specs[int(ranked.iloc[0].job_id)]
        selection["challenger_validation_ndcg"] = float(ranked.iloc[0].ndcg) if challenger is not None else None
        logger(f"[운영 {week}주] 후보 {len(specs)}개 선정 비교, 현재 {champ_val}, 도전 {selection['challenger_validation_ndcg']}")
        # 2) 확인 주(w) 지표
        prev = reg.state["previous"][-1] if reg.state["previous"] else None
        promoted_last_week = reg.state.get("last_change_week") == week - 1 and prev is not None
        compare = [champion] + ([challenger] if challenger is not None else []) + ([prev] if promoted_last_week else [])
        test = _context(profiles, log_df, catalog, week, {sig for s in compare for sig, _ in s["terms"]}, cfg.seed)
        masks = M.stage_masks(catalog, test["lb"]); codes = test["F"].codes[test["cands"].user]
        sel = make_select(test["cands"], test["lb"], catalog, cfg.k, SERVICE_GUARD)
        met = {s["hash"]: M.policy_metrics(sel(score_algo(algo_from_spec(s), test["bank"], test["lb"].nu)), test["cands"], test["lb"],
                                            catalog, masks, codes, cfg.k) for s in compare}
        m_champ = met[champion["hash"]]
        # 3) OPE(w주 탐색 기록)
        oplog = OpsLog(os.path.join(ops_dir, "logs"))
        logged = attach_rewards(oplog.impressions(week), oplog.feedback(week), cfg.reward_event)
        ope = _ope(profiles, log_df, catalog, week, logged, champion, challenger, prev if promoted_last_week else None, cfg)
        record = dict(week=week, data=data, champion=public_spec(champion), selection=selection, config=cfg.as_dict(),
                      code_version=__version__, confirmation=dict(champion=_summary(m_champ)), ope=ope.get("summary"))
        # 4) 되돌리기 판정(직전 주 교체)
        if promoted_last_week:
            m_prev = met[prev["hash"]]
            m_champ["paired_vs_previous"] = M.paired_ndcg(m_champ, m_prev, cfg.gate.bootstrap_n, cfg.seed)
            rb = rollback_check(cfg.gate, m_champ, m_prev)
            record["rollback_check"] = json_safe(rb); record["confirmation"]["previous"] = _summary(m_prev)
            if rb["rollback"]:
                rec = reg.rollback(week, f"교체 다음 주 확인 실패: {rb['reason'].strip()}", record)
                return _finish(ops_dir, reg, rec, dataset, log_df, base, week, cfg, truth, logger, t0)
        # 5) 게이트
        if challenger is None:
            rec = reg.append_history(dict(record, event="no_challenger", reason="선정 주에 현재 정책보다 나은 자격 후보 없음",
                                          champion_after=public_spec(champion)))
            return _finish(ops_dir, reg, rec, dataset, log_df, base, week, cfg, truth, logger, t0)
        m_chall = met[challenger["hash"]]
        m_chall["paired_ndcg"] = M.paired_ndcg(m_chall, m_champ, cfg.gate.bootstrap_n, cfg.seed)
        m_chall["paired_alignment"] = M.paired_alignment_ci(m_chall["alignment_counts"], m_champ["alignment_counts"], cfg.gate.bootstrap_n, cfg.seed)
        gate = evaluate_gate(cfg.gate, m_champ, m_chall, elig[challenger["hash"]], ope.get("gate"), reg.frozen, reg.weeks_since_change(week))
        record.update(challenger=public_spec(challenger), gate=json_safe(gate))
        record["confirmation"]["challenger"] = dict(_summary(m_chall), paired_ndcg=m_chall["paired_ndcg"],
                                                    paired_alignment=m_chall["paired_alignment"])
        if gate["passed"]:
            rec = reg.promote(challenger, week, "검증 게이트의 모든 차단 기준 통과", record)
        else:
            rec = reg.append_history(dict(record, event="kept", reason="게이트 미통과: " + ", ".join(gate["failed"]),
                                          champion_after=public_spec(champion)))
        return _finish(ops_dir, reg, rec, dataset, log_df, base, week, cfg, truth, logger, t0)


def _ope(profiles, log_df, catalog, week, logged, champion, challenger, previous, cfg) -> dict:
    """w주 탐색 기록으로 현재·도전(·이전) 정책의 요청당 성공 수 추정. 기록 정책과 재계산 목록의 일치도도 본다."""
    if not logged:
        return dict(summary=dict(requests=0, note="이번 주 탐색 기록 없음"), gate=None)
    users = sorted({int(r["user_ref"]) for r in logged})
    specs = [s for s in (champion, challenger, previous) if s is not None]
    lists = policy_lists(profiles, log_df, catalog, week, specs, users, cfg.k, cfg.seed)
    row = {u: i for i, u in enumerate(users)}
    targets = {s["hash"]: {r["request_id"]: [int(x) for x in lists[s["hash"]][row[int(r["user_ref"])]] if x >= 0] for r in logged}
               for s in specs}
    same = [r for r in logged if r["policy"]["hash"] == champion["hash"]]
    match = [targets[champion["hash"]][r["request_id"]][:len(r["prefix"])] == r["prefix"] for r in same]
    consistency = float(np.mean(match)) if match else None
    vals = {s["hash"]: policy_value(logged, targets[s["hash"]], cfg.k) for s in specs}
    summary = dict(requests=len(logged), explored=int(sum(bool(r["explored"]) for r in logged)), logged_value=logged_value(logged),
                   logging_consistency=consistency, champion=vals[champion["hash"]])
    gate = None
    if challenger is not None:
        summary["challenger"] = vals[challenger["hash"]]
        summary["diff"] = paired_difference(logged, targets[challenger["hash"]], targets[champion["hash"]], cfg.k)
        if consistency is None or consistency >= 0.95:
            gate = dict(champion=vals[champion["hash"]], challenger=vals[challenger["hash"]], diff=summary["diff"])
        else:
            summary["note"] = f"기록 정책과 재계산 목록 일치도 {consistency:.2f} < 0.95: OPE를 게이트에서 쓰지 않음"
    if previous is not None:
        summary["previous"] = vals[previous["hash"]]
    return dict(summary=json_safe(summary), gate=gate, lists=lists, users=users)


def _finish(ops_dir, reg, rec, dataset, log_df, base, week, cfg, truth, logger, t0) -> dict:
    extra = {}
    if truth is not None:                                          # 모의 실행: 전체 통과 기록으로 계산한 실제 성과(OPE 점검용)
        extra["truth"] = truth
    if cfg.refresh_serving and base is not None:
        path = refresh_serving(ops_dir, base, dataset, log_df, week + 1, reg.champion, cfg)
        reg.set_serving_bundle(path, week + 1); extra["serving_bundle"] = path
    extra["seconds"] = round(time.time() - t0, 1)
    logger(f"[운영 {week}주] 결정: {rec['event']} ({extra['seconds']}초)")
    return _write_report(ops_dir, rec, extra)


def _full_retrain(ops_dir, reg, dataset, log_df, week, base):
    """표준 학습 파이프라인을 w−1주 선정·w주 확인으로 다시 돌려 감사 기록(QA·개인정보 점검·결과표)이 있는 기준 번들을 만든다."""
    import dataclasses
    from .. import neural
    from ..pipeline import train
    tc = dataclasses.replace(base.config, val_week=week - 1, test_week=week)
    ds = Dataset(dataset.profiles, log_df.copy(), dataset.catalog, source=dataset.source, meta=dataset.meta)
    out = os.path.join(ops_dir, "bundles", f"week={week:04d}")
    b = train(ds, tc, out_dir=out, enable_neural=bool(base.models.enable_neural) and neural.HAS_TORCH, log=lambda *a, **k: None)
    reg.state["base_bundle"] = out; reg.save()
    return b


def _load_pickle(path: str):
    p = os.path.join(path, "bundle.pkl") if os.path.isdir(path) else path
    with open(p, "rb") as f:
        return pickle.load(f)


def refresh_serving(ops_dir, base, dataset, log_df, serve_week: int, champion: dict, cfg: LoopConfig) -> str:
    """기준 번들의 설정·모델 구성은 그대로 두고, 서빙 스냅샷만 serve_week 직전까지의 기록으로 바꾼 번들을 저장한다."""
    catalog = dataset.catalog
    before = log_df[log_df.week < serve_week]
    F = feature_store(dataset.profiles, before, catalog, serve_week)
    sup = supervised_from_log(before, base.config.train_max_rows, base.config.seed, n_items=catalog.n_items)
    b = copy.copy(base)
    b.store, b.reference = F, Reference.from_store(F, catalog, RADIX, sup)
    b.models = ModelStore(bool(base.models.enable_neural), seed=base.config.seed)
    b.profiles, b.log = generalize_profiles(dataset.profiles, F.codes), minimize_log(before)
    b.selection = dict(base.selection, ops_champion=public_spec(champion), ops_serving_week=int(serve_week))
    b.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    out_dir = os.path.join(ops_dir, "serving", f"week={serve_week:04d}")
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "bundle.pkl.tmp")
    with open(tmp, "wb") as f:
        pickle.dump(b, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, os.path.join(out_dir, "bundle.pkl"))
    root = os.path.join(ops_dir, "serving")
    old = sorted(d for d in os.listdir(root) if d.startswith("week="))[:-max(1, cfg.keep_serving)]
    for d in old:
        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    return out_dir


def _write_report(ops_dir: str, rec: dict, extra: dict) -> dict:
    out = dict(rec, **extra)
    d = os.path.join(ops_dir, "reports")
    os.makedirs(d, exist_ok=True)
    stem = f"week={int(rec['week']):04d}" if rec.get("week") is not None else f"seq={rec['seq']:04d}"
    with open(os.path.join(d, stem + ".json"), "w", encoding="utf-8") as f:
        json.dump(json_safe(out), f, ensure_ascii=False, indent=2)
    with open(os.path.join(d, stem + ".md"), "w", encoding="utf-8") as f:
        f.write(report_markdown(out))
    out["report"] = os.path.join(d, stem + ".md")
    return out


def _f(x, d=4):
    return "–" if x is None else (f"{x:.{d}f}" if isinstance(x, (int, float)) else str(x))


def report_markdown(r: dict) -> str:
    ev = {"promoted": "교체", "kept": "유지(게이트 미통과)", "no_challenger": "유지(더 나은 후보 없음)", "rolled_back": "되돌림",
          "skipped": "건너뜀(표본 부족)"}.get(r.get("event"), r.get("event"))
    lines = [f"# 운영 루프 {r.get('week')}주 보고서", "", f"- 결정: **{ev}** — {r.get('reason', '')}",
             f"- 현재 정책(판정 전): {r.get('champion', r.get('champion_before', {})).get('name', '–')}",
             f"- 판정 뒤 정책: {r.get('champion_after', {}).get('name', '–')}"]
    d = r.get("data") or {}
    lines += [f"- 데이터: {d.get('through_week')}주까지 {d.get('rows')}행, 확인 주 활동 {d.get('active_users_week')}명, "
              f"sha256 {str(d.get('sha256', ''))[:12]}…", ""]
    s = r.get("selection")
    if s:
        lines += ["## 재선정(선정 주)", f"- 후보 {s['candidates']}개 중 평가 {s['evaluated']}개(자격 미달 {s['ineligible']}개)",
                  f"- 현재 정책 NDCG@K {_f(s['champion_validation_ndcg'])}, 도전 정책 {_f(s.get('challenger_validation_ndcg'))}",
                  f"- 도전 정책: {(r.get('challenger') or {}).get('name', '없음')}", ""]
    g = r.get("gate")
    if g:
        lines += ["## 검증 게이트(확인 주)", "", "| 기준 | 결과 | 값 | 기준값 |", "| --- | --- | --- | --- |"]
        for c in g["criteria"]:
            mark = "통과" if c["passed"] is True else ("미평가" if c["passed"] is None else "실패")
            lines.append(f"| {c['name']} | {mark}{'' if c['blocking'] else ' (참고)'} | {json.dumps(c['value'], ensure_ascii=False, default=str)[:80]} | {c['threshold']} |")
        lines.append("")
    o = r.get("ope")
    if o and o.get("requests"):
        ch = o.get("champion") or {}
        lines += ["## 탐색 기록 OPE", f"- 요청 {o['requests']}건, 탐색 {o['explored']}건, 관측 성공 수 {_f(o['logged_value'])}/요청, "
                  f"기록 일치도 {_f(o.get('logging_consistency'), 3)}",
                  f"- 현재 정책 IPS {_f(ch.get('ips'))} (SNIPS {_f(ch.get('snips'))})"]
        if o.get("challenger"):
            dd = o.get("diff") or {}
            lines.append(f"- 도전 정책 IPS {_f(o['challenger'].get('ips'))}, 차이 {_f(dd.get('diff'))} [{_f(dd.get('ci_low'))}, {_f(dd.get('ci_high'))}], "
                         f"도전 정책만의 단원 관측 {dd.get('unique_matches')}건")
        lines.append("")
    t = r.get("truth")
    if t:
        lines += ["## 모의 실행 실제 성과(전체 통과 기록)", *[f"- {k}: {_f(v)}" for k, v in t.items()], ""]
    lines += [f"이력 seq {r.get('seq')} · hash {str(r.get('hash', ''))[:12]}…", ""]
    return "\n".join(lines)


# ---------- 모의 실행 ----------
def simulate(ops_dir: str, n: int = 3000, weeks: int = 8, start: int = 3, seed: int = SEED, cfg: LoopConfig = None,
             log=None, force: bool = False) -> dict:
    """합성 세계에서 서빙(탐색·노출 확률 기록) → 반응 기록 → 주간 작업을 start..weeks−1주 반복한다."""
    from ..pipeline import train
    from ..synth import make_world
    logger = log or get_logger().info
    if start < 3 or weeks <= start:
        raise ValueError("start는 3 이상(기준 번들 학습에 0~start−1주 필요), weeks는 start보다 커야 합니다")
    if os.path.exists(os.path.join(ops_dir, "registry.json")) and not force:
        raise FileExistsError(f"{ops_dir}에 이미 운영 기록이 있습니다(새로 시작하려면 다른 폴더나 --force)")
    if force and os.path.isdir(ops_dir):
        shutil.rmtree(ops_dir)
    cfg = cfg or LoopConfig(refresh_serving=False)
    tc = TrainConfig(n_learners=n, seed=seed, val_week=start - 2, test_week=start - 1, router_reps=1, bootstrap_n=100)
    catalog = Catalog.default(seed, version=tc.catalog_version)
    world = make_world(n, catalog, seed=seed, effect=tc.effect_scale, gender_effect=tc.gender_effect, n_weeks=weeks,
                       version=tc.generator_version, goal_effect=tc.goal_effect, prereq_penalty=tc.prereq_penalty)
    full = Dataset(world["profiles"], world["log"], catalog, source="synthetic", meta=dict(seed=seed, n_weeks=weeks, simulation=True))
    logger(f"[모의] 학습자 {n}명 · {weeks}주 세계, 기준 번들 학습(0~{start - 1}주)")
    base_ds = Dataset(full.profiles, full.log[full.log.week < start].copy(), catalog, source="synthetic", meta=full.meta)
    base = train(base_ds, tc, out_dir=None, enable_neural=False, log=lambda *a, **k: None)
    os.makedirs(ops_dir, exist_ok=True)
    base_path = os.path.join(ops_dir, "base_bundle.pkl")
    with open(base_path, "wb") as f:
        pickle.dump(base, f, protocol=pickle.HIGHEST_PROTOCOL)
    PolicyRegistry.init(ops_dir, declared_spec(), default_settings(cfg), base_bundle=base_path,
                        note=f"모의 실행: n={n}, weeks={weeks}, start={start}, seed={seed}")
    oplog = OpsLog(os.path.join(ops_dir, "logs"))
    rows = []
    for w in range(start, weeks):
        reg = PolicyRegistry(ops_dir)
        champ = reg.champion
        wk = full.log[full.log.week == w]
        users = sorted(wk.user.unique().tolist())                  # 그 주에 들어온 학습자에게 목록을 보인다
        imps = serve_batch(full.profiles, full.log[full.log.week < w], catalog, w, champ, cfg, users)
        oplog.append_impressions(imps)
        passes = wk[wk.quiz_pass.astype(bool)][["user", "item"]].drop_duplicates()
        oplog.append_feedback([dict(week=int(w), user_ref=int(u), item=int(i), event="quiz_pass", source="simulation")
                               for u, i in passes.itertuples(index=False)])
        passed = set(map(tuple, passes.to_numpy().tolist()))
        truth = dict(champion_true_hits=_true_hits(full, catalog, w, users, champ, cfg, passed))
        ds_w = Dataset(full.profiles, full.log[full.log.week <= w].copy(), catalog, source="synthetic", meta=full.meta)
        res = run_week(ops_dir, ds_w, w, cfg, base_bundle=base, truth=truth, log=logger)
        ope, chall = res.get("ope") or {}, res.get("challenger")
        rows.append(dict(week=w, event=res["event"], champion_before=(res.get("champion") or res.get("champion_before") or {}).get("name"),
                         champion_after=res["champion_after"]["name"], challenger=(chall or {}).get("name"),
                         failed=(res.get("gate") or {}).get("failed"), impressions=len(imps), explored=sum(r["explored"] for r in imps),
                         ope_champion=(ope.get("champion") or {}).get("ips"), true_champion=truth["champion_true_hits"],
                         ope_challenger=(ope.get("challenger") or {}).get("ips"),
                         true_challenger=_true_hits(full, catalog, w, users, chall, cfg, passed) if chall else None,
                         report=res["report"]))
    reg = PolicyRegistry(ops_dir)
    summary = dict(ops_dir=ops_dir, weeks=rows, final_champion=public_spec(reg.champion), history_ok=reg.verify()["ok"])
    with open(os.path.join(ops_dir, "simulation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(json_safe(summary), f, ensure_ascii=False, indent=2)
    return summary


def _true_hits(full, catalog, week, users, spec, cfg, passed: set):
    """모의 실행 전용: 정책 Top-K(탐색 없음)의 실제 요청당 성공 수(그 주 전체 통과 기록 기준). OPE 추정과 비교한다."""
    L = policy_lists(full.profiles, full.log[full.log.week < week], catalog, week, [spec], users, cfg.k, cfg.seed)[spec["hash"]]
    hits = [sum((int(u), int(i)) in passed for i in L[r] if i >= 0) for r, u in enumerate(users)]
    return float(np.mean(hits)) if hits else None
