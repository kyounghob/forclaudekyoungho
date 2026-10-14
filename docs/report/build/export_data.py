"""보고서 표에 쓸 데이터를 JSON으로 내보낸다(v2 번들·v1 번들·민감도·카탈로그·분류·퀴즈·출처·검증 사실)."""
import json, subprocess, sys
sys.path.insert(0, "/home/user/forclaudekyoungho")
import numpy as np
import pandas as pd
from etfrec.catalog import Catalog
from etfrec.config import GOALS, HORIZONS
from etfrec.quiz import QUESTIONS
from etfrec.roadmap import build_roadmap
from etfrec.sources.registry import SOURCES
from etfrec.taxonomy import ETF_TYPES, ROADMAP_TEMPLATES, COMMON_CORE, LEVERAGE_RULES, TAX_OTHER, TAX_KR_EQUITY, PENSION_OK
from etfrec.privacy import POLICY
from etfrec.nlparse import EXAMPLES
ROOT = "/home/user/forclaudekyoungho"
OUT = "/tmp/claude-0/-home-user-forclaudekyoungho/db6cf096-e4ef-53d5-afbe-466baac4ec50/scratchpad/report/report_data.json"
cat = Catalog.default()
m = json.load(open(f"{ROOT}/artifacts/bundle_v2/manifest.json", encoding="utf-8"))
res = pd.read_csv(f"{ROOT}/artifacts/bundle_v2/test_results.csv", encoding="utf-8-sig")
grp = pd.read_csv(f"{ROOT}/artifacts/bundle_v2/group_results.csv", encoding="utf-8-sig")
exp = pd.read_csv(f"{ROOT}/artifacts/bundle_v2/advanced_exposure.csv", encoding="utf-8-sig")
val = pd.read_csv(f"{ROOT}/artifacts/bundle_v2/validation_configurations.csv", encoding="utf-8-sig")
v1 = pd.read_csv(f"{ROOT}/artifacts/bundle_v1/test_results.csv", encoding="utf-8-sig")
v1m = json.load(open(f"{ROOT}/artifacts/bundle_v1/manifest.json", encoding="utf-8"))
sens = json.load(open(f"{ROOT}/docs/results/prereq_sensitivity.json", encoding="utf-8"))
roadmaps = {}
for g in GOALS:
    rm = build_roadmap(cat, g, 1, "mid", 1, np.zeros(cat.n_items, bool))
    roadmaps[g] = dict(label=rm["goal_label"], units_total=rm["units_total"], minutes_total=rm["minutes_total"],
                       stages={s["key"]: [u["title"] for u in s["units"]] for s in rm["stages"] if s["units"]},
                       types=[t["name"] for t in rm["stages"][-1]["types"]])
