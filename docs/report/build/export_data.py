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
from etfrec.lessons import LESSONS, ASOF as LESSON_ASOF
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
    dict(key="leverage_deposit", fact="레버리지·인버스 ETP 기본예탁금 1,000만원(2020년 도입). 단일종목 레버리지·인버스는 2026년 7월 31일부터 현금 3,000만원(대용증권 불인정, 매도대금은 결제 후 인정, 신규·추가 매수 모두; 당초 8월 5일 예정에서 앞당김), 2026년 8월 19일부터 사전교육 총 3시간(기본 1 + 심화 2)과 신규 투자자 한국거래소 모의거래 5시간(5거래일 이상, 하루 1시간 이상). 해외 상장 레버리지 ETP는 사전교육 의무 2025년 12월 15일, 기본예탁금 1,000만원 2026년 5월 22일(기존 거래자 제외, 인버스 포함 여부·등급별 금액은 증권사마다 다름)",
         sources=["https://www.korea.kr/news/policyNewsView.do?newsId=148968739", "https://www.fntimes.com/html/view.php?ud=2026072409284082340f4390e77d_18", "https://biz.sbs.co.kr/article/20000325011", "https://www.hankyung.com/article/202608127524i", "https://www.mt.co.kr/stock/2026/08/12/2026081216322792259", "https://biz.heraldcorp.com/article/10742195", "https://securities.miraeasset.com/bbs/board/message/view.do?categoryId=66&messageId=2339923"]),
    dict(key="kifin", fact="금융투자교육원 레버리지 ETP 사전교육(일반 과정) 약 1시간·4,000원, 수료 후 증권사에 이수번호 등록. 단일종목 레버리지·인버스 심화교육은 2026년 5월 22일 1시간으로 시작해 8월 기준 2시간(총 3시간)",
         sources=["https://www.kifin.or.kr", "https://www.kbsec.com/go.able?linkcd=s060901010000&seq=10009835&idt=20260512", "https://www.hankyung.com/article/202608127524i"]),
    dict(key="isa", fact="ISA 비과세 한도 일반형 순이익 200만원·서민형/농어민형 400만원, 초과분 9.9% 분리과세, 연 2,000만원·총 1억원 납입, 의무가입 3년, 만기 60일 안에 연금계좌 전환 시 전환금액의 10%(최대 300만원) 추가 세액공제 한도",
         sources=["https://korea-rich.kr/isa-%EA%B3%84%EC%A2%8C-%EB%B9%84%EA%B3%BC%EC%84%B8-%ED%95%9C%EB%8F%84-%EC%96%BC%EB%A7%88-200%EB%A7%8C%EC%9B%90%C2%B7400%EB%A7%8C%EC%9B%90-%EC%A1%B0%EA%B1%B4-2026-%EC%B4%9D%EC%A0%95%EB%A6%AC/", "https://www.financecoffeechat.com/tax/isa-guide", "https://bileotools.com/blog/isa-account-2026-guide"]),
    dict(key="irp", fact="IRP(퇴직연금) 위험자산 총투자한도 70%(계좌 평가액 기준, 30% 이상 안전자산, 초과 시 위험자산 추가 매수 제한), 연금저축펀드는 한도 없음; 세액공제 연금저축 600만원·IRP 합산 900만원; 사적연금 연 1,500만원 이하 수령 시 연금소득세 3.3~5.5%, 초과 시 종합과세 또는 16.5% 분리과세 선택; 70% 한도 완화는 2026년 논의 중",
         sources=["https://wikidocs.net/blog/@Insight_Lab/32343/", "https://www.kbsec.com/go.able?linkcd=s080400070100", "https://investpension.miraeasset.com/m/contents/view.do?idx=20427", "https://kbam.co.kr/fund/pension/guide/pension-withdrawal-income-tax-guide-15-million-threshold", "https://kbthink.com/main/asset-management/pension-n-old-age/kb-goldenlife/kb-goldenlife-240112.html", "https://www.heraldk.com/article/2026062318205779499"]),
    dict(key="tax_base_price", fact="국내 상장 해외주식형·채권·원자재 ETF 매매차익은 보유기간과세: 실제 매매차익과 과표기준가 상승분 중 작은 금액에 15.4% 배당소득세; 국내 상장 레버리지·인버스는 상품 구성(장외 스와프 여부 등)에 따라 매매차익 과세 여부가 달라 상품별 과세유형 확인; 해외 거래소 상장 ETF는 연 250만원 기본공제 후 22% 양도소득세(손익통산, 분리과세)",
         sources=["https://kbam.co.kr/insights/guide/etf-tax-guide-domestic-vs-other-types", "https://www.samsungfund.com/etf/insight/guide/view05.do", "https://www.ajunews.com/view/20231109161338226", "https://v.daum.net/v/20251219152204458"]),
    dict(key="privacy_law", fact="개인정보보호법 과징금 일반 상한은 전체 매출액의 3%(2023년 9월 시행). 2026년 3월 10일 공포·9월 11일 시행된 개정으로 고의·중과실로 3년 안에 위반을 반복하거나 1천만 명 이상 피해를 내는 등 중대한 경우 최대 10%(위반과 무관한 매출 제외; 조문 번호는 원문 확인 전). 개인정보보호위원회 가명정보 처리 가이드라인은 2026년 3월 31일 위험도 기반 체계로 전면 개정",
         sources=["https://www.newsis.com/view/NISX20260309_0003540588", "https://shinkim.com/kor/media/newsletter/3167", "https://www.shinkim.com/kor/media/newsletter/pdf/3319", "https://newsseoul.co.kr/news/view/1065587420951193", "https://m.boannews.com/html/detail.html?idx=121977"]),
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
    lessons=[dict(topic=t, level=l, title=str(cat.item_title[cat.unit(t, l)]), asof=LESSON_ASOF, **v) for (t, l), v in LESSONS.items()],
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
         ("MLP_BPRU", "MLP"), ("MLP_BPRU", "MLP_BPR"), ("MLP", "Random"), ("RouterNoGender", "Global"), ("RouterNoGender", "POP"),
         ("RouterNoGender", "Random"), ("RouterNoGender+prereq", "POP"), ("MLP", "POP")]
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
per_file = {}
for line in coll.splitlines():
    if "::" in line:
        f_ = line.split("::")[0]; per_file[f_] = per_file.get(f_, 0) + 1
