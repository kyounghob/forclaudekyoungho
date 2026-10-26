"""학습자 화면 API: 가입·로그인, 온보딩(목적·성향·관심 주제), 진단 퀴즈, 추천, 단원 학습·이해 확인, 로드맵, ETF 유형, 내 기록.

모든 /api/me 요청은 로그인 세션(HttpOnly·SameSite=Lax 쿠키)이 필요하고, 상태를 바꾸는 요청은 같은 출처 화면이 붙이는
X-Requested-With 머리글이 있어야 한다(다른 사이트의 폼 제출 차단). 추천은 운영 루프가 켜져 있으면 /api/serve와 같이
마지막 칸을 탐색하고 노출 확률을 기록하며, 학습 행동은 같은 주의 반응 기록으로 남긴다(학습자 번호 = 가명 ref).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..catalog import EXPS, LEVEL_NAMES, RISKS
from ..config import GOALS, HORIZONS, NOTICE
from ..quiz import QUESTIONS
from ..service import LearnerInput
from ..sources.registry import sources_for_items
from ..util import json_safe
from .security import COOKIE, CSRF_HEADER, CSRF_VALUE, RateLimiter, client_ip
from .store import CONSENT_VERSION, WebStore, validate_profile

CONSENT_TEXT = (
    "수집 항목: 아이디, 비밀번호(복원할 수 없는 해시로만 저장), 투자 목적·기간·위험성향·투자 경험·관심 주제·학습 기기, 진단 퀴즈 결과, "
    "단원 학습 기록(완료·이해 확인·저장), 추천 노출 기록. 연령·성별·소득·연락처는 받지 않습니다.\n"
    "이용 목적: 학습 단원 개인화 추천과 학습 경로 표시, 추천 품질 점검(주간 재학습·평가), 수업 연구용 통계. "
    "더 나은 추천을 찾기 위해 추천 목록의 마지막 칸은 가끔 다른 후보 단원으로 바뀌며, 어떤 단원이 보였는지와 학습 여부를 함께 기록합니다.\n"
    "보관과 권리: 탈퇴하면 계정과 학습 기록을 즉시 지우고, 언제든 내 데이터를 내려받을 수 있습니다.\n"
    "이 서비스는 교육 콘텐츠 추천이며 특정 ETF의 매수·매도를 권유하지 않습니다.")


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
    for q in QUESTIONS:                                        # 단원별 이해 확인 문항(통과 판정 문항만)
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
        if not limiter.take("signup:" + client_ip(request, cfg.trust_proxy), 10, 3600):
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
        if limiter.blocked("login-ip:" + ip, 20, 900) or limiter.blocked("login-user:" + name, 8, 900):
            raise HTTPException(429, "로그인 실패가 많아 15분 동안 막혔습니다")
        u = store.authenticate(body.username, body.password)
        if u is None:
            limiter.hit("login-ip:" + ip, 900); limiter.hit("login-user:" + name, 900)
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
        if o is not None:
            from ..ops.loop import impression_record
            r = wrap(lambda: svc.recommend(learner(u), k=k, exploration=o["exploration"], request_id=rid))
            slate = r.pop("exploration", None)
            if slate and slate["items"]:
                o["log"].append_impressions([impression_record(slate, week_now(), u["ref"], o["reg"].champion, k, r["candidates"], "web")])
        else:
            r = wrap(lambda: svc.recommend(learner(u), k=k))
        keep = ("item", "item_id", "title", "topic", "level", "level_name", "short", "minutes", "in_current_stage", "sources")
        interests = set(store.profile(u["id"]).get("interests") or [])
        stage = (r.get("roadmap") or {}).get("current_stage_name") or ""
        items = [{**{key: it.get(key) for key in keep}, "reason": learner_reason(it, interests, stage), "detail": it.get("reason"),
                  "has_check": int(it["item"]) in unit_question} for it in r["items"]]
        return json_safe(dict(request_id=rid, items=items, roadmap=r["roadmap"], candidates=r["candidates"], shortfall=r["shortfall"],
                              checks_passed=all(c["passed"] for c in r["checks"]), notice=r["notice"], week=week_now()))

    def _status(u, item):
        ev = [e for e in store.events(u["id"]) if e["item"] == item]
        return dict(passed=any(e["quiz_pass"] for e in ev), completed=any(e["complete"] for e in ev), saved=any(e["save"] for e in ev),
                    by_diagnosis=any(e["source"] == "diagnosis" for e in ev))

    def _item(item: int) -> int:
        if not 0 <= item < catalog.n_items:
            raise HTTPException(404, "없는 단원입니다")
        return item

    @app.get("/api/me/units/{item}")
    def unit(item: int, request: Request):
        u = need_user(request)
        d = catalog.item_info(_item(item))
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

    app.state.web_store = store
    app.state.web_user_of = user_of
    return store