diffstat = subprocess.run(["git", "-C", ROOT, "diff", "--stat", "HEAD~0", "--"], capture_output=True, text=True).stdout
changed = subprocess.run(["git", "-C", ROOT, "log", "--since=6 hours ago", "--stat", "--format=%h %s"], capture_output=True, text=True).stdout
FACTS = [
    dict(key="etf_market", fact="2025년 말 국내 상장 ETF 1,058종목, 순자산총액 297조 2천억 원(전년 대비 71% 증가); 2025년 7월 1,000종목 돌파",
         sources=["https://www.sidae.com/article/2025123016143338248", "https://www.heraldk.com/article/2025072215004989760"]),
    dict(key="leverage_deposit", fact="레버리지·인버스 ETP 기본예탁금 1,000만원(2020년 도입)은 유지 중이며, 단일종목 레버리지·인버스는 2026년 8월부터 3,000만원·심화교육 1시간 추가(총 2시간), 거래 경험에 따른 완화 관행 금지; 해외 상장 레버리지 ETP는 2025년 12월 15일부터 사전교육 의무화·기본예탁금 적용",
         sources=["https://www.investchosun.com/site/data/html_dir/2026/07/16/2026071680181.html", "https://v.daum.net/v/20260716174927498", "https://biz.heraldcorp.com/article/10742195", "https://www.kbsec.com/go.able?linkcd=s060901010000&seq=10009222&idt=20251114"]),
    dict(key="kifin", fact="금융투자교육원 레버리지 ETP 사전교육 약 1시간·4,000원, 수료 후 증권사에 이수번호 등록; 단일종목 레버리지·인버스 사전교육은 2026년 신설(4,000원, 8월 평가 18문항으로 강화)",
         sources=["https://www.kifin.or.kr", "https://news.bizwatch.co.kr/article/market/2026/08/11/0022", "https://v.daum.net/v/20260724070258227"]),
    dict(key="isa", fact="ISA 비과세 한도 일반형 순이익 200만원·서민형/농어민형 400만원, 초과분 9.9% 분리과세, 연 2,000만원·총 1억원 납입, 의무가입 3년, 만기 60일 안에 연금계좌 전환 시 전환금액의 10%(최대 300만원) 추가 세액공제 한도",
         sources=["https://korea-rich.kr/isa-%EA%B3%84%EC%A2%8C-%EB%B9%84%EA%B3%BC%EC%84%B8-%ED%95%9C%EB%8F%84-%EC%96%BC%EB%A7%88-200%EB%A7%8C%EC%9B%90%C2%B7400%EB%A7%8C%EC%9B%90-%EC%A1%B0%EA%B1%B4-2026-%EC%B4%9D%EC%A0%95%EB%A6%AC/", "https://www.financecoffeechat.com/tax/isa-guide", "https://bileotools.com/blog/isa-account-2026-guide"]),
    dict(key="irp", fact="IRP(퇴직연금) 위험자산 총투자한도 70%(30% 이상 안전자산, 2015년 40%→70%), 연금저축펀드는 한도 없음; 세액공제 연금저축 600만원·IRP 합산 900만원; 연금 수령 시 연금소득세 3.3~5.5%",
         sources=["https://wikidocs.net/blog/@Insight_Lab/32343/", "https://wikidocs.net/blog/@Insight_Lab/20821/", "https://www.kbsec.com/go.able?linkcd=s080400070100"]),
    dict(key="tax_base_price", fact="국내 상장 해외·채권·원자재·파생형 ETF 매매차익은 보유기간과세: 실제 매매차익과 과표기준가 상승분 중 작은 금액에 15.4% 배당소득세; 해외 상장 ETF는 연 250만원 공제 후 22% 양도소득세(분리과세)",
         sources=["https://kbam.co.kr/insights/guide/etf-tax-guide-domestic-vs-other-types", "https://www.samsungfund.com/etf/insight/guide/view05.do", "https://v.daum.net/v/20251219152204458"]),
    dict(key="privacy_law", fact="개인정보보호법 과징금 상한: 전체 매출액 3%(2023년 9월 시행); 2026년 3월 개정으로 반복·중대 위반에 최대 10% 특례(9월 시행); 가명정보 처리 가이드라인 전면 개정 2026년 3월 31일(위험도 기반 판단 체계)",
         sources=["https://news.mtn.co.kr/news-detail/2026030915535171389", "https://newsseoul.co.kr/news/view/1065587420951193", "https://m.boannews.com/html/detail.html?idx=121977"]),
    dict(key="krx_openapi", fact="KRX Open API: openapi.krx.co.kr에서 인증키 발급·서비스별 이용 신청, 비상업적 이용·재배포 금지·출처 표기 조건; 정보데이터시스템 화면 데이터는 로그인·API 신청 체계로 전환. 이용약관의 크롤링 금지 조항 원문은 검색으로 확인하지 못함",
         sources=["https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp", "https://github.com/skkimjj/krx-openapi-examples", "https://i-whale.com/entry/KRX-%EC%8B%9C%EC%84%B8-%EB%8D%B0%EC%9D%B4%ED%84%B0-%EC%9D%B4%EC%A0%9C-%EB%A1%9C%EA%B7%B8%EC%9D%B8-API%EB%A5%BC-%EC%8B%A0%EC%B2%AD-%ED%95%B4%EC%95%BC-%EC%93%B8-%EC%88%98-%EC%9E%88%EB%84%A4%EC%9A%94-%E3%85%9C"]),
]
data = dict(
    manifest=dict(created_at=m["created_at"], configurations=m["configurations"], signal_count=m["signal_count"], qa=len(m["qa"]),
                  qa_passed=sum(q["passed"] for q in m["qa"]), dataset=m["dataset"], validation=m["validation"], test=m["test"],
                  selection=dict(operational=m["selection"]["operational"], operational_algorithm=m["selection"]["operational_algorithm"],
                                 validation_best=m["selection"]["validation_best_ndcg"], router_lambdas=m["selection"]["router_lambdas"],
                                 families=m["selection"]["families"]), router_tuning=m["router_tuning"], family_counts=m["family_counts"],
                  config=m["config"], privacy=m.get("privacy"), training=m["training"]),
    operational_name=next((a for a in [None]), None),
    results=res.to_dict("records"), group_results=grp.to_dict("records"), exposure=exp.to_dict("records"),
    validation_top=val.sort_values("ndcg", ascending=False).head(8)[["job_id", "family", "name", "ndcg", "diversity"]].to_dict("records"),
    v1_results=v1.to_dict("records"), v1_dataset=v1m["dataset"], sensitivity=sens,
    catalog=dict(n_items=cat.n_items, n_topics=cat.n_topics, groups=cat.group_names, topics=cat.topics,
                 n_prereq_edges=int(sum(len(v) for v in cat.prereqs.values())), topic_group=[int(x) for x in cat.topic_group],
                 items=[cat.item_info(i) for i in range(cat.n_items)], v1_items=Catalog.default(version=1).n_items),
    goals=GOALS, horizons=HORIZONS, common_core=COMMON_CORE, templates=ROADMAP_TEMPLATES, roadmaps=roadmaps,
    types=[{k: v for k, v in t.items()} for t in ETF_TYPES], questions=QUESTIONS, sources=[dict(key=k, **v) for k, v in SOURCES.items()],
    examples=EXAMPLES, policy=POLICY, strings=dict(leverage=LEVERAGE_RULES, tax_other=TAX_OTHER, tax_kr=TAX_KR_EQUITY, pension_ok=PENSION_OK),
    facts=FACTS, changes=changed[:6000],
)
# 운영 설정 이름, 쌍 비교(사용자 단위 쌍 부트스트랩), 학습 감사 요약
from etfrec.evaluation import bootstrap_ci
from etfrec.pipeline import Bundle
b = Bundle.load(f"{ROOT}/artifacts/bundle_v2")
data["operational_name"] = b.algos[b.selection["operational_algorithm"]].name
data["global_name"] = b.algos[b.selection["families"]["Global"]].name
data["family_best_names"] = {k: b.algos[v].name for k, v in b.selection["families"].items()}
active = None
pu = b.per_user
if "RULE" in pu:
    tr = b.test_audit
    data["test_audit"] = tr
