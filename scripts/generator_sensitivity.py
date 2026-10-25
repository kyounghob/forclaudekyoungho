"""보고서 4.4절: 생성기 가정 민감도.

모의 데이터 생성기는 목적 친화도를 주제 선호에 더하고(goal_effect, 기본 0.8), 운영안도 같은 목적 친화도를 점수에 쓴다.
이 순환성 때문에 운영안의 NDCG 우위가 생성 가정에서 나온 것인지 확인하려고, goal_effect만 바꾼 모의 세계에서
같은 절차(학습 → 비교군 검증 선택 → 3주차 평가 → 공통 기초 이수 가정 평가)를 반복한다.

실행: python scripts/generator_sensitivity.py [--effects 0 0.8 1.6] [--seed 42]
산출: runs/goal_effect_<값>/ 번들과 평가 결과, runs/generator_sensitivity.csv, runs/generator_sensitivity_paired.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

from etfrec.config import TrainConfig
from etfrec.data import Dataset
from etfrec.pipeline import train

import goal_stage_evaluation as gse
import purpose_stage_evaluation as pse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effects", type=float, nargs="+", default=[0.0, 0.8, 1.6])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n", type=int, default=15000)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--reuse", action="store_true", help="이미 학습한 번들이 있으면 다시 학습하지 않는다")
    args = parser.parse_args()
    runs = args.runs if args.runs.is_absolute() else PROJECT / args.runs
    rows, paired = [], []
    for g in args.effects:
        started = time.time()
        tag = f"goal_effect_{g:g}"
        bundle_dir = runs / tag
        if not (args.reuse and (bundle_dir / "bundle.pkl").exists()):
            cfg = TrainConfig(n_learners=args.n, seed=args.seed, goal_effect=float(g))
            train(Dataset.synthetic(cfg), cfg, out_dir=str(bundle_dir), enable_neural=False, log=lambda *a, **k: None)
        ps = pse.run(bundle_dir, runs / f"{tag}_purpose", None, None)
        gs = gse.run(bundle_dir, runs / f"{tag}_goal")
        after = {r["method"]: r["stage_alignment"] for r in gs["methods"]}
        for r in ps["methods"]:
            rows.append(dict(goal_effect=g, method=r["method"], ndcg=r["ndcg"],
                             stage_alignment_common_core=r["purpose_current_stage_alignment"],
                             stage_alignment_after_common_core=after[r["method"]]))
        for c in ps["paired_comparisons"]:
            paired.append(dict(goal_effect=g, reference=c["reference"], ndcg_difference=c["ndcg_difference"],
                               ndcg_ci_low=c["ndcg_ci_low"], ndcg_ci_high=c["ndcg_ci_high"]))
        print(f"goal_effect {g:g}: {time.time() - started:.0f}초", flush=True)
    table = pd.DataFrame(rows)
    table["ndcg_rank"] = table.groupby("goal_effect").ndcg.rank(ascending=False, method="min").astype(int)
    table.to_csv(runs / "generator_sensitivity.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(paired).to_csv(runs / "generator_sensitivity_paired.csv", index=False, encoding="utf-8-sig")
    print(table.pivot(index="method", columns="goal_effect", values="ndcg").to_string(float_format=lambda x: f"{x:.6f}"))


if __name__ == "__main__":
    main()
