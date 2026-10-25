"""보고서 수치 재현: 두 seed 학습 → 목적·현재 단계 평가 → 공통 기초 이수 가정 평가 → 진단·페르소나
→ MF·MLP 비교와 생성기 민감도(scripts/reproduce_extensions.py) → 대응표.

실행(프로젝트 루트):  python scripts/reproduce_report.py      (MF·MLP·민감도 단계를 빼려면 --no-extensions)
산출: runs/     학습 번들(bundle.pkl)과 전체 결과(용량 큼, 배포하지 않음)
      results/  보고서 표에 대응하는 요약 CSV·JSON과 results/report_numbers.md
소요: 2코어 PC 기준 약 9분(--no-extensions면 약 3분). torch는 필요 없다(MF·MLP는 NumPy 구현).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
SEEDS = (42, 20261023)
LABEL = {"PurposeStageRule": "목적 단계 규칙 운영안", "GlobalPopularity": "전체 인기",
         "BehaviourGroupPopularity": "행동 집단 인기", "Content": "콘텐츠 기반", "UserCFPure": "사용자 CF 행동만",
         "ItemCF": "아이템 CF", "LegacyValidatedRule": "검증 선택 규칙"}
STAGE = {"core": "공통 기초", "goal": "목적별 핵심", "advanced": "심화", "connect": "ETF 유형 연결"}
SCENARIO = {"no_diagnosis": "진단 인정 없음", "conservative": "낮은 정답확률 가정",
            "central": "중간 정답확률 가정", "optimistic": "높은 정답확률 가정"}
KEEP = {
    "seed{seed}": ["test_results.csv", "manifest.json", "evaluation_protocol.json",
                   "validation_configurations.csv", "group_results.csv"],
    "purpose_stage_seed{seed}": ["Purpose_Stage_Method_Comparison.csv", "Purpose_Stage_Subgroup_Comparison.csv",
                                 "Purpose_Stage_Paired_Comparison.csv", "purpose_stage_evaluation_summary.json"],
    "goal_stage_seed{seed}": ["Goal_Stage_Method_Comparison.csv", "Goal_Stage_Paired_Comparison.csv",
                              "goal_stage_summary.json"],
}
KEEP_DIAGNOSIS = ["Diagnosis_Shortlist_Sensitivity.csv", "Diagnosis_Target_Definition_Impact.csv",
                  "Diagnosis_Sensitivity_Summary.json", "Persona_Diagnosis_Answers.csv",
                  "Persona_Recommendation_Lists.csv", "Curriculum_Time_Comparison.csv"]


def run(*args):
    cmd = [sys.executable, *map(str, args)]
    print("$ python", " ".join(cmd[1:]), flush=True)
    subprocess.run(cmd, cwd=PROJECT, check=True)


def stages(counts: dict) -> str:
    return ", ".join(f"{STAGE.get(k, k)} {int(v):,}명" for k, v in counts.items())


def pct(x, d=1):
    return f"{100 * float(x):.{d}f}%"


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def report_numbers(results: Path) -> str:
    out = ["# 보고서 수치 대응표", "",
           "`python scripts/reproduce_report.py`가 만든 값이다. 괄호 안은 보고서의 표·절 번호다.", ""]

    # 3.1 데이터와 평가 대상
    m42 = json.loads((results / "seed42" / "manifest.json").read_text(encoding="utf-8"))
    d, v, t = m42["dataset"], m42["validation"], m42["test"]
    out += ["## 모의 데이터와 평가 대상 (3.1, 4.4, 5.2)", "",
            f"- seed 42: 학습자 {d['users']:,}명, 학습 시도 {d['study_attempts']:,}건, 완료 {d['complete']:,}, "
            f"퀴즈 시도 {d['quiz_attempted']:,}, 퀴즈 통과 {d['quiz_pass']:,}, 저장 {d['save']:,}, 이탈 {d['drop']:,}",
            f"- 미완료·이탈 미표시 {d['not_complete'] - d['drop']:,}건, 서로 다른 사용자–단원 {d['distinct_pairs']:,}쌍 "
            f"(사용자당 {d['distinct_pairs'] / d['users']:.2f}개), 밀도 {pct(d['density'], 2)}",
            f"- 검증 대상 {v['rows']:,}명(2주차), 테스트 대상 {t['rows']:,}명(3주차), 정답 보유 {t['eligible_positive_users']:,}명 "
            f"({pct(t['eligible_positive_users'] / t['rows'])}), 정답 없음 {t['rows'] - t['eligible_positive_users']:,}명",
            f"- 고정 정답 {t['eligible_positive_items']:,}개 중 선수 미충족 {t['prerequisite_blocked_positive_items']:,}개 "
            f"({pct(t['prerequisite_blocked_positive_items'] / t['eligible_positive_items'])})", ""]

    # 표 9
    comp = {s: read(results / f"purpose_stage_seed{s}" / "Purpose_Stage_Method_Comparison.csv").set_index("method") for s in SEEDS}
    out += ["## 표 9 동일 후보와 선수 필터에서의 두 핵심 지표", "",
            "| 방법 | seed 42 NDCG | 현재 단계 정합 | 새 seed NDCG | 현재 단계 정합 |", "| --- | ---: | ---: | ---: | ---: |"]
    for key, name in LABEL.items():
        a, b = comp[42].loc[key], comp[20261023].loc[key]
        out.append(f"| {name} | {a.ndcg:.6f} | {pct(a.purpose_current_stage_alignment, 2)} | "
                   f"{b.ndcg:.6f} | {pct(b.purpose_current_stage_alignment, 2)} |")
    s42 = json.loads((results / "purpose_stage_seed42" / "purpose_stage_evaluation_summary.json").read_text(encoding="utf-8"))
    paired = read(results / "purpose_stage_seed42" / "Purpose_Stage_Paired_Comparison.csv").set_index("reference")
    lg = paired.loc["LegacyValidatedRule"]
    ext = results / "extensions"
    if all((ext / f"mf_mlp_seed{s}" / "MF_MLP_Method_Comparison.csv").exists() for s in SEEDS):
        mf = {s: read(ext / f"mf_mlp_seed{s}" / "MF_MLP_Method_Comparison.csv").set_index("method") for s in SEEDS}
        for key, name in (("MF_ALS", "MF(ALS)"), ("MF_BPR", "MF(BPR)"), ("MLP", "MLP")):
            a, b = mf[42].loc[key], mf[20261023].loc[key]
            out.append(f"| {name} | {a.ndcg:.6f} | {pct(a.stage_alignment_common_core, 2)} | "
                       f"{b.ndcg:.6f} | {pct(b.stage_alignment_common_core, 2)} |")
    out += ["", f"- 평가 대상: seed 42 {int(comp[42].loc['PurposeStageRule'].users):,}명, "
                f"새 seed {int(comp[20261023].loc['PurposeStageRule'].users):,}명. 현재 단계: "
                f"{stages(s42['current_stage_counts'])}",
            f"- 짧은 목록 비율(seed 42) {pct(comp[42].loc['PurposeStageRule'].short_list_rate)}, "
            f"추천 0개 요청 {int(comp[42].loc['PurposeStageRule'].zero_display_requests)}건, 선수 위반 "
            f"{pct(comp[42].loc['PurposeStageRule'].prerequisite_violation_rate)}",
            f"- 같은 표시 개수의 정합률 최대치(seed 42) "
            f"{pct(s42['attainable_stage_alignment_with_same_display_count_constraints']['alignment_rate'])}",
            f"- 운영안 − 검증 선택 규칙(seed 42): NDCG {lg.ndcg_difference:+.6f}, 정합률 {100 * lg.alignment_difference:+.2f}%p", ""]
    if (ext / "generator_sensitivity_paired.csv").exists():
        gp = read(ext / "generator_sensitivity_paired.csv")
        r0 = gp[(gp.goal_effect == 0) & (gp.reference == "GlobalPopularity")].iloc[0]
        out += ["## 생성기 목적 효과 민감도 (4.4)", "",
                f"- 목적 효과 0인 seed 42 세계: 운영안 − 전체 인기 NDCG@5 {r0.ndcg_difference:+.6f} "
                f"[{r0.ndcg_ci_low:+.6f}, {r0.ndcg_ci_high:+.6f}] (자세한 표는 extensions/extension_numbers.md)", ""]

    # 4.3 공통 기초 이수 가정
    goal = {s: json.loads((results / f"goal_stage_seed{s}" / "goal_stage_summary.json").read_text(encoding="utf-8")) for s in SEEDS}
    out += ["## 공통 기초 이수 가정의 정합률 (4.3)", "",
            "평가 대상자 전원이 공통 기초 9단원을 이수했다고 가정해 다음 단계로 옮긴 결과다(행동 기록은 그대로).", "",
            "| 방법 | seed 42 | 새 seed |", "| --- | ---: | ---: |"]
    rows = {s: {r["method"]: r for r in goal[s]["methods"]} for s in SEEDS}
    for key, name in LABEL.items():
        out.append(f"| {name} | {pct(rows[42][key]['stage_alignment'])} | {pct(rows[20261023][key]['stage_alignment'])} |")
    out.append(f"| 같은 표시 개수의 최대치 | {pct(goal[42]['attainable_alignment_same_display_count']['alignment_rate'])} | "
               f"{pct(goal[20261023]['attainable_alignment_same_display_count']['alignment_rate'])} |")
    gaps = [p["alignment_difference"] for s in SEEDS for p in goal[s]["paired_comparisons"]]
    out += ["", f"- 단계 분포: seed 42 {stages(goal[42]['current_stage_counts'])}, 새 seed {stages(goal[20261023]['current_stage_counts'])}",
            f"- 운영안과 비교군의 차이는 최소 {100 * min(gaps):+.2f}%p (두 seed, 대응 부트스트랩 500회 구간은 "
            f"goal_stage_seed*/Goal_Stage_Paired_Comparison.csv)", ""]

    # 표 10
    sens = read(results / "diagnosis" / "Diagnosis_Shortlist_Sensitivity.csv")
    out += ["## 표 10 진단 이수 인정 가정에 따른 짧은 목록 민감도", "",
            "| 조건 | 5개 미만 사용자 | 전체 비율 | 무이력 비율 | 목적 단계 진입 |", "| --- | ---: | ---: | ---: | ---: |"]
    for key, name in SCENARIO.items():
        a = sens[(sens.scenario == key) & (sens.cohort == "all")].iloc[0]
        n = sens[(sens.scenario == key) & (sens.cohort == "no_study_history")].iloc[0]
        moved = int(a.users - a.current_stage_core_users)
        out.append(f"| {name} | {int(a.short_list_users):,}/{int(a.users):,} | {pct(a.short_list_rate, 2)} | "
                   f"{pct(n.short_list_rate, 2)} (무이력 {int(n.users):,}명) | {moved}명 |")
    out.append("")

    # 표 4·5
    lists = read(results / "diagnosis" / "Persona_Recommendation_Lists.csv")
    for snap, title in (("after_diagnosis", "표 4 진단 직후 실제 추천 목록"), ("after_common_core", "표 5 공통 위험 기초 이수 후 실제 추천 목록")):
        out += [f"## {title}", "", "| 사용자 | 순위와 단원 | 후보 | 진행률 | 현재 단계 정합 |", "| --- | --- | ---: | ---: | ---: |"]
        for persona, g in lists[lists.snapshot == snap].groupby("persona"):
            g = g.sort_values("rank")
            items = "<br>".join(f"{int(r['rank'])} {r.title}" + (" [현재 단계]" if bool(r.in_current_stage) else "") for _, r in g.iterrows())
            out.append(f"| {persona} | {items} | {int(g.candidate_count.iloc[0])} | {pct(g.stage_progress.iloc[0])} | "
                       f"{int(g.in_current_stage.astype(bool).sum())} / {len(g)} |")
        out.append("")
    a1 = lists[(lists.snapshot == "after_diagnosis") & (lists.persona == "A") & (lists["rank"] == 1)].iloc[0]
    out += [f"- A 진단 직후 1위 {a1.title}: 총점 {a1.score:.4f}", ""]

    # 표 7
    tm = read(results / "diagnosis" / "Curriculum_Time_Comparison.csv").set_index("persona")
    out += ["## 표 7 고정된 66단원 전체 기준과 목적별 분량의 분해", "",
            "| 사용자 | 전체 기준 분 | 목적 과정 분 | 범위 차이 분 | 진단 인정 분 | 잔여 분 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for p, r in tm.iterrows():
        out.append(f"| {p} | {r.full_fixed_curriculum_minutes} | {r.purpose_roadmap_total_minutes} | {r.purpose_scope_difference_minutes} | "
                   f"{r.diagnosis_recognised_minutes_within_roadmap} | {r.purpose_roadmap_minutes_remaining} |")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="runs", help="학습 번들과 전체 결과 폴더(프로젝트 기준 상대 경로)")
    parser.add_argument("--results", default="results", help="요약 결과 폴더(프로젝트 기준 상대 경로)")
    parser.add_argument("--reuse", action="store_true", help="runs/에 학습 번들이 있으면 다시 학습하지 않는다")
    parser.add_argument("--no-extensions", action="store_true", help="MF·MLP 비교와 생성기 민감도 단계를 건너뛴다")
    args = parser.parse_args()
    runs, results = Path(args.runs), Path(args.results)
    started = time.time()
    for seed in SEEDS:
        bundle = runs / f"seed{seed}"
        if not (args.reuse and (PROJECT / bundle / "bundle.pkl").exists()):
            run("-m", "etfrec", "train", "--n", 15000, "--seed", seed, "--out", bundle, "--no-neural",
                "--prereq-policy", "required", "--operational-policy", "PurposeStageRule")
        run("scripts/purpose_stage_evaluation.py", "--bundle", bundle, "--out", runs / f"purpose_stage_seed{seed}")
        run("scripts/goal_stage_evaluation.py", "--bundle", bundle, "--out", runs / f"goal_stage_seed{seed}")
    run("scripts/diagnosis_recheck.py", "--bundle", runs / "seed42", "--out", runs / "diagnosis")

    target = PROJECT / results
    for seed in SEEDS:                                    # 이 스크립트가 만드는 폴더만 비운다(extensions는 아래 단계가 관리)
        for folder in KEEP:
            shutil.rmtree(target / folder.format(seed=seed), ignore_errors=True)
    shutil.rmtree(target / "diagnosis", ignore_errors=True)
    for seed in SEEDS:
        for folder, names in KEEP.items():
            src, dst = PROJECT / runs / folder.format(seed=seed), target / folder.format(seed=seed)
            dst.mkdir(parents=True, exist_ok=True)
            for name in names:
                shutil.copy2(src / name, dst / name)
    (target / "diagnosis").mkdir(parents=True, exist_ok=True)
    for name in KEEP_DIAGNOSIS:
        shutil.copy2(PROJECT / runs / "diagnosis" / name, target / "diagnosis" / name)
    if not args.no_extensions:
        run("scripts/reproduce_extensions.py", "--runs", runs, "--results", results / "extensions")
    (target / "report_numbers.md").write_text(report_numbers(target), encoding="utf-8")
    print(f"\n완료: {results}/report_numbers.md ({time.time() - started:.0f}초)")


if __name__ == "__main__":
    main()
