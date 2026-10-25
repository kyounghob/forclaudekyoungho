"""공통 기초 이수 가정에서의 목적·현재 단계 정합률 (보고서 4.3절).

평가 주차의 사용자 전원이 공통 기초 단원을 이수했다고 가정한다. 행동 기록은 그대로 두고
이수 상태만 바꾼 뒤 후보를 다시 만들고, 목적 단계 규칙과 비교군이 표시한 단원 가운데
첫 미완료 단계(대부분 목적별 핵심)의 학습 가능 단원이 차지하는 비율을 계산한다.
점수와 지표가 같은 로드맵을 쓰므로 학습 효과가 아니라 로드맵 기준의 출력 일관성을 나타낸다.

실행: python scripts/goal_stage_evaluation.py --bundle runs/seed42 --out runs/goal_stage_seed42
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

from etfrec.config import K, GuardrailConfig
from etfrec.data import Dataset
from etfrec.evaluation import make_select, primary_eval, row_metrics
from etfrec.pipeline import Bundle
from etfrec.purpose_policy import purpose_stage_algorithm
from etfrec.roadmap import _closure, _units
from etfrec.signals import SignalBank, build_signals
from etfrec.taxonomy import COMMON_CORE
from etfrec.zoo import score_algo

import purpose_stage_evaluation as pse  # 같은 정합률 정의·비교군 선택·대응 부트스트랩을 재사용한다


def run(bundle_path: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    bundle = Bundle.load(str(bundle_path))
    dataset = Dataset.synthetic(bundle.config)
    assert dataset.summary()["study_attempts"] == bundle.dataset_summary["study_attempts"]
    catalog = bundle.catalog
    core = sorted(_closure(catalog, _units(catalog, COMMON_CORE)))
    users = np.asarray(bundle.test_users)

    # 이수 상태만 바꾼다(행동 행렬·선호·인기 신호는 그대로)
    und = bundle.store.und.copy()
    und[users, :] |= np.isin(np.arange(catalog.n_items), core)[None, :]
    store = replace(bundle.store, und=und)

    guard = GuardrailConfig(prereq_block=True)
    cands, lb = primary_eval(bundle.config.test_week, store, dataset.log, catalog, guard)
    assert np.array_equal(cands.users, users)
    methods = {"PurposeStageRule": purpose_stage_algorithm(), **pse.selected_comparators(bundle)}
    bank = SignalBank(cands)
    build_signals(bank, bundle.reference, lb, catalog, bundle.models,
                  needed={sig for algo in methods.values() for sig in algo.signals})
    select = make_select(cands, lb, catalog, K, guard)
    masks, stages, whole = pse.stage_membership(catalog, lb)

    oracle = select(masks[np.arange(cands.R)[:, None], cands.cand0].astype(float) + cands.jitter)
    oracle_items = row_metrics(oracle, cands, catalog.item_topic, K)[3]
    upper = pse.aggregate(pse.alignment_counts(oracle_items, masks, whole, stages))

    rows, counts = [], {}
    for name, algo in methods.items():
        items = row_metrics(select(score_algo(algo, bank, lb.nu)), cands, catalog.item_topic, K)[3]
        c = pse.alignment_counts(items, masks, whole, stages)
        counts[name] = c
        a = pse.aggregate(c)
        rows.append(dict(method=name, algorithm_name=algo.name, users=a["users"],
                         displayed_items=a["displayed_items"], aligned_items=a["aligned_items"],
                         stage_alignment=a["alignment_rate"],
                         in_roadmap_share=float(c["roadmap"].sum() / max(c["shown"].sum(), 1)),
                         short_list_rate=float((c["shown"] < K).mean())))
    seed = int(bundle.config.seed)
    paired = []
    base = pse.aggregate(counts["PurposeStageRule"])["alignment_rate"]
    for name in methods:
        if name == "PurposeStageRule":
            continue
        lo, hi = pse.paired_ratio_ci(counts["PurposeStageRule"], counts[name], seed, 500)
        paired.append(dict(reference=name, alignment_difference=base - pse.aggregate(counts[name])["alignment_rate"],
                           ci_low=lo, ci_high=hi, bootstrap_resamples=500, unit="paired evaluation-week users"))

    stage_counts = {str(k): int(v) for k, v in zip(*np.unique(stages, return_counts=True))}
    pd.DataFrame(rows).to_csv(out / "Goal_Stage_Method_Comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(paired).to_csv(out / "Goal_Stage_Paired_Comparison.csv", index=False, encoding="utf-8-sig")
    summary = dict(seed=seed, users=int(len(users)), common_core_units=[int(i) for i in core],
                   assumption="all evaluation-week users have passed the common-core units; behaviour log, preferences and popularity unchanged",
                   current_stage_counts=stage_counts, attainable_alignment_same_display_count=upper,
                   methods=rows, paired_comparisons=paired,
                   scope="conformance to the authored roadmap that is also a scoring signal; not a learning-effect estimate")
    (out / "goal_stage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"seed {seed} | users {len(users)} | stages after common core {stage_counts} | attainable {upper['alignment_rate']:.4f}")
    print(pd.DataFrame(rows)[["method", "stage_alignment", "in_roadmap_share", "short_list_rate"]].to_string(index=False))
    for p in paired:
        print(f"  vs {p['reference']:24s} {p['alignment_difference'] * 100:+.2f}%p  [{p['ci_low'] * 100:+.2f}, {p['ci_high'] * 100:+.2f}]")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.bundle, args.out)
