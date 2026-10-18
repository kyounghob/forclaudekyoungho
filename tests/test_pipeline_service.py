import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

from etfrec.api import create_app
from etfrec.config import GuardrailConfig
from etfrec.service import LearnerInput, RecommendationService


def test_pipeline_outputs(small_bundle):
    b = small_bundle
    assert all(q["passed"] for q in b.qa) and len(b.qa) > 50
    assert set(b.results.method) >= {"Global", "RouterNoGender", "RouterFull", "POP", "RULE", "CONTENT", "UCF", "ICF", "Random", "MF_BPR", "MLP_BPR", "MLP_BPRU", "MLP_NEXT"}
    assert np.isfinite(b.results[["ndcg", "ndcg_active", "diversity"]].values).all()
    r = b.results.set_index("method")
    assert (r.ndcg_active >= r.ndcg).all() and r.active_users.min() > 0 and b.privacy["router_leaves"]["RouterNoGender"]["leaves"] > 0     # 활성 사용자 기준은 항상 크거나 같다
    assert np.allclose(r.ndcg_active * r.active_users, r.ndcg * r.users) and r.active_users.nunique() == 1
    g = b.group_results
    assert {"ndcg_active", "active_share", "active_users"} <= set(g.columns) and (g.active_users <= g.users).all()
    assert b.test_audit["raw_positive_users"] >= b.test_audit["eligible_positive_users"] == int(r.active_users.iloc[0])
    assert b.selection["operational_algorithm"] is not None
    assert len(b.algos) > 1000 and len(b.signal_meta) >= 140


