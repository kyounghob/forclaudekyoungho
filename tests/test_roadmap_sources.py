import numpy as np
import pandas as pd

from etfrec.catalog import Catalog
from etfrec.config import GOAL_KEYS
from etfrec.quiz import QUESTIONS, public_questions, score_quiz
from etfrec.roadmap import build_roadmap, roadmap_priority, roadmap_priority_rows
from etfrec.privacy import generalization_plan, k_anonymity
from etfrec.sources import load_etf_universe, sync_all, type_stats
from etfrec.sources.sync import SAMPLE_ETF
from etfrec.sources.krx import classify_row, normalize
from etfrec.sources.registry import SOURCES
from etfrec.taxonomy import ETF_TYPES, LEVERAGE_RULES, PENSION_OK, ROADMAP_TEMPLATES, TYPE_BY_KEY
from etfrec.lessons import LESSONS

cat = Catalog.default()


def test_catalog_v2_has_prereqs_without_cycles():
    assert cat.n_items == 66 and cat.n_topics == 22 and cat.unit("절세 계좌", 3) is not None
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
    items = [e["item"] for e in full["events"]]
    units = {cat.unit(q["topic"], q["level"]) for q in QUESTIONS if q.get("marks_pass", True)}
    assert full["level"] == 3 and len(items) == len(set(items)) == len(units) and all(e["quiz_pass"] for e in full["events"])
    wrong = score_quiz({q["id"]: (q["answer"] + 1) % 4 for q in QUESTIONS}, cat)
    assert wrong["level"] == 1 and not wrong["events"]


def test_quiz_is_not_gameable_and_regulation_item_does_not_skip_risk_unit():
    from collections import Counter
    pos = Counter(q["answer"] for q in QUESTIONS)
    assert max(pos.values()) <= 6                                   # 정답 위치가 한쪽에 몰리지 않음
    for k in range(4):                                              # 한 위치만 골라도 수준 1
        assert score_quiz({q["id"]: k for q in QUESTIONS}, cat)["level"] == 1
    q20 = next(q for q in QUESTIONS if q["id"] == "q20")
    lev3 = cat.unit("레버리지·인버스", 3)
    r = score_quiz({"q20": q20["answer"]}, cat)
    assert r["results"][-1]["correct"] and lev3 not in [e["item"] for e in r["events"]]
    # 같은 단원(해외 ETF 3)의 두 문항만으로는 수준 3이 되지 않는다
    base = {q["id"]: q["answer"] for q in QUESTIONS if q["level"] < 3}
    assert score_quiz(dict(base, q13=QUESTIONS[12]["answer"], q18=QUESTIONS[17]["answer"]), cat)["level"] == 2
    # 같은 단원 두 문항 중 하나를 틀리면 그 단원은 통과로 기록하지 않는다
    r2 = score_quiz({"q13": QUESTIONS[12]["answer"], "q18": (QUESTIONS[17]["answer"] + 1) % 4}, cat)
    assert cat.unit("해외 ETF", 3) not in [e["item"] for e in r2["events"]]


def test_domain_rules_lessons_and_templates():
    for k in ("1,000만원", "3,000만원", "2026-07-31", "모의거래", "2026-08-19", "2026-05-22"):
        assert k in LEVERAGE_RULES, k
    assert "70%" in PENSION_OK and "1,500만원" in PENSION_OK
    for (tp, lv) in LESSONS:
        assert cat.unit(tp, lv) is not None
        info = cat.item_info(cat.unit(tp, lv)); assert info["lesson"] and info["lesson"]["points"]
    assert Catalog.default(version=1).item_info(0)["lesson"] is None
    assert ("절세 계좌", 1) in ROADMAP_TEMPLATES["income"]["core"] and ("해외 ETF", 3) in ROADMAP_TEMPLATES["trading"]["advanced"]
    v1 = Catalog.default(version=1)
    assert "과표기준가" not in v1.concepts(v1.unit("해외 ETF", 3)) and "과표기준가" in cat.concepts(cat.unit("해외 ETF", 3))


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


