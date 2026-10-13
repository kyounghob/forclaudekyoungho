"""학습 → 검증 → 선택 → 테스트 → 서빙 번들 저장.

테스트 데이터는 설정 선택에 쓰지 않는다. 검증에서 고른 설정·라우터·기법별 최적을 잠근 뒤
테스트 스냅샷에서는 선택된 설정만 평가한다. 번들에는 서빙에 필요한 스냅샷·모델·설정과
감사 기록(선택 기록, 학습 로그, QA, 결과표)이 함께 들어간다.
"""
from __future__ import annotations

import copy
import json
import os
import pickle
import platform
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import __version__, neural
from .catalog import RADIX, Catalog
from .config import CTX_NAMES, K, RULE_PARTS, SEED, SEG_VARS, GuardrailConfig, TrainConfig
from .data import Dataset
from .evaluation import (bootstrap_ci, evaluate_zoo, hit_at_k, make_select, ndcg_at_k, primary_eval, row_metrics,
                         select_topk, simple_diversity)
from .features import FeatureStore, feature_store
from .router import ShrinkRouter, tune_router
from .signals import CandidateBatch, LearnerBatch, ModelStore, Reference, SignalBank, build_signals, supervised_from_log
from .util import get_logger, json_safe
from .zoo import Algo, algo_uses, build_zoo, score_algo

BUNDLE_FILE = "bundle.pkl"


@dataclass
class Bundle:
    """서빙·감사에 필요한 모든 것."""
    version: str
    created_at: str
    config: TrainConfig
    catalog: Catalog
    store: FeatureStore                 # 서빙 스냅샷(테스트 스냅샷과 같음: 오프라인·온라인 일치 검사를 위해)
    reference: Reference
    models: ModelStore
    algos: list
    signal_meta: dict
    selection: dict
    routers: dict
    router_tuning: dict
    results: pd.DataFrame
    group_results: pd.DataFrame
    validation_jobs: pd.DataFrame
    predictions: dict
    per_user: dict
    qa: list
    dataset_summary: dict
    validation_audit: dict
    test_audit: dict
    dataset_meta: dict = None
    profiles: pd.DataFrame = None       # 서빙에서 기존 학습자 조회용
    log: pd.DataFrame = None            # 서빙에서 학습 이력 표시용(서빙 스냅샷 이전 주만)
    zoo_skipped: list = field(default_factory=list)
    test_users: np.ndarray = None       # predictions의 행 순서(오프라인·온라인 일치 검사용)
    exposure: pd.DataFrame = None

    @property
    def family_counts(self):
        return pd.Series([a.family for a in self.algos]).value_counts().to_dict()

    def manifest(self) -> dict:
        return json_safe(dict(
            version=self.version, created_at=self.created_at, config=self.config.__dict__ | {"guardrail": self.config.guardrail.__dict__},
            dataset=self.dataset_summary, dataset_meta=self.dataset_meta, validation=self.validation_audit, test=self.test_audit,
            configurations=len(self.algos), family_counts=self.family_counts, signal_count=len(self.signal_meta),
            selection=self.selection, router_tuning=self.router_tuning, training=self.models.audit,
            results=self.results.to_dict("records"), group_results=self.group_results.to_dict("records"), qa=self.qa,
            neural_enabled=self.models.enable_neural, zoo_skipped=len(self.zoo_skipped),
            environment=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                             torch=getattr(neural.torch, "__version__", None) if neural.HAS_TORCH else None, os=platform.platform()),
            implementation_status="executed prototype; synthetic data unless a real log directory was given"))

    def save(self, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, BUNDLE_FILE), "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(self.manifest(), f, ensure_ascii=False, indent=2)
        self.results.to_csv(os.path.join(out_dir, "test_results.csv"), index=False, encoding="utf-8-sig")
        self.group_results.to_csv(os.path.join(out_dir, "group_results.csv"), index=False, encoding="utf-8-sig")
        self.validation_jobs.to_csv(os.path.join(out_dir, "validation_configurations.csv"), index=False, encoding="utf-8-sig")
        self.store.users.to_csv(os.path.join(out_dir, "learner_profiles.csv"), index=False, encoding="utf-8-sig")

    @classmethod
    def load(cls, path: str) -> "Bundle":
        if os.path.isdir(path):
            path = os.path.join(path, BUNDLE_FILE)
        with open(path, "rb") as f:
            return pickle.load(f)