data["tests_per_file"] = per_file
# 개인정보 감사(새 형식): 측정값만 옮긴다
from etfrec.privacy import CHECK_NAMES, K_RELEASE, MIN_LEAF_DISPLAY, POLICY_IMPLEMENTED, POLICY_ORGANIZATIONAL, QUASI_IDENTIFIERS
P = m.get("privacy") or {}
Q = P.get("quasi") or {}
data["privacy_summary"] = dict(
    k=K_RELEASE, leaf_threshold=MIN_LEAF_DISPLAY, quasi_identifiers=list(QUASI_IDENTIFIERS),
    quasi={k: Q.get(k) for k in ("columns", "missing", "k", "rows", "groups", "min_group", "median_group", "groups_below_k", "users_below_k", "share_below_k", "satisfied")},
    generalization=[s_["drop"] for s_ in (P.get("generalization") or [])], generalization_status=P.get("generalization_status"),
    release=P.get("release"), stored=P.get("stored"),
    router_leaves={k: {kk: v.get(kk) for kk in ("variables", "threshold", "min_users_param", "lam", "leaves", "leaves_below", "users_in_small_leaves", "min_leaf", "users", "decision_min_n", "distinct_leaf_champions", "leaf_champion_is_root_share")}
                   for k, v in (P.get("router_leaves") or {}).items()},
    published=P.get("published"), policy_implemented=POLICY_IMPLEMENTED, policy_organizational=POLICY_ORGANIZATIONAL,
    users_table={k: (P.get("users_table") or {}).get(k) for k in ("columns", "quasi", "quasi_extended")} if P.get("users_table") else None,
    qa=[dict(test=q["test"], passed=q["passed"], details=q.get("details")) for q in m["qa"] if q["test"] in CHECK_NAMES],
    check_names=list(CHECK_NAMES))
