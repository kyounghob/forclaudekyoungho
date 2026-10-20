"""한국어 자연어 온보딩 파서(규칙 기반, 외부 API 없음).

"ETF 구조와 비용에 관심 있는 초급 학습자, 모바일로 저녁에 공부" 같은 문장에서
관심 주제·수준·기기·시간대·연령·경험·위험성향·요청 개수를 읽어 내고, 어떤 단어로 읽었는지 근거를 남긴다.
읽어 낸 값은 화면의 입력칸에 다시 표시되어 사람이 확인·수정한다.
"""
from __future__ import annotations

import re

from .privacy import income_from_text

from .catalog import Catalog

# 길이가 긴 키워드부터 검사한다. "금 etf"처럼 짧은 키워드는 바로 앞 글자가 한글이면 단어 일부로 보고 건너뛴다(연금 ETF·현금 ETF ≠ 금 ETF).
TOPIC_KEYWORDS = {
    "ETF 구조": ["etf 구조", "etf의 구조", "etf란", "etf 기초", "nav", "괴리율", "설정·환매", "lp", "유동성공급자"],
    "지수": ["지수", "코스피", "s&p", "kospi", "시가총액 가중", "동일 가중", "구성 종목", "정기변경"],
    "추적오차": ["추적오차", "추적차이", "트래킹"],
    "비용": ["비용", "총보수", "보수", "수수료", "스프레드", "총비용"],
    "분배금": ["분배금", "배당", "배당소득세"],
    "섹터 ETF": ["섹터", "반도체", "기술주", "업종", "로테이션"],
    "채권 ETF": ["채권", "국채", "회사채", "듀레이션"],
    "금 ETF": ["금 etf", "골드", "금값", "금 가격", "인플레이션"],
    "환헤지": ["환헤지", "환율", "환노출", "달러", "금리차"],
    "레버리지·인버스": ["레버리지", "인버스", "곱버스", "2배", "음의 복리"],
    "커버드콜 ETF": ["커버드콜", "covered call", "옵션 프리미엄", "콜옵션 매도"],
    "리밸런싱": ["리밸런싱", "재조정", "밴드"],
    "자산배분": ["자산배분", "분산투자", "분산", "포트폴리오", "상관관계", "주식·채권"],
    "해외 ETF": ["해외", "미국", "나스닥", "글로벌", "양도소득세", "환전"],
    "유동성": ["유동성", "거래량", "호가"],
    "테마 ETF": ["테마", "2차전지", "ai etf", "인공지능", "집중 위험"],
    "원자재 ETF": ["원자재", "선물", "롤오버", "콘탱고", "백워데이션", "원유"],
    "리츠 ETF": ["리츠", "부동산", "reit"],
    "연금계좌 ETF": ["연금계좌", "연금", "irp", "연금저축", "세액공제", "과세이연", "퇴직"],
    "절세 계좌": ["isa", "개인종합자산관리", "절세 계좌", "절세계좌", "비과세 한도", "분리과세"],
    "액티브 ETF": ["액티브", "패시브", "비교지수"],
    "ESG ETF": ["esg", "그린워싱", "친환경"],
}
LEFT_BOUNDARY = {"금 etf", "금값", "금 가격"}            # 앞 글자가 한글이면 다른 단어의 일부(연금 ETF, 현금 가격)
NOT_FOLLOWED_BY = {"보수": "적"}                          # '보수적'(위험성향)은 비용 주제가 아니다
INTEREST_CUES = ["관심", "궁금", "배우고", "알고 싶", "공부하고 싶"]
LEVEL_WORDS = [(3, ["고급", "심화", "상급", "전문", "어려운"]), (2, ["중급", "중간"]), (1, ["초급", "입문", "처음", "기초", "초보", "왕초보", "쉬운"])]
# 경험은 '경험'이라는 말 주변(앞 8자 ~ 뒤 14자)에서만 읽고, 가장 긴 표현을 고른다('1~3년'이 '3년'보다, '3년 이상'이 '3년'보다 우선).
EXP_WORDS = [(0, ["경험 없", "경험이 없", "경험은 없", "경험도 없", "경험 무"]),
             (1, ["1~3년", "1-3년", "2~3년", "1년", "2년", "조금", "약간"]),
             (2, ["3년 이상", "3년", "4년", "5년", "10년", "오래"])]
