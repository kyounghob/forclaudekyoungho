"""파일럿 결과 분석: 웹 저장소 기록으로 중간보고서 7절의 평가 계획을 계산한다.

- 주 지표: 참가자 가운데 가입 뒤 7일 안에 단원 이해 확인(퀴즈)을 하나 이상 통과한 비율(Wilson 95% 구간)
- 점검 항목: 진단의 과도한 면제(면제 단원 가운데 학습자가 '아직 모름'으로 되돌린 비율), 추천 이유 이해도(1~5),
  후보 부족(목록이 k개보다 짧은 비율), 추천 반응(목록에서 연 비율, 7일 안 통과 적중), 마무리 설문
- 기법 비교: 추천을 받은 시점의 학습자 상태를 다시 만들어 기법마다 Top-k를 계산하고, 그 뒤 7일 안에 통과한 단원을
  맞혔는지 본다(학습자 단위 부트스트랩 95% 구간). 학습자가 실제로 본 목록은 운영 정책이므로 노출 편향이 있다.
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime

import numpy as np

from .store import SURVEY_ITEMS

DAY = 86400.0
PASS_SOURCES = ("quiz", "self")           # 이해 확인 통과의 출처: 문항 정답, 문항 없는 단원의 스스로 확인(진단 인정은 제외)
PROFILE_KEYS = ("goal", "horizon", "risk", "exp")


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n == 0:
        return dict(k=0, n=0, rate=None, lo=None, hi=None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return dict(k=int(k), n=int(n), rate=p, lo=max(0.0, (c - h) / d), hi=min(1.0, (c + h) / d))


def likert(values) -> dict:
    v = [int(x) for x in values]
    if not v:
        return dict(n=0, mean=None, median=None, top2=wilson(0, 0), dist={})
    return dict(n=len(v), mean=float(np.mean(v)), median=float(np.median(v)), top2=wilson(sum(x >= 4 for x in v), len(v)),
                dist={i: v.count(i) for i in range(1, 6)})


def cluster_bootstrap(per_user: dict, boot: int = 1000, seed: int = 42) -> tuple:
    """per_user: {사용자: [값...]} → (전체 평균, 하한, 상한). 사용자를 복원 추출해 한 사람의 여러 목록이 한 묶음으로 움직인다."""
    users = [u for u, v in per_user.items() if v]
    if not users:
        return None, None, None
    allv = [x for u in users for x in per_user[u]]
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(boot):
        pick = rng.integers(0, len(users), len(users))
        vals = [x for i in pick for x in per_user[users[i]]]
        means.append(float(np.mean(vals)))
    return float(np.mean(allv)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def pilot_report(store, svc=None, window_days: int = 7, now: float = None, k: int = 5, boot: int = 1000, seed: int = 42) -> dict:
    """store(WebStore) 기록으로 파일럿 지표를 계산한다. svc(RecommendationService)를 주면 기법 비교도 한다."""
    from ..service import LearnerInput
    now = time.time() if now is None else float(now)
    W = window_days * DAY
    D = store.dump()
    D["events"] = [e for e in D["events"] if e["ts"] <= now]                    # 분석 기준 시각 뒤의 기록은 쓰지 않는다
    D["recs"] = [r for r in D["recs"] if r["ts"] <= now]
    D["feedback"] = [f for f in D["feedback"] if f["ts"] <= now]
    users = [u for u in D["users"] if not u["is_admin"] and _epoch(u["created_at"]) <= now]
    ids = [u["id"] for u in users]
    ref = {u["id"]: u["ref"] for u in users}
    start = {u["id"]: _epoch(u["created_at"]) for u in users}
    prof = {u["id"]: u["profile"] for u in users}
    ev, recs, fb = defaultdict(list), defaultdict(list), defaultdict(list)
    for e in D["events"]:
        ev[e["user_id"]].append(e)
    for r in D["recs"]:
        recs[r["user_id"]].append(r)
    for f in D["feedback"]:
        fb[f["user_id"]].append(f)

    def passes(uid, t0=None, t1=None, sources=PASS_SOURCES):
        return {e["item"] for e in ev[uid] if e["quiz_pass"] and e["source"] in sources
                and (t0 is None or e["ts"] > t0) and (t1 is None or e["ts"] <= t1)}

    def known_before(uid, t):
        return {e["item"] for e in ev[uid] if e["quiz_pass"] and e["ts"] < t}

    rec_views = defaultdict(set)
    for uid in ids:
        for f in fb[uid]:
            if f["kind"] == "view" and f["request_id"]:
                rec_views[f["request_id"]].add(f["item"])

    # 1. 참가와 이용 흐름
    complete = {uid for uid in ids if all(prof[uid].get(x) is not None for x in PROFILE_KEYS)}
    diagnosed = {uid for uid in ids if prof[uid].get("diagnosis")}
    got_recs = {uid for uid in ids if recs[uid]}
    opened = {uid for uid in ids if any(rec_views.get(r["request_id"]) for r in recs[uid])}
    quiz_pass = {uid for uid in ids if passes(uid, sources=("quiz",))}
    any_pass = {uid for uid in ids if passes(uid)}
    funnel = [("가입·동의", len(ids)), ("목적·성향 입력", len(complete)), ("진단 퀴즈", len(diagnosed)), ("추천 받음", len(got_recs)),
              ("추천 단원 열람", len(opened)), ("이해 확인 통과(문항)", len(quiz_pass)), ("이해 확인 통과(문항+스스로 확인)", len(any_pass))]

    # 2. 주 지표: 가입 뒤 7일 안 통과(7일 관측이 끝난 참가자만)
    eligible = [uid for uid in ids if now - start[uid] >= W]
    primary = wilson(sum(bool(passes(uid, start[uid], start[uid] + W, ("quiz",))) for uid in eligible), len(eligible))
    lenient = wilson(sum(bool(passes(uid, start[uid], start[uid] + W)) for uid in eligible), len(eligible))

    # 3. 진단 면제 점검
    review = {uid: [f for f in fb[uid] if f["kind"] == "diagnosis_review"][-1]["value"] for uid in ids
              if any(f["kind"] == "diagnosis_review" for f in fb[uid])}
    exempt_n = [len(review[uid]["exempted"]) if uid in review else sum(e["source"] == "diagnosis" for e in ev[uid]) for uid in diagnosed]
    ex_units = sum(len(v["exempted"]) for v in review.values())
    fl_units = sum(len(v["flagged"]) for v in review.values())
    diagnosis = dict(diagnosed=len(diagnosed), exempted_mean=float(np.mean(exempt_n)) if exempt_n else None,
                     exempted_median=float(np.median(exempt_n)) if exempt_n else None,
                     reviewed=wilson(len([u for u in review if u in diagnosed]), len(diagnosed)),
                     over_exemption=wilson(fl_units, ex_units),
                     users_flagging=wilson(sum(bool(v["flagged"]) for v in review.values()), len(review)))

    # 4. 추천 이유 이해도
    ratings = [f["value"] for uid in ids for f in fb[uid] if f["kind"] == "reason_rating"]
    surveys = {uid: [f for f in fb[uid] if f["kind"] == "exit_survey"][-1]["value"] for uid in ids
               if any(f["kind"] == "exit_survey" for f in fb[uid])}
    # 5. 후보 부족, 6. 추천 반응
    lists = [r for uid in ids for r in recs[uid]]
    shortfall = dict(lists=len(lists), short=wilson(sum(r["shortfall"] > 0 for r in lists), len(lists)),
                     mean_len=float(np.mean([len(r["items"]) for r in lists])) if lists else None,
                     users_short=wilson(sum(any(r["shortfall"] > 0 for r in recs[uid]) for uid in got_recs), len(got_recs)))
    observed = [r for r in lists if r["ts"] + W <= now]
    hit_lists = []
    for r in observed:
        target = passes(r["user_id"], r["ts"], r["ts"] + W) - known_before(r["user_id"], r["ts"])
        hit_lists.append(bool(set(r["items"]) & target))
    engagement = dict(list_ctr=wilson(sum(bool(rec_views.get(r["request_id"])) for r in lists), len(lists)),
                      item_ctr=wilson(sum(len(rec_views.get(r["request_id"], set()) & set(r["items"])) for r in lists),
                                      sum(len(r["items"]) for r in lists)),
                      hit_at_k=wilson(sum(hit_lists), len(hit_lists)), explored_lists=sum(r["explored_slot"] is not None for r in lists))

    # 7. 기법 비교: 사용자·날짜마다 첫 목록, 7일 관측이 끝난 목록만
    comparison, compare_note, bundle_info = [], None, None
    if svc is not None:
        cfg = getattr(svc.b, "config", None)
        man = svc.b.manifest() if callable(getattr(svc.b, "manifest", None)) else {}
        bundle_info = dict(n_learners=getattr(cfg, "n_learners", None), seed=getattr(cfg, "seed", None),
                           created_at=man.get("created_at"), policy=svc.operational_label)
    if svc is None:
        compare_note = "번들을 주지 않아 기법 비교를 건너뛰었다(--bundle 또는 --ops-dir)."
    else:
        labels = {m["key"]: m["label"] for m in svc.method_names()}
        picked, seen = [], set()
        for r in sorted(observed, key=lambda x: x["ts"]):
            key = (r["user_id"], datetime.fromtimestamp(r["ts"]).date())
            if key not in seen:
                seen.add(key); picked.append(r)
        hit, rec_, n_target = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list)), 0
        for r in picked:
            uid = r["user_id"]
            target = passes(uid, r["ts"], r["ts"] + W) - known_before(uid, r["ts"])
            if not target:
                continue
            n_target += 1
            out = svc.compare(LearnerInput(**store.learner_fields(uid, before=r["ts"])), k=k)
            tops = {m["key"]: [it["item"] for it in m["items"]] for m in out.get("methods", [])}
            tops["__shown__"] = r["items"]
            for m, top in tops.items():
                got = len(set(top) & target)
                hit[m][uid].append(float(got > 0)); rec_[m][uid].append(got / len(target))
        for m in hit:
            mean, lo, hi = cluster_bootstrap(hit[m], boot, seed)
            comparison.append(dict(method=m, label="실제로 보인 목록(운영 정책+탐색)" if m == "__shown__" else labels.get(m, m),
                                   lists=sum(len(v) for v in hit[m].values()), users=len(hit[m]), hit=mean, hit_lo=lo, hit_hi=hi,
                                   recall=cluster_bootstrap(rec_[m], boot, seed)[0]))
        comparison.sort(key=lambda x: (x["method"] != "__shown__", -(x["hit"] or 0)))
        compare_note = (f"사용자·날짜마다 첫 추천 목록 {len(picked)}개 가운데 그 뒤 7일 안에 새로 통과한 단원이 있는 {n_target}개로 비교했다."
                        if picked else "7일 관측이 끝난 추천 목록이 아직 없다.")

    return dict(generated_at=datetime.fromtimestamp(now).isoformat(timespec="seconds"), window_days=window_days, k=k,
                service_start=store.meta("service_start"), participants=len(ids), eligible_7d=len(eligible),
                funnel=funnel, primary=primary, lenient=lenient, diagnosis=diagnosis,
                reason_rating=likert(ratings), shortfall=shortfall, engagement=engagement,
                survey={key: likert([s["answers"][key] for s in surveys.values() if key in s["answers"]]) for key, _ in SURVEY_ITEMS},
                survey_n=len(surveys), comments=[dict(ref=ref[uid], days=s.get("days"), text=s["comment"])
                                                 for uid, s in surveys.items() if s.get("comment")],
                comparison=comparison, comparison_note=compare_note, bundle=bundle_info)


def _pct(w: dict) -> str:
    if not w or w.get("rate") is None:
        return "–"
    return f"{w['rate'] * 100:.1f}% ({w['k']}/{w['n']}, 95% CI {w['lo'] * 100:.1f}~{w['hi'] * 100:.1f}%)"


def _num(x, d=2) -> str:
    return "–" if x is None else f"{x:.{d}f}"


def report_markdown(rep: dict) -> str:
    survey_text = dict(SURVEY_ITEMS)
    L = [f"# 파일럿 결과 (자동 생성 {rep['generated_at']})", "",
         f"서비스 시작일 {rep['service_start']} · 참가자 {rep['participants']}명 · 7일 관측이 끝난 참가자 {rep['eligible_7d']}명 · 추천 목록 길이 k={rep['k']}", "",
         "## 1. 참가와 이용 흐름", "", "| 단계 | 사람 수 | 가입 대비 |", "| --- | --- | --- |"]
    n0 = rep["funnel"][0][1] or 1
    L += [f"| {name} | {n} | {n / n0 * 100:.0f}% |" for name, n in rep["funnel"]]
    L += ["", "## 2. 주 지표: 가입 뒤 7일 안 이해 확인 통과율", "",
          f"- 문항 정답 기준(보고서의 주 지표): {_pct(rep['primary'])}",
          f"- 스스로 확인 포함: {_pct(rep['lenient'])}", "",
          "## 3. 진단 면제 점검", "",
          f"- 진단한 참가자 {rep['diagnosis']['diagnosed']}명, 1인당 면제 단원 평균 {_num(rep['diagnosis']['exempted_mean'], 1)}개(중앙값 {_num(rep['diagnosis']['exempted_median'], 1)})",
          f"- 면제 확인에 응답한 비율: {_pct(rep['diagnosis']['reviewed'])}",
          f"- 과도한 면제(면제 단원 가운데 '아직 모름'으로 되돌린 비율): {_pct(rep['diagnosis']['over_exemption'])}",
          f"- 되돌린 단원이 하나 이상인 참가자: {_pct(rep['diagnosis']['users_flagging'])}", "",
          "## 4. 추천 이유 이해도", ""]
    rr = rep["reason_rating"]
    dist = ", ".join(f"{i}점 {rr['dist'].get(i, 0)}" for i in range(1, 6)) if rr["n"] else "–"
    L += [f"- 목록 평가 {rr['n']}건, 평균 {_num(rr['mean'])}점, 4점 이상 {_pct(rr['top2'])}",
          f"- 점수 분포(1~5): {dist}", "",
          "## 5. 후보 부족", "",
          f"- 추천 목록 {rep['shortfall']['lists']}개, 평균 길이 {_num(rep['shortfall']['mean_len'], 2)}",
          f"- k개보다 짧은 목록: {_pct(rep['shortfall']['short'])} · 짧은 목록을 한 번이라도 받은 참가자: {_pct(rep['shortfall']['users_short'])}", "",
          "## 6. 추천 반응", "",
          f"- 목록에서 단원을 하나 이상 연 비율: {_pct(rep['engagement']['list_ctr'])}",
          f"- 보인 단원 가운데 연 비율: {_pct(rep['engagement']['item_ctr'])}",
          f"- 보인 목록의 7일 안 통과 적중(Hit@{rep['k']}, 7일 관측이 끝난 목록): {_pct(rep['engagement']['hit_at_k'])}",
          f"- 마지막 칸을 탐색한 목록: {rep['engagement']['explored_lists']}개", "",
          f"## 7. 기법 비교(추천 시점 상태로 다시 계산, 7일 안 통과 적중)", "", rep["comparison_note"] or "", ""]
    if rep.get("bundle"):
        b = rep["bundle"]
        L += [f"비교에 쓴 번들: 모의 학습자 {b['n_learners']:,}명(seed {b['seed']}, 생성 {b['created_at']}), 운영 정책 {b['policy']}. "
              "서버가 실제로 쓴 번들과 같은지 확인한다.", ""]
    if rep["comparison"]:
        L += ["| 방법 | 목록 수 | 사람 수 | 적중률 [95% 구간] | 재현율 |", "| --- | --- | --- | --- | --- |"]
        L += [f"| {c['label']} | {c['lists']} | {c['users']} | {_num(c['hit'], 3)} [{_num(c['hit_lo'], 3)}, {_num(c['hit_hi'], 3)}] | {_num(c['recall'], 3)} |"
              for c in rep["comparison"]]
        L += ["", "구간은 참가자 단위 부트스트랩이다. 참가자가 실제로 본 목록은 운영 정책이므로 다른 기법의 단원은 덜 노출되었다(노출 편향). "
              "소규모 편의표본의 탐색적 결과로만 해석한다."]
    L += ["", f"## 8. 마무리 설문 (응답 {rep['survey_n']}명)", "", "| 문항 | 응답 | 평균 | 4점 이상 |", "| --- | --- | --- | --- |"]
    L += [f"| {survey_text.get(key, key)} | {v['n']} | {_num(v['mean'])} | {_pct(v['top2'])} |" for key, v in rep["survey"].items()]
    if rep["comments"]:
        L += ["", "자유 의견(참가자 번호는 가명 ref):", ""] + [f"- #{c['ref']} ({c['days']}일차): {c['text']}" for c in rep["comments"]]
    L += ["", "## 해석할 때 주의할 점", "",
          "- 참가자는 소규모 편의표본이다. 비율은 Wilson 95% 구간을 함께 본다.",
          "- 기법 비교는 추천 당시의 학습 기록과 현재 프로필로 다시 계산했다. 프로필을 바꾼 참가자는 당시와 다를 수 있다.",
          "- 스스로 확인은 문항이 없는 단원의 자기 보고라 주 지표에서 뺐다. 진단으로 인정한 단원은 통과 지표에 넣지 않는다.",
          "- 탈퇴한 참가자의 기록은 지워져 분석에 없다."]
    return "\n".join(L) + "\n"


def write_report(rep: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    paths = dict(markdown=os.path.join(out_dir, "pilot_report.md"), json=os.path.join(out_dir, "pilot_metrics.json"),
                 comparison=os.path.join(out_dir, "pilot_comparison.csv"))
    with open(paths["markdown"], "w", encoding="utf-8") as f:
        f.write(report_markdown(rep))
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
    with open(paths["comparison"], "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["method", "label", "lists", "users", "hit", "hit_lo", "hit_hi", "recall"])
        w.writeheader(); w.writerows(rep["comparison"])
    return paths