def test_offline_online_parity(small_bundle):
    """오프라인 평가에서 라우터가 고른 Top-5와 서비스 추천이 같은 사용자에서 일치한다(평가와 같은 가드레일)."""
    svc = RecommendationService(small_bundle)
    users = small_bundle.test_users
    hits = 0
    for row in range(0, len(users), max(1, len(users) // 15)):
        uid = int(users[row])
        expected = [int(i) for i in small_bundle.predictions["RouterNoGender"][row] if i >= 0]
        got = [it["item"] for it in svc.recommend(uid, k=5, algorithm="RouterNoGender", guard=small_bundle.config.guardrail)["items"]]
        assert got == expected, (uid, got, expected)
        hits += 1
    assert hits >= 10


def test_adhoc_learner_and_guardrails(small_bundle):
    svc = RecommendationService(small_bundle)
    li = LearnerInput(age=25, interests=[2, 10], placement=1, mobile=1, events=[dict(item=0, quiz_pass=True), dict(item=6, complete=True)])
    r = svc.recommend(li, k=5)
    assert len(r["items"]) == 5 and all(c["passed"] for c in r["checks"])
    assert all(it["level"] - r["level"] < 2 for it in r["items"]) and sum(it["level"] - r["level"] == 1 for it in r["items"]) <= 1
    assert 0 not in [it["item"] for it in r["items"]]
    r2 = svc.recommend(li, k=5, guard=GuardrailConfig(plus_one_max=0))
    assert all(it["level"] == r2["level"] or it["level"] < r2["level"] for it in r2["items"])
    r3 = svc.recommend(li, k=5, topic_cap=1)
    assert len({it["topic"] for it in r3["items"]}) == len(r3["items"])
    sim = svc.recommend(li, k=5, assume_passed=[r["items"][0]["item"]])
    assert r["items"][0]["item"] not in [it["item"] for it in sim["items"]]
    pre = svc.recommend(li, k=5, guard=GuardrailConfig(prereq_block=True))
    assert all(not it["missing_prereqs"] for it in pre["items"]) and pre["roadmap"]["current_stage"] in ("core", "goal", "advanced", "connect")


def test_roadmap_types_quiz_sources_service(small_bundle):
    svc = RecommendationService(small_bundle)
    li = LearnerInput(age=45, goal="pension", horizon="long", risk=0, interests=[17], placement=1, events=[dict(item=0, quiz_pass=True)])
    rm = svc.roadmap(li)
    assert rm["goal"] == "pension" and rm["current_stage"] == "core" and rm["next_unit"] and rm["stages"][-1]["types"]
    assert rm["stages"][1]["units"][0]["sources"][0]["name"]
    ty = svc.types(li)
    assert ty["cards"][0]["recommended_for_goal"] and ty["cards"][0]["stats"] is not None and ty["universe"]["kind"] in ("sample", "snapshot")
    lev = next(c for c in ty["cards"] if c["key"] == "leverage_inverse")
    assert "사전교육" in lev["regulation"] and "불가" in lev["pension"]
    qs = svc.quiz_questions(); assert len(qs) >= 12
    sc = svc.quiz_score({qs[0]["id"]: 1}); assert sc["level"] in (1, 2, 3) and "results" in sc
    assert svc.sources()["sources"] and svc.sources()["type_stats"]
    ex = svc.recommend(0, k=5); assert ex["learner"]["goal"] in ("pension", "income", "long_term", "trading", "diversify") and "roadmap" in ex


def test_gender_flip_invariance_operational(small_bundle):
    svc = RecommendationService(small_bundle)
    users = small_bundle.test_users[:40]
    for uid in users:
        base = svc.recommend(int(uid), k=5)
        flip = svc.recommend(int(uid), k=5, overrides={"gender": 1 - base["segment"]["gender"]["code"]})
        assert [i["item"] for i in base["items"]] == [i["item"] for i in flip["items"]]


def test_all_families_serve_adhoc(small_bundle):
    svc = RecommendationService(small_bundle)
    li = LearnerInput(age=40, interests=[5], placement=2, events=[dict(item=15, quiz_pass=True), dict(item=16, complete=True)])
    for fam in small_bundle.selection["families"]:
        r = svc.recommend(li, k=3, algorithm=fam)
        assert len(r["items"]) == 3, fam


def test_recommend_new_and_errors(small_bundle):
    svc = RecommendationService(small_bundle)
    assert len(svc.recommend_new([0, 3], 1, 5)["items"]) == 5
    with pytest.raises(ValueError):
        svc.recommend(-1)
    with pytest.raises(ValueError):
        svc.recommend(0, k=0)
    with pytest.raises(ValueError):
        svc.recommend(0, overrides={"height": 1})


def test_api_endpoints(small_bundle, tmp_path):
    app = create_app(small_bundle, designs_dir=str(tmp_path))
    c = TestClient(app)
    assert c.get("/api/health").json()["training_in_request"] is False
    assert len(c.get("/api/catalog").json()["items"]) == small_bundle.catalog.n_items
    r = c.post("/api/recommend", json={"learner_id": 1, "k": 5}); assert r.status_code == 200 and len(r.json()["items"]) <= 5
    r = c.post("/api/recommend", json={"learner": {"age": 30, "interests": [1], "placement": 1}, "k": 3}); assert r.status_code == 200
    assert c.post("/api/recommend", json={"learner_id": 1, "k": 0}).status_code == 422
    assert c.post("/api/recommend", json={"k": 5}).status_code == 422
    assert c.get("/api/learners/999999").status_code == 422
    assert c.post("/api/parse", json={"text": "채권 ETF 초급 모바일"}).json()["fields"]["interests"]
    assert c.post("/api/compare", json={"learner_id": 1, "k": 5, "methods": ["RULE", "UCF"]}).status_code == 200
    assert len(c.get("/api/evaluation").json()["results"]) >= 10
    assert c.post("/api/designs", json={"name": "t1", "payload": {"summary": "x"}}).status_code == 200
    assert c.get("/api/designs/t1").status_code == 200 and c.delete("/api/designs/t1").status_code == 200
    assert c.post("/api/parse-log", json={"csv_text": "item,quiz_pass\n0,1\n"}).json()["events"][0]["item"] == 0
    assert c.post("/api/roadmap", json={"learner": {"goal": "income", "placement": 2}}).json()["goal"] == "income"
    assert c.post("/api/types", json={"goal": "trading", "risk": 2}).json()["cards"][0]["key"] == "leverage_inverse"
    qs = c.get("/api/quiz").json(); assert len(qs) >= 12
    assert c.post("/api/quiz/score", json={"answers": {qs[0]["id"]: 1}}).status_code == 200
    assert c.get("/api/sources").json()["universe_rows"] > 0 and "pension" in c.get("/api/goals").json()["goals"]
    assert c.post("/api/recommend", json={"learner": {"goal": "nope"}, "k": 3}).status_code == 422


@pytest.mark.skipif(not os.environ.get("ETFREC_FULL"), reason="전체 규모 재현은 ETFREC_FULL=1 일 때만 (약 2~3분)")
def test_full_regression_matches_notebook():
    from etfrec.config import TrainConfig
    from etfrec.data import Dataset
    from etfrec.pipeline import train
    cfg = TrainConfig(catalog_version=1, generator_version=1)
    b = train(Dataset.synthetic(cfg), cfg, out_dir=None, log=lambda *a, **k: None)
    got = b.results.set_index("method").ndcg
    for k, v in NOTEBOOK_V1.items():
        assert abs(got[k] - v) < 5e-5, (k, got[k], v)


NOTEBOOK_V1 = {"RULE": 0.17123, "Global": 0.17123, "RouterNoGender": 0.17119, "RouterFull": 0.17116, "RouterNoGenderIncome": 0.15702,
               "NoDemographics": 0.15355, "UCF": 0.14268, "POP": 0.11875, "ICF": 0.11112, "CONTENT": 0.09957, "MF": 0.09264,
               "MF_OBS": 0.07099, "Random": 0.05993, "MLP": 0.05325}


def test_committed_v1_results_match_notebook():
    """저장소에 커밋된 v1 결과가 노트북 B의 14개 기록과 5자리까지 같은지(코드 재학습 검사는 ETFREC_FULL=1의 전체 재현)."""
    import pandas as pd
    path = os.path.join(os.path.dirname(__file__), "..", "artifacts", "bundle_v1", "test_results.csv")
    if not os.path.exists(path):
        pytest.skip("artifacts/bundle_v1 없음")
    got = pd.read_csv(path, encoding="utf-8-sig").set_index("method").ndcg
    for k, v in NOTEBOOK_V1.items():
        assert abs(got[k] - v) < 5e-5, (k, got[k], v)


def test_adhoc_drop_cannot_coexist_with_complete(small_bundle):
    svc = RecommendationService(small_bundle)
    li = LearnerInput(age=30, interests=[1], placement=1, events=[dict(item=0, complete=True, drop=True), dict(item=3, quiz_pass=True)])
    lg = svc._adhoc_log(li)
    assert not (lg["drop"] & lg.complete).any() and bool(lg.complete.iloc[0]) and not bool(lg["drop"].iloc[0])
    assert bool(lg.quiz.iloc[1]) and bool(lg.complete.iloc[1])     # 통과 ⇒ 퀴즈 ⇒ 완료
    r = svc.recommend(li, k=3)
    assert len(r["items"]) == 3                                   # 정규화 후에도 정상 추천


def test_dataset_normalizes_event_flags():
    import pandas as pd
    from etfrec.config import TrainConfig
    from etfrec.data import Dataset, normalize_event_flags
    ds = Dataset.synthetic(TrainConfig(n_learners=200))
    assert ds.event_repairs["rows_changed"] == 0                  # 모의 생성기는 구성상 논리를 만족한다
    bad = ds.log.head(4).copy()
    bad.loc[bad.index[0], ["complete", "drop"]] = [True, True]
    bad.loc[bad.index[1], ["quiz", "quiz_pass", "complete"]] = [False, True, False]
    fixed, rep = normalize_event_flags(bad)
    assert rep["drop_cleared_by_complete"] >= 1 and rep["quiz_from_pass"] >= 1 and rep["complete_from_quiz"] >= 1
    assert not (fixed["drop"] & fixed.complete).any() and (fixed.quiz_pass <= fixed.quiz).all() and (fixed.quiz <= fixed.complete).all()
    one = ds.log.head(1).copy()                                     # 한 행에 세 가지 수정 → 행 수 1, 플래그 수정 3
    one.loc[one.index[0], ["quiz_pass", "quiz", "complete", "drop"]] = [True, False, False, True]
    _, rep1 = normalize_event_flags(one)
    assert rep1["rows_changed"] == 1 and rep1["flag_fixes"] == 3
    lg = ds.log.copy(); lg["score"] = 7                              # 입력 점수는 고치지 않은 행에서 유지되고, 고친 행만 다시 채점
    lg.loc[lg.index[0], ["complete", "drop"]] = [True, True]
    ds2 = Dataset(ds.profiles, lg, ds.catalog)
    assert ds2.event_repairs["rows_changed"] == 1 and (ds2.log.score.values[1:] == 7).all() and ds2.log.score.values[0] in (2, 3)


def test_pairwise_models_cover_only_pair_users(small_bundle):
    obs = small_bundle.models.observed
    for (snap, kind), w in obs.items():
        if kind in ("mlp9_bpr", "mlp9_bpru", "mlp9_next"):          # 쌍에 나온 사용자만 '학습됨'
            assert int(w.user_seen.sum()) == w.audit["pair_users"] == w.audit["users_with_pairs"]
    m = {k: w for (s, k), w in obs.items() if s == small_bundle.reference.snapshot_key}
    assert m["mlp9"].user_seen.sum() > m["mlp9_bpru"].user_seen.sum()   # 통과가 없는 사용자는 쌍별 모델에서 콘텐츠 대체 점수


def test_leakage_probe_detects_future_reads(monkeypatch):
    from etfrec import pipeline
    from etfrec.config import TrainConfig
    from etfrec.data import Dataset
    from etfrec.features import build_features
    ds = Dataset.synthetic(TrainConfig(n_learners=300))
    ok, _ = pipeline.leakage_probe(ds, ds.catalog, (2, 3))
    assert ok
    monkeypatch.setattr(pipeline, "feature_store", lambda p, lg, c, w: build_features(p, lg[lg.week <= w], c, w))   # 정답 주를 읽는 잘못된 구현
    ok2, detail = pipeline.leakage_probe(ds, ds.catalog, (2, 3))
    assert not ok2 and "달라진 주 [2, 3]" in detail


def test_pair_pools_use_full_rows_when_training_rows_are_subsampled():
    from etfrec import neural
    from etfrec.config import TrainConfig
    from etfrec.data import Dataset
    from etfrec.signals import supervised_from_log
    ds = Dataset.synthetic(TrainConfig(n_learners=400))
    lg = ds.log[ds.log.week < 3]
    sup = supervised_from_log(lg, cap=int(len(lg) * 0.6), n_items=ds.catalog.n_items)
    assert len(sup["u"]) < len(lg) and sup["pair_rows"] is not None and len(sup["pair_rows"]["u"]) == len(lg)
    w = neural.fit_observed_model(sup["u"], sup["i"], sup["y"], sup["score"], ds.n_users, ds.catalog.n_items, "mlp9_bpru", epochs=1,
                                  pair_rows=sup["pair_rows"])
    assert w.audit["pair_source_rows"] == len(lg)
    pr = sup["pair_rows"]
    pairs = neural._observed_pairs(pr["u"], pr["i"], pr["y"], ds.catalog.n_items, np.random.default_rng(0), mode="unobserved")
    seen = set(zip(pr["u"].tolist(), pr["i"].tolist()))
    assert not any((u, j) in seen for u, j in zip(pairs["u"].tolist(), pairs["j"].tolist()))   # 미관측 음성은 실제로 시도한 단원이 아니다


def test_api_universe_has_no_local_paths(small_bundle, tmp_path, monkeypatch):
    """/api/types·/api/sources·/api/meta의 universe에는 화면에 필요한 필드만 있다(로컬 경로·내려받은 파일 경로·오류 원문 없음)."""
    import json
    from etfrec.sources import sync_all
    from etfrec.sources.sync import SAMPLE_ETF
    monkeypatch.delenv("KRX_OPEN_API_KEY", raising=False)
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
    home = tmp_path / "Users" / "hong.gildong" / "Downloads"
    home.mkdir(parents=True)
    src = home / "data_4601_20261013.csv"
    src.write_bytes(open(SAMPLE_ETF, "rb").read())
    snap = str(tmp_path / "snap")
    sync_all(snap, krx_csv=str(src), krx_csv_date="20261013")
    sync_all(snap, krx_csv=str(home / "없는파일.csv"))
    c = TestClient(create_app(small_bundle, designs_dir=str(tmp_path / "d"), sources_dir=snap))
    for r in (c.get("/api/sources"), c.get("/api/meta"), c.post("/api/types", json={"goal": "pension", "risk": 1})):
        assert r.status_code == 200
        u = r.json()["universe"]
        text = json.dumps(u, ensure_ascii=False)
        assert u["kind"] == "snapshot" and "path" not in u and "detail" not in u and "hong.gildong" not in text and str(tmp_path) not in text
