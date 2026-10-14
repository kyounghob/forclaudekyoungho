"""번들의 test_results.csv로 README 결과 표(마크다운)를 만든다: python scripts/results_table.py artifacts/bundle_v2"""
import json, sys
import pandas as pd

KO = {"RULE": "규칙(검증 1위 = 전역)", "Global": None, "RouterNoGender": "라우터(성별 제외, 운영)", "RouterFull": "라우터(성별 포함)",
      "RouterNoGenderIncome": "라우터(성별·소득 제외)", "NoDemographics": "인구통계 미사용 1위", "UCF": "사용자 CF",
      "RouterNoGender+prereq": "운영 라우터 + 선수 가드레일", "POP": "인기", "ICF": "아이템 CF", "CONTENT": "콘텐츠",
      "MLP": "MLP(9주차, BCE)", "MLP_BPR": "MLP 쌍별(관측 음성)", "MLP_BPRU": "MLP 쌍별(미관측 음성)", "MLP_NEXT": "MLP 목표 정렬(다음 주 통과)",
      "MF_OBS": "관측 MF", "MF": "표본 MF", "MF_BPR": "BPR MF", "Random": "무작위"}


def table(bundle_dir: str) -> str:
    res = pd.read_csv(f"{bundle_dir}/test_results.csv", encoding="utf-8-sig")
    m = json.load(open(f"{bundle_dir}/manifest.json", encoding="utf-8"))
    t = m["test"]
    head = (f"테스트 {t['week']}주차 · 전체 {t['rows']:,}명(다음 주 정답 없음 {t['zero_observed_target']:,}명 포함) · "
            f"활성 {int(res.active_users.iloc[0]):,}명")
    lines = [head, "", "| 방법 | NDCG@5 전체 | NDCG@5 활성 | Diversity@5 | 선수 미이수 | 전역 1위 대비 [95% 구간] |", "| --- | --- | --- | --- | --- | --- |"]
    fam = m.get("selection", {}).get("families", {})
    same = fam.get("Global") == fam.get("RULE")          # 전역 1위가 규칙 계열 1위와 같은 설정이면 한 행으로 쓴다
    ko = dict(KO, RULE="규칙(검증 1위 = 전역)" if same else "규칙(계열 1위)", Global=None if same else "전역 검증 1위")
    for _, r in res.iterrows():
        name = ko.get(r.method, r.method)
        if name is None:
            continue
        diff = "기준" if r.method == ("RULE" if same else "Global") else f"{r.difference_vs_global:+.4f} [{r.ci_low:+.4f}, {r.ci_high:+.4f}]"
        lines.append(f"| {name} | {r.ndcg:.4f} | {r.ndcg_active:.4f} | {r.diversity:.3f} | {r.prereq_violation_rate:.3f} | {diff} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table(sys.argv[1] if len(sys.argv) > 1 else "artifacts/bundle_v2"))
