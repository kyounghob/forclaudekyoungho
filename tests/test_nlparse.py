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


def test_unit_status_negation_and_sentence_scope():
    def status(text):
        ev = parse_onboarding(text, cat)["fields"]["events"]
        return ["pass" if e["quiz_pass"] else "complete" if e["complete"] else "view" for e in ev]
    assert status("'ETF란 무엇인가'는 아직 통과하지 못했어.") == ["view"]
    assert status("'ETF란 무엇인가'는 완료했는데 퀴즈는 통과 못 했어.") == ["complete"]
    assert status("'추적오차의 기초'는 미완료 상태야.") == ["view"]
    assert status("'ETF란 무엇인가'를 조금 봤어. 퀴즈 통과가 목표야.") == ["view"]          # 다음 문장의 '통과'를 읽지 않는다
    assert status("'ETF란 무엇인가'는 퀴즈에서 떨어졌어(통과 실패).") == ["view"]
    assert status("'ETF란 무엇인가'는 통과 안 했어") == ["view"]
    assert status("'ETF란 무엇인가'와 'ETF 총보수 이해하기'는 통과했고 'ETF 거래량과 유동성'은 수강 중이야.") == ["pass", "pass", "view"]
    assert status("'ETF란 무엇인가'는 통과했어.") == ["pass"] and status("'ETF란 무엇인가'는 끝까지 다 봤어") == ["complete"]


def test_unit_status_reads_common_positive_and_negative_forms():
    def status(text):
        ev = parse_onboarding(text, cat)["fields"]["events"]
        return ["pass" if e["quiz_pass"] else "complete" if e["complete"] else "view" for e in ev]
    U = "'ETF란 무엇인가'"
    want = {f"{U} 퀴즈는 처음엔 떨어졌는데 재시험에서 통과했어.": "pass",          # 실패어가 통과보다 앞이면 통과
            "'레버리지·인버스 ETF란'은 가격이 떨어질 때 수익이 나는 구조를 배워서 통과했어.": "pass",
            f"{U}는 통과는 전에 했어.": "pass", f"{U}는 지난주에 통과했어.": "pass", f"{U}는 완료는 전에 했어.": "complete",
            f"{U}는 수강을 전부 마쳤어.": "complete", f"{U}는 1.5배속으로 끝까지 봤어.": "complete", f"{U}는 0.5배속으로 다 봤어.": "complete",
            f"{U}는 중간에 끊지 않고 끝까지 봤어.": "complete", f"{U}는 전부 다 봤어.": "complete",
            f"{U}는 통과 안됐어.": "view", f"{U}는 통과 안함.": "view", f"{U}는 통과하지는 못했어.": "view", f"{U}는 통과하진 못했어.": "view",
            f"{U}는 통과는 아직이야.": "view", f"{U}는 통과하는 데 실패했어.": "view", f"{U}는 끝까지 보지 못했어.": "view", f"{U}는 완료 안됨.": "view",
            f"{U}는 통과하지 못했어.": "view", f"{U}는 통과 못 했어.": "view", f"{U}는 통과 전이야.": "view", f"{U}는 수강 중이야.": "view",
            f"{U}는 통과하려고 공부 중이야.": "view", f"{U}는 통과하고 싶어.": "view", f"{U}는 미통과야.": "view", f"{U}는 불합격이었어.": "view",
            f"{U}는 통과할 줄 알았는데 떨어졌어.": "view",                       # 실패어가 마지막이면 통과가 아니다
            f"{U}는 퀴즈를 통과했고 점수가 조금 떨어졌지만 괜찮아.": "view"}       # 애매하면 통과로 보지 않는다(잘못 읽으면 후보에서 빠짐)
    for text, w in want.items():
        assert status(text) == [w], (text, status(text))


def test_income_reads_eok_and_monthly_forms_like_design_scrub():
    for text, want in (("45세 직장인, 연소득 1억 2천만원, 연금 준비", 12000.0), ("45세, 연봉 1억5천만원", 15000.0), ("연봉 1억 2000만원", 12000.0),
                       ("월급 450만원 받는 직장인", 5400.0), ("연소득 1.2억", 12000.0), ("연봉 6천", 6000.0)):
        assert parse_onboarding(text, cat)["fields"]["income"] == want, text
    for text in ("목돈 5000만원 있음", "연금소득 1,500만원 넘으면 어떻게 돼?", "ISA 한도 2,000만원"):
        assert "income" not in parse_onboarding(text, cat)["fields"], text     # 소득 키워드가 없는 금액은 소득으로 읽지 않는다


def test_experience_window_stays_in_its_clause():
    for text in ("경험 없음. 3년 이상 장기 투자 예정", "ETF 구조에 관심 있는 초보, 경험 없어. 3년 이상 모을 거야", "경험 없고 3년 이상 장기 투자할 거야"):
        assert parse_onboarding(text, cat)["fields"]["exp"] == 0, text      # 다음 문장·뒤의 기간 표현이 경험을 뒤집지 않는다
    assert parse_onboarding("경험 없음. 3년 이상 장기 투자 예정", cat)["fields"]["horizon"] == "long"
    assert parse_onboarding("3년 이상 모을 거야", cat)["fields"]["horizon"] == "mid"
    f = parse_onboarding("투자 경험 3년 이상, 장기 투자", cat)["fields"]
    assert f["exp"] == 2 and f["horizon"] == "long"