def train(dataset: Dataset, cfg: TrainConfig = None, out_dir: str = None, enable_neural: bool = True, log=None) -> Bundle:
    cfg = cfg or TrainConfig()
    logger = log or get_logger().info
    catalog = dataset.catalog
    guard = cfg.guardrail
    profiles, LOG = dataset.profiles, dataset.log
    t0 = time.time()
    # --- 1단계: 검증(테스트 데이터는 적합·선택에 쓰지 않는다) ---
    F_val = feature_store(profiles, LOG, catalog, cfg.val_week)
    cands_val, lb_val = primary_eval(cfg.val_week, F_val, LOG, catalog, guard)
    sup_val = supervised_from_log(LOG[LOG.week < cfg.val_week], cfg.train_max_rows, cfg.seed)
    ref_val = Reference.from_store(F_val, catalog, RADIX, sup_val)
    models = ModelStore(enable_neural)
    logger(f"데이터 {dataset.summary()}")
    logger(f"검증 {cands_val.audit}")
    bank_val = SignalBank(cands_val)
    build_signals(bank_val, ref_val, lb_val, catalog, models)
    algos = build_zoo(bank_val, RULE_PARTS, CTX_NAMES)
    skipped = list(build_zoo.skipped)
    logger(f"신호 {len(bank_val.sig)}개, 설정 {len(algos)}개 (건너뜀 {len(skipped)}개), {time.time() - t0:.1f}초")
    select_val = make_select(cands_val, lb_val, catalog, K, guard)
    M_val, H_val, jobs = evaluate_zoo(algos, bank_val, lb_val.nu, select_val, catalog.item_topic, cfg.n_workers, log=logger)
    logger(f"검증 배치 완료: 최고 NDCG@5 {jobs.ndcg.max():.5f} ({time.time() - t0:.1f}초)")
    # --- 선택(검증에서만) ---
    uses = [algo_uses(a, bank_val.info) for a in algos]
    use_g = np.array(["gender" in u for u in uses]); use_i = np.array(["income" in u for u in uses]); use_a = np.array(["age" in u for u in uses])
    allowed_ng = ~use_g; allowed_ngi = ~(use_g | use_i)
    assert all("income" not in uses[j] for j in np.flatnonzero(allowed_ngi))
    cu = F_val.codes[cands_val.users]
    router_settings = {
        "RouterFull": (tuple(SEG_VARS), np.ones(len(algos), bool)),
        "RouterNoGender": (tuple(v for v in SEG_VARS if v != "gender"), allowed_ng),
        "RouterNoGenderIncome": (tuple(v for v in SEG_VARS if v not in ("gender", "income_q")), allowed_ngi)}
    routers, router_tunes = {}, {}
    for name, (order, allowed) in router_settings.items():
        tune = tune_router(M_val, cu, lams=cfg.router_lams, reps=cfg.router_reps, order=order, allowed=allowed, seed=cfg.seed)
        lam = float(tune.loc[tune["mean"].idxmax(), "lam"])
        routers[name] = ShrinkRouter(lam, order).fit(M_val, cu, allowed)
        router_tunes[name] = tune.to_dict("records")
        logger(f"{name}: λ={lam:g}, 노드 {[len(x['keys']) for x in routers[name].levels]}")
    selectable = {}
    for family in ("POP", "RULE", "CONTENT", "UCF", "ICF", "MF", "MF_OBS", "MLP"):
        ids = np.array([a.aid for a in algos if a.family == family])
        if len(ids):
            selectable[family] = int(ids[np.argmax(M_val[:, ids].mean(0))])
    selectable["Global"] = int(M_val.mean(0).argmax())
    selectable["NoDemographics"] = int(np.where(~(use_g | use_i | use_a), M_val.mean(0), -np.inf).argmax())
    selection = dict(families=selectable, router_lambdas={k: rt.lam for k, rt in routers.items()}, operational=cfg.operational_router,
                     operational_algorithm=None, no_gender_configs=int(allowed_ng.sum()), no_gender_income_configs=int(allowed_ngi.sum()),
                     min_leaf_users=routers["RouterFull"].min_users, validation_best_ndcg=float(jobs.ndcg.max()))
    logger(f"선택 잠금 {selection}")
    signal_meta = copy.deepcopy(bank_val.info)
    del bank_val
    # --- 2단계: 테스트(선택된 설정만) ---
    F_test = feature_store(profiles, LOG, catalog, cfg.test_week)
    cands_test, lb_test = primary_eval(cfg.test_week, F_test, LOG, catalog, guard)
    sup_test = supervised_from_log(LOG[LOG.week < cfg.test_week], cfg.train_max_rows, cfg.seed)
    ref_test = Reference.from_store(F_test, catalog, RADIX, sup_test)
    needed_aids = set(selectable.values())
    for rt in routers.values():
        for L in rt.levels:
            needed_aids.update(map(int, L["champ"]))
    need_sig = {sig for aid in needed_aids for sig in algos[aid].signals}
    bank_test = SignalBank(cands_test)
    build_signals(bank_test, ref_test, lb_test, catalog, models, needed=need_sig)
    logger(f"테스트 {cands_test.audit}")
    select_test = make_select(cands_test, lb_test, catalog, K, guard)
    rows, predictions, per_user = [], {}, {}
    CATS = catalog.item_topic

    def record(name, sel):
        nd, ht, dv, it = row_metrics(sel, cands_test, CATS)
        nuser = cands_test.per_user(nd); huser = cands_test.per_user(ht); duser = cands_test.per_user(dv)
        per_user[name] = nuser; predictions[name] = it
        rows.append(dict(method=name, ndcg=float(nuser.mean()), diversity=float(duser.mean()), hit_diagnostic=float(huser.mean()),
                         coverage_diagnostic=float(np.unique(it[it >= 0]).size / max(cands_test.n_pool, 1)),
                         short_list_rate=float((np.sum(it >= 0, 1) < K).mean()), users=len(nuser), requests=cands_test.R))

    for name, aid in selectable.items():
        record(name, select_test(score_algo(algos[aid], bank_test, lb_test.nu)))
    for name, rt in routers.items():
        champ, _, _ = rt.route(F_test.codes[cands_test.user])
        sel = np.full((cands_test.R, K), -1)
        for c in np.unique(champ):
            rr = np.flatnonzero(champ == c)
            sel[rr] = score_and_select_rows(algos[c], bank_test, lb_test, catalog, rr, guard)
        record(name, sel)
    rng = np.random.default_rng(cfg.seed + 91)
    record("Random", select_test(np.where(cands_test.valid, rng.random(cands_test.cand.shape), -np.inf)))
    results = pd.DataFrame(rows)
    for idx, row in results.iterrows():
        diff = per_user[row["method"]] - per_user["Global"]; lo, hi = bootstrap_ci(diff, cfg.bootstrap_n, cfg.seed)
        results.loc[idx, "difference_vs_global"] = float(diff.mean()); results.loc[idx, "ci_low"] = lo; results.loc[idx, "ci_high"] = hi
    results = results.sort_values("ndcg", ascending=False).reset_index(drop=True)
    logger("테스트 결과\n" + results[["method", "ndcg", "diversity", "hit_diagnostic", "difference_vs_global", "ci_low", "ci_high"]].round(5).to_string(index=False))
    # 운영 설정: 운영 라우터가 테스트 사용자에게 배정한 챔피언 가운데 가장 많이 쓰인 것(전역 1위와 같은 경우가 보통)
    op_champ, _, _ = routers[cfg.operational_router].route(F_test.codes[cands_test.user])
    selection["operational_algorithm"] = int(np.bincount(op_champ).argmax())
    selection["operational_champion_counts"] = {int(k): int(v) for k, v in zip(*np.unique(op_champ, return_counts=True))}
    # 집단별 진단(동등 대우의 증거가 아니라 진단)
    group_rows = []
    for method in ("Global", "RouterFull", "RouterNoGender", "RouterNoGenderIncome"):
        vv = per_user[method]
        for variable in ("gender", "age_band", "income_q", "click_tier"):
            c = F_test.codes[cands_test.users, SEG_VARS.index(variable)]
            for val in np.unique(c):
                m = c == val
                lo, hi = bootstrap_ci(vv[m], 200, cfg.seed)
                group_rows.append(dict(method=method, variable=variable, group=int(val), users=int(m.sum()), ndcg=float(vv[m].mean()),
                                       ci_low=lo, ci_high=hi))
    group_results = pd.DataFrame(group_rows)
    # 심화·레버리지 콘텐츠 노출률(공정성 점검 확장)
    exposure_rows = []
    for method in ("Global", "RouterNoGender"):
        it = predictions[method]; ok = it >= 0
        adv = catalog.advanced[np.maximum(it, 0)] & ok
        for variable in ("gender", "age_band", "income_q"):
            c = F_test.codes[cands_test.user, SEG_VARS.index(variable)]
            for val in np.unique(c):
                m = c == val
                exposure_rows.append(dict(method=method, variable=variable, group=int(val), users=int(m.sum()),
                                          advanced_share=float(adv[m].sum() / max(ok[m].sum(), 1))))
    qa = run_qa(cands_test, catalog, results, predictions, F_test, models, selection, dataset, allowed_ngi, uses, lb_test)
    bundle = Bundle(version=__version__, created_at=time.strftime("%Y-%m-%dT%H:%M:%S"), config=cfg, catalog=catalog, store=F_test,
                    reference=ref_test, models=models, algos=algos, signal_meta=signal_meta, selection=selection, routers=routers,
                    router_tuning=router_tunes, results=results, group_results=group_results, validation_jobs=jobs,
                    predictions=predictions, per_user=per_user, qa=qa, dataset_summary=dataset.summary(),
                    validation_audit=cands_val.audit, test_audit=cands_test.audit, dataset_meta=dataset.meta, profiles=profiles,
                    log=LOG[LOG.week < cfg.test_week].reset_index(drop=True), zoo_skipped=skipped,
                    test_users=cands_test.user.copy(), exposure=pd.DataFrame(exposure_rows))
    logger(f"QA {len(qa)}건 통과, 총 {time.time() - t0:.1f}초")
    if out_dir:
        bundle.save(out_dir)
        bundle.exposure.to_csv(os.path.join(out_dir, "advanced_exposure.csv"), index=False, encoding="utf-8-sig")
        logger(f"번들 저장: {os.path.abspath(out_dir)}")
    return bundle