def test_sync_uses_manual_csv_and_official_apis_only(tmp_path):
    prov = sync_all(str(tmp_path), krx_csv=SAMPLE_ETF)            # 키 없음: 공식 API는 건너뛰고 수동 CSV만 정규화
    assert prov["policy"] == "official-apis-and-manual-download-only" and prov["items"]["krx_etf_list"]["status"] == "ok"
    assert prov["items"]["krx_etf_daily"]["status"] == "skipped" and prov["items"]["datagokr_etf_prices"]["status"] == "skipped"
    df, info = load_etf_universe(str(tmp_path)); assert info["kind"] == "snapshot" and len(df) >= 40
    from etfrec.sources import krx
    assert not hasattr(krx, "fetch_etf_list") and not hasattr(krx, "KRX_JSON_URL")   # 비공식 화면 엔드포인트 호출 제거


def test_k_anonymity_and_generalization():
    df = pd.DataFrame(dict(age_band=[0, 0, 0, 1, 1, 1, 2], income_q=[0, 0, 0, 1, 1, 1, 4], gender=[0, 0, 0, 1, 1, 1, 0]))
    r = k_anonymity(df, ["age_band", "income_q", "gender"], k=3)
    assert r["groups"] == 3 and r["min_group"] == 1 and r["users_below_k"] == 1 and not r["satisfied"]
    plan = generalization_plan(df, ["age_band", "income_q", "gender"], k=3)
    assert plan and plan[-1]["satisfied"]


def test_bpr_models_train_and_rank():
    import pytest
    from etfrec import neural
    if not neural.HAS_TORCH:
        pytest.skip("torch 없음")
    rng = np.random.default_rng(0)
    rows = np.repeat(np.arange(30), 4); cols = (rows * 7 + rng.integers(0, 4, len(rows))) % 20
    P, Q, losses, audit = neural.train_mf_bpr(rows, cols, 30, 20, k=8, epochs=20, seed=1)
    assert P.shape == (30, 8) and Q.shape == (20, 8) and losses[-1] < losses[0] and audit["final_negative_collisions"] == 0
    pos = (P[rows] * Q[cols]).sum(1).mean(); neg = (P[rows] * Q[(cols + 10) % 20]).sum(1).mean()
    assert pos > neg                                            # 관측 양성이 미관측보다 앞선다
    u = np.repeat(np.arange(30), 6); i = (u * 3 + np.tile(np.arange(6), 30)) % 20; y = (np.tile(np.arange(6), 30) < 3).astype(np.float32)
    w = neural.fit_observed_model(u, i, y, y, 30, 20, "mlp9_bpr", seed=1, epochs=5)
    assert w.kind == "mlp9_bpr" and w.audit["pairs"] > 0 and w.audit["pairs_with_observed_negative"] > 0
    assert np.isfinite(w.score(np.array([1, 2]), np.array([1, 2]))).all()
    wu = neural.fit_observed_model(u, i, y, y, 30, 20, "mlp9_bpru", seed=1, epochs=5)
    assert wu.audit["pairs"] > 0 and wu.audit["pairs_with_observed_negative"] == 0          # 표준 BPR: 음성은 모두 미관측
    from etfrec.signals import next_week_pairs
    import pandas as pd
    log = pd.DataFrame(dict(user=u, item=i, week=np.tile(np.arange(6) % 3, 30), quiz_pass=y.astype(bool)))
    pairs = next_week_pairs(log, 20, seed=1)
    wn = neural.fit_observed_model(u, i, y, y, 30, 20, "mlp9_next", seed=1, epochs=5, pairs=pairs)
    assert wn.audit["pairs"] == len(pairs["u"]) > 0 and np.isfinite(wn.score(np.array([1]), np.array([2]))).all()
