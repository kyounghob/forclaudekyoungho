"""학습 콘텐츠: 66개 단원 모두 학습 요점과 단원 확인 문항이 있고, 확인 문항은 진단 문항과 겹치지 않으며 정답 위치가 고르다."""
from collections import Counter

from etfrec.catalog import Catalog
from etfrec.lessons import LESSONS, lesson
from etfrec.quiz import QUESTIONS
from etfrec.sources.registry import SOURCES
from etfrec.unit_checks import UNIT_CHECKS, unit_check


def _keys(cat):
    return [(cat.topics[cat.item_topic[i]], int(cat.item_level[i])) for i in range(cat.n_items)]


def test_every_unit_has_lesson_points_and_valid_sources():
    cat = Catalog.default()
    for key in _keys(cat):
        x = lesson(*key)
        assert x is not None, key
        assert len(x["points"]) >= 3 and all(len(p) > 20 for p in x["points"]) and len(x["example"]) > 20, key
        assert x["sources"] and all(s in SOURCES for s in x["sources"]), key
        assert x["asof"] in ("2026-10-13", "2026-10-26"), key
    assert set(LESSONS) == set(_keys(cat))
    assert lesson("ETF 구조", 1, version=1) is None                              # 노트북 재현용 v1 카탈로그에는 붙이지 않는다


def test_unit_checks_cover_all_units_without_reusing_diagnostic_questions():
    cat = Catalog.default()
    assert set(UNIT_CHECKS) == set(_keys(cat))
    diag = {q["text"] for q in QUESTIONS}
    for key, q in UNIT_CHECKS.items():
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4 and 0 <= q["answer"] < 4, key
        assert q["text"] not in diag and len(q["explain"]) > 10, key              # 진단 결과에 공개된 문항을 다시 쓰지 않는다
    counts = Counter(q["answer"] for q in UNIT_CHECKS.values())
    assert set(counts) == {0, 1, 2, 3} and max(counts.values()) - min(counts.values()) <= 1   # 찍기 방지: 정답 위치 균형
    q = unit_check("채권 ETF", 3)
    q["options"].append("x")
    assert len(UNIT_CHECKS[("채권 ETF", 3)]["options"]) == 4 and unit_check("없는 주제", 1) is None
