"""보고서 표 9의 MF·MLP 행(두 seed)과 4.4절의 생성기 목적 효과 민감도를 만든다.

실행(프로젝트 루트):  python scripts/reproduce_extensions.py
먼저 scripts/reproduce_report.py를 실행해 runs/seed42·runs/seed20261023 번들이 있어야 한다(없으면 여기서 학습한다).
산출: results/extensions/ 요약 CSV와 extension_numbers.md. 소요: 2코어 PC 기준 약 6분(학습 번들이 없으면 약 8분).
scripts/reproduce_report.py가 마지막 단계에서 이 스크립트를 실행한다.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
SEEDS = (42, 20261023)
LABEL = {"PurposeStageRule": "목적 단계 규칙 운영안", "GlobalPopularity": "전체 인기", "BehaviourGroupPopularity": "행동 집단 인기",
         "Content": "콘텐츠 기반", "UserCFPure": "사용자 CF 행동만", "ItemCF": "아이템 CF", "LegacyValidatedRule": "검증 선택 규칙",
         "MF_ALS": "MF(ALS)", "MF_BPR": "MF(BPR)", "MLP": "MLP(목표 정렬 BPR)"}


def run(*args):
    cmd = [sys.executable, *map(str, args)]
    print("$ python", " ".join(cmd[1:]), flush=True)
    subprocess.run(cmd, cwd=PROJECT, check=True)


def pct(x, d=1):
    return f"{100 * float(x):.{d}f}%"


def numbers(target: Path) -> str:
    out = ["# MF·MLP 비교와 생성기 민감도", "", "`python scripts/reproduce_extensions.py`가 만든 값이다. 보고서 표 9의 MF·MLP 행과 4.4절 수치의 근거다.", ""]
    comp = {s: pd.read_csv(target / f"mf_mlp_seed{s}" / "MF_MLP_Method_Comparison.csv", encoding="utf-8-sig").set_index("method") for s in SEEDS}
    out += ["## MF·MLP 동일 조건 비교 (표 9와 같은 후보·필터·정답)", "",
            "| 방법 | NDCG@5 seed 42 / 새 seed | 정합률: 공통 기초 seed 42 / 새 seed | 정합률: 공통 기초 이수 가정 seed 42 / 새 seed |",
            "| --- | --- | --- | --- |"]
    for key, name in LABEL.items():
        a, b = comp[42].loc[key], comp[20261023].loc[key]
        out.append(f"| {name} | {a.ndcg:.6f} / {b.ndcg:.6f} | {pct(a.stage_alignment_common_core, 2)} / {pct(b.stage_alignment_common_core, 2)} | "
                   f"{pct(a.stage_alignment_after_common_core)} / {pct(b.stage_alignment_after_common_core)} |")
    out += ["", "선택 설정(2주차 검증 NDCG@5 기준):", ""]
    for s in SEEDS:
        for key in ("MF_ALS", "MF_BPR", "MLP"):
            r = comp[s].loc[key]
            out.append(f"- seed {s} {LABEL[key]}: {r.selected_params} (검증 {r.validation_ndcg:.6f})")
    pair = {s: pd.read_csv(target / f"mf_mlp_seed{s}" / "MF_MLP_Paired_Comparison.csv", encoding="utf-8-sig").set_index("reference") for s in SEEDS}
    out += ["", "운영안 − MF·MLP의 NDCG@5 차이 [대응 부트스트랩 95% 구간]:", ""]
    for s in SEEDS:
        for key in ("MF_ALS", "MF_BPR", "MLP"):
            p = pair[s].loc[key]
            out.append(f"- seed {s} {LABEL[key]}: {p.ndcg_difference:+.6f} [{p.ndcg_ci_low:+.6f}, {p.ndcg_ci_high:+.6f}]")

    sens = pd.read_csv(target / "generator_sensitivity.csv", encoding="utf-8-sig")
    paired = pd.read_csv(target / "generator_sensitivity_paired.csv", encoding="utf-8-sig")
    effects = sorted(sens.goal_effect.unique())
    out += ["", "## 생성기 목적 효과 민감도 (seed 42)", "",
            "생성기의 goal_effect만 바꿔 같은 절차로 학습·평가했다. 기본값은 0.8(본문 결과)이다.", "",
            "| 방법 | " + " | ".join(f"NDCG@5 (goal_effect {g:g})" for g in effects) + " |",
            "| --- | " + " | ".join("---:" for _ in effects) + " |"]
    for key, name in LABEL.items():
        if key not in set(sens.method):
            continue
        vals = [sens[(sens.goal_effect == g) & (sens.method == key)].iloc[0] for g in effects]
        out.append(f"| {name} | " + " | ".join(f"{v.ndcg:.6f} ({int(v.ndcg_rank)}위)" for v in vals) + " |")
    out += ["", "운영안 − 전체 인기 / 운영안 − 검증 선택 규칙의 NDCG@5 차이 [95% 구간]:", ""]
    for g in effects:
        parts = []
        for ref in ("GlobalPopularity", "LegacyValidatedRule"):
            p = paired[(paired.goal_effect == g) & (paired.reference == ref)].iloc[0]
            parts.append(f"{LABEL[ref]} {p.ndcg_difference:+.6f} [{p.ndcg_ci_low:+.6f}, {p.ndcg_ci_high:+.6f}]")
        out.append(f"- goal_effect {g:g}: " + "; ".join(parts))
    out += ["", "공통 기초 이수 가정 정합률(운영안 / 전체 인기):", ""]
    for g in effects:
        a = sens[(sens.goal_effect == g) & (sens.method == "PurposeStageRule")].iloc[0]
        b = sens[(sens.goal_effect == g) & (sens.method == "GlobalPopularity")].iloc[0]
        out.append(f"- goal_effect {g:g}: {pct(a.stage_alignment_after_common_core)} / {pct(b.stage_alignment_after_common_core)}")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--results", default="results/extensions")
    args = parser.parse_args()
    runs, target = Path(args.runs), PROJECT / args.results
    started = time.time()
    for seed in SEEDS:
        bundle = runs / f"seed{seed}"
        if not (PROJECT / bundle / "bundle.pkl").exists():
            run("-m", "etfrec", "train", "--n", 15000, "--seed", seed, "--out", bundle, "--no-neural",
                "--prereq-policy", "required", "--operational-policy", "PurposeStageRule")
        run("scripts/mf_mlp_comparison.py", "--bundle", bundle, "--out", runs / f"mf_mlp_seed{seed}")
    run("scripts/generator_sensitivity.py", "--runs", runs)

    if target.exists():
        shutil.rmtree(target)
    for seed in SEEDS:
        dst = target / f"mf_mlp_seed{seed}"
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("MF_MLP_Method_Comparison.csv", "MF_MLP_Paired_Comparison.csv", "MF_MLP_Validation_Grid.csv", "mf_mlp_summary.json"):
            shutil.copy2(PROJECT / runs / f"mf_mlp_seed{seed}" / name, dst / name)
    for name in ("generator_sensitivity.csv", "generator_sensitivity_paired.csv"):
        shutil.copy2(PROJECT / runs / name, target / name)
    (target / "extension_numbers.md").write_text(numbers(target), encoding="utf-8")
    print(f"\n완료: {args.results}/extension_numbers.md ({time.time() - started:.0f}초)")


if __name__ == "__main__":
    main()