def score_and_select_rows(algo: Algo, bank: SignalBank, lb: LearnerBatch, catalog: Catalog, rows, guard: GuardrailConfig):
    """라우터가 배정한 행들만 해당 설정으로 점수를 매기고 같은 후처리로 Top-K를 고른다."""
    from .evaluation import choose_items
    from .zoo import score_rows
    S = score_rows(algo, bank, lb.nu, rows)
    return choose_items(bank.cands, lb, catalog, S, rows, K, guard)


def run_qa(cands_test, catalog, results, predictions, F_test, models, selection, dataset, allowed_ngi, uses, lb_test) -> list:
    """강의 지표 함수와 벡터화 구현의 일치, 빈칸·짧은 목록, 가드레일, 중복, 학습 감사 항목을 검사한다."""
    QA = []

    def check(name, condition, details=None):
        ok = bool(condition); QA.append(dict(test=name, passed=ok, details=details))
        if not ok:
            raise AssertionError(name + ": " + str(details))

    cat = np.array([0, 0, 1, 2, 3])
    ee = CandidateBatch(np.array([0, 1]), np.tile(np.arange(5), (2, 1)), np.array([[1, 0, 1, 0, 0], [0, 1, 0, 0, 0]], bool))
    ss = np.array([[0, 1, 2, -1, -1], [1, -1, -1, -1, -1]])
    nd, ht, dv, its = row_metrics(ss, ee, cat)
    for r in range(2):
        rec = its[r][its[r] >= 0].tolist(); truth = np.flatnonzero(ee.rel[r]).tolist()
        check(f"metric_ndcg_{r}", np.isclose(nd[r], ndcg_at_k(rec, truth, 5)))
        check(f"metric_hit_{r}", np.isclose(ht[r], hit_at_k(rec, truth, 5)))
        check(f"metric_diversity_{r}", np.isclose(dv[r], simple_diversity(rec, cat)))
    short = select_topk(np.array([[1., 2., 3.]]), k=5)
    check("topk_fixed_shape", short.shape == (1, 5)); check("topk_padding", (short[0, 3:] == -1).all())
    check("zero_positive_label_retained", cands_test.audit["zero_observed_target"] > 0)
    check("no_income_alias_bypass", all("income" not in uses[j] for j in np.flatnonzero(allowed_ngi)))
    check("MF_negative_collision", all(x.get("final_negative_collisions", 0) == 0 for x in models.audit))
    check("finite_metric_table", np.isfinite(results[["ndcg", "diversity"]].values).all())
    check("metric_ranges", ((results[["ndcg", "diversity"]].values >= 0) & (results[["ndcg", "diversity"]].values <= 1 + 1e-12)).all())
    if models.enable_neural:
        check("MLP_actually_trained", any(x["model"] == "mlp9" and x["training_rows"] > 0 for x in models.audit))
        check("MLP_has_observed_zeros", all(x.get("zero", 1) > 0 for x in models.audit if x["model"] == "mlp9"))
        check("observed_models_trained_at_validation_and_test_snapshots",
              len({x.get("snapshot") for x in models.audit if x["model"] in ("mf_observed", "mlp9")}) >= 2)
    a = np.array([0, 1, 2, 0, 1, 2]); inter = np.array([[0], [1]])
    correct = (a[None, :, None] == inter[:, None, :]).any(-1)
    check("per_user_interest_broadcast", not np.array_equal(correct[0], correct[1]))
    check("mastery_equals_quiz_pass", np.array_equal(dataset.log.understood.values, dataset.log.quiz_pass.values))
    check("ordered_study_times", bool((dataset.log.groupby(["user", "week"])["minute"].apply(lambda x: np.all(np.diff(x.values) >= 0))).all()))
    lv_rows = lb_test.level
    for name, it in predictions.items():
        check(f"unique_items_{name}", all(len(x) == len(set(x)) for x in [v[v >= 0].tolist() for v in it]))
        valid = it >= 0; levels = catalog.item_level[np.maximum(it, 0)] - lv_rows[:, None]
        check(f"level_guard_{name}", not np.any(valid & (levels >= 2)))
        check(f"plus_one_limit_{name}", np.all((valid & (levels == 1)).sum(1) <= 1))
        passed_rec = F_test.und[cands_test.user[:, None], np.maximum(it, 0)] & valid
        check(f"no_passed_unit_recommended_{name}", not passed_rec.any())
    check("selection_operational_is_locked", selection["operational_algorithm"] is not None)
    return QA
