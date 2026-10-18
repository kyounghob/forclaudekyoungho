from etfrec.catalog import Catalog
from etfrec.nlparse import EXAMPLES, parse_onboarding

cat = Catalog.default()


def test_parse_basic_sentence():
    p = parse_onboarding("ETF 구조와 비용에 관심 있는 초급 학습자야. 투자 경험은 없고 모바일로 저녁에 공부해. 5개 추천해 줘.", cat)
    f = p["fields"]
    assert f["interests"] == [cat.ti["ETF 구조"], cat.ti["비용"]]
    assert f["placement"] == 1 and f["exp"] == 0 and f["mobile"] == 1 and f["hour"] == 2 and f["k"] == 5
    assert not p["warnings"]


def test_parse_age_income_gender_risk():
    f = parse_onboarding("50대 여성, 연금계좌 ETF와 분배금에 관심. 투자 경험 3년 이상, 안정 성향, 고급 수준. 연소득 6000만원", cat)["fields"]
    assert f["age"] == 55 and f["gender"] == 1 and f["exp"] == 2 and f["risk"] == 0 and f["placement"] == 3 and f["income"] == 6000
    assert f["interests"] == [cat.ti["연금계좌 ETF"], cat.ti["분배금"]]


def test_parse_quoted_history_becomes_events_not_interests():
    p = parse_onboarding("추적오차와 리밸런싱에 관심 있는 25세 초급 학습자. 'ETF란 무엇인가'와 '추적오차의 기초'는 퀴즈를 통과했고 '추적오차가 생기는 이유'는 완료만 했어.", cat)
    f = p["fields"]
    assert f["interests"] == [cat.ti["추적오차"], cat.ti["리밸런싱"]]
    ev = {e["item"]: e for e in f["events"]}
    assert ev[0]["quiz_pass"] and ev[6]["quiz_pass"] and ev[7]["complete"] and not ev[7]["quiz_pass"]


def test_examples_all_parse_something():
    for ex in EXAMPLES:
        assert parse_onboarding(ex["text"], cat)["fields"]


def test_parse_goal_and_horizon():
    f = parse_onboarding("45세 직장인, 연금저축과 IRP로 노후 준비. 10년 이상 장기로 모바일 저녁 학습.", cat)["fields"]
    assert f["goal"] == "pension" and f["horizon"] == "long" and f["age"] == 45
    f = parse_onboarding("월배당으로 현금흐름을 만들고 싶어. 3년 정도 투자", cat)["fields"]
    assert f["goal"] == "income" and f["horizon"] == "mid"
    f = parse_onboarding("단기 매매로 레버리지 ETF를 써 보려는 27세 적극 성향, 몇 달 단위", cat)["fields"]
    assert f["goal"] == "trading" and f["horizon"] == "short" and f["risk"] == 2


def test_empty_text_warns():
    p = parse_onboarding("안녕하세요", cat)
    assert not p["fields"] and p["warnings"]


def _named(f):
    return {k: ([cat.topics[x] for x in v] if k == "interests" else v) for k, v in f.items() if k != "events"}


EXPECTED_EXAMPLES = {      # 화면 예시 9개의 읽기 결과를 고정한다(경험·기간 혼동, 커버드콜 누락이 다시 생기지 않게)
    "기초 입문 예시": dict(interests=["ETF 구조", "비용"], placement=1, exp=0, mobile=1, hour=2, k=5),
    "수준 2 학습자 예시": dict(interests=["채권 ETF", "자산배분"], placement=2, exp=1, risk=1, mobile=0, hour=1, age=35),
    "고위험 관심 예시": dict(interests=["레버리지·인버스", "테마 ETF"], exp=0, risk=2, mobile=1, hour=3, k=3, age=25),
    "연금 투자자 예시": dict(interests=["연금계좌 ETF", "분배금"], gender=1, exp=2, risk=0, placement=3, goal="pension", age=55),
    "해외 투자 예시": dict(interests=["해외 ETF", "환헤지"], gender=0, placement=2, mobile=1, hour=0, income=6000.0, age=45),
    "기록 포함 예시": dict(interests=["추적오차", "리밸런싱"], placement=1, age=25),
    "연금 로드맵 예시": dict(interests=["연금계좌 ETF"], goal="pension", exp=1, risk=0, horizon="long", mobile=1, hour=2, placement=1, age=45),
    "인컴 로드맵 예시": dict(interests=["커버드콜 ETF", "리츠 ETF"], goal="income", horizon="mid", risk=1, mobile=0, hour=1, placement=2, age=38),
    "단기 매매 로드맵 예시": dict(interests=["레버리지·인버스"], goal="trading", exp=0, horizon="short", risk=2, mobile=1, hour=3, k=3, age=27),
}


def test_all_ui_examples_parse_exactly():
    for ex in EXAMPLES:
        assert _named(parse_onboarding(ex["text"], cat)["fields"]) == EXPECTED_EXAMPLES[ex["title"]], ex["title"]


def test_experience_and_horizon_do_not_bleed():
    f = parse_onboarding("투자 경험 1~3년, 장기 투자", cat)["fields"]
    assert f["exp"] == 1 and f["horizon"] == "long"                  # '1~3년'이 '3년 이상'으로 읽히지 않는다
    f = parse_onboarding("투자 경험 3년 이상", cat)["fields"]
    assert f["exp"] == 2 and "horizon" not in f                      # 경험 표현이 투자 기간으로 새지 않는다
    f = parse_onboarding("3년 정도 투자할 계획", cat)["fields"]
    assert f["horizon"] == "mid" and "exp" not in f


def test_topic_keyword_boundaries_and_covered_call():
    assert _named(parse_onboarding("커버드콜 ETF에 관심 있어요", cat)["fields"])["interests"] == ["커버드콜 ETF"]
    assert _named(parse_onboarding("연금 ETF에 관심 있는 초급자", cat)["fields"])["interests"] == ["연금계좌 ETF"]   # 금 ETF 아님
    assert "interests" not in parse_onboarding("현금 ETF가 궁금", cat)["fields"]
    assert _named(parse_onboarding("금 ETF와 채권에 관심", cat)["fields"])["interests"] == ["금 ETF", "채권 ETF"]
    assert _named(parse_onboarding("보수적 성향의 50대, 채권 ETF에 관심", cat)["fields"])["interests"] == ["채권 ETF"]   # '보수적' ≠ 비용
    assert "지수" not in _named(parse_onboarding("연금계좌에 편입할 채권 ETF가 궁금", cat)["fields"])["interests"]


def test_count_income_and_history_clauses():
    f = parse_onboarding("6개월 안에 쓸 돈으로 단기 매매", cat)["fields"]
    assert "k" not in f and f["horizon"] == "short"                  # '6개월'은 요청 개수가 아니다
    assert parse_onboarding("연봉 5,000만원 직장인", cat)["fields"]["income"] == 5000.0
    ev = parse_onboarding("'추적오차가 생기는 이유'는 완료만 했고 '추적오차의 기초'는 통과했어", cat)["fields"]["events"]
    by = {str(cat.item_title[e["item"]]).split(":")[0]: e for e in ev}
    assert by["추적오차가 생기는 이유"]["complete"] and not by["추적오차가 생기는 이유"]["quiz_pass"]   # 다음 절의 '통과'를 읽지 않는다
    assert by["추적오차의 기초"]["quiz_pass"]
