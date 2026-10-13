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


def test_empty_text_warns():
    p = parse_onboarding("안녕하세요", cat)
    assert not p["fields"] and p["warnings"]
