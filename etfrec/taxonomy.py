"""투자 목적 · ETF 유형 · 로드맵 템플릿.

이 파일은 "진단 → 기초 개념 → 적합한 ETF 유형" 로드맵의 도메인 지식을 한곳에 모은다.
세율·규제는 2026년 10월 13일 기준 보도·기관 안내를 검색으로 확인한 일반 안내다(법령·공지 원문 대조 전). 거래 전 증권사·국세청·
금융투자교육원·한국거래소 안내로 확인해야 하며, 제도가 바뀌면 이 파일의 문구만 고치면 된다.
검색으로 확인한 항목: 레버리지·인버스 ETP 사전교육(약 1시간, 4,000원, 증권사 이수번호 등록)과 기본예탁금 1,000만원(2020년 도입),
단일종목 레버리지·인버스의 현금 3,000만원(대용증권 불인정, 신규·추가 매수, 2026-07-31 시행)·사전교육 총 3시간·신규 투자자 모의거래 5시간
(2026-08-19 시행), 해외 상장 레버리지 ETP 사전교육(2025-12-15)·기본예탁금 1,000만원(2026-05-22), ISA 비과세 한도(일반형 순이익 200만원·
서민형 400만원, 초과분 9.9% 분리과세, 연 2,000만원·총 1억원 납입, 의무가입 3년, 만기 60일 안에 연금계좌 전환 시 전환금액의 10%·최대 300만원
추가 세액공제), IRP 위험자산 총투자한도 70%(계좌 평가액 기준, 초과 시 위험자산 추가 매수 제한), 연금저축 600만원·IRP 합산 900만원 세액공제,
연금소득세 3.3~5.5%(사적연금 연 1,500만원 이하; 초과 시 종합과세 또는 16.5% 분리과세 선택), 국내 상장 해외주식형·채권·원자재 ETF 매매차익의
보유기간과세(실제 차익과 과표기준가 상승분 중 작은 금액에 15.4%), 해외 거래소 상장 ETF의 양도소득세 22%(연 250만원 기본공제, 손익통산,
분리과세). 국내 상장 레버리지·인버스의 매매차익 과세 여부는 상품 구성에 따라 달라 상품별 과세유형 확인으로 안내한다.
여기의 어떤 항목도 특정 상품의 매수·매도 권유가 아니다.
"""
from __future__ import annotations

from .config import GOALS, HORIZONS

# 투자 목적 → 주제 친화도(0~1). 규칙 신호 r:goal 과 생성기 버전 2의 선호 기울기에 쓴다.
GOAL_TOPIC_AFFINITY = {
    "pension": {"연금계좌 ETF": 1.0, "자산배분": 0.9, "절세 계좌": 0.8, "비용": 0.8, "해외 ETF": 0.7, "환헤지": 0.6, "리밸런싱": 0.6, "채권 ETF": 0.6,
                "지수": 0.5, "ETF 구조": 0.5, "분배금": 0.4},
    "income": {"분배금": 1.0, "커버드콜 ETF": 1.0, "리츠 ETF": 0.8, "채권 ETF": 0.7, "절세 계좌": 0.5, "비용": 0.5, "ETF 구조": 0.4, "해외 ETF": 0.4, "금 ETF": 0.2},
    "long_term": {"지수": 1.0, "비용": 0.9, "해외 ETF": 0.8, "리밸런싱": 0.7, "자산배분": 0.7, "추적오차": 0.6, "절세 계좌": 0.6, "ETF 구조": 0.5,
                  "환헤지": 0.4, "연금계좌 ETF": 0.4},
    "trading": {"유동성": 1.0, "레버리지·인버스": 1.0, "지수": 0.7, "테마 ETF": 0.7, "섹터 ETF": 0.6, "원자재 ETF": 0.5, "ETF 구조": 0.5, "비용": 0.4},
    "diversify": {"자산배분": 1.0, "채권 ETF": 0.9, "금 ETF": 0.8, "리밸런싱": 0.7, "환헤지": 0.6, "해외 ETF": 0.5, "ETF 구조": 0.4, "원자재 ETF": 0.4, "절세 계좌": 0.3},
}

