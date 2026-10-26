"""교육 검토자 평가지 (중간보고서 7절: 파일럿 전에 목적·선행 지식만 제시한 사례를 교육 검토자에게 독립적으로 평가받는다).

투자 목적 5개 × 선행 지식 3단계 = 15개 사례마다 운영 정책(목적 단계 규칙)의 현재 로드맵 단계와 추천 단원 5개를 뽑아
검토자가 채울 칸(적절성 1~5, 순서 문제, 빠진 필수 단원, 의견)과 함께 CSV·마크다운으로 쓴다.
검토자가 채운 CSV를 --summarize로 넘기면 사례별 평균 적절성, 순서 문제 비율, 검토자 간 일치도를 정리한다.

실행:
    python scripts/expert_review_packet.py --bundle runs/seed42 --out docs/pilot
    python scripts/expert_review_packet.py --summarize 검토자A.csv 검토자B.csv --out results/pilot
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from etfrec.config import GOALS, HORIZONS  # noqa: E402
from etfrec.roadmap import _closure, _units  # noqa: E402
from etfrec.taxonomy import COMMON_CORE  # noqa: E402

RISK_NAMES = ["안정", "중립", "적극"]
GOAL_SETTINGS = {"pension": ("long", 1), "income": ("mid", 0), "long_term": ("long", 1), "trading": ("short", 2), "diversify": ("mid", 0)}
KNOWLEDGE = [("처음 배움", 0, 1, []),
             ("기초 일부(공통 기초의 수준1 단원과 그 선수 단원 통과)", 1, 1, [p for p in COMMON_CORE if p[1] == 1]),
             ("기초 완료(공통 기초 단원과 그 선수 단원 전부 통과)", 2, 2, list(COMMON_CORE))]
REVIEW_COLS = ["적절성(1~5)", "순서 문제(O/X)", "빠진 필수 단원", "의견"]


def build_cases(bundle_dir: str, k: int = 5) -> list:
    from etfrec.pipeline import Bundle
    from etfrec.service import LearnerInput, RecommendationService
    svc = RecommendationService(Bundle.load(bundle_dir))
    cat = svc.catalog
    rows, n = [], 0
    for goal, (horizon, risk) in GOAL_SETTINGS.items():
        for know, exp, placement, pairs in KNOWLEDGE:
            n += 1
            passed = _closure(cat, _units(cat, pairs))                 # 통과한 단원의 선수 단원까지 통과로 둔다(실제로 가능한 상태)
            events = [dict(item=int(i), week=0, complete=True, quiz=True, quiz_pass=True, source="diagnosis") for i in passed]
            r = svc.recommend(LearnerInput(label=f"사례 {n}", goal=goal, horizon=horizon, risk=risk, exp=exp, placement=placement,
                                           interests=[], events=events), k=k)
            stage = (r.get("roadmap") or {}).get("current_stage_name", "")
            for rank, it in enumerate(r["items"], 1):
                rows.append({"사례": n, "투자 목적": GOALS[goal], "기간": HORIZONS[horizon], "위험성향": RISK_NAMES[risk], "선행 지식": know,
                             "현재 로드맵 단계": stage, "순위": rank, "추천 단원": it["title"], "주제": it["topic"], "수준": it["level_name"],
                             "현재 단계 단원": "예" if it.get("in_current_stage") else "아니오", **{c: "" for c in REVIEW_COLS}})
    return rows


def write_packet(rows: list, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "expert_review_cases.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    L = ["# 교육 검토자 평가지", "",
         "각 사례는 투자 목적과 선행 지식만 정한 가상의 학습자입니다. 시스템이 고른 현재 로드맵 단계와 다음에 공부할 단원 5개를 보고 평가해 주세요.",
         "다른 검토자와 상의하지 않고 독립적으로 평가합니다. `expert_review_cases.csv`의 오른쪽 네 칸에 적어 주시면 됩니다.", "",
         "- **적절성(1~5)**: 이 학습자가 지금 이 단원을 공부하는 것이 적절한가(1 전혀 아니다 ~ 5 매우 그렇다)",
         "- **순서 문제(O/X)**: 먼저 배워야 할 단원보다 앞서 나왔으면 O",
         "- **빠진 필수 단원**: 이 학습자에게 지금 꼭 필요한데 목록에 없는 단원(사례의 첫 행에만 적어도 됨)",
         "- **의견**: 자유롭게", ""]
    for case in sorted({r["사례"] for r in rows}):
        rs = [r for r in rows if r["사례"] == case]
        h = rs[0]
        L += [f"## 사례 {case}. {h['투자 목적']} · {h['기간']} · 위험성향 {h['위험성향']} · {h['선행 지식']}", "",
              f"현재 로드맵 단계: {h['현재 로드맵 단계']}", "", "| 순위 | 추천 단원 | 주제 | 수준 | 현재 단계 단원 |", "| --- | --- | --- | --- | --- |"]
        L += [f"| {r['순위']} | {r['추천 단원']} | {r['주제']} | {r['수준']} | {r['현재 단계 단원']} |" for r in rs] + [""]
    (out / "expert_review_cases.md").write_text("\n".join(L), encoding="utf-8")


def summarize(paths: list, out: Path):
    import numpy as np
    sheets = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            sheets.append([r for r in csv.DictReader(f)])
    def score(r):
        v = (r.get("적절성(1~5)") or "").strip()
        return int(v) if v.isdigit() and 1 <= int(v) <= 5 else None
    keyed = [{(r["사례"], r["순위"]): r for r in s} for s in sheets]
    keys = sorted(set().union(*keyed), key=lambda x: (int(x[0]), int(x[1])))
    L = ["# 교육 검토자 평가 요약", "", f"검토자 {len(sheets)}명 · 평가 행 {len(keys)}개", "",
         "| 사례 | 학습자 | 평균 적절성 | 4점 이상 | 순서 문제 |", "| --- | --- | --- | --- | --- |"]
    all_scores = []
    for case in sorted({k[0] for k in keys}, key=int):
        rows = [kd[k] for kd in keyed for k in keys if k[0] == case and k in kd]
        sc = [score(r) for r in rows if score(r) is not None]
        all_scores += sc
        order = [r for r in rows if (r.get("순서 문제(O/X)") or "").strip().upper() == "O"]
        h = rows[0]
        L.append(f"| {case} | {h['투자 목적']} · {h['선행 지식']} | {np.mean(sc):.2f} | {np.mean([x >= 4 for x in sc]) * 100:.0f}% | {len(order)}/{len(rows)} |"
                 if sc else f"| {case} | {h['투자 목적']} · {h['선행 지식']} | – | – | {len(order)}/{len(rows)} |")
    L += ["", f"전체 평균 적절성 {np.mean(all_scores):.2f}점, 4점 이상 {np.mean([x >= 4 for x in all_scores]) * 100:.0f}% (평가 {len(all_scores)}건)"
          if all_scores else "적절성 점수가 아직 없다."]
    if len(sheets) >= 2:
        pairs = [(score(keyed[0][k]), score(keyed[1][k])) for k in keys if k in keyed[0] and k in keyed[1]]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if pairs:
            d = np.abs(np.array([a - b for a, b in pairs]))
            L += [f"검토자 1·2 일치도: 같은 점수 {np.mean(d == 0) * 100:.0f}%, 1점 이내 {np.mean(d <= 1) * 100:.0f}%, 평균 차이 {d.mean():.2f}점 ({len(pairs)}쌍)"]
    notes = [(r["사례"], r.get("빠진 필수 단원", "").strip(), r.get("의견", "").strip()) for s in sheets for r in s
             if r.get("빠진 필수 단원", "").strip() or r.get("의견", "").strip()]
    if notes:
        L += ["", "## 빠진 필수 단원과 의견", ""] + [f"- 사례 {c}: " + " / ".join(x for x in (m and f"빠진 단원: {m}", o) if x) for c, m, o in notes]
    out.mkdir(parents=True, exist_ok=True)
    (out / "expert_review_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out / "expert_review_summary.md")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bundle", default="runs/seed42")
    ap.add_argument("--out", default="docs/pilot")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--summarize", nargs="+", default=None, help="검토자가 채운 CSV들")
    a = ap.parse_args()
    if a.summarize:
        summarize(a.summarize, Path(a.out))
        return
    rows = build_cases(a.bundle, a.k)
    write_packet(rows, Path(a.out))
    print(f"사례 {len({r['사례'] for r in rows})}개, 행 {len(rows)}개 → {Path(a.out) / 'expert_review_cases.csv'}")


if __name__ == "__main__":
    main()
