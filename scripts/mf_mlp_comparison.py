"""보고서 표 9의 MF·MLP 행: MF·MLP를 같은 서비스 조건(같은 후보·수준·선수 필터·정답·지표)에서 운영안·기존 비교군과 비교한다.

torch 없이 NumPy로 학습한다(etfrec.factor_models).
- MF(ALS): 암묵 피드백 ALS [Hu·Koren·Volinsky 2008]. 반응 점수 합을 신뢰도로 쓴다.
- MF(BPR): 쌍별 순위 손실 MF [Rendle 외 2009]. 미관측 단원을 '양성보다 뒤'로만 본다.
- MLP: 9주차 구조(임베딩 8 → 결합 → 은닉 16 ReLU → 출력). 학습 주마다 '그 주에 처음 통과한 단원'을
  '그 주까지 통과하지 않은 단원'보다 앞에 두도록 BPR로 학습한다(평가 정답과 같은 정의, 평가 주 기록은 쓰지 않음).
설정은 다른 비교군과 같이 2주차 검증 NDCG@5로 고르고, 0~2주 자료로 다시 학습해 3주차에서 평가한다.
공통 기초 이수 가정(scripts/goal_stage_evaluation.py와 같은 조건)의 정합률도 함께 계산한다.

실행: python scripts/mf_mlp_comparison.py --bundle runs/seed42 --out runs/mf_mlp_seed42
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

from etfrec.config import K, GuardrailConfig
from etfrec.data import Dataset
from etfrec.evaluation import bootstrap_ci, make_select, primary_eval, row_metrics
from etfrec.factor_models import PairMLP, bpr_mf, implicit_als
from etfrec.features import feature_store
from etfrec.pipeline import Bundle
from etfrec.purpose_policy import purpose_stage_algorithm
from etfrec.roadmap import _closure, _units
from etfrec.signals import SignalBank, build_signals, next_week_pairs
from etfrec.taxonomy import COMMON_CORE
from etfrec.zoo import score_algo

import purpose_stage_evaluation as pse

GRIDS = {
    "MF_ALS": [dict(k=k, lam=lam, alpha=a) for k in (2, 4, 8, 16) for lam in (10.0, 100.0, 300.0) for a in (0.3, 1.0, 5.0)],
    "MF_BPR": [dict(k=k, weight_decay=wd) for k in (2, 4, 8, 16) for wd in (1e-5, 1e-4, 1e-3)],
    "MLP": [dict(epochs=e, weight_decay=wd) for e in (12, 24, 48) for wd in (1e-5, 1e-4, 1e-3, 1e-2)],
}
LABEL = {"PurposeStageRule": "목적 단계 규칙 운영안", "GlobalPopularity": "전체 인기", "BehaviourGroupPopularity": "행동 집단 인기",
         "Content": "콘텐츠 기반", "UserCFPure": "사용자 CF 행동만", "ItemCF": "아이템 CF", "LegacyValidatedRule": "검증 선택 규칙",
         "MF_ALS": "MF(ALS)", "MF_BPR": "MF(BPR)", "MLP": "MLP(목표 정렬 BPR)"}


class Factor:
    def __init__(self, U, V):
        self.U, self.V = U, V

    def score(self, u, i):
        return np.sum(self.U[u] * self.V[i], axis=1)


def fit(family: str, params: dict, store, log_before: pd.DataFrame, n_items: int, seed: int):
    if family == "MF_ALS":
        return Factor(*implicit_als(store.Rw, seed=seed, **params))
    if family == "MF_BPR":
        P, Q, _ = bpr_mf(store.Rw, seed=seed, **params)
        return Factor(P, Q)
    pairs = next_week_pairs(log_before, n_items, seed)
    return PairMLP(store.n, n_items, seed=seed).fit(pairs["u"], pairs["i"], pairs["j"], **params)


def score_matrix(model, cands) -> np.ndarray:
    S = model.score(np.repeat(cands.user, cands.L), cands.cand0.ravel()).reshape(cands.R, cands.L).astype(np.float64)
    S = S + cands.jitter                      # 다른 기법과 같은 고정 동점 순서
    S[~cands.valid] = -np.inf
    return S


def condition(bundle, store, log, guard):
    cands, lb = primary_eval(bundle.config.test_week, store, log, bundle.catalog, guard)
    select = make_select(cands, lb, bundle.catalog, K, guard)
    masks, stages, whole = pse.stage_membership(bundle.catalog, lb)
    return cands, lb, select, (masks, whole, stages)


def run(bundle_path: Path, out: Path) -> dict:
    started = time.time()
    out.mkdir(parents=True, exist_ok=True)
    bundle = Bundle.load(str(bundle_path))
    cfg, catalog = bundle.config, bundle.catalog
    seed = int(cfg.seed)
    dataset = Dataset.synthetic(cfg)
    assert dataset.summary()["study_attempts"] == bundle.dataset_summary["study_attempts"]
    guard = GuardrailConfig(prereq_block=True)
    n_items = catalog.n_items

    # 1) 검증: 0~1주 자료로 학습, 2주차 NDCG@5로 설정 선택
    F_val = feature_store(dataset.profiles, dataset.log, catalog, cfg.val_week)
    cands_v, lb_v = primary_eval(cfg.val_week, F_val, dataset.log, catalog, guard)
    select_v = make_select(cands_v, lb_v, catalog, K, guard)
    log_v = dataset.log[dataset.log.week < cfg.val_week]
    grid_rows, best = [], {}
    for family, grid in GRIDS.items():
        for params in grid:
            t0 = time.time()
            model = fit(family, params, F_val, log_v, n_items, seed)
            nd = row_metrics(select_v(score_matrix(model, cands_v)), cands_v, catalog.item_topic, K)[0]
            v = float(cands_v.per_user(nd).mean())
            grid_rows.append(dict(family=family, params=json.dumps(params), validation_ndcg=v, seconds=round(time.time() - t0, 2)))
            if family not in best or v > best[family][1]:
                best[family] = (params, v)
        print(f"{family}: 검증 최고 NDCG@5 {best[family][1]:.6f} {best[family][0]}", flush=True)

    # 2) 테스트: 0~2주 자료로 다시 학습, 3주차 평가(운영안·기존 비교군과 같은 후보·필터)
    log_t = dataset.log[dataset.log.week < cfg.test_week]
    models = {fam: fit(fam, best[fam][0], bundle.store, log_t, n_items, seed) for fam in GRIDS}
    existing = {"PurposeStageRule": purpose_stage_algorithm(), **pse.selected_comparators(bundle)}
    needed = {sig for algo in existing.values() for sig in algo.signals}

    cands, lb, select, (masks, whole, stages) = condition(bundle, bundle.store, dataset.log, guard)
    assert np.array_equal(cands.users, bundle.test_users)
    bank = SignalBank(cands)
    build_signals(bank, bundle.reference, lb, catalog, bundle.models, needed=needed)
    missing = catalog.missing_prereq_count(lb.und)

    users = np.asarray(bundle.test_users)
    core = sorted(_closure(catalog, _units(catalog, COMMON_CORE)))
    und = bundle.store.und.copy()
    und[users, :] |= np.isin(np.arange(n_items), core)[None, :]
    cands2, lb2, select2, (masks2, whole2, stages2) = condition(bundle, replace(bundle.store, und=und), dataset.log, guard)
    bank2 = SignalBank(cands2)
    build_signals(bank2, bundle.reference, lb2, catalog, bundle.models, needed=needed)

    rows, ndcg, counts, counts2 = [], {}, {}, {}
    for name in list(existing) + list(GRIDS):
        if name in existing:
            S, S2 = score_algo(existing[name], bank, lb.nu), score_algo(existing[name], bank2, lb2.nu)
        else:
            S, S2 = score_matrix(models[name], cands), score_matrix(models[name], cands2)
        nd, _, _, items = row_metrics(select(S), cands, catalog.item_topic, K)
        ndcg[name] = cands.per_user(nd)
        counts[name] = pse.alignment_counts(items, masks, whole, stages)
        items2 = row_metrics(select2(S2), cands2, catalog.item_topic, K)[3]
        counts2[name] = pse.alignment_counts(items2, masks2, whole2, stages2)
        shown = items >= 0
        viol = (missing[np.arange(len(items))[:, None], np.maximum(items, 0)] > 0) & shown
        rows.append(dict(method=name, label=LABEL[name],
                         selected_params=(json.dumps(best[name][0]) if name in best else "기존 비교군(검증 선택) 또는 고정 운영안"),
                         validation_ndcg=(best[name][1] if name in best else None),
                         ndcg=float(ndcg[name].mean()),
                         ndcg_positive_target_users=float(ndcg[name][cands.full_relevant_count > 0].mean()),
                         stage_alignment_common_core=pse.aggregate(counts[name])["alignment_rate"],
                         short_list_rate=float((counts[name]["shown"] < K).mean()),
                         prerequisite_violation_rate=float(viol.sum() / max(shown.sum(), 1)),
                         stage_alignment_after_common_core=pse.aggregate(counts2[name])["alignment_rate"]))
    paired = []
    for name in rows[1:]:
        m = name["method"]
        lo, hi = bootstrap_ci(ndcg["PurposeStageRule"] - ndcg[m], 500, seed)
        alo, ahi = pse.paired_ratio_ci(counts["PurposeStageRule"], counts[m], seed, 500)
        blo, bhi = pse.paired_ratio_ci(counts2["PurposeStageRule"], counts2[m], seed, 500)
        base = rows[0]
        paired.append(dict(reference=m, ndcg_difference=base["ndcg"] - name["ndcg"], ndcg_ci_low=lo, ndcg_ci_high=hi,
                           alignment_core_difference=base["stage_alignment_common_core"] - name["stage_alignment_common_core"],
                           alignment_core_ci_low=alo, alignment_core_ci_high=ahi,
                           alignment_after_core_difference=base["stage_alignment_after_common_core"] - name["stage_alignment_after_common_core"],
                           alignment_after_core_ci_low=blo, alignment_after_core_ci_high=bhi, bootstrap_resamples=500))

    pd.DataFrame(grid_rows).to_csv(out / "MF_MLP_Validation_Grid.csv", index=False, encoding="utf-8-sig")
    table = pd.DataFrame(rows)
    table.to_csv(out / "MF_MLP_Method_Comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(paired).to_csv(out / "MF_MLP_Paired_Comparison.csv", index=False, encoding="utf-8-sig")
    summary = dict(seed=seed, evaluation_users=int(len(users)), selected={k: dict(params=v[0], validation_ndcg=v[1]) for k, v in best.items()},
                   grids={k: len(v) for k, v in GRIDS.items()}, implementation="NumPy (etfrec.factor_models); torch not used",
                   protocol="same candidates, level/prerequisite post-filter, fixed targets and IDCG as Table 9; settings chosen on week-2 validation NDCG@5; refit on weeks 0-2; tested on week 3",
                   no_history_users=int((lb.nu == 0).sum()),
                   no_history_note="users without training interactions get zero factors (MF) or zero user embedding (MLP); like the basic CF comparators they fall back to the fixed tie order or item-only scores",
                   methods=rows, paired_comparisons=paired, seconds=round(time.time() - started, 1))
    (out / "mf_mlp_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    view = table[["label", "ndcg", "stage_alignment_common_core", "stage_alignment_after_common_core"]].copy()
    print(view.to_string(index=False, float_format=lambda x: f"{x:.6f}"))
    print(f"소요 {summary['seconds']}초")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.bundle, args.out)
