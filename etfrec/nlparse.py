"""한국어 자연어 온보딩 파서(규칙 기반, 외부 API 없음).

"ETF 구조와 비용에 관심 있는 초급 학습자, 모바일로 저녁에 공부" 같은 문장에서
관심 주제·수준·기기·시간대·연령·경험·위험성향·요청 개수를 읽어 내고, 어떤 단어로 읽었는지 근거를 남긴다.
읽어 낸 값은 화면의 입력칸에 다시 표시되어 사람이 확인·수정한다.
"""
from __future__ import annotations

import re

from .catalog import Catalog

# 길이가 긴 키워드부터 검사한다("연금"이 "금"보다 먼저 잡히도록).
TOPIC_KEYWORDS = {
    "ETF 구조": ["etf 구조", "etf란", "etf 기초", "nav", "괴리율", "설정·환매", "lp", "유동성공급자", "구조"],
    "지수": ["지수", "코스피", "s&p", "kospi", "시가총액 가중", "동일 가중", "편입"],
    "추적오차": ["추적오차", "추적차이", "트래킹"],
    "비용": ["비용", "총보수", "보수", "수수료", "스프레드", "총비용"],
    "분배금": ["분배금", "배당", "배당소득세"],
    "섹터 ETF": ["섹터", "반도체", "기술주", "업종", "로테이션"],
    "채권 ETF": ["채권", "국채", "회사채", "듀레이션"],
    "금 ETF": ["금 etf", "골드", "금값", "금 가격", "인플레이션"],
    "환헤지": ["환헤지", "환율", "환노출", "달러", "금리차"],
    "레버리지·인버스": ["레버리지", "인버스", "곱버스", "2배", "음의 복리"],
    "리밸런싱": ["리밸런싱", "재조정", "밴드"],
    "자산배분": ["자산배분", "분산투자", "분산", "포트폴리오", "상관관계", "주식·채권"],
    "해외 ETF": ["해외", "미국", "나스닥", "글로벌", "양도소득세", "환전"],
    "유동성": ["유동성", "거래량", "호가"],
    "테마 ETF": ["테마", "2차전지", "ai etf", "인공지능", "집중 위험"],
    "원자재 ETF": ["원자재", "선물", "롤오버", "콘탱고", "백워데이션", "원유"],
    "리츠 ETF": ["리츠", "부동산", "reit"],
    "연금계좌 ETF": ["연금계좌", "연금", "irp", "연금저축", "세액공제", "과세이연", "퇴직"],
    "액티브 ETF": ["액티브", "패시브", "비교지수"],
    "ESG ETF": ["esg", "그린워싱", "친환경"],
}
LEVEL_WORDS = [(3, ["고급", "심화", "상급", "전문", "어려운"]), (2, ["중급", "중간"]), (1, ["초급", "입문", "처음", "기초", "초보", "왕초보", "쉬운"])]
EXP_WORDS = [(2, ["3년 이상", "오래", "베테랑", "3년", "4년", "5년", "10년"]), (1, ["1~3년", "1년", "2년", "조금", "약간"]),
             (0, ["경험 없", "경험이 없", "경험은 없", "경험도 없", "경험 무", "투자해 본 적 없", "무경험", "처음 투자", "시작하는"])]
RISK_WORDS = [(2, ["공격적", "적극", "고위험", "high risk"]), (0, ["안정", "보수적", "저위험", "안전"]), (1, ["중립", "보통"])]
DEVICE_WORDS = [(1, ["모바일", "스마트폰", "휴대폰", "폰으로", "앱으로", "앱에서"]), (0, ["pc", "데스크톱", "데스크탑", "노트북", "컴퓨터"])]
HOUR_WORDS = [(0, ["출근", "아침", "오전"]), (1, ["점심"]), (2, ["저녁", "퇴근", "오후"]), (3, ["심야", "밤", "새벽", "자기 전"])]
GENDER_WORDS = [(1, ["여성", "여자", "여학생"]), (0, ["남성", "남자", "남학생"])]
EXAMPLES = [
    dict(title="기초 입문 예시", text="ETF 구조와 비용에 관심 있는 초급 학습자야. 투자 경험은 없고 모바일로 저녁에 공부해. 5개 추천해 줘."),
    dict(title="수준 2 학습자 예시", text="30대 중급 학습자, 채권 ETF와 자산배분에 관심. 투자 경험 1~3년, 위험성향 중립, PC로 점심시간에 학습."),
    dict(title="고위험 관심 예시", text="레버리지·인버스와 테마 ETF가 궁금한 20대. 경험 없음, 적극적 성향, 스마트폰 심야 학습. 3개만 보여줘."),
    dict(title="연금 투자자 예시", text="50대 여성, 연금계좌 ETF와 분배금에 관심. 투자 경험 3년 이상, 안정 성향, 고급 수준."),
    dict(title="해외 투자 예시", text="해외 ETF와 환헤지를 배우고 싶은 40대 남성, 중급, 모바일 출근길 학습, 연소득 6000만원."),
    dict(title="기록 포함 예시", text="추적오차와 리밸런싱에 관심 있는 25세 초급 학습자. 'ETF란 무엇인가'와 '추적오차의 기초'는 퀴즈를 통과했고 '추적오차가 생기는 이유'는 완료만 했어."),
]