lp = pd.read_csv(f"{ROOT}/artifacts/bundle_v2/learner_profiles.csv", encoding="utf-8-sig", nrows=3)
data["learner_profiles_columns"] = list(lp.columns)
# 라우터 잎 챔피언(개인정보 감사가 아니라 선택 결과 서술용): 번들의 학습된 라우터에서 직접 센다
data["router_champions"] = {name: dict(lam=float(rt.lam), leaves=int(len(rt.levels[-1]["champ"])),
                                       distinct_leaf_champions=int(len(np.unique(rt.levels[-1]["champ"]))),
                                       leaf_is_root_share=float(np.mean(np.asarray(rt.levels[-1]["champ"]) == rt.levels[0]["champ"][0])))
                            for name, rt in b.routers.items()}
data["bundle_log_columns"] = list(b.log.columns); data["bundle_profile_columns"] = list(b.profiles.columns)
data["store_has_raw"] = bool(hasattr(b.store, "age") or hasattr(b.store, "income"))
import os as _os
data["screens"] = len([f for f in _os.listdir(f"{ROOT}/docs/screens") if f.endswith(".png")])
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("exported", OUT, "| operational:", data["operational_name"], "| v2 rows", len(res), "| privacy quasi:", data["privacy_summary"]["quasi"].get("groups_below_k"),
      "| leaves:", {k: (v["leaves"], v["leaves_below"]) for k, v in data["privacy_summary"]["router_leaves"].items()}, "| privacy QA:", [(q["test"], q["passed"]) for q in data["privacy_summary"]["qa"]])

