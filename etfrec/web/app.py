"""학습자 화면 API: 가입·로그인, 온보딩(목적·성향·관심 주제), 진단 퀴즈, 추천, 단원 학습·이해 확인, 로드맵, ETF 유형, 내 기록.

모든 /api/me 요청은 로그인 세션(HttpOnly·SameSite=Lax 쿠키)이 필요하고, 상태를 바꾸는 요청은 같은 출처 화면이 붙이는
X-Requested-With 머리글이 있어야 한다(다른 사이트의 폼 제출 차단). 추천은 운영 루프가 켜져 있으면 /api/serve와 같이
마지막 칸을 탐색하고 노출 확률을 기록하며, 학습 행동은 같은 주의 반응 기록으로 남긴다(학습자 번호 = 가명 ref).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from ..catalog import EXPS, LEVEL_NAMES, RISKS
from ..config import GOALS, HORIZONS, NOTICE
from ..quiz import QUESTIONS
from ..service import LearnerInput
from ..sources.registry import sources_for_items
from ..unit_checks import unit_check
from ..util import json_safe
from .security import COOKIE, CSRF_HEADER, CSRF_VALUE, RateLimiter, client_ip
from .store import CONSENT_VERSION, SURVEY_ITEMS, WebStore, validate_profile

CONSENT_TEXT = (
    "수집 항목: 아이디, 비밀번호(복원할 수 없는 해시로만 저장), 투자 목적·기간·위험성향·투자 경험·관심 주제·학습 기기, 진단 퀴즈 결과, "
    "단원 학습 기록(완료·이해 확인·저장), 추천 노출 기록. 연령·성별·소득·연락처는 받지 않습니다.\n"
    "이용 목적: 학습 단원 개인화 추천과 학습 경로 표시, 추천 품질 점검(주간 재학습·평가), 수업 연구용 통계. "
    "더 나은 추천을 찾기 위해 추천 목록의 마지막 칸은 가끔 다른 후보 단원으로 바뀌며, 어떤 단원이 보였는지와 학습 여부를 함께 기록합니다.\n"
    "보관과 권리: 탈퇴하면 계정과 학습 기록을 즉시 지우고, 언제든 내 데이터를 내려받을 수 있습니다.\n"
    "이 서비스는 교육 콘텐츠 추천이며 특정 ETF의 매수·매도를 권유하지 않습니다.")


# 시도 횟수 제한. 강의실처럼 여러 사람이 같은 공인 IP를 쓰는 경우를 고려해 IP 기준은 넉넉히, 아이디 기준은 엄격히 둔다.
SIGNUP_PER_IP = (60, 3600)              # IP당 1시간 60회
LOGIN_FAIL_PER_IP = (100, 900)          # IP당 15분 실패 100회
LOGIN_FAIL_PER_USER = (8, 900)          # 아이디당 15분 실패 8회
RATING_INTERVAL = 20 * 3600             # 추천 이유 이해도는 하루에 한 번 정도만 묻는다
SURVEY_AFTER_DAYS = 7                   # 마무리 설문을 권하는 시점(가입 뒤 일수)


@dataclass
class WebConfig:
    db_path: str
    public: bool = False                  # True: 학습자 화면이 기본(/), 스튜디오·운영 API는 관리자만
    invite_code: str = None               # 있으면 가입에 필요(파일럿 참여자만)
    secure_cookies: bool = False          # HTTPS 뒤에서 운영할 때 True
    trust_proxy: bool = False             # 리버스 프록시 뒤: X-Forwarded-For로 속도 제한 IP 판단
    service_start: str = None             # 주차 기준일 YYYY-MM-DD(처음 한 번 저장)
    k: int = 5


class SignupBody(BaseModel):
    username: str = Field(max_length=30)
    password: str = Field(max_length=128)
    consent: bool = False
    invite_code: Optional[str] = Field(None, max_length=64)


class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class ProfileBody(BaseModel):
    goal: str
    horizon: str
    risk: int
    exp: int
    interests: list[int] = []
    mobile: int = 1


class DiagnosisBody(BaseModel):
    answers: dict


class ProgressBody(BaseModel):
    action: str                           # complete | save | check
    answer: Optional[int] = Field(None, ge=0, le=9)
    self_check: bool = False
    request_id: Optional[str] = Field(None, max_length=80)


class DeleteBody(BaseModel):
    password: str = Field(max_length=128)


class RatingBody(BaseModel):
    request_id: str = Field(max_length=80)
    value: int = Field(ge=1, le=5)


class ReviewBody(BaseModel):
    items: list[int] = Field(default_factory=list, max_length=66)


class SurveyBody(BaseModel):
    answers: dict[str, int]
    comment: str = Field("", max_length=500)


def learner_reason(it: dict, interests: set, stage_name: str) -> str:
    """학습자에게 보이는 추천 이유(쉬운 말). 점수 기여 신호로 쓴 기술적 설명은 detail로 따로 보낸다."""
    parts = [f"지금 로드맵 단계({stage_name})의 단원"] if it.get("in_current_stage") and stage_name else []
    gap = int(it.get("level_gap") or 0)
    parts.append("기초를 다지는 단원" if gap < 0 else ("지금 수준에 맞는 단원" if gap == 0 else "한 단계 위에 도전하는 단원"))
    if it.get("topic_id") in interests:
        parts.append("관심 주제")
    return " · ".join(parts)


def install_web(app, svc, cfg: WebConfig, ops_get=None) -> WebStore:
    """ops_get(): 운영 루프 상태(dict) 또는 None. 반환값은 저장소(관리자 판정 등에 씀)."""
    store = WebStore(cfg.db_path)
    start = store.service_start(cfg.service_start)
    limiter = RateLimiter()
    catalog = svc.catalog
    unit_question = {}
    if getattr(catalog, "version", 2) >= 2:                    # 단원 확인 전용 문항(진단 문항과 따로, unit_checks.py)
        for i in range(catalog.n_items):
            q = unit_check(catalog.topics[catalog.item_topic[i]], int(catalog.item_level[i]))
            if q is not None:
                unit_question[i] = q
    for q in QUESTIONS:                                        # 전용 문항이 없는 단원만 진단의 통과 판정 문항으로 대신한다
        if q.get("marks_pass", True):
            it = catalog.unit(q["topic"], q["level"])
            if it is not None:
                unit_question.setdefault(int(it), q)

    def week_now() -> int:
        return max(0, (date.today() - start).days // 7)

    def user_of(request: Request):
        return store.session_user(request.cookies.get(COOKIE))

    def need_user(request: Request) -> dict:
        u = user_of(request)
        if u is None:
            raise HTTPException(401, "로그인이 필요합니다")
        if request.method not in ("GET", "HEAD") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(403, "요청 머리글이 없습니다(같은 화면에서만 요청할 수 있습니다)")
        return u

    def set_cookie(resp, token: str):
        resp.set_cookie(COOKIE, token, max_age=14 * 24 * 3600, httponly=True, samesite="lax", secure=cfg.secure_cookies, path="/")

    def learner(u: dict) -> LearnerInput:
        return LearnerInput(**store.learner_fields(u["id"]))

    def ops_feedback(u, item, event, request_id=None):
        o = ops_get() if ops_get else None
        if o is not None:
            o["log"].append_feedback([dict(week=week_now(), user_ref=u["ref"], item=int(item), event=event, request_id=request_id,
                                           source="web")])

    def wrap(fn):
        try:
            return fn()
        except ValueError as e:
            raise HTTPException(422, str(e))

    # ---------- 공개 ----------
    @app.get("/api/public/config")
    def public_config():
        return json_safe(dict(topics=[dict(id=i, name=t, group=catalog.group_names[catalog.topic_group[i]]) for i, t in enumerate(catalog.topics)],
                              groups=catalog.group_names, goals=GOALS, horizons=HORIZONS, risks=RISKS, exps=EXPS, levels=LEVEL_NAMES,
                              notice=NOTICE, consent_text=CONSENT_TEXT, consent_version=CONSENT_VERSION,
                              invite_required=bool(cfg.invite_code), quiz_questions=len(svc.quiz_questions())))

    # ---------- 계정 ----------
    @app.post("/api/auth/signup")
    def signup(body: SignupBody, request: Request):
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(403, "요청 머리글이 없습니다")
        if not limiter.take("signup:" + client_ip(request, cfg.trust_proxy), *SIGNUP_PER_IP):
            raise HTTPException(429, "가입 시도가 너무 많습니다. 잠시 뒤에 다시 시도하세요")
        if cfg.invite_code and body.invite_code != cfg.invite_code:
            raise HTTPException(403, "초대 코드가 맞지 않습니다")
        if not body.consent:
            raise HTTPException(422, "개인정보 수집·이용에 동의해야 가입할 수 있습니다")
        try:
            u = store.create_user(body.username, body.password, CONSENT_VERSION)
        except FileExistsError as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        resp = JSONResponse(dict(username=u["username"], profile_complete=False))
        set_cookie(resp, store.create_session(u["id"]))
        return resp

    @app.post("/api/auth/login")
    def login(body: LoginBody, request: Request):
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(403, "요청 머리글이 없습니다")
        ip, name = client_ip(request, cfg.trust_proxy), body.username.strip().lower()
        if limiter.blocked("login-ip:" + ip, *LOGIN_FAIL_PER_IP) or limiter.blocked("login-user:" + name, *LOGIN_FAIL_PER_USER):
            raise HTTPException(429, "로그인 실패가 많아 15분 동안 막혔습니다")
        u = store.authenticate(body.username, body.password)
        if u is None:
            limiter.hit("login-ip:" + ip, LOGIN_FAIL_PER_IP[1]); limiter.hit("login-user:" + name, LOGIN_FAIL_PER_USER[1])
            raise HTTPException(401, "아이디 또는 비밀번호가 맞지 않습니다")
        limiter.clear("login-user:" + name)
        resp = JSONResponse(dict(username=u["username"], profile_complete=store.profile(u["id"])["complete"], is_admin=bool(u["is_admin"])))
        set_cookie(resp, store.create_session(u["id"]))
        return resp

    @app.post("/api/auth/logout")
    def logout(request: Request):
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(403, "요청 머리글이 없습니다")
        store.delete_session(request.cookies.get(COOKIE))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    def me_payload(u: dict) -> dict:
        p = store.profile(u["id"])
        return json_safe(dict(username=u["username"], is_admin=bool(u["is_admin"]), created_at=u["created_at"], profile=p,
                              profile_complete=p["complete"], week=week_now()))

    @app.get("/api/auth/session")
    def session(request: Request):
        """로그인 여부 확인(로그인 전에도 200). 화면이 처음 열릴 때 쓴다."""
        u = user_of(request)
        return {"authenticated": False} if u is None else {"authenticated": True, **me_payload(u)}

    # ---------- 내 정보 ----------
    @app.get("/api/me")
    def me(request: Request):
        return me_payload(need_user(request))

    @app.put("/api/me/profile")
    def put_profile(body: ProfileBody, request: Request):
        u = need_user(request)
        data = wrap(lambda: validate_profile(body.model_dump(), catalog.n_topics))
        store.save_profile(u["id"], data)
        return json_safe(store.profile(u["id"]))

    @app.get("/api/me/quiz")
    def my_quiz(request: Request):
        need_user(request)
        return svc.quiz_questions()

    @app.post("/api/me/diagnosis")
    def diagnosis(body: DiagnosisBody, request: Request):
        u = need_user(request)
        r = wrap(lambda: svc.quiz_score({str(k): v for k, v in body.answers.items() if v is not None}))
        items = [int(e["item"]) for e in r["events"]]
        store.replace_diagnosis(u["id"], items)
        store.save_profile(u["id"], dict(placement=int(r["level"]),
                                          diagnosis=dict(level=int(r["level"]), correct=r["correct"], answered=r["answered"],
                                                         total=r["total"], summary=r.get("summary", ""), units=len(items))))
        return r

    @app.post("/api/me/diagnosis/review")
    def diagnosis_review(body: ReviewBody, request: Request):
        """진단 면제 확인: 학습자가 '아직 잘 모름'으로 고른 단원은 인정을 거두고 다시 추천한다. 빈 목록 = 모두 맞음(이것도 기록)."""
        u = need_user(request)
        exempted = sorted({e["item"] for e in store.events(u["id"]) if e["source"] == "diagnosis"})
        removed = wrap(lambda: store.unexempt(u["id"], body.items))
        store.add_feedback(u["id"], "diagnosis_review", value=dict(exempted=exempted, flagged=removed))
        return dict(ok=True, exempted=len(exempted), flagged=len(removed), remaining=len(exempted) - len(removed))

    def _need_profile(u):
        if not store.profile(u["id"])["complete"]:
            raise HTTPException(409, "먼저 투자 목적·기간·성향을 입력하세요")

    @app.get("/api/me/recommendations")
    def my_recommendations(request: Request, k: int = 5):
        u = need_user(request)
        _need_profile(u)
        if not 1 <= k <= 10:
            raise HTTPException(422, "k는 1~10입니다")
        o = ops_get() if ops_get else None
        rid = uuid.uuid4().hex
        slate, policy = None, getattr(svc, "operational_label", None)
        if o is not None:
            from ..ops.loop import impression_record
            r = wrap(lambda: svc.recommend(learner(u), k=k, exploration=o["exploration"], request_id=rid))
            slate = r.pop("exploration", None)
            policy = o["reg"].champion.get("hash")
            if slate and slate["items"]:
                o["log"].append_impressions([impression_record(slate, week_now(), u["ref"], o["reg"].champion, k, r["candidates"], "web")])
        else:
            r = wrap(lambda: svc.recommend(learner(u), k=k))
        store.record_rec(u["id"], rid, [it["item"] for it in r["items"]], shortfall=r["shortfall"],
                         explored_slot=(slate["slot"] if slate and slate["explored"] else None), policy=policy)
        last = store.feedback(u["id"], "reason_rating")
        keep = ("item", "item_id", "title", "topic", "level", "level_name", "short", "minutes", "in_current_stage", "sources")
        interests = set(store.profile(u["id"]).get("interests") or [])
        stage = (r.get("roadmap") or {}).get("current_stage_name") or ""
        items = [{**{key: it.get(key) for key in keep}, "reason": learner_reason(it, interests, stage), "detail": it.get("reason"),
                  "has_check": int(it["item"]) in unit_question} for it in r["items"]]
        return json_safe(dict(request_id=rid, items=items, roadmap=r["roadmap"], candidates=r["candidates"], shortfall=r["shortfall"],
                              checks_passed=all(c["passed"] for c in r["checks"]), notice=r["notice"], week=week_now(),
                              ask_rating=bool(items) and (not last or time.time() - last[-1]["ts"] > RATING_INTERVAL)))

    @app.post("/api/me/rating")
    def rating(body: RatingBody, request: Request):
        """추천 목록 하나의 '추천 이유' 이해도(1 전혀 아니다 ~ 5 매우 그렇다)."""
        u = need_user(request)
        if store.rec(u["id"], body.request_id) is None:
            raise HTTPException(404, "내가 받은 추천 목록이 아닙니다")
        store.add_feedback(u["id"], "reason_rating", request_id=body.request_id, value=int(body.value))
        return dict(ok=True)

    @app.get("/api/me/survey")
    def survey_status(request: Request):
        u = need_user(request)
        days = max(0, (date.today() - date.fromisoformat(u["created_at"][:10])).days)
        done = store.feedback(u["id"], "exit_survey")
        return dict(items=[dict(key=k, text=t) for k, t in SURVEY_ITEMS], days=days, suggested=days >= SURVEY_AFTER_DAYS,
                    done=bool(done), answers=(done[-1]["value"] if done else None))

    @app.post("/api/me/survey")
    def survey(body: SurveyBody, request: Request):
        u = need_user(request)
        keys = [k for k, _ in SURVEY_ITEMS]
        if set(body.answers) != set(keys) or any(isinstance(v, bool) or not 1 <= v <= 5 for v in body.answers.values()):
            raise HTTPException(422, f"모든 문항({len(keys)}개)에 1~5로 답해 주세요")
        days = max(0, (date.today() - date.fromisoformat(u["created_at"][:10])).days)
        store.add_feedback(u["id"], "exit_survey", value=dict(answers={k: int(body.answers[k]) for k in keys},
                                                              comment=body.comment.strip(), days=days))
        return dict(ok=True)

    def _status(u, item):
        ev = [e for e in store.events(u["id"]) if e["item"] == item]
        return dict(passed=any(e["quiz_pass"] for e in ev), completed=any(e["complete"] for e in ev), saved=any(e["save"] for e in ev),
                    by_diagnosis=any(e["source"] == "diagnosis" for e in ev))

    def _item(item: int) -> int:
        if not 0 <= item < catalog.n_items:
            raise HTTPException(404, "없는 단원입니다")
        return item

    @app.get("/api/me/units/{item}")
    def unit(item: int, request: Request, rid: Optional[str] = None):
        """단원 화면. rid(추천 목록 번호)를 주면 그 목록에 있던 단원일 때만 '추천에서 열람'으로 기록한다."""
        u = need_user(request)
        d = catalog.item_info(_item(item))
        rec = store.rec(u["id"], rid) if rid and len(rid) <= 80 else None
        from_rec = rec is not None and item in rec["items"]
        if store.add_view(u["id"], item, rid if from_rec else None):
            ops_feedback(u, item, "view", rid if from_rec else None)
        q = unit_question.get(item)
        d.update(sources=sources_for_items(d["sources"]), status=_status(u, item),
                 prereq_titles=[catalog.item_title[p] for p in d["prereqs"]],
                 check=(dict(text=q["text"], options=q["options"]) if q else None))
        return json_safe(d)

    @app.post("/api/me/units/{item}/progress")
    def progress(item: int, body: ProgressBody, request: Request):
        u = need_user(request)
        _item(item)
        if body.action == "complete":
            store.add_event(u["id"], item, "complete", "web"); ops_feedback(u, item, "complete", body.request_id)
            return dict(ok=True, status=_status(u, item))
        if body.action == "save":
            store.add_event(u["id"], item, "save", "web"); ops_feedback(u, item, "save", body.request_id)
            return dict(ok=True, status=_status(u, item))
        if body.action != "check":
            raise HTTPException(422, "action은 complete·save·check 중 하나입니다")
        q = unit_question.get(item)
        if q is None:                                          # 확인 문항이 없는 단원: 스스로 확인(자기 보고로 따로 표시)
            if not body.self_check:
                raise HTTPException(422, "이 단원은 확인 문항이 없어 self_check로 이해했음을 표시합니다")
            store.add_event(u["id"], item, "quiz_pass", "self"); ops_feedback(u, item, "quiz_pass", body.request_id)
            return dict(ok=True, correct=None, self_check=True, status=_status(u, item))
        if body.answer is None or body.answer >= len(q["options"]):
            raise HTTPException(422, "보기 번호를 고르세요")
        ok = int(body.answer) == int(q["answer"])
        store.add_event(u["id"], item, "quiz_pass" if ok else "quiz_fail", "quiz")
        if ok:
            ops_feedback(u, item, "quiz_pass", body.request_id)
        return dict(ok=True, correct=ok, correct_option=q["options"][q["answer"]] if ok else None, explain=q["explain"] if ok else None,
                    status=_status(u, item))

    @app.get("/api/me/roadmap")
    def my_roadmap(request: Request):
        u = need_user(request)
        _need_profile(u)
        return wrap(lambda: svc.roadmap(learner(u)))

    @app.get("/api/me/types")
    def my_types(request: Request):
        u = need_user(request)
        _need_profile(u)
        return wrap(lambda: svc.types(learner(u)))

    @app.get("/api/me/history")
    def history(request: Request):
        u = need_user(request)
        kind = lambda e: "진단 통과" if e["source"] == "diagnosis" else ("이해 확인" if e["quiz_pass"] else ("확인 문항 오답" if e["quiz"] else
                                                                                                    ("저장" if e["save"] else "학습 완료")))
        return [dict(item=e["item"], title=catalog.item_title[e["item"]], kind=kind(e), self_check=e["source"] == "self", ts=e["ts"])
                for e in reversed(store.events(u["id"]))]

    @app.get("/api/me/export")
    def export(request: Request):
        u = need_user(request)
        return JSONResponse(json_safe(store.export_user(u["id"])),
                            headers={"Content-Disposition": f'attachment; filename="etfrec-{u["username"]}.json"'})

    @app.delete("/api/me")
    def delete_me(body: DeleteBody, request: Request):
        u = need_user(request)
        if store.authenticate(u["username"], body.password) is None:
            raise HTTPException(401, "비밀번호가 맞지 않습니다")
        ref = store.delete_user(u["id"])
        o = ops_get() if ops_get else None
        if o is not None and ref is not None:
            o["log"].purge_user(ref)
        resp = JSONResponse({"deleted": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ---------- 관리자: 파일럿 보고서·분석 자료 ----------
    def need_admin(request: Request) -> dict:
        u = need_user(request)
        if not u["is_admin"]:
            raise HTTPException(403, "관리자만 쓸 수 있는 기능입니다")
        return u

    def _pilot(as_of: Optional[str], window_days: int, compare: bool) -> dict:
        from .pilot import pilot_report
        now = None
        if as_of:
            try:
                now = datetime.fromisoformat(as_of + "T23:59:59").timestamp()
            except ValueError:
                raise HTTPException(422, "as_of는 YYYY-MM-DD입니다")
        if not 1 <= window_days <= 60:
            raise HTTPException(422, "window_days는 1~60입니다")
        return pilot_report(store, svc=svc if compare else None, window_days=window_days, now=now)

    @app.get("/api/admin/pilot-report")
    def admin_pilot_report(request: Request, as_of: Optional[str] = None, window_days: int = 7, compare: bool = True):
        """파일럿 지표 보고서(마크다운 글). 브라우저에서 바로 읽는다."""
        need_admin(request)
        from .pilot import report_markdown
        return PlainTextResponse(report_markdown(_pilot(as_of, window_days, compare)))

    @app.get("/api/admin/pilot-data")
    def admin_pilot_data(request: Request, as_of: Optional[str] = None, window_days: int = 7, compare: bool = True):
        """분석 자료 묶음(zip): 보고서·지표, 학습 형식 데이터(profiles·study_log·catalog), 추천 목록·응답 기록.
        학습자는 가명 번호(ref)로만 나오고 아이디·비밀번호 해시는 없다."""
        need_admin(request)
        import csv as _csv
        import io
        import zipfile
        from .pilot import report_markdown
        rep = _pilot(as_of, window_days, compare)
        D = store.dump()
        admins = {u["id"] for u in D["users"] if u["is_admin"]}
        ref = {u["id"]: u["ref"] for u in D["users"]}
        profiles, log = store.export_dataset(start)
        keep_refs = {ref[i] for i in ref if i not in admins}
        log = log[log.user.isin(keep_refs)]

        def table(rows, cols):
            buf = io.StringIO(); w = _csv.writer(buf); w.writerow(cols); w.writerows(rows)
            return "\ufeff" + buf.getvalue()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("pilot_report.md", report_markdown(rep))
            z.writestr("pilot_metrics.json", json.dumps(json_safe(rep), ensure_ascii=False, indent=2))
            z.writestr("dataset/profiles.csv", "\ufeff" + profiles.to_csv(index=False))      # 번호가 0부터 이어져야 해서 모든 행을 둔다(관리자 기록은 log에서 뺌)
            z.writestr("dataset/study_log.csv", "\ufeff" + log.to_csv(index=False))
            z.writestr("dataset/catalog.csv", "\ufeff" + catalog.to_frame()[["item", "title", "topic", "level", "short", "prereqs", "sources"]].to_csv(index=False))
            z.writestr("recommendation_lists.csv", table([(ref[r["user_id"]], round(r["ts"]), r["request_id"], " ".join(map(str, r["items"])), r["shortfall"],
                                                            "" if r["explored_slot"] is None else r["explored_slot"]) for r in D["recs"] if r["user_id"] not in admins],
                                                          ["ref", "ts", "request_id", "items", "shortfall", "explored_slot"]))
            z.writestr("responses.csv", table([(ref[f["user_id"]], round(f["ts"]), f["kind"], "" if f["item"] is None else f["item"], f["request_id"] or "",
                                                 json.dumps(f["value"], ensure_ascii=False) if f["value"] is not None else "") for f in D["feedback"]
                                                if f["user_id"] not in admins], ["ref", "ts", "kind", "item", "request_id", "value"]))
            z.writestr("README.txt", "ETF 학습 추천 파일럿 분석 자료. 학습자는 가명 번호(ref)로만 표시한다. ts는 유닉스 시각(초).\n"
                                     "dataset/은 학습 파이프라인 형식(python -m etfrec ops run-week --data dataset 등)이다.\n")
        name = f"etfrec-pilot-{(as_of or date.today().isoformat())}.zip"
        return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    app.state.web_store = store
    app.state.web_user_of = user_of
    return store
