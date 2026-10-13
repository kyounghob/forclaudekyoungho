import numpy as np
import pandas as pd

from etfrec.catalog import Catalog
from etfrec.config import GOAL_KEYS
from etfrec.quiz import QUESTIONS, public_questions, score_quiz
from etfrec.roadmap import build_roadmap, roadmap_priority, roadmap_priority_rows
from etfrec.sources import load_etf_universe, type_stats
from etfrec.sources.krx import classify_row, normalize
from etfrec.sources.registry import SOURCES
from etfrec.taxonomy import ETF_TYPES, ROADMAP_TEMPLATES, TYPE_BY_KEY

cat = Catalog.default()


def test_catalog_v2_has_prereqs_without_cycles():
    assert cat.n_items == 63 and cat.n_topics == 21
    P = cat.prereq_matrix.astype(int); R = P.copy()
    for _ in range(12):
        R = ((R @ P) > 0).astype(int) | R
    assert not np.diag(R).any()
    for i in range(cat.n_items):
        if cat.item_level[i] > 1:
            assert cat.unit(cat.topics[cat.item_topic[i]], cat.item_level[i] - 1) in cat.prereqs[i]
    assert Catalog.default(version=1).n_items == 60


def test_roadmap_orders_prereqs_first_and_tracks_status():
    passed = np.zeros(cat.n_items, bool)
    for goal in GOAL_KEYS:
        rm = build_roadmap(cat, goal, 1, "mid", 1, passed)
        seen = set()
        for s in rm["stages"]:
            for u in s["units"]:
                for p in cat.prereqs[u["item"]]:
                    assert p in seen or p not in {x["item"] for st in rm["stages"] for x in st["units"]}, (goal, u["title"])
                seen.add(u["item"])
        assert rm["current_stage"] == "core" and rm["next_unit"] is not None and rm["units_total"] >= 15
        assert set(rm["types"]) <= set(TYPE_BY_KEY)
    passed[:] = True
    rm = build_roadmap(cat, "pension", 1, "long", 3, passed)
    assert rm["current_stage"] == "connect" and rm["progress"] == 1.0 and rm["minutes_left"] == 0


def test_roadmap_priority_rows_and_risk_filter():
    passed = np.zeros((3, cat.n_items), bool); passed[1, cat.unit("ETF 구조", 1)] = True
    pr = roadmap_priority_rows(cat, ["trading", "trading", "pension"], np.array([0, 2, 1]), ["short", "short", "long"], np.array([1, 1, 2]), passed)
    assert pr.shape == (3, cat.n_items) and pr.max() == 1.0
    lev3 = cat.unit("레버리지·인버스", 3)
    assert pr[0, lev3] == 0 and pr[1, lev3] > 0          # 안정 성향에서는 레버리지 심화가 로드맵 밖


def test_quiz_scoring_levels_and_events():
    assert len(public_questions()) == len(QUESTIONS) and "answer" not in public_questions()[0]
    none = score_quiz({}, cat); assert none["level"] == 1 and none["correct"] == 0 and not none["events"]
    full = score_quiz({q["id"]: q["answer"] for q in QUESTIONS}, cat)
    assert full["level"] == 3 and len(full["events"]) == len(QUESTIONS) and all(e["quiz_pass"] for e in full["events"])
    wrong = score_quiz({q["id"]: (q["answer"] + 1) % 4 for q in QUESTIONS}, cat)
    assert wrong["level"] == 1 and not wrong["events"]


def test_taxonomy_concepts_exist_in_catalog():
    for t in ETF_TYPES:
        for tp, lv in t["concepts"]:
            assert cat.unit(tp, lv) is not None, (t["key"], tp, lv)
    for g, tpl in ROADMAP_TEMPLATES.items():
        for tp, lv in tpl["core"] + tpl["advanced"]:
            assert cat.unit(tp, lv) is not None, (g, tp, lv)


def test_krx_classification_and_sample_universe():
    df = normalize(pd.DataFrame([
        dict(ISU_ABBRV="예시 코스피200", IDX_MKT_CLSS_NM="국내", IDX_ASST_CLSS_NM="주식", ETF_TOT_FEE="0.05"),
        dict(ISU_ABBRV="예시 레버리지", IDX_MKT_CLSS_NM="국내", IDX_ASST_CLSS_NM="주식", ETF_TOT_FEE="0.64"),
        dict(ISU_ABBRV="예시 미국S&P500(H)", IDX_MKT_CLSS_NM="해외", IDX_ASST_CLSS_NM="주식", ETF_TOT_FEE="0.09"),
        dict(ISU_ABBRV="예시 국고채10년", IDX_MKT_CLSS_NM="국내", IDX_ASST_CLSS_NM="채권", ETF_TOT_FEE="0.05"),
        dict(ISU_ABBRV="예시 나스닥100커버드콜", IDX_MKT_CLSS_NM="해외", IDX_ASST_CLSS_NM="주식", ETF_TOT_FEE="0.37"),
    ]))
    assert df.etf_type.tolist() == ["kr_broad", "leverage_inverse", "global_equity", "bond", "income"]
    assert df.hedged.tolist() == [False, False, True, False, False] and df.pension_eligible.tolist() == [True, False, True, True, True]
    uni, prov = load_etf_universe("/nonexistent")
    assert prov["kind"] == "sample" and len(uni) >= 40
    stats = {t["key"]: t for t in type_stats(uni)}
    assert stats["leverage_inverse"]["count"] >= 3 and stats["global_equity"]["hedged"] >= 1
    assert all(SOURCES[k]["name"] for k in SOURCES) and "kcie_etf_school" in SOURCES