# ---- 비판 5.1·5.2 보완 내용(측정값을 넣어 문장으로) ----
PSM = data["privacy_summary"]; QQ = PSM["quasi"]; RL = PSM.get("release") or {}; LFN = PSM["router_leaves"].get("RouterNoGender", {})
PGR = (PSM.get("published") or {}).get("group_results") or {}
nsrc, npriv = per_file.get("tests/test_sources.py", 0), per_file.get("tests/test_privacy.py", 0)
pq_ok = sum(q["passed"] for q in PSM["qa"])
gen_ko = {"gender": "성별", "mobile": "기기", "exp": "경험", "risk": "성향", "horizon": "기간", "goal": "목적", "income_q": "소득분위", "age_band": "연령대"}
_lam_op = float(m["selection"]["router_lambdas"]["RouterNoGender"])
lam_txt = "∞" if _lam_op >= 1e8 else f"{_lam_op:g}"
data["fix9"] = [
    "화면용 비공식 엔드포인트(getJsonData.cmd) 호출 코드를 삭제했다(저장소 코드에서 호출 0건). 자동 수집은 KRX Open API(인증키 AUTH_KEY 헤더)와 공공데이터포털 API(serviceKey)만 쓴다.",
    "ETF 전종목 기본정보는 이용자가 정보데이터시스템 화면에서 직접 내려받은 파일을 `sources sync --krx-csv 파일 [--krx-csv-date YYYYMMDD]`로 정규화한다. CSV는 UTF-8·cp949를 모두 읽고, Excel은 openpyxl·xlrd가 설치된 경우에만 읽으며 없으면 원인을 적어 fail로 기록한다(‘Excel 지원’ 문구를 코드와 맞춤).",
    "Open API 정규화 결함을 고쳤다. ISU_CD는 ISIN 모양(KR로 시작하는 12자)일 때만 ISIN, 아니면 단축코드로 보고, 약명이 없으면 전체 이름에서 법정 꼬리를 떼어 이름으로 쓴다. 그래서 레버리지 ETF가 이름이 비어 시장대표형으로 분류되던 문제가 없어졌다. 추적배수 열이 있으면 파생형 판정에도 쓴다.",
    "호출 정책: 클라이언트마다 실행당 호출 상한(기본 30회)과 호출 간격(1초)을 지키고 보낸 요청 수를 기록한다. ‘일 한도 준수’ 문구는 지우고, 인증키별 호출 한도는 제공처 이용 조건으로 확인한다고 고쳤다. 키가 없으면 요청을 하나도 보내지 않는다.",
    "상태 기록: 0행 응답은 empty(휴장일·미공개 안내), 페이지 상한·빈 쪽으로 일부만 받으면 partial(멈춘 이유 기록), 호출 오류·형식 오류는 fail로 기록하고 기존 파일을 바꾸지 않는다. 기준일 기본값은 직전 평일이고, 공공데이터포털 시세는 totalCount까지 페이지를 넘겨 받는다.",
    "신선도: provenance.json에 파일별 자료 기준일과 저장 시각을 남기고, 이번 실행에서 다시 쓰지 않은 파일은 이전 기록을 유지한다. 옛 파일을 오늘 날짜로 표시하던 문제를 없앴고, 30일이 지나면 화면 라벨에 경고한다.",
    "최종 검토 반영(5절 표): 파일과 기록은 임시 파일에 다 쓴 뒤 교체한다(쓰다가 실패해도 기존 스냅샷 유지). 파일마다 내용 해시를 기록하고 파일을 바꾼 직후 기록도 저장해, 실행이 끊겨도 파일과 기록이 어긋나지 않고 다르면 ‘기록 불일치’를 표시한다. 다른 화면의 파일·바뀐 필드 이름은 형식 검사로 거른다. 인증키는 환경변수로만 받고 오류 문구에서 가리며, API 응답에는 로컬 경로·오류 원문을 넣지 않는다. 일부만 받음 표시를 다음 실행에도 유지하고, 날짜 인자를 검사하고, CLI와 서버의 스냅샷 폴더 규칙을 맞추고, 샘플 파일을 패키지에 넣었다.",
    "괴리율·거래량: 시세 스냅샷을 단축코드로 결합해 유형 카드에 괴리율 절댓값 중앙값과 거래량 중앙값을 시세 기준일과 함께 표시한다(‘괴리율 예시’ 문구를 실제 기능과 맞춤).",
    "이용 범위: 등록부·README·화면·중간보고서에 비상업 수업 프로젝트 범위와, 상용화하려면 공공데이터포털 이용허락 범위 확인이나 KRX와의 별도 데이터 이용 계약이 필요하다는 점을 적었다. 접근 점검은 출처 루트마다 HEAD 1회, User-Agent는 프로젝트 이름을 그대로 밝힌다.",
    f"검증: 가짜 응답으로 요청 헤더·주소·파싱·페이지 넘김·상태·호출 상한·시세 결합을 검사하는 테스트 {nsrc}건(tests/test_sources.py). 실제 호출은 개발 환경의 네트워크 제한으로 하지 못했고 키 발급 후 로컬에서 확인한다.",
]
data["change9"] = f"비공식 호출 코드 0줄. 공식 API 3종(KRX Open API 일별매매정보, 공공데이터포털 증권상품시세정보·KRX상장종목정보) + 사람이 내려받은 파일 정규화. 상태 7종·파일별 기준일·해시 기록, 원자적 교체·형식 검사·키 가림, 수집 테스트 {nsrc}건."
data["fix10"] = [
    "저장 최소화: 번들 프로필·특징 저장소·learner_profiles.csv에서 원시 연령·연소득을 없애고 연령대·소득분위 구간만 남겼다. 모델 입력은 원래 구간 코드라 결과가 같다(v1 14개 값 5자리 일치를 다시 확인했고, 변경 전후 v1 결과 파일이 시간 열을 빼고 동일). 번들 로그는 주차·4개 시간대·주 안 순서(seq)만 남기고 일·분을 버린다.",
    "API·화면: /api/learners와 학습자 상세는 구간 코드·이름만 반환한다. 기존 학습자를 새 학습자로 복사하면 입력란에 구간 대표값을 채우고 원값이 아니라고 표시한다. 저장 설계는 쓰기 전에 원값을 구간 코드로 바꾸고 자유 입력의 연령·소득 표현(예: 45세, 연봉 5,000만원)을 구간 이름으로 가린다.",
    f"감사 대상 정정: 저장된 준식별자 {len(PSM['quasi_identifiers'])}개 조합 전체를 k={PSM['k']}로 감사한다(현재 번들: {QQ.get('groups', 0):,}개 셀 중 k 미만 {QQ.get('groups_below_k', 0):,}개, {QQ.get('users_below_k', 0):,}명 = {100 * (QQ.get('share_below_k') or 0):.1f}%). 2차본 초안의 ‘라우팅 k=20 충족’ 대신 실제 라우터 잎 크기를 잰다(운영 라우터 잎 {LFN.get('leaves')}개 중 20명 미만 {LFN.get('leaves_below')}개, 최소 {LFN.get('min_leaf')}명, λ={lam_txt}). 추천 경로 출력은 20명 미만 노드의 정확한 n과 원시 평균을 숨긴다.",
    f"반출 k-익명화: export-deid는 일반화 계층을 한 단계씩 적용하고 남은 작은 셀을 국소 억제해 모든 셀이 5명 이상일 때만 파일을 쓴다(현재 번들: 일반화 {len(RL.get('generalized', []))}단계, 억제 {RL.get('suppressed_rows', 0)}행, 삭제 {RL.get('removed_rows', 0)}행 → {RL.get('rows_out', 0):,}/{RL.get('rows_in', 0):,}행, 최소 셀 {RL.get('final_min_group')}명). 가명 번호·관심 주제·진단 수준은 내보내지 않는다.",
    f"공개 집단표: group_results·advanced_exposure에서 5명 미만 집단을 빼고 활성 5명 미만이면 활성 기준 값을 비운다(현재 번들은 해당 행 {PGR.get('rows_removed', 0)}건, 최소 셀 {PGR.get('min_users')}명).",
    f"QA: 개인정보 검사 {len(PSM['qa'])}건(원값·일분 비저장, 공개 셀 ≥ 5, 감사 열 누락 없음)을 번들 저장 전에 실행하고, 하나라도 실패하면 학습을 멈춘다(현재 {pq_ok}/{len(PSM['qa'])} 통과).",
    "가명처리 도구: `pseudonymize` 명령이 운영 원본의 외부 회원 ID를 HMAC-SHA256 가명과 연속 번호로 바꾼다. 키는 환경변수에서만 읽고(16자 미만이면 거부), 매핑표는 학습 입력 폴더 밖에만 쓰며, 로그의 일·분을 지운다.",
    "정책 구분: manifest의 privacy.policy를 ‘코드로 강제되는 항목’(강제하는 코드·검사 이름 포함)과 ‘조직 정책’(권한·망 분리, 역할 분리, 반출 심사, 접근 기록 감사, 외부 결합 통제, 보관·삭제, 재식별 금지)으로 나눴다. 현재는 모의 데이터라 실제 개인정보를 처리하지 않는다는 점과, 서비스 제공(이용자 동의·계약 근거)과 가명정보 특례(통계 작성·과학적 연구·공익적 기록 보존 목적의 재이용)의 구분을 중간보고서 4.5절에 적었다.",
    "최종 검토 반영(5절 표): 학습 입력의 스키마 밖 열(외부 회원 ID·분 단위 시각·IP 등)을 읽을 때 버리고 번들 로그는 허용 열만 남긴다(QA 확인). 반출 표는 반출 값으로 정렬해 원래 학습자 순서를 지운다. API로 고를 수 있는 기법은 화면의 기법 목록뿐이고(임의 설정 번호는 개발 모드), 학습자 조회 API는 로컬 실행에서만 기본으로 켠다. 경로 출력은 크기 구간만 보이고 원시 평균을 내보내지 않으며, 공개 집단표는 보완 억제를 한다. 저장 설계 가림을 설계 이름·모든 문자열·여러 표기·이벤트 시각으로 넓혔고, 매핑표 경로는 실제 경로로 비교한다.",
    f"검증: 개인정보 테스트 {npriv}건(tests/test_privacy.py)과 번들 전체 탐색(원시 연령·연소득 배열과 일·분 열이 어디에도 없음).",
]
data["change10"] = f"원시 연령·연소득·일·분과 스키마 밖 열 비저장, 저장 준식별자 {len(PSM['quasi_identifiers'])}개 k=5 감사(서빙 학습자 표 확장 조합 포함), 라우터 잎 실측·경로 출력 크기 구간, export-deid(최소 셀 {RL.get('final_min_group')}명, 행 순서 제거), 공개 집단표 5명 미만 제외·보완 억제, 학습자 조회 API 로컬 한정·임의 설정 번호 차단, 개인정보 QA {len(PSM['qa'])}건, 가명처리 도구, 정책 구분."
data["priv_after"] = data["change10"]
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("fix9/fix10 exported")