EXP_ANYWHERE = [(0, ["무경험", "투자해 본 적 없", "처음 투자"]), (2, ["베테랑"])]   # '경험'이 없어도 경험으로 읽는 표현
RISK_WORDS = [(2, ["공격적", "적극", "고위험", "high risk"]), (0, ["안정", "보수적", "저위험", "안전"]), (1, ["중립", "보통"])]
DEVICE_WORDS = [(1, ["모바일", "스마트폰", "휴대폰", "폰으로", "앱으로", "앱에서"]), (0, ["pc", "데스크톱", "데스크탑", "노트북", "컴퓨터"])]
HOUR_WORDS = [(0, ["출근", "아침", "오전"]), (1, ["점심"]), (2, ["저녁", "퇴근", "오후"]), (3, ["심야", "밤", "새벽", "자기 전"])]
GENDER_WORDS = [(1, ["여성", "여자", "여학생"]), (0, ["남성", "남자", "남학생"])]
GOAL_WORDS = [("pension", ["연금", "노후", "은퇴", "irp", "퇴직"]), ("income", ["배당", "월배당", "인컴", "현금흐름", "분배금 받", "커버드콜"]),
              ("trading", ["단기 매매", "단타", "트레이딩", "매매", "단기 투자", "레버리지로", "급등주"]),
              ("diversify", ["분산", "안정적으로", "안전하게", "잃지 않", "방어"]),
              ("long_term", ["장기", "적립식", "지수 투자", "노후 자산", "자산형성", "꾸준히", "10년"])]
# 투자 기간은 경험으로 읽은 구간을 빼고 찾는다(가장 긴 표현 우선).
HORIZON_WORDS = [("short", ["1년 미만", "몇 달", "몇 개월", "개월", "단기간", "단기"]), ("long", ["5년 이상", "10년", "20년", "장기간", "장기", "노후", "은퇴"]),
                 ("mid", ["1~5년", "2~3년", "3년", "중기", "몇 년"])]
EXAMPLES = [
    dict(title="기초 입문 예시", text="ETF 구조와 비용에 관심 있는 초급 학습자야. 투자 경험은 없고 모바일로 저녁에 공부해. 5개 추천해 줘."),
    dict(title="수준 2 학습자 예시", text="30대 중급 학습자, 채권 ETF와 자산배분에 관심. 투자 경험 1~3년, 위험성향 중립, PC로 점심시간에 학습."),
    dict(title="고위험 관심 예시", text="레버리지·인버스와 테마 ETF가 궁금한 20대. 경험 없음, 적극적 성향, 스마트폰 심야 학습. 3개만 보여줘."),
    dict(title="연금 투자자 예시", text="50대 여성, 연금계좌 ETF와 분배금에 관심. 투자 경험 3년 이상, 안정 성향, 고급 수준."),
    dict(title="해외 투자 예시", text="해외 ETF와 환헤지를 배우고 싶은 40대 남성, 중급, 모바일 출근길 학습, 연소득 6000만원."),
    dict(title="기록 포함 예시", text="추적오차와 리밸런싱에 관심 있는 25세 초급 학습자. 'ETF란 무엇인가'와 '추적오차의 기초'는 퀴즈를 통과했고 '추적오차가 생기는 이유'는 완료만 했어."),
    dict(title="연금 로드맵 예시", text="45세 직장인, 연금저축과 IRP로 노후 준비를 시작하려고 해. 투자 경험 1~3년, 안정 성향, 10년 이상 장기로 모바일 저녁 학습. 초급."),
    dict(title="인컴 로드맵 예시", text="월배당으로 현금흐름을 만들고 싶은 38세 중급 학습자. 커버드콜과 리츠에 관심, 중립 성향, 3년 정도 투자, PC 점심시간."),
    dict(title="단기 매매 로드맵 예시", text="단기 매매로 레버리지 ETF를 써 보려는 27세 적극 성향, 경험 없음, 몇 달 단위 투자, 스마트폰 심야 학습. 3개만."),
]


def _find(text, table):
    for value, words in table:
        for w in words:
            if w in text:
                return value, w
    return None, None


def _occurrences(text, w):
    start = text.find(w)
    while start >= 0:
        yield start
        start = text.find(w, start + 1)


def _ok_at(text, w, pos):
    """키워드 경계: LEFT_BOUNDARY 키워드는 앞 글자가 한글이면, NOT_FOLLOWED_BY 키워드는 뒤에 금지 글자가 오면 일치로 보지 않는다."""
    if w in LEFT_BOUNDARY and pos > 0 and "가" <= text[pos - 1] <= "힣":
        return False
    nf = NOT_FOLLOWED_BY.get(w)
    return not (nf and text.startswith(nf, pos + len(w)))


