"""실사용자 웹 서비스: 가입·로그인·세션, 관리자 경로 차단, 학습자 흐름(온보딩 → 진단 → 추천 → 단원 확인),
내 데이터 내려받기·탈퇴(운영 기록 삭제 포함), 주간 작업용 학습 데이터 내보내기, 관리 명령."""
import json
import os
import time
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from etfrec.catalog import Catalog
from etfrec.config import GuardrailConfig
from etfrec.data import Dataset
from etfrec.evaluation import primary_eval
from etfrec.features import feature_store
from etfrec.ops.logstore import OpsLog
from etfrec.ops.loop import default_settings
from etfrec.ops.policies import declared_spec
from etfrec.ops.registry import PolicyRegistry
from etfrec.quiz import QUESTIONS
from etfrec.web.store import WebStore

H = {"X-Requested-With": "etfrec"}
PROFILE = dict(goal="long_term", horizon="long", risk=1, exp=0, interests=[0, 3], mobile=1)


def make_client(bundle, tmp_path, ops=None, public=True, **kw):
    from fastapi.testclient import TestClient
    from etfrec.api import create_app
    from etfrec.web.app import WebConfig
    cfg = WebConfig(db_path=str(tmp_path / "web.db"), public=public, **kw)
    return TestClient(create_app(bundle, designs_dir=str(tmp_path / "d"), ops_dir=ops, web=cfg))


def signup(c, name="learner1", pw="correct-horse-1"):
    r = c.post("/api/auth/signup", json=dict(username=name, password=pw, consent=True), headers=H)
    assert r.status_code == 200, r.text
    return r