def _find(text, table):
    for value, words in table:
        for w in words:
            if w in text:
                return value, w
    return None, None


def parse_onboarding(text: str, catalog: Catalog) -> dict:
    """문장 → {fields, evidence, warnings}. 못 읽은 항목은 fields에 넣지 않는다(화면 기본값 유지)."""
    raw = text or ""
    # 따옴표 안의 단원 제목은 학습 이력으로만 읽고, 관심 주제 탐지에서는 뺀다.
    t = re.sub(r"['‘’\"“”][^'‘’\"“”]{2,40}['‘’\"“”]", " ", raw).lower().replace("  ", " ")
    fields, evidence, warnings = {}, [], []
    # 관심 주제: 등장 위치 순, 최대 2개
    hits = []
    for topic, words in TOPIC_KEYWORDS.items():
        if topic not in catalog.ti:
            continue
        for w in sorted(words, key=len, reverse=True):
            pos = t.find(w)
            if pos >= 0:
                hits.append((pos, len(w), topic, w)); break
    hits.sort(key=lambda x: (x[0], -x[1]))
    seen, topics = set(), []
    for pos, _, topic, w in hits:
        if topic in seen:
            continue
        seen.add(topic); topics.append(topic)
        evidence.append(dict(field="interests", value=topic, matched=w))
    if topics:
        fields["interests"] = [catalog.ti[x] for x in topics[:2]]
        if len(topics) > 2:
            warnings.append(f"관심 주제가 {len(topics)}개 읽혔습니다. 앞의 2개({topics[0]}, {topics[1]})만 사용했습니다.")
    # 수준·경험·성향·기기·시간대·성별
    for key, table in (("placement", LEVEL_WORDS), ("exp", EXP_WORDS), ("risk", RISK_WORDS), ("mobile", DEVICE_WORDS),
                       ("hour", HOUR_WORDS), ("gender", GENDER_WORDS)):
        v, w = _find(t, table)
        if v is not None:
            fields[key] = v; evidence.append(dict(field=key, value=v, matched=w))
    # 연령
    m = re.search(r"(\d{2})\s*(세|살)", t)
    if m:
        fields["age"] = int(m.group(1)); evidence.append(dict(field="age", value=fields["age"], matched=m.group(0)))
    else:
        m = re.search(r"(\d)0\s*대", t)
        if m:
            fields["age"] = int(m.group(1)) * 10 + 5; evidence.append(dict(field="age", value=fields["age"], matched=m.group(0)))
    # 소득
    m = re.search(r"(연소득|연봉|소득)\s*(\d{3,5})\s*만\s*원?", t)
    if m:
        fields["income"] = float(m.group(2)); evidence.append(dict(field="income", value=fields["income"], matched=m.group(0)))
    else:
        m = re.search(r"(\d)\s*천\s*만\s*원", t)
        if m:
            fields["income"] = float(m.group(1)) * 1000; evidence.append(dict(field="income", value=fields["income"], matched=m.group(0)))
    # 요청 개수
    m = re.search(r"(\d{1,2})\s*개", t)
    if m and 1 <= int(m.group(1)) <= 20:
        fields["k"] = int(m.group(1)); evidence.append(dict(field="k", value=fields["k"], matched=m.group(0)))
    # 학습 이력: 따옴표 안의 단원 제목 + 통과/완료 동사
    events = []
    for quote in re.findall(r"['‘’\"“”]([^'‘’\"“”]{2,40})['‘’\"“”]", raw):
        q = quote.strip()
        matches = [i for i, title in enumerate(catalog.item_title) if q in title or title in q]
        if not matches:
            warnings.append(f"'{q}'와 일치하는 단원 제목을 찾지 못했습니다.")
            continue
        item = matches[0]
        tail = raw[raw.find(quote) + len(quote): raw.find(quote) + len(quote) + 40]
        passed = any(w in tail for w in ("통과", "합격", "맞췄", "끝냈"))
        done = passed or any(w in tail for w in ("완료", "다 봤", "끝까지", "수강"))
        events.append(dict(item=int(item), week=0, complete=bool(done), quiz=bool(passed), quiz_pass=bool(passed), save=False, drop=False, replay=False))
        evidence.append(dict(field="events", value=catalog.item_title[item], matched=("통과" if passed else "완료" if done else "조회")))
    if events:
        fields["events"] = events
    if not fields:
        warnings.append("읽어 낸 조건이 없습니다. 관심 주제·수준·기기 등을 문장에 적어 주세요.")
    return dict(fields=fields, evidence=evidence, warnings=warnings, text=raw)
