"""학습 → 검증 → 선택 → 테스트 → 서빙 번들 저장.

테스트 데이터는 설정 선택에 쓰지 않는다. 검증에서 고른 설정·라우터·기법별 최적을 잠근 뒤
테스트 스냅샷에서는 선택된 설정만 평가한다. 번들에는 서빙에 필요한 스냅샷·모델·설정과
감사 기록(선택 기록, 학습 로그, QA, 결과표)이 함께 들어간다.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import pickle
import platform
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp

from . import __version__, neural
from .catalog import RADIX, Catalog
from .config import CTX_NAMES, GOALS, K, SEED, SEG_VARS, GuardrailConfig, TrainConfig
from .data import Dataset
from .evaluation import (bootstrap_ci, evaluate_zoo, hit_at_k, make_select, ndcg_at_k, primary_eval, row_metrics,
                         select_topk, simple_diversity)
from .features import FeatureStore, feature_store
from .router import ShrinkRouter, tune_router
from .signals import CandidateBatch, LearnerBatch, ModelStore, Reference, SignalBank, build_signals, supervised_from_log
from .util import get_logger, json_safe
from .privacy import K_RELEASE, generalize_profiles, minimize_log, privacy_audit, privacy_checks, suppress_small_groups
from .zoo import Algo, algo_uses, build_zoo, score_algo
from .purpose_policy import POLICY_KEY, policy_metadata, purpose_stage_algorithm

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
    profiles: pd.DataFrame = None       # 서빙에서 기존 학습자 조회용: 일반화 표(연령대·소득분위 코드, 원시 연령·연소득 없음)
    log: pd.DataFrame = None            # 학습 이력 표시용(서빙 스냅샷 이전 주만): 주차·4개 시간대·주 안 순서(seq), 일·분 없음
    zoo_skipped: list = field(default_factory=list)
    test_users: np.ndarray = None       # predictions의 행 순서(오프라인·온라인 일치 검사용)
    exposure: pd.DataFrame = None       # 심화 콘텐츠 노출(5명 미만 집단 제외)
    evaluation_protocol: dict = None    # 후보·정답·IDCG·선정 조건의 독립 감사 명세
    privacy: dict = None                # 개인정보 감사(etfrec.privacy.privacy_audit): 준식별자 k=5·라우터 잎 크기·정책 구분

    @property
    def family_counts(self):
        return pd.Series([a.family for a in self.algos]).value_counts().to_dict()

    def manifest(self) -> dict:
        return json_safe(dict(
            version=self.version, created_at=self.created_at, config=self.config.__dict__ | {"guardrail": self.config.guardrail.__dict__},
            dataset=self.dataset_summary, dataset_meta=self.dataset_meta, validation=self.validation_audit, test=self.test_audit,
            configurations=len(self.algos), family_counts=self.family_counts, signal_count=len(self.signal_meta),
            selection=self.selection, router_tuning=self.router_tuning, training=self.models.audit,
            evaluation_protocol=getattr(self, "evaluation_protocol", None),
            results=self.results.to_dict("records"), group_results=self.group_results.to_dict("records"), qa=self.qa,
            neural_enabled=self.models.enable_neural, zoo_skipped=len(self.zoo_skipped), privacy=self.privacy,
            environment=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                             torch=getattr(neural.torch, "__version__", None) if neural.HAS_TORCH else None, os=platform.platform()),
            implementation_status="executed prototype; synthetic data unless a real log directory was given"))

    def save(self, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, BUNDLE_FILE), "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(self.manifest(), f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "evaluation_protocol.json"), "w", encoding="utf-8") as f:
            json.dump(json_safe(getattr(self, "evaluation_protocol", None)), f, ensure_ascii=False, indent=2)
        self.results.to_csv(os.path.join(out_dir, "test_results.csv"), index=False, encoding="utf-8-sig")
        self.group_results.to_csv(os.path.join(out_dir, "group_results.csv"), index=False, encoding="utf-8-sig")
        self.validation_jobs.to_csv(os.path.join(out_dir, "validation_configurations.csv"), index=False, encoding="utf-8-sig")
        # 내부 서빙용 학습자 요약(연령대·소득분위 이름, 원시 연령·연소득 없음). k-익명 반출 표가 아니다 → 반출은 export-deid
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
    sup_val = supervised_from_log(LOG[LOG.week < cfg.val_week], cfg.train_max_rows, cfg.seed, n_items=catalog.n_items)
    ref_val = Reference.from_store(F_val, catalog, RADIX, sup_val)
    models = ModelStore(enable_neural, seed=cfg.seed)
    logger(f"데이터 {dataset.summary()}")
    logger(f"검증 {cands_val.audit}")
    bank_val = SignalBank(cands_val)
    build_signals(bank_val, ref_val, lb_val, catalog, models)
    algos = build_zoo(bank_val, cfg.rule_parts, CTX_NAMES)
    skipped = list(build_zoo.skipped)
    logger(f"신호 {len(bank_val.sig)}개, 설정 {len(algos)}개 (건너뜀 {len(skipped)}개), {time.time() - t0:.1f}초")
    select_val = make_select(cands_val, lb_val, catalog, K, guard)
    M_val, H_val, jobs = evaluate_zoo(algos, bank_val, lb_val.nu, select_val, catalog.item_topic, cfg.n_workers, log=logger)
    declared_policy = getattr(cfg, "operational_policy", POLICY_KEY) == POLICY_KEY
    policy_algo = purpose_stage_algorithm()
    policy_val_ndcg = None
    if declared_policy:
        nd_policy, _, _, _ = row_metrics(select_val(score_algo(policy_algo, bank_val, lb_val.nu)), cands_val, catalog.item_topic)
        policy_val_ndcg = float(cands_val.per_user(nd_policy).mean())
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
    for family in ("POP", "RULE", "CONTENT", "UCF", "ICF", "MF", "MF_BPR", "MF_OBS", "MLP", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"):
        ids = np.array([a.aid for a in algos if a.family == family])
        if len(ids):
            selectable[family] = int(ids[np.argmax(M_val[:, ids].mean(0))])
    selectable["Global"] = int(M_val.mean(0).argmax())
    selectable["NoDemographics"] = int(np.where(~(use_g | use_i | use_a), M_val.mean(0), -np.inf).argmax())
    # 온라인 A/B 대조군 A(세그먼트 인기): 성별을 쓰지 않는 세그먼트 인기 설정 중 검증 1위. 실험 설계의 오프라인 근거로만 평가하고
    # 서빙 기법 목록(families)에는 넣지 않는다(작은 세그먼트 설정을 API로 고르지 못하게 하는 개인정보 원칙과 같은 이유).
    seg_ids = np.array([a.aid for a in algos if a.family == "SEGPOP" and allowed_ng[a.aid]])
    ab_control = int(seg_ids[np.argmax(M_val[:, seg_ids].mean(0))]) if len(seg_ids) else None
    selection = dict(families=selectable, router_lambdas={k: rt.lam for k, rt in routers.items()}, operational=cfg.operational_router,
                     ab_control_algorithm=ab_control,
                     operational_algorithm=None, no_gender_configs=int(allowed_ng.sum()), no_gender_income_configs=int(allowed_ngi.sum()),
                     min_leaf_users=routers["RouterFull"].min_users, validation_best_ndcg=float(jobs.ndcg.max()))
    # 운영 대표 설정도 검증에서 잠근다. 테스트 사용자 분포로 대표 설정을 다시 고르지 않는다.
    val_champ, _, _ = routers[cfg.operational_router].route(cu)
    selection["operational_algorithm"] = int(np.bincount(val_champ).argmax())
    selection["operational_champion_counts"] = {int(k): int(v) for k, v in zip(*np.unique(val_champ, return_counts=True))}
    selection["legacy_operational_algorithm"] = selection["operational_algorithm"]
    selection["legacy_operational_router"] = cfg.operational_router
    selection["operational_policy"] = POLICY_KEY if declared_policy else "legacy"
    selection["declared_policy_count"] = int(declared_policy)
    selection["exploration_configuration_count"] = len(algos)
    if declared_policy:
        selection["operational"] = POLICY_KEY
        selection["operational_algorithm"] = -1
        selection["operational_algorithm_name"] = policy_algo.name
        selection["operational_champion_counts"] = {-1: len(cands_val.users)}
        selection["policy_validation_ndcg"] = policy_val_ndcg
        selection["policy_definition"] = policy_metadata()
    selection["locked_before_test"] = True
    selection["selection_guardrail"] = dict(guard.__dict__)
    ng_best = int(np.where(allowed_ng, M_val.mean(0), -np.inf).argmax())
    selection["no_gender_best_algorithm"] = ng_best
    selection["no_gender_best_validation_ndcg"] = float(M_val[:, ng_best].mean())
    selection["selection_configs_evaluated"] = int(len(algos))
    selection["selection_configs_excluded_gender"] = int(use_g.sum())
    selection["neural_requested"] = bool(enable_neural)
    selection["neural_enabled"] = bool(models.enable_neural)
    selection["skipped_configurations"] = int(len(skipped))
    logger(f"선택 잠금 {selection}")
    signal_meta = copy.deepcopy(bank_val.info)
    del bank_val
    # --- 2단계: 테스트(선택된 설정만) ---
    F_test = feature_store(profiles, LOG, catalog, cfg.test_week)
    cands_test, lb_test = primary_eval(cfg.test_week, F_test, LOG, catalog, guard)
    sup_test = supervised_from_log(LOG[LOG.week < cfg.test_week], cfg.train_max_rows, cfg.seed, n_items=catalog.n_items)
    ref_test = Reference.from_store(F_test, catalog, RADIX, sup_test)
    needed_aids = set(selectable.values()) | ({ab_control} if ab_control is not None else set())
    for rt in routers.values():
        for L in rt.levels:
            needed_aids.update(map(int, L["champ"]))
    need_sig = {sig for aid in needed_aids for sig in algos[aid].signals}
    if declared_policy:
        need_sig.update(policy_algo.signals)
    bank_test = SignalBank(cands_test)
    build_signals(bank_test, ref_test, lb_test, catalog, models, needed=need_sig)
    logger(f"테스트 {cands_test.audit}")
    select_test = make_select(cands_test, lb_test, catalog, K, guard)
    rows, predictions, per_user, active_users = [], {}, {}, {}
    CATS = catalog.item_topic

    missing_test = catalog.missing_prereq_count(F_test.und[cands_test.user])      # (R, n_items) 테스트 시점 미이수 선수 단원 수
    # 다음 주 정답이 하나라도 있는 '활성' 사용자. 노트북 규칙(정답 없는 사용자 = NDCG 0 포함)과 표준 규칙(제외)을 둘 다 보고한다.
    active_test = cands_test.per_user(np.asarray(cands_test.full_relevant_count, float)) > 0
    active_users[cfg.operational_router] = active_test

    def record(name, sel, cands=None, active=None):
        cands = cands_test if cands is None else cands
        active = active_test if active is None else active
        nd, ht, dv, it = row_metrics(sel, cands, CATS)
        nuser = cands.per_user(nd); huser = cands.per_user(ht); duser = cands.per_user(dv)
        per_user[name] = nuser; predictions[name] = it
        ok = it >= 0
        viol = (missing_test[np.arange(cands.R)[:, None], np.maximum(it, 0)] > 0) & ok
        rows.append(dict(method=name,
                         prerequisite_policy="required" if cands.audit.get("guardrail", {}).get("prereq_block") else "off",
                         target_policy="fixed_before_prerequisite_filter", zero_target_policy="include_as_zero",
                         ndcg=float(nuser.mean()), diversity=float(duser.mean()), hit_diagnostic=float(huser.mean()),
                         ndcg_active=float(nuser[active].mean()) if active.any() else 0.0,
                         hit_active=float(huser[active].mean()) if active.any() else 0.0, active_users=int(active.sum()),
                         coverage_diagnostic=float(np.unique(it[it >= 0]).size / max(cands_test.n_pool, 1)),
                         short_list_rate=float((np.sum(it >= 0, 1) < K).mean()),
                         prereq_violation_rate=float(viol.sum() / max(ok.sum(), 1)), users=len(nuser), requests=cands.R))

    for name, aid in selectable.items():
        record(name, select_test(score_algo(algos[aid], bank_test, lb_test.nu)))
    if declared_policy:
        record(POLICY_KEY, select_test(score_algo(policy_algo, bank_test, lb_test.nu)))
    for name, rt in routers.items():
        champ, _, _ = rt.route(F_test.codes[cands_test.user])
        sel = np.full((cands_test.R, K), -1)
        for c in np.unique(champ):
            rr = np.flatnonzero(champ == c)
            sel[rr] = score_and_select_rows(algos[c], bank_test, lb_test, catalog, rr, guard)
        record(name, sel)
    rng = np.random.default_rng(cfg.seed + 91)
    record("Random", select_test(np.where(cands_test.valid, rng.random(cands_test.cand.shape), -np.inf)))
    # 선수 개념 가드레일(서빙 기본)을 켠 채로 운영 라우터를 평가한다. 후보에서 빠진 정답은 IDCG에 남겨 불이익을 그대로 받는다.
    guard_pre = GuardrailConfig(**{**guard.__dict__, "prereq_block": True})
    cands_pre, lb_pre = primary_eval(cfg.test_week, F_test, LOG, catalog, guard_pre)
    if not np.array_equal(cands_pre.users, cands_test.users) or not np.array_equal(cands_pre.full_relevant_count, cands_test.full_relevant_count):
        raise AssertionError("선수 필터 전후 평가 사용자와 IDCG 정답 수가 다릅니다")
    bank_pre = SignalBank(cands_pre)
    op_router = routers[cfg.operational_router]
    champ_pre, _, _ = op_router.route(F_test.codes[cands_pre.user])
    build_signals(bank_pre, ref_test, lb_pre, catalog, models, needed={sig for c in np.unique(champ_pre) for sig in algos[int(c)].signals})
    sel_pre = np.full((cands_pre.R, K), -1)
    for c in np.unique(champ_pre):
        rr = np.flatnonzero(champ_pre == c)
        sel_pre[rr] = score_and_select_rows(algos[c], bank_pre, lb_pre, catalog, rr, guard_pre)
    active_pre = cands_pre.per_user(np.asarray(cands_pre.full_relevant_count, float)) > 0
    record(cfg.operational_router + "+prereq", sel_pre, cands=cands_pre, active=active_pre)
    if ab_control is not None:                                              # A/B 대조군 A의 오프라인 값(평가 전용 행)
        record("ABControl", select_test(score_algo(algos[ab_control], bank_test, lb_test.nu)))
    results = pd.DataFrame(rows)
    for idx, row in results.iterrows():
        diff = per_user[row["method"]] - per_user["Global"]; lo, hi = bootstrap_ci(diff, cfg.bootstrap_n, cfg.seed)
        results.loc[idx, "difference_vs_global"] = float(diff.mean()); results.loc[idx, "ci_low"] = lo; results.loc[idx, "ci_high"] = hi
        act = active_pre if row["method"].endswith("+prereq") else active_test
        if len(diff) == len(act) and act.any():
            lo_a, hi_a = bootstrap_ci(diff[act], cfg.bootstrap_n, cfg.seed)
            results.loc[idx, "difference_vs_global_active"] = float(diff[act].mean()); results.loc[idx, "ci_low_active"] = lo_a; results.loc[idx, "ci_high_active"] = hi_a
    results = results.sort_values("ndcg", ascending=False, kind="mergesort").reset_index(drop=True)   # 안정 정렬: 동점 행은 기록 순서 유지
    logger("테스트 결과\n" + results[["method", "ndcg", "ndcg_active", "diversity", "hit_diagnostic", "prereq_violation_rate", "difference_vs_global", "ci_low", "ci_high"]].round(5).to_string(index=False))
    # 테스트의 챔피언 분포는 진단만 기록하며 검증에서 잠근 운영 대표 설정은 바꾸지 않는다
    op_champ, _, _ = routers[cfg.operational_router].route(F_test.codes[cands_test.user])
    selection["test_champion_counts_diagnostic"] = ({-1: len(cands_test.users)} if declared_policy else
                                                  {int(k): int(v) for k, v in zip(*np.unique(op_champ, return_counts=True))})
    # 집단별 진단(동등 대우의 증거가 아니라 진단)
    group_rows = []
    for method in ("Global", "RouterFull", "RouterNoGender", "RouterNoGenderIncome"):
        vv = per_user[method]
        for variable in ("gender", "age_band", "income_q", "click_tier"):
            c = F_test.codes[cands_test.users, SEG_VARS.index(variable)]
            for val in np.unique(c):
                m = c == val
                group_rows.append(_group_row(method, variable, int(val), vv, m, active_test, cfg.seed))
    goals_test = np.asarray(F_test.goal, dtype=object)[cands_test.users] if F_test.goal is not None else np.full(len(cands_test.users), "long_term", object)
    for method in ("Global", "RouterNoGender"):
        vv = per_user[method]
        for g in GOALS:
            m = goals_test == g
            if m.any():
                group_rows.append(_group_row(method, "goal", g, vv, m, active_test, cfg.seed))
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
    # 개인정보(etfrec.privacy): 모델 입력은 그대로 두고 저장물만 줄인다. 원시 연령·연소득·일·분은 번들에 넣지 않고,
    # 공개 집단표는 5명 미만 셀을 처리한 뒤 넣는다. 감사 → QA(개인정보 검사 포함) 순서로 저장 전에 확인한다.
    group_results, cells_g = suppress_small_groups(group_results, K_RELEASE)
    exposure, cells_e = suppress_small_groups(pd.DataFrame(exposure_rows), K_RELEASE)
    stored_log, log_dropped = minimize_log(LOG[LOG.week < cfg.test_week], return_dropped=True)
    bundle = Bundle(version=__version__, created_at=time.strftime("%Y-%m-%dT%H:%M:%S"), config=cfg, catalog=catalog, store=F_test,
                    reference=ref_test, models=models, algos=algos, signal_meta=signal_meta, selection=selection, routers=routers,
                    router_tuning=router_tunes, results=results, group_results=group_results, validation_jobs=jobs,
                    predictions=predictions, per_user=per_user, qa=[], dataset_summary=dataset.summary(),
                    validation_audit=cands_val.audit, test_audit=cands_test.audit, dataset_meta=dataset.meta,
                    profiles=generalize_profiles(profiles, F_test.codes), log=stored_log,
                    evaluation_protocol=dict(
                        version=2,
                        selection_week=int(cfg.val_week), test_week=int(cfg.test_week),
                        selection_guardrail=dict(guard.__dict__), test_guardrail=dict(guard.__dict__),
                        selected_before_test=True,
                        reported_extra_prerequisite_method_is_alias=bool(guard.prereq_block),
                        operational_router=POLICY_KEY if declared_policy else cfg.operational_router,
                        historical_comparison_router=cfg.operational_router,
                        operational_policy=policy_metadata() if declared_policy else None,
                        declared_policy_count=int(declared_policy), exploration_configuration_count=len(algos),
                        gender_in_operational_inputs=False if declared_policy else bool("gender" in router_settings[cfg.operational_router][0]),
                        age_in_operational_inputs=False if declared_policy else bool("age_band" in router_settings[cfg.operational_router][0]),
                        income_in_operational_inputs=False if declared_policy else bool("income_q" in router_settings[cfg.operational_router][0]),
                        no_gender_configurations_evaluated=int(allowed_ng.sum()),
                        configurations_evaluated=int(len(algos)), neural_enabled=bool(models.enable_neural),
                        validation=cands_val.audit, test=cands_test.audit,
                        filtered_test=cands_pre.audit,
                        bootstrap=dict(unit="evaluation user; paired per-method differences", replicates=int(cfg.bootstrap_n),
                                       interval="2.5/97.5 percentile", generator_uncertainty=False,
                                       model_selection_uncertainty=False, multiple_testing_adjusted=False),
                        causal_claim=False,
                    ),
                    zoo_skipped=skipped, test_users=cands_test.user.copy(), exposure=exposure, privacy=None)
    bundle.privacy = privacy_audit(bundle.profiles, bundle.routers, store=bundle.store,
                                   published=dict(group_results=cells_g, advanced_exposure=cells_e), log=bundle.log, log_dropped=log_dropped)
    qa = bundle.qa = run_qa(cands_test, catalog, results, predictions, F_test, models, selection, dataset, allowed_ngi, uses, lb_test,
                            bundle=bundle, weeks=(cfg.val_week, cfg.test_week))
    logger(f"QA {len(qa)}건 통과, 총 {time.time() - t0:.1f}초")
    if out_dir:
        bundle.save(out_dir)
        bundle.exposure.to_csv(os.path.join(out_dir, "advanced_exposure.csv"), index=False, encoding="utf-8-sig")
        logger(f"번들 저장: {os.path.abspath(out_dir)}")
    return bundle


def _group_row(method, variable, group, vv, m, active, seed) -> dict:
    """집단별 NDCG: 전체 기준(정답 없는 사용자 = 0 포함)과 활성 기준(정답 ≥1 사용자만)을 함께 기록한다.
    활성 비율이 집단마다 다르면 두 기준의 집단 순서가 달라질 수 있으므로(예: 학습활동) 둘 다 보고한다."""
    lo, hi = bootstrap_ci(vv[m], 200, seed)
    ma = m & active
    lo_a, hi_a = bootstrap_ci(vv[ma], 200, seed) if ma.sum() > 1 else (float("nan"), float("nan"))
    return dict(method=method, variable=variable, group=group, users=int(m.sum()), ndcg=float(vv[m].mean()), ci_low=lo, ci_high=hi,
                active_users=int(ma.sum()), active_share=float(ma.sum() / max(m.sum(), 1)),
                ndcg_active=float(vv[ma].mean()) if ma.any() else float("nan"), ci_low_active=lo_a, ci_high_active=hi_a)


def score_and_select_rows(algo: Algo, bank: SignalBank, lb: LearnerBatch, catalog: Catalog, rows, guard: GuardrailConfig):
    """라우터가 배정한 행들만 해당 설정으로 점수를 매기고 같은 후처리로 Top-K를 고른다."""
    from .evaluation import choose_items
    from .zoo import score_rows
    S = score_rows(algo, bank, lb.nu, rows)
    return choose_items(bank.cands, lb, catalog, S, rows, K, guard)


def _same_value(a, b) -> bool:
    if sp.issparse(a) or sp.issparse(b):
        return sp.issparse(a) and sp.issparse(b) and a.shape == b.shape and (a != b).nnz == 0
    if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
        return isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame) and a.equals(b)
    if isinstance(a, dict) or isinstance(b, dict):
        return isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys() and all(_same_value(a[k], b[k]) for k in a)
    if a is None or b is None:
        return a is None and b is None
    x, y = np.asarray(a), np.asarray(b)
    if x.shape != y.shape:
        return False
    return bool(np.array_equal(x, y, equal_nan=True)) if np.issubdtype(x.dtype, np.number) and np.issubdtype(y.dtype, np.number) \
        else bool(np.array_equal(x, y))


def store_diff(A: FeatureStore, B: FeatureStore) -> list:
    """두 특징 저장소에서 값이 다른 필드 이름(모든 필드: 행렬·블록·통계·화면 요약 포함)."""
    return [f.name for f in dataclasses.fields(A) if not _same_value(getattr(A, f.name), getattr(B, f.name))]


def leakage_probe(dataset, catalog, weeks, seed: int = 42) -> tuple:
    """누수 검사: 각 기준 주 w의 특징 저장소를 세 로그로 만들어 모든 필드를 비교한다 — (가) 원래 로그, (나) w 이후 행(정답 주 포함)의
    모든 열(사용자·단원·주차·일·시각·플래그·점수)을 행끼리 섞고 미래 행을 더 붙인 로그, (다) w 이후 행을 모두 지운 로그.
    미래 행의 내용·개수·사용자·시간대 어느 것을 읽어도 (나)나 (다)에서 달라진다. 모델 학습 행(supervised_from_log)과 목표 정렬 쌍은
    호출 쪽에서 LOG[LOG.week < 기준 주]로 잘라 넘기므로 특징 저장소가 남은 경로다."""
    lg = dataset.log
    rng = np.random.default_rng(seed + 97)
    changed, checked = [], []
    for w in weeks:
        fut = np.flatnonzero((lg.week >= w).values)
        if not len(fut):
            continue
        pert = lg.copy()
        for c in pert.columns:                                         # 미래 행 안에서 열마다 따로 섞는다(주차는 w 이상끼리)
            vals = pert[c].values.copy(); vals[fut] = rng.permutation(vals[fut]); pert[c] = vals
        extra = pert.iloc[rng.choice(fut, size=max(1, len(fut) // 5))].copy()
        extra["user"] = rng.integers(0, dataset.n_users, len(extra))
        pert = pd.concat([pert, extra], ignore_index=True)
        A = feature_store(dataset.profiles, lg, catalog, w)
        diffs = sorted(set(store_diff(A, feature_store(dataset.profiles, pert, catalog, w)))
                       | set(store_diff(A, feature_store(dataset.profiles, lg[lg.week < w], catalog, w))))
        checked.append(int(w))
        if diffs:
            changed.append((int(w), diffs))
    return not changed and bool(checked), (f"기준 주 {checked}: 이후 행을 섞고 더한 로그·지운 로그로 만든 특징 저장소를 모든 필드에서 비교, "
                                           f"달라진 주 {[c[0] for c in changed]}" + (f" (필드 {changed})" if changed else ""))


def run_qa(cands_test, catalog, results, predictions, F_test, models, selection, dataset, allowed_ngi, uses, lb_test, bundle=None,
           weeks=None) -> list:
    """강의 지표 함수와 벡터화 구현의 일치, 빈칸·짧은 목록, 가드레일, 중복, 학습 감사 항목을 검사한다.
    bundle을 주면(조립 직후·저장 전) 개인정보 검사 5개(etfrec.privacy.privacy_checks)도 같은 규칙으로 실행한다."""
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
    check("zero_positive_label_retained",
          cands_test.audit["zero_observed_target"] + cands_test.audit["eligible_positive_users"] == len(cands_test.users),
          "정답 없는 사용자가 있으면 NDCG=0으로 포함하며, 없더라도 정상 데이터다")
    check("no_income_alias_bypass", all("income" not in uses[j] for j in np.flatnonzero(allowed_ngi)))
    check("MF_negative_collision", all(x.get("final_negative_collisions", 0) == 0 for x in models.audit))
    check("finite_metric_table", np.isfinite(results[["ndcg", "diversity"]].values).all())
    check("metric_ranges", ((results[["ndcg", "diversity"]].values >= 0) & (results[["ndcg", "diversity"]].values <= 1 + 1e-12)).all())
    if models.enable_neural:
        check("MLP_actually_trained", any(x["model"] == "mlp9" and x["training_rows"] > 0 for x in models.audit))
        check("MLP_has_observed_zeros", all(x.get("zero", 1) > 0 for x in models.audit if x["model"] == "mlp9"))
        for kind in ("mlp9_bpr", "mlp9_bpru", "mlp9_next"):
            rows_k = [x for x in models.audit if x["model"] == kind]
            if rows_k:
                check(f"{kind}_pairs_at_two_snapshots", all(x.get("pairs", 0) > 0 for x in rows_k) and len({x.get("snapshot") for x in rows_k}) >= 2)
        bpr = [x for x in models.audit if x["model"] == "MF_BPR"]
        if bpr:
            check("MF_BPR_trained_at_two_snapshots", len({x.get("snapshot") for x in bpr}) >= 2 and all(x["final_negative_collisions"] == 0 for x in bpr))
        check("observed_models_trained_at_validation_and_test_snapshots",
              len({x.get("snapshot") for x in models.audit if x["model"] in ("mf_observed", "mlp9")}) >= 2)
        pw = [w for (_, kind), w in models.observed.items() if kind in ("mlp9_bpr", "mlp9_bpru", "mlp9_next")]
        if pw:      # 쌍별 모델은 쌍에 나온 사용자만 모델 점수를 받고 나머지는 콘텐츠 대체 점수를 받는다
            check("pairwise_models_score_only_pair_users", all(int(w.user_seen.sum()) == w.audit.get("pair_users", -1) for w in pw),
                  [(w.kind, int(w.user_seen.sum()), w.audit.get("pair_users")) for w in pw])
    a = np.array([0, 1, 2, 0, 1, 2]); inter = np.array([[0], [1]])
    correct = (a[None, :, None] == inter[:, None, :]).any(-1)
    check("per_user_interest_broadcast", not np.array_equal(correct[0], correct[1]))
    check("mastery_equals_quiz_pass", np.array_equal(dataset.log.understood.values, dataset.log.quiz_pass.values))
    lg = dataset.log
    check("event_logic_drop_excludes_complete", not bool((lg["drop"].astype(bool) & lg.complete.astype(bool)).any()),
          "이탈과 완료는 같은 시도에서 동시에 참일 수 없다")
    check("event_logic_quiz_pass_requires_quiz_and_complete",
          bool((lg.quiz_pass.astype(bool) <= lg.quiz.astype(bool)).all() and (lg.quiz.astype(bool) <= lg.complete.astype(bool)).all()),
          "퀴즈 통과 ⊆ 퀴즈 시도 ⊆ 완료")
    if "ndcg_active" in results.columns:
        ok_id = np.allclose(results.ndcg_active.values * results.active_users.values, results.ndcg.values * results.users.values, atol=1e-9)
        check("ndcg_active_identity", ok_id, "활성 사용자 NDCG × 활성 수 = 전체 NDCG × 전체 수 (정답 없는 사용자는 모든 방법에서 0)")
        check("active_users_identical_across_methods", results.active_users.nunique() == 1,
              "모든 방법이 같은 활성 사용자 집합으로 평가되어야 두 기준의 순위가 같다")
        check("active_rank_preserved", list(results.sort_values(["ndcg", "method"], ascending=[False, True]).method)
              == list(results.sort_values(["ndcg_active", "method"], ascending=[False, True]).method), "전체·활성 기준의 방법 순위가 같다")
    check("ordered_study_times", bool((dataset.log.groupby(["user", "week"])["minute"].apply(lambda x: np.all(np.diff(x.values) >= 0))).all()))
    lv_rows = lb_test.level
    for name, it in predictions.items():
        check(f"unique_items_{name}", all(len(x) == len(set(x)) for x in [v[v >= 0].tolist() for v in it]))
        valid = it >= 0; levels = catalog.item_level[np.maximum(it, 0)] - lv_rows[:, None]
        check(f"level_guard_{name}", not np.any(valid & (levels >= 2)))
        check(f"plus_one_limit_{name}", np.all((valid & (levels == 1)).sum(1) <= 1))
        passed_rec = F_test.und[cands_test.user[:, None], np.maximum(it, 0)] & valid
        check(f"no_passed_unit_recommended_{name}", not passed_rec.any())
    check("selection_operational_is_locked", selection["operational_algorithm"] is not None and selection.get("locked_before_test", False))
    if bundle is not None and bundle.config.guardrail.prereq_block:
        check("prerequisite_policy_used_for_selection_and_test",
              selection.get("selection_guardrail", {}).get("prereq_block") is True
              and bool(cands_test.audit.get("guardrail", {}).get("prereq_block")))
        check("prerequisite_required_all_methods", bool((results.prereq_violation_rate == 0).all()))
    if weeks:                   # 누수: 기준 주 이후 행을 섞어도 스냅샷 입력이 같아야 한다
        ok_leak, leak_detail = leakage_probe(dataset, catalog, weeks)
        check("no_future_leakage_feature_store", ok_leak, leak_detail)
    if bundle is not None:      # 개인정보: 원값·일분 비저장, 공개 셀 ≥ 5, 감사 열 누락 없음(실패하면 학습 중단, 번들 미저장)
        for name, ok, details in privacy_checks(bundle):
            check(name, ok, details)
    return QA