def test_public_mode_serves_learner_app_and_gates_admin_apis(small_bundle, tmp_path):
    c = make_client(small_bundle, tmp_path)
    home = c.get("/")
    assert home.status_code == 200 and "/static/learn/learn.js" in home.text
    for h, v in (("x-frame-options", "DENY"), ("x-content-type-options", "nosniff")):
        assert home.headers[h] == v
    assert "script-src 'self'" in home.headers["content-security-policy"] and "strict-transport-security" not in home.headers
    r = c.get("/studio", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?admin=1"
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404     # 공개 모드는 API 문서를 열지 않는다
    assert c.get("/api/health").status_code == 200 and c.get("/api/quiz").status_code == 200    # 공개해도 되는 것만 열림
    for method, path in (("GET", "/api/meta"), ("GET", "/api/learners"), ("POST", "/api/recommend"), ("GET", "/api/ops/status"),
                         ("GET", "/api/evaluation"), ("GET", "/api/sources"), ("POST", "/api/feedback"), ("GET", "/api/designs")):
        r = c.request(method, path, json={})
        assert r.status_code == 401, (path, r.status_code)
        assert r.headers["cache-control"] == "no-store" and "content-security-policy" in r.headers   # 차단 응답에도 보안 헤더
    cfg = c.get("/api/public/config").json()
    assert cfg["invite_required"] is False and len(cfg["topics"]) == small_bundle.catalog.n_topics and "연령" in cfg["consent_text"]
    signup(c)
    assert c.get("/api/meta").status_code == 403                                   # 일반 학습자는 관리자 API를 못 쓴다
    assert c.get("/studio", follow_redirects=False).status_code == 303
    c.app.state.web_store.create_user("teacher", "admin-pass-123", is_admin=True)
    c.post("/api/auth/logout", headers=H)
    r = c.post("/api/auth/login", json=dict(username="teacher", password="admin-pass-123"), headers=H)
    assert r.status_code == 200 and r.json()["is_admin"] is True
    assert c.get("/api/meta").status_code == 200 and c.get("/studio").status_code == 200
    assert c.get("/api/learners").status_code == 403                               # 공개 모드는 관리자에게도 모의 학습자 표를 열지 않는다


def test_local_web_mode_keeps_studio_at_root(small_bundle, tmp_path):
    c = make_client(small_bundle, tmp_path, public=False)
    assert "/static/learn/learn.js" not in c.get("/").text and "/static/learn/learn.js" in c.get("/learn").text
    assert c.get("/api/meta").status_code == 200 and c.get("/studio").status_code == 404
    assert c.get("/docs").status_code == 200 and "content-security-policy" not in c.get("/docs").headers


def test_signup_login_session_and_csrf_header(small_bundle, tmp_path):
    c = make_client(small_bundle, tmp_path)
    body = dict(username="learner1", password="correct-horse-1", consent=True)
    assert c.post("/api/auth/signup", json=body).status_code == 403               # 같은 화면 머리글 없음
    assert c.post("/api/auth/signup", json={**body, "consent": False}, headers=H).status_code == 422
    for bad in (dict(username="A!"), dict(password="short"), dict(username="samepass", password="samepass")):
        assert c.post("/api/auth/signup", json={**body, **bad}, headers=H).status_code == 422, bad
    r = signup(c)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie and "secure" not in cookie
    assert c.post("/api/auth/signup", json=body, headers=H).status_code == 409
    me = c.get("/api/me").json()
    assert me["username"] == "learner1" and me["profile_complete"] is False and me["is_admin"] is False
    assert c.put("/api/me/profile", json=PROFILE).status_code == 403              # 상태 변경은 머리글 필수
    assert c.post("/api/auth/logout").status_code == 403
    assert c.post("/api/auth/logout", headers=H).status_code == 200 and c.get("/api/me").status_code == 401
    assert c.post("/api/auth/login", json=dict(username="learner1", password="wrong-pass-1"), headers=H).status_code == 401
    assert c.post("/api/auth/login", json=dict(username="nobody", password="wrong-pass-1"), headers=H).status_code == 401
    assert c.post("/api/auth/login", json=dict(username="LEARNER1", password="correct-horse-1"), headers=H).status_code == 200
    raw = open(tmp_path / "web.db", "rb").read()
    assert b"correct-horse-1" not in raw and b"scrypt$" in raw                    # 비밀번호는 해시로만


def test_login_rate_limit_and_invite_code(small_bundle, tmp_path):
    c = make_client(small_bundle, tmp_path, invite_code="class-2026")
    assert c.get("/api/public/config").json()["invite_required"] is True
    body = dict(username="learner1", password="correct-horse-1", consent=True)
    assert c.post("/api/auth/signup", json=body, headers=H).status_code == 403
    assert c.post("/api/auth/signup", json={**body, "invite_code": "class-2026"}, headers=H).status_code == 200
    for _ in range(8):
        assert c.post("/api/auth/login", json=dict(username="learner1", password="bad-guess-00"), headers=H).status_code == 401
    r = c.post("/api/auth/login", json=dict(username="learner1", password="correct-horse-1"), headers=H)
    assert r.status_code == 429                                                    # 아이디별 실패 8회 → 15분 차단


def test_rate_limiter_keeps_no_state_for_lookups_only():
    from etfrec.web.security import RateLimiter
    rl = RateLimiter()
    for i in range(500):
        assert not rl.blocked(f"login-user:random{i}", 8, 900)          # 조회만 한 키는 메모리에 남지 않는다
    assert rl.hits == {}
    assert all(rl.take("signup:1.2.3.4", 3, 3600) for _ in range(3)) and not rl.take("signup:1.2.3.4", 3, 3600)
    rl.hit("login-ip:5.6.7.8", 900)
    assert len(rl.hits["signup:1.2.3.4"]) == 3 and len(rl.hits["login-ip:5.6.7.8"]) == 1


def test_learner_flow_logs_impressions_and_feedback_then_delete_purges(small_bundle, tmp_path):
    ops = str(tmp_path / "ops")
    PolicyRegistry.init(ops, declared_spec(), default_settings())
    c = make_client(small_bundle, tmp_path, ops=ops)
    catalog = small_bundle.catalog
    signup(c)
    assert c.get("/api/me/recommendations").status_code == 409                    # 목적·성향 입력 전
    assert c.put("/api/me/profile", json={**PROFILE, "interests": [0, 1, 2]}, headers=H).status_code == 422
    assert c.put("/api/me/profile", json={**PROFILE, "risk": 5}, headers=H).status_code == 422
    assert c.put("/api/me/profile", json=PROFILE, headers=H).json()["complete"] is True
    qs = c.get("/api/me/quiz").json()
    assert qs and all("answer" not in q and "explain" not in q for q in qs)
    l1 = {q["id"]: q["answer"] for q in QUESTIONS if q["level"] == 1}
    d = c.post("/api/me/diagnosis", json=dict(answers=l1), headers=H).json()
    known = {int(e["item"]) for e in d["events"]}
    assert known and c.get("/api/me").json()["profile"]["diagnosis"]["units"] == len(known)

    r = c.get("/api/me/recommendations?k=5").json()
    items = [it["item"] for it in r["items"]]
    assert items and not known & set(items) and r["checks_passed"] is True and r["week"] == 0
    assert set(r["items"][0]) >= {"title", "reason", "level_name", "minutes", "has_check"}
    log = OpsLog(os.path.join(ops, "logs"))
    imp = log.impressions(0)
    assert len(imp) == 1 and imp[0]["user_ref"] == 0 and imp[0]["request_id"] == r["request_id"] and imp[0]["source"] == "web"
    assert imp[0]["items"] == items and all(0 < p <= 1 for p in imp[0]["propensity"])

    q2 = next(q for q in QUESTIONS if q["level"] == 2 and q.get("marks_pass", True) and catalog.unit(q["topic"], 2) is not None)
    unit = int(catalog.unit(q2["topic"], 2))
    u = c.get(f"/api/me/units/{unit}").json()
    assert u["check"]["text"] == q2["text"] and "answer" not in u["check"] and u["status"]["passed"] is False
    wrong = (q2["answer"] + 1) % len(q2["options"])
    send = lambda b: c.post(f"/api/me/units/{unit}/progress", json={**b, "request_id": r["request_id"]}, headers=H)
    assert send(dict(action="check", answer=wrong)).json()["correct"] is False
    ok = send(dict(action="check", answer=q2["answer"])).json()
    assert ok["correct"] is True and ok["status"]["passed"] is True
    assert send(dict(action="save")).json()["status"]["saved"] is True
    assert send(dict(action="watch")).status_code == 422
    with_q = {int(catalog.unit(q["topic"], q["level"])) for q in QUESTIONS if q.get("marks_pass", True) and catalog.unit(q["topic"], q["level"]) is not None}
    free = next(i for i in range(catalog.n_items) if i not in with_q and i not in known)
    assert c.post(f"/api/me/units/{free}/progress", json=dict(action="check"), headers=H).status_code == 422
    sc = c.post(f"/api/me/units/{free}/progress", json=dict(action="check", self_check=True), headers=H).json()
    assert sc["self_check"] is True and sc["status"]["passed"] is True
    assert c.get("/api/me/units/999").status_code == 404
    fb = [f for f in log.feedback(0) if f["event"] != "view"]                       # 단원 열람(view)은 따로 확인한다
    assert [(f["item"], f["event"]) for f in fb] == [(unit, "quiz_pass"), (unit, "save"), (free, "quiz_pass")]
    assert fb[0]["request_id"] == r["request_id"] and all(f["user_ref"] == 0 for f in fb)       # 오답은 반응으로 남기지 않는다
    hist = c.get("/api/me/history").json()
    assert hist[0]["item"] == free and hist[0]["self_check"] is True and any(h["kind"] == "진단 통과" for h in hist)
    assert unit not in [it["item"] for it in c.get("/api/me/recommendations").json()["items"]]      # 통과 단원은 다시 추천하지 않는다
    rm = c.get("/api/me/roadmap").json()
    assert rm["units_passed"] >= 1 and rm["stages"]
    assert c.get("/api/me/types").json()["cards"]

    ex = c.get("/api/me/export")
    assert ex.status_code == 200 and "attachment" in ex.headers["content-disposition"]
    assert '"pw"' not in ex.text and "scrypt" not in ex.text and len(ex.json()["events"]) >= 3

    assert c.request("DELETE", "/api/me", json=dict(password="wrong-pass-1"), headers=H).status_code == 401
    assert c.request("DELETE", "/api/me", json=dict(password="correct-horse-1")).status_code == 403
    assert c.request("DELETE", "/api/me", json=dict(password="correct-horse-1"), headers=H).json() == {"deleted": True}
    assert c.get("/api/me").status_code == 401
    assert log.impressions(0) == [] and log.feedback(0) == []                     # 탈퇴하면 운영 기록도 지운다
    assert c.app.state.web_store.stats()["users"] == 0


def test_pilot_instrumentation_records_lists_views_ratings_review_and_survey(small_bundle, tmp_path):
    ops = str(tmp_path / "ops")
    PolicyRegistry.init(ops, declared_spec(), default_settings())
    c = make_client(small_bundle, tmp_path, ops=ops)
    store = c.app.state.web_store
    signup(c)
    c.put("/api/me/profile", json=PROFILE, headers=H)
    l1 = {q["id"]: q["answer"] for q in QUESTIONS if q["level"] == 1}
    d = c.post("/api/me/diagnosis", json=dict(answers=l1), headers=H).json()
    known = [m["item"] for m in d["mastered"]]
    assert len(known) >= 2
    assert c.post("/api/me/diagnosis/review", json=dict(items=[999]), headers=H).status_code == 422
    rv = c.post("/api/me/diagnosis/review", json=dict(items=[known[0]]), headers=H).json()
    assert rv == dict(ok=True, exempted=len(known), flagged=1, remaining=len(known) - 1)
    st = c.get(f"/api/me/units/{known[0]}").json()["status"]
    assert st["passed"] is False and st["by_diagnosis"] is False                    # 되돌린 단원은 다시 학습 대상
    assert c.get(f"/api/me/units/{known[1]}").json()["status"]["by_diagnosis"] is True

    r = c.get("/api/me/recommendations").json()
    assert r["ask_rating"] is True
    uid = store.user_by_name("learner1")["id"]
    assert store.rec(uid, r["request_id"])["items"] == [it["item"] for it in r["items"]]
    assert c.post("/api/me/rating", json=dict(request_id="nope", value=4), headers=H).status_code == 404
    assert c.post("/api/me/rating", json=dict(request_id=r["request_id"], value=6), headers=H).status_code == 422
    assert c.post("/api/me/rating", json=dict(request_id=r["request_id"], value=4), headers=H).json() == {"ok": True}
    r2 = c.get("/api/me/recommendations").json()
    assert r2["ask_rating"] is False                                                # 하루에 한 번만 묻는다

    first = r2["items"][0]["item"]
    c.get(f"/api/me/units/{first}?rid={r2['request_id']}")
    c.get(f"/api/me/units/{first}?rid={r2['request_id']}")                          # 다시 그려도 한 번으로 센다
    other = next(i for i in range(small_bundle.catalog.n_items) if i not in [it["item"] for it in r2["items"]] and i not in known)
    c.get(f"/api/me/units/{other}?rid={r2['request_id']}")                          # 목록에 없던 단원은 추천 열람이 아니다
    views = store.feedback(uid, "view")
    assert [f["item"] for f in views if f["request_id"] == r2["request_id"]] == [first]   # 목록에서 연 단원만, 한 번
    assert any(f["item"] == other and f["request_id"] is None for f in views)
    fb = OpsLog(os.path.join(ops, "logs")).feedback(0)
    assert (first, "view", r2["request_id"]) in [(f["item"], f["event"], f["request_id"]) for f in fb]

    sv = c.get("/api/me/survey").json()
    assert sv["done"] is False and sv["suggested"] is False and len(sv["items"]) == 5
    answers = {q["key"]: 4 for q in sv["items"]}
    assert c.post("/api/me/survey", json=dict(answers={**answers, "fit": 0}), headers=H).status_code == 422
    assert c.post("/api/me/survey", json=dict(answers={"fit": 5}), headers=H).status_code == 422
    assert c.post("/api/me/survey", json=dict(answers=answers, comment=" 좋아요 "), headers=H).json() == {"ok": True}
    sv = c.get("/api/me/survey").json()
    assert sv["done"] is True and sv["answers"]["comment"] == "좋아요" and sv["answers"]["days"] == 0
    ex = c.get("/api/me/export").json()
    assert len(ex["recommendations"]) == 2 and {x["kind"] for x in ex["responses"]} == {"view", "reason_rating", "diagnosis_review", "exit_survey"}
    stt = store.stats()
    assert stt["recommendation_lists"] == 2 and stt["responses"] == 3 and stt["unit_views"] >= 4
    c.request("DELETE", "/api/me", json=dict(password="correct-horse-1"), headers=H)
    dump = store.dump()
    assert dump["recs"] == [] and dump["feedback"] == []                            # 탈퇴하면 계측 기록도 지운다


def _ts(day: date, hour: int) -> float:
    return datetime(day.year, day.month, day.day, hour, 30).timestamp()


def test_export_dataset_feeds_training_and_keeps_diagnosis_out_of_targets(tmp_path):
    store = WebStore(str(tmp_path / "web.db"))
    start = date.today() - timedelta(days=21)
    store.service_start(start.isoformat())
    a = store.create_user("alpha", "alpha-pass-1")
    b = store.create_user("bravo", "bravo-pass-1")
    gone = store.create_user("charlie", "charlie-pass-1")
    for u in (a, b, gone):
        store.save_profile(u["id"], dict(PROFILE, interests=[2]))
    store.replace_diagnosis(a["id"], [0, 1], ts=_ts(start + timedelta(days=8), 9))         # 1주차 진단 인정(정답 아님)
    store.add_event(a["id"], 5, "quiz_pass", "quiz", ts=_ts(start + timedelta(days=9), 13))
    store.add_event(b["id"], 7, "complete", "web", ts=_ts(start + timedelta(days=2), 23))
    store.add_event(b["id"], 8, "quiz_pass", "self", ts=_ts(start + timedelta(days=10), 18))
    store.add_event(gone["id"], 9, "complete", "web", ts=_ts(start + timedelta(days=3), 12))
    store.delete_user(gone["id"])
    profiles, log = store.export_dataset(start)
    assert list(profiles.user) == [0, 1, 2] and set(profiles.interest2) == {-1}           # 탈퇴자도 번호 자리는 유지
    assert 2 not in set(log.user) and set(log.day) == {0} and set(log.minute) == {0} and log.hour.between(0, 3).all()
    assert sorted(log.week.tolist()) == [0, 1, 1, 1, 1] and set(log.source) == {"diagnosis", "quiz", "web", "self"}
    cat = Catalog.default()
    ds = Dataset(profiles, log, cat, source="web")
    out = tmp_path / "export"
    ds.save_csv(str(out))
    back = Dataset.from_csv(str(out))
    assert "source" in back.log.columns and (back.log.source == "diagnosis").sum() == 2
    F = feature_store(back.profiles, back.log, back.catalog, 2)
    assert F.und[0, 0] and F.und[0, 1] and F.und[0, 5]                                    # 진단 인정은 통과로 반영
    F1 = feature_store(back.profiles, back.log, back.catalog, 1)
    cands, _ = primary_eval(1, F1, back.log, back.catalog, GuardrailConfig())
    row = list(cands.user).index(0)
    assert cands.full_relevant_count[row] <= 1 and not {0, 1} & set(cands.cand[row][cands.rel[row]].tolist())   # 진단 단원은 정답이 아니다
    only_diag = back.log[back.log.source != "diagnosis"].copy()
    only_diag.loc[only_diag.user == 0, "week"] = 0                                        # 1주에 진단 인정만 남은 학습자는 평가 대상이 아니다
    users1, _ = primary_eval(1, feature_store(back.profiles, pd.concat([only_diag, back.log[back.log.source == "diagnosis"]]), back.catalog, 1),
                             pd.concat([only_diag, back.log[back.log.source == "diagnosis"]]), back.catalog, GuardrailConfig())
    assert 0 not in set(users1.user.tolist())


def test_cli_web_commands(tmp_path, monkeypatch, capsys):
    from etfrec.cli import main
    db = str(tmp_path / "web.db")
    monkeypatch.setenv("ETFREC_ADMIN_PASSWORD", "admin-pass-123")
    main(["web", "create-admin", "--db", db, "--username", "teacher"])
    store = WebStore(db)
    assert store.user_by_name("teacher")["is_admin"] == 1 and store.authenticate("teacher", "admin-pass-123")
    monkeypatch.setenv("ETFREC_ADMIN_PASSWORD", "new-pass-4567")
    main(["web", "reset-password", "--db", db, "--username", "teacher"])
    assert store.authenticate("teacher", "new-pass-4567") and not store.authenticate("teacher", "admin-pass-123")
    main(["web", "revoke-admin", "--db", db, "--username", "teacher"])
    assert store.user_by_name("teacher")["is_admin"] == 0
    with pytest.raises(SystemExit, match="서비스 시작일"):
        main(["web", "export-dataset", "--db", db, "--out", str(tmp_path / "x")])
    with pytest.raises(SystemExit, match="없는 아이디"):
        main(["web", "reset-password", "--db", db, "--username", "ghost"])
    start = date.today() - timedelta(days=14)
    store.service_start(start.isoformat())
    u = store.create_user("alpha", "alpha-pass-1")
    store.save_profile(u["id"], PROFILE)
    store.add_event(u["id"], 3, "quiz_pass", "quiz", ts=_ts(start + timedelta(days=8), 10))
    store.add_event(u["id"], 4, "complete", "web", ts=time.time())                       # 진행 중인 주: 기본 내보내기에서 빠진다
    capsys.readouterr()
    main(["web", "export-dataset", "--db", db, "--out", str(tmp_path / "exp")])
    assert "기록 1행" in capsys.readouterr().out
    assert len(Dataset.from_csv(str(tmp_path / "exp")).log) == 1
    main(["web", "backup", "--db", db, "--out", str(tmp_path / "bk.db")])
    assert WebStore(str(tmp_path / "bk.db")).user_by_name("alpha") is not None
    with pytest.raises(SystemExit, match="이미 있는 파일"):
        main(["web", "backup", "--db", db, "--out", str(tmp_path / "bk.db")])
    capsys.readouterr()
    main(["web", "stats", "--db", db])
    st = json.loads(capsys.readouterr().out)
    assert st["users"] == 2 and st["service_start"] == start.isoformat()


def test_pilot_report_computes_plan_metrics_and_technique_comparison(small_bundle, tmp_path, capsys):
    from etfrec.cli import main
    from etfrec.service import RecommendationService
    from etfrec.web.pilot import pilot_report, wilson, write_report
    db = str(tmp_path / "web.db")
    store = WebStore(db)
    store.service_start(date.today().isoformat())
    a, b, c = (store.create_user(n, n + "-pass-1") for n in ("alpha", "bravo", "charlie"))
    store.create_user("teacher", "teacher-pass-1", is_admin=True)                       # 관리자는 참가자에서 빠진다
    t0 = time.time()
    for u in (a, b):
        store.save_profile(u["id"], PROFILE)
    store.save_profile(a["id"], dict(diagnosis=dict(level=1, correct=5, answered=8, total=20, units=2)))
    store.replace_diagnosis(a["id"], [0, 1], ts=t0 + 60)
    store.unexempt(a["id"], [1])
    store.add_feedback(a["id"], "diagnosis_review", value=dict(exempted=[0, 1], flagged=[1]), ts=t0 + 70)
    store.record_rec(a["id"], "ra", [5, 6, 7, 8, 9], shortfall=0, ts=t0 + 3600)
    store.add_feedback(a["id"], "view", item=5, request_id="ra", ts=t0 + 3700)
    store.add_event(a["id"], 5, "quiz_pass", "quiz", ts=t0 + 86400)
    store.add_feedback(a["id"], "reason_rating", request_id="ra", value=4, ts=t0 + 3800)
    store.record_rec(b["id"], "rb", [10, 11, 12, 13], shortfall=1, ts=t0 + 7200)
    store.add_event(b["id"], 20, "quiz_pass", "self", ts=t0 + 2 * 86400)
    store.add_feedback(b["id"], "reason_rating", request_id="rb", value=2, ts=t0 + 7300)
    store.add_feedback(b["id"], "exit_survey", value=dict(answers=dict(fit=4, order=4, reason=4, diagnosis=4, reuse=5),
                                                          comment="예시가 더 있으면 좋겠어요", days=8), ts=t0 + 8 * 86400)
    rep = pilot_report(store, svc=RecommendationService(small_bundle), now=t0 + 9 * 86400, boot=200)
    assert rep["participants"] == 3 and rep["eligible_7d"] == 3
    assert dict(rep["funnel"])["목적·성향 입력"] == 2 and dict(rep["funnel"])["추천 단원 열람"] == 1
    assert (rep["primary"]["k"], rep["primary"]["n"]) == (1, 3) and (rep["lenient"]["k"], rep["lenient"]["n"]) == (2, 3)
    assert rep["primary"]["lo"] == pytest.approx(wilson(1, 3)["lo"]) and 0 < rep["primary"]["lo"] < 1 / 3 < rep["primary"]["hi"] < 1
    assert (rep["diagnosis"]["over_exemption"]["k"], rep["diagnosis"]["over_exemption"]["n"]) == (1, 2)
    assert rep["reason_rating"]["n"] == 2 and rep["reason_rating"]["mean"] == 3.0
    assert (rep["shortfall"]["short"]["k"], rep["shortfall"]["short"]["n"]) == (1, 2)
    assert (rep["engagement"]["list_ctr"]["k"], rep["engagement"]["item_ctr"]["k"], rep["engagement"]["item_ctr"]["n"]) == (1, 1, 9)
    assert (rep["engagement"]["hit_at_k"]["k"], rep["engagement"]["hit_at_k"]["n"]) == (1, 2)
    shown = next(x for x in rep["comparison"] if x["method"] == "__shown__")
    assert shown["lists"] == 2 and shown["hit"] == 0.5 and len(rep["comparison"]) > 3
    assert rep["survey"]["reuse"]["mean"] == 5.0 and rep["comments"][0]["text"].startswith("예시")
    paths = write_report(rep, str(tmp_path / "pilot"))
    md = open(paths["markdown"], encoding="utf-8").read()
    assert "주 지표" in md and "33.3% (1/3" in md and "기법 비교" in md
    capsys.readouterr()
    main(["web", "pilot-report", "--db", db, "--out", str(tmp_path / "pilot2"), "--no-compare"])
    assert "참가자 3명" in capsys.readouterr().out


def test_bootstrap_scale_and_idempotent_first_run(small_bundle, tmp_path, monkeypatch, capsys):
    from etfrec.cli import _bootstrap_scale, main
    gib = 2 ** 30
    assert _bootstrap_scale(None, None)[:2] == (15000, 2) and _bootstrap_scale(None, 4 * gib)[:2] == (15000, 2)
    assert _bootstrap_scale(None, 2 * gib)[:2] == (15000, 1)
    assert _bootstrap_scale(None, gib // 2)[:2] == (3000, 1)                       # 512MB 서버(Render starter)
    assert _bootstrap_scale("6000", gib // 2)[:2] == (6000, 1)
    bundle, ops, db = str(tmp_path / "bundle"), str(tmp_path / "ops"), str(tmp_path / "web.db")
    small_bundle.save(bundle)                                                       # 번들이 있으면 학습을 건너뛴다
    monkeypatch.setenv("ETFREC_ADMIN_USERNAME", "teacher")
    monkeypatch.setenv("ETFREC_ADMIN_PASSWORD", "admin-pass-123")
    args = ["web", "bootstrap", "--db", db, "--bundle", bundle, "--ops-dir", ops]
    main(args)
    out = capsys.readouterr().out
    assert "번들이 없어" not in out and "운영 등록부를 만들었습니다" in out and "관리자 계정을 만들었습니다: teacher" in out
    assert PolicyRegistry(ops).champion["key"] == "PurposeStageRule" and WebStore(db).user_by_name("teacher")["is_admin"] == 1
    main(args)                                                                      # 두 번째 실행은 아무것도 바꾸지 않는다
    assert capsys.readouterr().out == "" and len(PolicyRegistry(ops).history()) == 1


def test_admin_pilot_report_and_data_download(small_bundle, tmp_path):
    import io
    import zipfile
    c = make_client(small_bundle, tmp_path)
    signup(c)
    c.put("/api/me/profile", json=PROFILE, headers=H)
    r = c.get("/api/me/recommendations").json()
    c.get(f"/api/me/units/{r['items'][0]['item']}?rid={r['request_id']}")
    assert c.get("/api/admin/pilot-report").status_code == 403                     # 학습자는 못 본다
    c.post("/api/auth/logout", headers=H)
    assert c.get("/api/admin/pilot-data").status_code == 401
    c.app.state.web_store.create_user("teacher", "admin-pass-123", is_admin=True)
    c.post("/api/auth/login", json=dict(username="teacher", password="admin-pass-123"), headers=H)
    md = c.get("/api/admin/pilot-report?compare=false")
    assert md.status_code == 200 and md.text.startswith("# 파일럿 결과") and "| 추천 단원 열람 | 1 |" in md.text
    assert c.get("/api/admin/pilot-report?as_of=2026-13-01").status_code == 422
    z = c.get("/api/admin/pilot-data?compare=false")
    assert z.status_code == 200 and "attachment" in z.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    names = set(zf.namelist())
    assert {"pilot_report.md", "pilot_metrics.json", "dataset/profiles.csv", "dataset/catalog.csv", "recommendation_lists.csv",
            "responses.csv"} <= names
    allt = "".join(zf.read(n).decode("utf-8-sig") for n in names)
    assert "learner1" not in allt and "teacher" not in allt and "scrypt" not in allt      # 아이디·해시는 나가지 않는다
    rows = zf.read("recommendation_lists.csv").decode("utf-8-sig").splitlines()
    assert rows[0].startswith("ref,ts,request_id") and rows[1].startswith("0,")