# ---- 페르소나(표 3): 페르소나마다 자기 설정(목적·성향·기간)과 진단 답안으로 로드맵을 계산한다 ----
from etfrec.quiz import score_quiz
from etfrec.taxonomy import learn_only_types
L1_ALL = {q["id"] for q in QUESTIONS if q["level"] == 1}
PERSONAS = dict(
    A=dict(goal="pension", risk=0, horizon="long", correct={"q01", "q02", "q04", "q07", "q15", "q17", "q08"},
           desc="기초 문항 위주 정답(수준1 6/9, 수준2 1/6, 수준3 0/5)"),
    B=dict(goal="income", risk=1, horizon="mid", correct=L1_ALL | {"q03", "q10", "q11", "q14"},
           desc="수준1 전부, 수준2 절반(괴리율·스프레드·채권 금리) 정답"),
    C=dict(goal="trading", risk=2, horizon="short", correct={"q01", "q02", "q07", "q15", "q10", "q20"},
           desc="레버리지 복리 문항(q05) 오답, 수준1 4/9"),
)
personas = {}
for key, P in PERSONAS.items():
    ans = {q["id"]: (q["answer"] if q["id"] in P["correct"] else (q["answer"] + 1) % 4) for q in QUESTIONS}
    r = score_quiz(ans, cat)
    passed = np.zeros(cat.n_items, bool)
    for e in r["events"]:
        passed[e["item"]] = True
    rm = build_roadmap(cat, P["goal"], P["risk"], P["horizon"], r["level"], passed,
                       dict(level=r["level"], correct=r["correct"], answered=r["answered"], total=r["total"]))
    st = {s["key"]: s for s in rm["stages"]}
    lev2 = cat.unit("레버리지·인버스", 2)
    personas[key] = dict(goal=P["goal"], goal_label=rm["goal_label"], risk=P["risk"], horizon=P["horizon"], horizon_label=rm["horizon_label"],
                         quiz_desc=P["desc"], level=r["level"], correct=r["correct"], answered=r["answered"], by_level=r["by_level"],
                         mastered=[m["title"] for m in r["mastered"]], units_total=rm["units_total"], units_passed=rm["units_passed"],
                         minutes_total=rm["minutes_total"], minutes_left=rm["minutes_left"],
                         next_unit=(rm["next_unit"] or {}).get("title"), current_stage=rm["current_stage"],
                         stage_counts={k: len(st[k]["units"]) for k in ("core", "goal", "advanced") if k in st},
                         stage_titles={k: [u["title"] for u in st[k]["units"]] for k in ("core", "goal", "advanced") if k in st},
                         types=[t["name"] for t in st["connect"]["types"]], learn_only=[TYPE_BY_KEY[k]["name"] for k in learn_only_types(P["goal"], P["risk"])],
                         lev2_in_core=bool(any(u["item"] == lev2 for u in st["core"]["units"])),
                         lev2_status=next((u["status"] for u in st["core"]["units"] if u["item"] == lev2), None),
                         isa_cautions=sum(1 for s in rm["stages"] for u in s["units"] if u.get("caution")),
                         short_liquidity_added=bool(P["horizon"] == "short" and cat.unit("유동성", 2) in [u["item"] for u in st["advanced"]["units"]]))