# 모든 목적에 공통인 필수 기초: 총보수(비용 1), 괴리율(ETF 구조 2), 환헤지 여부(환헤지 1), 파생형 위험 인지(레버리지·인버스 1), 유동성
COMMON_CORE = [("ETF 구조", 1), ("비용", 1), ("ETF 구조", 2), ("유동성", 1), ("환헤지", 1), ("레버리지·인버스", 1)]

ROADMAP_TEMPLATES = {
    "pension": dict(
        core=[("연금계좌 ETF", 1), ("연금계좌 ETF", 2), ("절세 계좌", 1), ("절세 계좌", 2), ("자산배분", 1), ("자산배분", 2), ("해외 ETF", 1), ("환헤지", 2),
              ("리밸런싱", 1), ("채권 ETF", 1)],
        advanced=[("연금계좌 ETF", 3), ("절세 계좌", 3), ("자산배분", 3), ("리밸런싱", 2), ("채권 ETF", 2), ("환헤지", 3)],
        types=["global_equity", "bond", "allocation", "kr_broad"]),
    "income": dict(
        core=[("분배금", 1), ("분배금", 2), ("커버드콜 ETF", 1), ("커버드콜 ETF", 2), ("리츠 ETF", 1), ("채권 ETF", 1), ("절세 계좌", 1)],
        advanced=[("분배금", 3), ("커버드콜 ETF", 3), ("리츠 ETF", 2), ("채권 ETF", 2), ("해외 ETF", 3), ("절세 계좌", 2)],
        types=["income", "reit_infra", "bond", "kr_broad"]),
    "long_term": dict(
        core=[("지수", 1), ("지수", 2), ("비용", 2), ("해외 ETF", 1), ("추적오차", 1), ("리밸런싱", 1), ("자산배분", 1), ("절세 계좌", 1)],
        advanced=[("비용", 3), ("추적오차", 2), ("해외 ETF", 2), ("해외 ETF", 3), ("리밸런싱", 2), ("자산배분", 2), ("연금계좌 ETF", 1)],
        types=["kr_broad", "global_equity", "allocation", "bond"]),
    "trading": dict(
        core=[("유동성", 1), ("유동성", 2), ("레버리지·인버스", 2), ("지수", 1), ("테마 ETF", 1), ("섹터 ETF", 1)],
        advanced=[("레버리지·인버스", 3), ("유동성", 3), ("테마 ETF", 3), ("원자재 ETF", 2), ("원자재 ETF", 3), ("해외 ETF", 3)],
        types=["leverage_inverse", "kr_sector_theme", "commodity_fx", "kr_broad"]),
    "diversify": dict(
        core=[("자산배분", 1), ("자산배분", 2), ("채권 ETF", 1), ("금 ETF", 1), ("리밸런싱", 1), ("해외 ETF", 1)],
        advanced=[("자산배분", 3), ("채권 ETF", 2), ("금 ETF", 2), ("환헤지", 2), ("리밸런싱", 2), ("원자재 ETF", 1), ("절세 계좌", 1)],
        types=["allocation", "bond", "commodity_fx", "global_equity"]),
}

TAX_KR_EQUITY = ("매매차익 비과세, 분배금 배당소득세 15.4%. 매매차익이 이미 비과세라 ISA의 효과는 분배금에 한정된다"
                 "(ISA 안에서는 순이익 200만원·서민형 400만원까지 비과세, 초과분 9.9% 분리과세)")
TAX_OTHER = ("매매차익·분배금 배당소득세 15.4%(보유기간과세: 매매차익은 '실제 차익'과 '과표기준가 상승분' 중 작은 금액에 과세하므로, "
             "실제 이익이 있어도 과표기준가가 내렸으면 과세되지 않고, 계좌 밖에서는 손실을 다른 이익과 통산하지 않는다), "
             "연 금융소득 2,000만원 초과 시 종합과세. ISA(비과세·9.9% 분리과세)·연금계좌(과세이연) 편입으로 완화 가능")