def _longest(text, table, lo=0, hi=None, exclude=()):
    """[lo, hi) 구간에서 표의 표현 중 가장 긴 일치(같으면 앞쪽)를 (값, 표현, 시작, 끝)으로. exclude 구간과 겹치면 건너뛴다."""
    hi = len(text) if hi is None else hi
    best = None
    for value, words in table:
        for w in words:
            for pos in _occurrences(text, w):
                end = pos + len(w)
                if pos < lo or end > hi or any(pos < e and end > s for s, e in exclude) or not _ok_at(text, w, pos):
                    continue
                if best is None or len(w) > len(best[1]) or (len(w) == len(best[1]) and pos < best[2]):
                    best = (value, w, pos, end)
    return best


PASS_VERBS = ("통과", "합격", "맞췄", "끝냈")
DONE_VERBS = ("완료", "다 봤", "끝까지", "수강", "마쳤")
FAIL_WORDS = ("떨어", "불합격", "미통과", "낙제")
_NEG_PREFIX = ("미", "불")                                              # 미완료·미통과·불합격
_NEG_AFTER = re.compile(                                                # 동사 바로 뒤의 부정·실패·의도·미완 표현
    r"\s*(?:하지는|하지|하진|를|을|은|는|도|에는|에|이|가)?\s*"
    r"(?:못|않|안\s*(?:했|됐|됨|함|해|돼|되)|안\s|실패|아직|하려|하고\s*싶|하는\s*데\s*실패|데\s*실패|목표"
    r"|전(?:이|인|임|\s*상태|$|\s*[.,!?)])|중(?:이|인|$|\s*[.,!?)]))"
    r"|\s*\S{0,3}지\s*(?:는\s*)?못")                                     # '끝까지 보지 못했어'·'다 듣지 못했어'


def _affirmed(gap: str, words, after: int = 0) -> bool:
    """gap에서 after 위치 이후에 부정·실패가 붙지 않은 동사가 있는지. '통과하지 못했어'·'통과 안됐어'·'통과는 아직'·'통과 전이야'·
    '통과하는 데 실패'·'미완료'·'불합격'·'수강 중'·'끝까지 보지 못했어'는 아니고, '통과는 전에 했어'·'수강을 전부 마쳤어'는 맞다."""
    for w in words:
        for m in re.finditer(re.escape(w), gap):
            if m.start() < after or gap[max(0, m.start() - 1):m.start()] in _NEG_PREFIX or _NEG_AFTER.match(gap, m.end()):
                continue
            return True
    return False


def _passed(gap: str) -> bool:
    """통과: 마지막 실패 표현('떨어'·'불합격'…)보다 뒤에 긍정 통과 동사가 있어야 한다. '처음엔 떨어졌는데 재시험에서 통과했어'는 통과,
    '통과할 줄 알았는데 떨어졌어'는 아니다(애매하면 통과로 보지 않는다: 잘못 통과로 읽으면 그 단원이 후보에서 빠진다)."""
    last_fail = max((m.end() for w in FAIL_WORDS for m in re.finditer(re.escape(w), gap)), default=-1)
    return _affirmed(gap, PASS_VERBS, after=last_fail)