data["personas"] = personas

# ---- 신경망 비교의 사용자군 분해(표 18): 모든 신경망이 학습한 사용자 / 기록은 있지만 쌍이 없는 사용자 / 기록 없음 ----
def nn_groups(bundle, pairs_list):
    obs = bundle.models.observed
    snap = bundle.reference.snapshot_key
    seen = {k: w.user_seen for (s, k), w in obs.items() if s == snap}
    tu = np.asarray(bundle.test_users)
    if not all(k in seen for k in ("mlp9", "mlp9_bpr", "mlp9_bpru", "mlp9_next")):
        return None
    common = seen["mlp9"][tu] & seen["mlp9_bpr"][tu] & seen["mlp9_bpru"][tu] & seen["mlp9_next"][tu]
    hist_only = seen["mlp9"][tu] & ~common
    none = ~seen["mlp9"][tu]
    out = dict(users=int(len(tu)), common=int(common.sum()), history_no_pairs=int(hist_only.sum()), no_history=int(none.sum()), pairs={})
    pu = bundle.per_user
    for a, c in pairs_list:
        if a in pu and c in pu:
            d = np.asarray(pu[a]) - np.asarray(pu[c])
            row = {}
            for nm, m in (("all", np.ones(len(d), bool)), ("common", common), ("history_no_pairs", hist_only), ("no_history", none)):
                if m.sum() > 1:
                    lo, hi = bootstrap_ci(d[m], 500, 42)
                    row[nm] = dict(diff=float(d[m].mean()), ci_low=float(lo), ci_high=float(hi), n=int(m.sum()))
            out["pairs"][f"{a}-{c}"] = row
    return out