PENSION_OK = ("연금저축·IRP 편입 가능(국내 상장). IRP는 위험자산 총투자한도 70%(계좌 평가액 기준, 30% 이상은 예금·안전자산; "
              "한도를 넘으면 위험자산 추가 매수가 제한되어 주문이 들어가지 않는다; 적격 TDF 등 예외는 금융사 확인), 연금저축펀드는 한도 없음. "
              "과세이연 후 연금 수령 시 연금소득세 3.3~5.5%(사적연금 연 1,500만원 이하, 초과 시 종합과세 또는 16.5% 분리과세 선택). "
              "세액공제: 연금저축 600만원·IRP 합산 900만원")
PENSION_NO = "연금저축·IRP 편입 불가(ISA 편입 가능 여부는 금융사 안내 확인)"
LEVERAGE_RULES = ("(2026-10-13 기준) ① 금융투자교육원 레버리지 ETP 사전교육(약 1시간, 4,000원) 이수 후 증권사에 이수번호 등록. "
                  "② 기본예탁금 1,000만원 이상(2020년 도입; 투자자 등급별 금액과 추가 매수 적용 방식은 증권사 기준 확인). "
                  "③ 단일종목 레버리지·인버스: 현금 3,000만원 이상(대용증권 불인정, 매도대금은 결제 후 인정, 신규·추가 매수 모두, 2026-07-31 시행), 사전교육 총 3시간"
                  "(기본 1시간 + 심화 2시간), 신규 투자자는 한국거래소 모의거래 5시간(5거래일 이상, 2026-08-19 시행). "
                  "④ 해외 상장 레버리지 ETP: 사전교육(2025-12-15)과 기본예탁금 1,000만원(2026-05-22, 기존 거래자 제외, 인버스 포함 여부·등급별 금액은 증권사마다 다름). "
                  "요건을 채우지 못하면 매수 주문이 들어가지 않는다.")