PAIRS = [("MLP_NEXT", "MLP"), ("MLP_NEXT", "POP"), ("MLP_NEXT", "RULE"), ("MLP_NEXT", "Global"), ("MF_BPR", "MF"), ("MLP_BPR", "MLP"),
         ("MLP_BPRU", "MLP"), ("MLP_BPRU", "MLP_BPR"), ("MLP", "Random"), ("RouterNoGender", "Global")]
paired = []
for a, c in PAIRS:
    if a in pu and c in pu and len(pu[a]) == len(pu[c]):
        d = np.asarray(pu[a]) - np.asarray(pu[c]); lo, hi = bootstrap_ci(d, 500, 42)
        paired.append(dict(a=a, b=c, diff=float(d.mean()), ci_low=float(lo), ci_high=float(hi), n=int(len(d))))
data["paired"] = paired
b1 = Bundle.load(f"{ROOT}/artifacts/bundle_v1")
paired_v1 = []
for a, c in PAIRS:
    p1 = b1.per_user
    if a in p1 and c in p1 and len(p1[a]) == len(p1[c]):
        d = np.asarray(p1[a]) - np.asarray(p1[c]); lo, hi = bootstrap_ci(d, 500, 42)
        paired_v1.append(dict(a=a, b=c, diff=float(d.mean()), ci_low=float(lo), ci_high=float(hi), n=int(len(d))))
data["paired_v1"] = paired_v1
data["v1_test_audit"] = b1.test_audit
del b1
aud = {}
for x in b.models.audit:
    k = x["model"]; aud.setdefault(k, []).append({kk: x.get(kk) for kk in ("factors", "reg", "positive_rows", "pairs", "pairs_with_observed_negative",
                                                                          "training_rows", "positive", "zero", "loss_first", "loss_last", "users_with_pairs", "snapshot")})
data["training_audit"] = aud
# 집단별: 학습활동(click_tier) 순서가 기준에 따라 바뀌는지
g = grp[(grp.method == "RouterNoGender") & (grp.variable == "click_tier")].sort_values("group")
if "ndcg_active" in g.columns and len(g):
    data["click_tier"] = g[["group", "users", "ndcg", "ndcg_active", "active_share", "ci_low", "ci_high", "ci_low_active", "ci_high_active"]].to_dict("records")
# 다양성: 목록 길이별(가드레일 시 다양성이 오르는 이유가 짧은 목록인지 같은 주제 선수 사슬인지 확인)
from etfrec.evaluation import simple_diversity, candidate_items
from etfrec.config import GuardrailConfig
divlen = {}
for name in ["RouterNoGender", "RouterNoGender+prereq", "RULE", "POP"]:
    if name not in b.predictions:
        continue
    it = np.asarray(b.predictions[name]); n = (it >= 0).sum(1)
    div = np.array([simple_diversity([x for x in row if x >= 0], b.catalog.item_topic) for row in it])
    same = np.array([len(set(b.catalog.item_topic[[x for x in row if x >= 0]])) < k for row, k in zip(it, n)])
    divlen[name] = dict(mean=float(div.mean()), same_topic_rows=float(same.mean()), short=float(np.mean(n < 5)),
                        by_len={int(L): dict(share=float(np.mean(n == L)), div=float(div[n == L].mean()), same_topic_rows=float(same[n == L].mean()))
                                for L in range(2, 6) if (n == L).any()})
S = b.store; g_ = GuardrailConfig(prereq_block=True)
nc = np.array([len(candidate_items(S.und[u], S.level[u], b.catalog, g_)) for u in b.test_users])
shown = (np.asarray(b.predictions["RouterNoGender+prereq"]) >= 0).sum(1)
divlen["prereq_candidates_below_k"] = float(np.mean(nc < 5)); divlen["prereq_shown_below_k"] = float(np.mean(shown < 5))
data["diversity_by_len"] = divlen
data["n_root_units"] = int(sum(1 for i in range(cat.n_items) if not cat.prereqs.get(i)))
coll = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
import re as _re
mm = _re.search(r"(\d+) tests? collected", coll)
data["tests_collected"] = int(mm.group(1)) if mm else None
import os as _os
data["screens"] = len([f for f in _os.listdir(f"{ROOT}/docs/screens") if f.endswith(".png")])
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("exported", OUT, "| operational:", data["operational_name"], "| v2 rows", len(res), "| privacy:", (m.get("privacy") or {}).get("routing"))