NN_PAIRS = [("MF_BPR", "MF"), ("MLP_BPR", "MLP"), ("MLP_BPRU", "MLP_BPR"), ("MLP_BPRU", "MLP"), ("MLP_NEXT", "MLP"), ("MLP", "Random")]
data["nn_groups"] = nn_groups(b, NN_PAIRS)
b1 = Bundle.load(f"{ROOT}/artifacts/bundle_v1")
data["nn_groups_v1"] = nn_groups(b1, NN_PAIRS)
del b1
# 쌍별 MLP의 쌍 구성(관측 음성 비율)·쌍 사용자 수: 테스트 스냅샷 기준
aud_t = [x for x in b.models.audit if x.get("snapshot") == b.reference.snapshot_key]
data["pair_audit"] = {x["model"]: {k: x.get(k) for k in ("pairs", "pairs_with_observed_negative", "pair_users", "users_with_pairs", "training_rows")}
                      for x in aud_t if x["model"] in ("mlp9_bpr", "mlp9_bpru", "mlp9_next")}
# QA 항목 분류(표 13): 이름 접두어로 센다
qa_names = [q["test"] for q in m["qa"]]
def _qcat(n):
    for pre, lab in (("metric_", "지표 함수 일치"), ("unique_items_", "가드레일·중복"), ("level_guard_", "가드레일·중복"), ("plus_one_limit_", "가드레일·중복"),
                     ("no_passed_unit_recommended_", "가드레일·중복"), ("topk_", "Top-K 형식"), ("event_logic_", "이벤트 논리"),
                     ("ndcg_active", "활성 지표 항등식·순위"), ("active_", "활성 지표 항등식·순위"), ("no_future_leakage", "누수 검사"),
                     ("bundle_", "개인정보"), ("feature_store_no_raw", "개인정보"), ("published_group", "개인정보"), ("privacy_audit", "개인정보")):
        if n.startswith(pre):
            return lab
    if any(k in n.lower() for k in ("mlp", "mf_", "mf_bpr", "observed_models", "pairwise", "neural")):
        return "신경망 학습 확인"
    return "기타 데이터·선택 검사"
from collections import Counter as _C
data["qa_categories"] = dict(_C(_qcat(n) for n in qa_names))
data["qa_leakage"] = next((dict(test=q["test"], passed=q["passed"], details=q.get("details")) for q in m["qa"] if q["test"] == "no_future_leakage_feature_store"), None)
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("personas/nn_groups/qa_categories exported", {k: (v["level"], v["units_total"], v["next_unit"]) for k, v in personas.items()})