ETF_TYPES = [
    dict(key="kr_broad", name="국내 시장대표 주식형", risk=3,
         description="코스피200·KRX300·코스닥150처럼 시장 전체를 따르는 ETF. 총보수가 가장 낮은 편이고 비교가 쉽다.",
         concepts=[("ETF 구조", 1), ("지수", 1), ("비용", 1), ("추적오차", 1)],
         goals=["long_term", "diversify", "pension"], tax=TAX_KR_EQUITY, pension=PENSION_OK, regulation="",
         cautions=["시장 전체가 하락하면 같이 하락한다", "같은 지수라도 총보수·괴리율·거래량이 다르다"],
         krx=dict(keywords=["200", "KRX300", "코스닥150", "코스피", "KOSPI", "TOP10", "TOP 10", "MSCI Korea"], asset=["주식"], market=["국내"])),
    dict(key="kr_sector_theme", name="국내 섹터·테마 주식형", risk=4,
         description="반도체·2차전지·AI·바이오처럼 특정 업종이나 테마에 집중하는 ETF. 구성 종목이 적고 집중 위험이 크다.",
         concepts=[("섹터 ETF", 1), ("테마 ETF", 1), ("테마 ETF", 3), ("유동성", 2)],
         goals=["trading"], tax=TAX_KR_EQUITY, pension=PENSION_OK, regulation="",
         cautions=["테마 열기가 식으면 거래량·괴리율이 나빠질 수 있다", "구성 종목 상위 몇 개가 수익을 좌우한다"],
         krx=dict(keywords=["반도체", "2차전지", "이차전지", "AI", "인공지능", "바이오", "로봇", "자동차", "은행", "증권", "건설", "게임", "엔터",
                            "조선", "방산", "우주", "원자력", "수소", "테마", "섹터", "소프트웨어", "헬스케어", "K-"], asset=["주식"], market=["국내"])),
    dict(key="global_equity", name="해외 주식형(국내 상장)", risk=3,
         description="미국 S&P500·나스닥100, 선진·신흥시장 지수를 국내 거래소에서 사는 ETF. 환헤지(H) 변형과 환노출형이 있다.",
         concepts=[("해외 ETF", 1), ("환헤지", 1), ("환헤지", 2), ("해외 ETF", 3)],
         goals=["long_term", "pension", "diversify"], tax=TAX_OTHER, pension=PENSION_OK, regulation="",
         cautions=["환율 변동이 수익률에 더해진다(환노출형)", "해외 거래소에 직접 상장된 ETF는 과세 체계가 다르다: 양도소득세 22%(연 250만원 기본공제, 같은 해 해외주식 손익 통산, 분리과세)"],
         krx=dict(keywords=["미국", "S&P", "나스닥", "NASDAQ", "선진", "신흥", "글로벌", "차이나", "중국", "일본", "인도", "유럽", "베트남", "다우", "러셀", "MSCI"],
                  asset=["주식"], market=["해외"])),
    dict(key="bond", name="채권형", risk=2,
         description="국채·회사채·단기채·만기매칭형. 금리가 오르면 가격이 내리며, 듀레이션이 길수록 민감하다.",
         concepts=[("채권 ETF", 1), ("채권 ETF", 2), ("채권 ETF", 3), ("분배금", 1)],
         goals=["pension", "diversify", "income"], tax=TAX_OTHER, pension=PENSION_OK + ". 일부 국공채·단기채권형은 IRP 안전자산(30% 몫)으로 분류될 수 있다(금융사 기준)", regulation="",
         cautions=["금리 상승기에는 손실이 날 수 있다", "회사채형은 신용 위험이 있다"],
         krx=dict(keywords=["채권", "국채", "국고채", "회사채", "단기채", "머니마켓", "MMF", "KOFR", "CD금리", "금리", "만기", "크레딧", "하이일드", "TIPS"],
                  asset=["채권"], market=[])),
    dict(key="commodity_fx", name="원자재·통화", risk=4,
         description="금·원유·구리 등 원자재와 달러·엔 통화 ETF. 선물 기반이면 롤오버 비용(콘탱고)이 생긴다.",
         concepts=[("원자재 ETF", 1), ("원자재 ETF", 2), ("원자재 ETF", 3), ("금 ETF", 1)],
         goals=["diversify", "trading"], tax=TAX_OTHER, pension="연금저축은 상품별로 가능, 퇴직연금(IRP)은 선물형 제한 — 금융사 확인",
         regulation="", cautions=["선물형은 현물 가격과 장기 수익률이 다를 수 있다", "통화 ETF는 환율 방향에 베팅하는 상품이다"],
         krx=dict(keywords=["금", "골드", "원유", "WTI", "구리", "은선물", "농산물", "달러", "엔선물", "통화", "원자재", "천연가스", "팔라듐"],
                  asset=["원자재", "통화"], market=[])),
    dict(key="reit_infra", name="리츠·인프라", risk=3,
         description="상장 리츠와 인프라 자산에 투자해 임대료·배당을 분배하는 ETF. 금리에 민감하다.",
         concepts=[("리츠 ETF", 1), ("리츠 ETF", 2), ("분배금", 1)],
         goals=["income", "diversify"], tax=TAX_OTHER, pension=PENSION_OK, regulation="",
         cautions=["금리 상승기에 가격이 약해진다", "분배금이 보장된 것은 아니다"],
         krx=dict(keywords=["리츠", "REIT", "인프라", "부동산"], asset=["부동산"], market=[])),
    dict(key="income", name="배당·커버드콜(인컴)", risk=3,
         description="고배당주나 커버드콜 전략으로 월·분기 분배금을 노리는 ETF. 커버드콜은 상승이 제한되고 분배금은 옵션 프리미엄에서 나온다.",
         concepts=[("분배금", 1), ("분배금", 3), ("커버드콜 ETF", 1), ("커버드콜 ETF", 2), ("커버드콜 ETF", 3)],
         goals=["income"], tax="분배금 배당소득세 15.4%, 매매차익은 기초자산(국내주식형 여부)에 따라 다름", pension=PENSION_OK, regulation="",
         cautions=["높은 분배율이 총수익을 보장하지 않는다(원금 잠식 가능)", "커버드콜은 상승장에서 지수보다 덜 오른다"],
         krx=dict(keywords=["배당", "고배당", "커버드콜", "인컴", "프리미엄", "월배당", "Dividend", "분배"], asset=[], market=[])),
    dict(key="allocation", name="자산배분·혼합", risk=2,
         description="주식·채권을 섞거나 목표 시점에 맞춰 비중을 바꾸는(TDF·TRF) ETF. 한 상품으로 분산과 리밸런싱을 한다.",
         concepts=[("자산배분", 1), ("자산배분", 2), ("리밸런싱", 1), ("채권 ETF", 1)],
         goals=["pension", "diversify", "long_term"], tax=TAX_OTHER, pension=PENSION_OK + ". 적격 TDF는 IRP 위험자산 한도 예외(100%까지, 금융사 확인)", regulation="",
         cautions=["혼합 비율에 따라 기대수익과 위험이 다르다", "총보수가 단일 지수형보다 높은 경우가 있다"],
         krx=dict(keywords=["자산배분", "TDF", "TRF", "혼합", "밸런스", "주식채권", "올웨더", "멀티에셋", "TIF"], asset=["혼합자산"], market=[])),
    dict(key="leverage_inverse", name="레버리지·인버스(파생형)", risk=5,
         description="기초지수 일일 수익률의 2배(레버리지) 또는 반대 방향(인버스)을 따르는 ETF. 일일 복리 때문에 장기 보유 시 누적 수익이 기초지수와 크게 달라진다.",
         concepts=[("레버리지·인버스", 1), ("레버리지·인버스", 2), ("레버리지·인버스", 3), ("유동성", 2)],
         goals=["trading"], tax=("국내 상장 레버리지·인버스는 상품 구성(장내 선물만인지, 장외 스와프를 쓰는지 등)에 따라 매매차익 과세 여부가 다르다. "
                                 "과세 대상이면 보유기간과세(실제 차익과 과표기준가 상승분 중 작은 금액에 15.4%), 분배금은 15.4%. 거래 전 운용사·KRX의 과세유형 공시 확인"),
         pension=PENSION_NO,
         regulation=LEVERAGE_RULES,
         cautions=["단기 매매 수단이며 장기 보유 상품이 아니다", "변동성 장세에서는 지수가 제자리여도 손실이 누적된다(음의 복리)",
                   "사전교육을 마쳐도 기본예탁금(1,000만원, 단일종목형은 현금 3,000만원)이 없으면 매수 주문이 들어가지 않는다",
                   "단일종목형은 사전교육 총 3시간과 신규 투자자 모의거래 5시간이 추가로 필요하다(2026-08-19부터)"],
         krx=dict(keywords=["레버리지", "인버스", "2X", "곱버스", "-2X"], asset=[], market=[])),
    dict(key="active_esg", name="액티브·ESG", risk=3,
         description="비교지수를 두고 운용역이 종목을 고르는 액티브 ETF와 ESG 지수를 따르는 ETF.",
         concepts=[("액티브 ETF", 1), ("액티브 ETF", 2), ("ESG ETF", 1), ("ESG ETF", 3)],
         goals=["long_term"], tax="기초자산에 따라 국내주식형 또는 기타 과세", pension=PENSION_OK, regulation="",
         cautions=["액티브는 비교지수와 다르게 움직일 수 있고 보수가 높다", "ESG 평가 방법이 운용사마다 다르다(그린워싱)"],
         krx=dict(keywords=["액티브", "ESG", "탄소", "친환경", "Active"], asset=[], market=[])),
]
TYPE_BY_KEY = {t["key"]: t for t in ETF_TYPES}
# 분류 우선순위: 먼저 맞는 유형이 이긴다.
CLASSIFY_ORDER = ["leverage_inverse", "income", "allocation", "bond", "commodity_fx", "reit_infra", "active_esg", "kr_sector_theme", "global_equity", "kr_broad"]


def goal_label(key: str) -> str:
    return GOALS.get(key, key)


def horizon_label(key: str) -> str:
    return HORIZONS.get(key, key)


def types_for_goal(goal: str, risk: int = 1) -> list:
    """목적에 맞는 유형 키 순서. 안정 성향(0)이면 위험 5 유형은 '학습만'으로 뒤로 보낸다."""
    keys = list(ROADMAP_TEMPLATES.get(goal, ROADMAP_TEMPLATES["long_term"])["types"])
    if risk == 0:
        keys = [k for k in keys if TYPE_BY_KEY[k]["risk"] < 5] + [k for k in keys if TYPE_BY_KEY[k]["risk"] >= 5]
    return keys