def _clauses(text):
    """문장부호(. , ! ? 줄바꿈)로 나눈 구간 [(시작, 끝)]."""
    out, start = [], 0
    for m in re.finditer(r"(?<!\d)[.,](?!\d)|[!?\n]", text):           # 숫자 사이의 점·쉼표(1.5배, 1,000)는 경계가 아니다
        out.append((start, m.start())); start = m.end()
    out.append((start, len(text)))
    return out


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
            pos = next((p for p in _occurrences(t, w) if _ok_at(t, w, p)), -1)
            if pos >= 0:
                hits.append((pos, len(w), topic, w)); break
    cue_spans = [c for c in _clauses(t) if any(cue in t[c[0]:c[1]] for cue in INTEREST_CUES)]
    in_cue = lambda pos: any(a <= pos < b for a, b in cue_spans)
    hits.sort(key=lambda x: (not in_cue(x[0]), x[0], -x[1]))          # '관심·궁금' 구간의 주제를 먼저, 그다음 등장 순
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
    for key, table in (("placement", LEVEL_WORDS), ("risk", RISK_WORDS), ("mobile", DEVICE_WORDS),
                       ("hour", HOUR_WORDS), ("gender", GENDER_WORDS), ("goal", GOAL_WORDS)):
        v, w = _find(t, table)
        if v is not None:
            fields[key] = v; evidence.append(dict(field=key, value=v, matched=w))
    exp_hit, used = None, []
    for m in re.finditer("경험", t):                                   # 경험: '경험'이 든 절 안의 주변에서만(다음 문장의 기간 표현을 읽지 않게)
        cs, ce = next((a, b) for a, b in _clauses(t) if a <= m.start() <= b)
        lo, hi = max(cs, m.start() - 8), min(ce, m.end() + 14)
        h = _longest(t, EXP_WORDS[:1], lo, hi) or _longest(t, EXP_WORDS, lo, hi)     # '경험 없…'은 길이와 상관없이 우선
        if h and (exp_hit is None or ((h[0] == 0) != (exp_hit[0] == 0) and h[0] == 0)
                  or ((h[0] == 0) == (exp_hit[0] == 0) and len(h[1]) > len(exp_hit[1]))):
            exp_hit = h
    exp_hit = exp_hit or _longest(t, EXP_ANYWHERE)
    if exp_hit:
        fields["exp"] = exp_hit[0]; used.append(exp_hit[2:]); evidence.append(dict(field="exp", value=exp_hit[0], matched=exp_hit[1]))
    hz = _longest(t, HORIZON_WORDS, exclude=used)                      # 기간: 경험으로 읽은 구간은 빼고
    if hz and hz[0] == "mid" and re.match(r"[1-4]\s*년\s*이상", t[hz[2]:hz[2] + 8]):    # '3년 이상'은 중기·장기 어느 쪽도 된다: '장기'가 있으면 장기
        hz = _longest(t, [("long", ["장기간", "장기"])], exclude=used) or hz
    if hz:
        fields["horizon"] = hz[0]; evidence.append(dict(field="horizon", value=hz[0], matched=hz[1]))
    # 연령
    m = re.search(r"(\d{2})\s*(세|살)", t)
    if m:
        fields["age"] = int(m.group(1)); evidence.append(dict(field="age", value=fields["age"], matched=m.group(0)))
    else:
        m = re.search(r"(\d)0\s*대", t)
        if m:
            fields["age"] = int(m.group(1)) * 10 + 5; evidence.append(dict(field="age", value=fields["age"], matched=m.group(0)))
    # 소득: 저장 설계 가림과 같은 규칙(privacy.income_from_text — 억 단위 합산, 월급은 연으로 환산)
    inc, matched = income_from_text(raw)
    if inc is not None:
        fields["income"] = inc; evidence.append(dict(field="income", value=inc, matched=matched))
    # 요청 개수
    m = re.search(r"(\d{1,2})\s*개(?!월)", t)
    if m and 1 <= int(m.group(1)) <= 20:
        fields["k"] = int(m.group(1)); evidence.append(dict(field="k", value=fields["k"], matched=m.group(0)))
    # 학습 이력: 따옴표 안의 단원 제목 + 통과/완료 동사
    events = []
    quotes = list(re.finditer(r"['‘’\"“”]([^'‘’\"“”]{2,40})['‘’\"“”]", raw))
    verbs = []                                                       # 따옴표마다 그 뒤 동사 구간의 (통과, 완료)
    for k, mq in enumerate(quotes):
        nxt = quotes[k + 1].start() if k + 1 < len(quotes) else min(len(raw), mq.end() + 40)
        end = re.search(r"(?<!\d)\.(?!\d)|[!?\n]", raw[mq.end():nxt])     # 동사는 같은 문장 안에서만 찾는다(1.5배속의 점은 문장 끝이 아님)
        gap = raw[mq.end():mq.end() + end.start() if end else nxt]
        verbs.append((_passed(gap), _affirmed(gap, DONE_VERBS),
                      k + 1 < len(quotes) and re.fullmatch(r"\s*(와|과|,|및|하고|랑|이랑)\s*", gap) is not None))
    for k in range(len(verbs) - 2, -1, -1):                         # 'A와 B는 통과' → A는 B의 동사를 따른다
        if verbs[k][2]:
            verbs[k] = (verbs[k + 1][0], verbs[k + 1][1], True)
    for k, mq in enumerate(quotes):
        q = mq.group(1).strip()
        matches = [i for i, title in enumerate(catalog.item_title) if q in title or title in q]
        if not matches:
            warnings.append(f"'{q}'와 일치하는 단원 제목을 찾지 못했습니다.")
            continue
        item = matches[0]
        passed = verbs[k][0]
        done = passed or verbs[k][1]
        events.append(dict(item=int(item), week=0, complete=bool(done), quiz=bool(passed), quiz_pass=bool(passed), save=False, drop=False, replay=False))
        evidence.append(dict(field="events", value=catalog.item_title[item], matched=("통과" if passed else "완료" if done else "조회")))
    if events:
        fields["events"] = events
    if not fields:
        warnings.append("읽어 낸 조건이 없습니다. 관심 주제·수준·기기 등을 문장에 적어 주세요.")
    return dict(fields=fields, evidence=evidence, warnings=warnings, text=raw)
