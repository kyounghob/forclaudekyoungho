"""FastAPI 애플리케이션: REST API + 정적 UI.

실행: ``python -m etfrec serve --bundle runs/seed42 --port 8000`` 후 http://localhost:8000
모든 추천은 미리 학습된 번들로 계산하며 요청 중 재학습은 없다.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Optional, Union

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import GuardrailConfig
from .data import parse_history_csv
from .nlparse import EXAMPLES, parse_onboarding
from .pipeline import Bundle
from .ops.exploration import ExplorationConfig
from .ops.logstore import EVENTS, OpsLog
from .ops.loop import impression_record
from .ops.policies import public_spec
from .ops.registry import PolicyRegistry
from .privacy import strip_outputs
from .service import LearnerInput, RecommendationService
from .util import json_safe

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")


class Guardrail(BaseModel):
    block_gap: int = Field(2, ge=1, le=3)
    plus_one_max: int = Field(1, ge=0, le=5)
    exclude_passed: bool = True
    prereq_block: bool = True        # 화면 기본: 선수 단원 미이수 단원 제외


class Event(BaseModel):
    item: int = Field(ge=0)
    week: int = Field(0, ge=0)
    day: int = Field(0, ge=0, le=6)
    hour: int = Field(0, ge=0, le=3)
    minute: int = Field(0, ge=0, le=10079)
    complete: bool = False
    quiz: bool = False
    quiz_pass: bool = False
    save: bool = False
    drop: bool = False
    replay: bool = False
    source: Optional[str] = None     # "diagnosis": 이수 인정만 반영; 행동·관심·조회 통계에는 쓰지 않음


class Learner(BaseModel):
    age: int = Field(35, ge=10, le=100)
    gender: int = Field(0, ge=0, le=1)
    income: Optional[float] = Field(None, ge=0)
    exp: int = Field(0, ge=0, le=2)
    risk: int = Field(1, ge=0, le=2)
    mobile: int = Field(1, ge=0, le=1)
    interests: list[int] = []
    placement: int = Field(1, ge=1, le=3)
    hour: int = Field(4, ge=0, le=4)
    events: list[Event] = []
    label: str = "새 학습자"
    goal: str = "long_term"
    horizon: str = "mid"
    diagnosis: Optional[dict] = None


class RecommendRequest(BaseModel):
    learner_id: Optional[int] = None
    learner: Optional[Learner] = None
    k: int = Field(5, ge=1, le=20)
    algorithm: Optional[Union[str, int]] = None
    guardrail: Optional[Guardrail] = None
    topic_cap: Optional[int] = Field(None, ge=1, le=5)
    overrides: Optional[dict] = None
    assume_passed: list[int] = []


class CompareRequest(RecommendRequest):
    methods: Optional[list[str]] = None


class RoadmapRequest(BaseModel):
    learner_id: Optional[int] = None
    learner: Optional[Learner] = None
    assume_passed: list[int] = []
    overrides: Optional[dict] = None


class TypesRequest(BaseModel):
    learner_id: Optional[int] = None
    learner: Optional[Learner] = None
    goal: Optional[str] = None
    risk: Optional[int] = Field(None, ge=0, le=2)
    assume_passed: list[int] = []


class QuizAnswers(BaseModel):
    answers: dict


class ParseRequest(BaseModel):
    text: str


class NewUserRequest(BaseModel):
    topics: list[int] = []
    level: int = Field(1, ge=1, le=3)
    k: int = Field(5, ge=1, le=20)
    mobile: int = Field(1, ge=0, le=1)
    goal: str = "long_term"
    horizon: str = "mid"
    risk: int = Field(1, ge=0, le=2)


class ServeRequest(BaseModel):
    learner_id: Optional[int] = None
    learner: Optional[Learner] = None
    k: int = Field(5, ge=1, le=20)


class FeedbackRequest(BaseModel):
    item: int = Field(ge=0)
    event: str
    learner_id: Optional[int] = None
    request_id: Optional[str] = Field(None, max_length=80)


class LogText(BaseModel):
    csv_text: str


class Design(BaseModel):
    name: str
    payload: dict


def _learner_input(req, allow_none: bool = False):
    if req.learner_id is not None:
        return int(req.learner_id)
    if req.learner is None:
        if allow_none:
            return None
        raise HTTPException(422, "learner_id 또는 learner 가운데 하나는 있어야 합니다")
    d = req.learner.model_dump()
    d["events"] = [e if isinstance(e, dict) else e.model_dump() for e in d["events"]]
    return LearnerInput(**d)


def create_app(bundle: Union[Bundle, str], designs_dir: str = None, sources_dir: str = None, expose_learners: bool = True,
               allow_any_config: bool = None, ops_dir: str = None) -> FastAPI:
    """expose_learners: 기준 학습자 조회(/api/learners, /api/learners/{uid})를 켤지. 학습자 단위 표라 학습 환경 안(로컬 실행)에서만 켠다
    (cli serve는 로컬 주소가 아니면 --expose-learners를 줄 때만 켠다). allow_any_config: 임의 설정 번호 허용(기본: 환경변수 ETFREC_DEV_CONFIGS=1일 때만)."""
    bundle = Bundle.load(bundle) if isinstance(bundle, str) else bundle
    if allow_any_config is None:
        allow_any_config = os.environ.get("ETFREC_DEV_CONFIGS") == "1"
    svc = RecommendationService(bundle, sources_dir=sources_dir, allow_any_config=allow_any_config)
    designs_dir = designs_dir or os.path.join(os.getcwd(), "artifacts", "designs")
    os.makedirs(designs_dir, exist_ok=True)
    app = FastAPI(title="ETF 교육 콘텐츠 추천 시스템", version=__version__,
                  description="교육 콘텐츠 추천 시연기. 특정 ETF의 매수·매도를 권유하지 않습니다.")
    app.state.service = svc
    ops = None
    if ops_dir:                                                       # 운영 루프: 등록부의 현재 정책으로 서빙하고 노출·반응을 기록
        reg = PolicyRegistry(ops_dir)
        ops = dict(dir=ops_dir, reg=reg, log=OpsLog(os.path.join(ops_dir, "logs")), mtime=reg.mtime(),
                   exploration=ExplorationConfig(**reg.settings.get("exploration", {})), k=int(reg.settings.get("k", 5)))
        svc.set_operational_spec(reg.champion)

    def ops_sync():
        """주간 작업이 등록부를 바꾸면(교체·되돌림) 다음 요청부터 새 정책을 쓴다(서버 재시작 없이)."""
        if ops is None:
            raise HTTPException(503, "운영 루프가 설정되지 않았습니다(serve --ops-dir)")
        m = os.path.getmtime(ops["reg"].path)
        if m != ops["mtime"]:
            ops["reg"] = PolicyRegistry(ops["dir"]); ops["mtime"] = m
            svc.set_operational_spec(ops["reg"].champion)
        return ops

    def guard(g: Optional[Guardrail]) -> GuardrailConfig:
        """요청의 가드레일. 생략하면 스키마 기본값(화면 기본: 선수 단원 차단 켬)과 같게 처리한다."""
        chosen = g or Guardrail()
        if not chosen.prereq_block and not allow_any_config:
            raise HTTPException(422, "선수 학습을 마친 단원만 추천합니다. 선수 조건을 해제한 비교는 개발 모드에서만 가능합니다")
        return GuardrailConfig(**chosen.model_dump())

    def wrap(fn):
        try:
            return fn()
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.get("/api/health")
    def health():
        return {"status": "ready", "version": __version__, "bundle_created_at": bundle.created_at,
                "router": svc.operational_router, "training_in_request": False, "neural_enabled": bundle.models.enable_neural}

    @app.get("/api/meta")
    def meta():
        return {**svc.meta(), "learners_enabled": bool(expose_learners),
                "guardrail": Guardrail().model_dump(),                         # 요청에서 생략할 때 쓰는 값(화면 기본)
                "prerequisite_policy_required": not bool(allow_any_config),
                "evaluation_guardrail": dict(bundle.config.guardrail.__dict__)}   # 번들 평가에 실제 사용한 조건

    @app.get("/api/catalog")
    def catalog():
        return json_safe(dict(items=bundle.catalog.to_frame().to_dict("records"), topics=bundle.catalog.topics,
                              groups=bundle.catalog.group_names, topic_group=bundle.catalog.topic_group))

    @app.get("/api/examples")
    def examples():
        return EXAMPLES

    @app.post("/api/parse")
    def parse(req: ParseRequest):
        return json_safe(parse_onboarding(req.text, bundle.catalog))

    LEARNERS_OFF = ("기준 학습자 조회가 꺼져 있습니다. 학습자 단위 정보라 학습 환경 안(로컬 실행)에서만 켭니다"
                    "(python -m etfrec serve는 127.0.0.1에서 기본으로 켜고, 다른 주소로 열 때는 --expose-learners가 필요합니다)")

    @app.get("/api/learners")
    def learners(q: str = "", limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
        if not expose_learners:
            raise HTTPException(status_code=403, detail=LEARNERS_OFF)
        return svc.learners(q, limit, offset)

    @app.get("/api/learners/{uid}")
    def learner(uid: int):
        if not expose_learners:
            raise HTTPException(status_code=403, detail=LEARNERS_OFF)
        return wrap(lambda: svc.learner(uid))

    def learner_of(req, allow_none: bool = False):
        """learner_id(기준 학습자)는 학습자 조회와 같은 스위치로 막는다: 꺼져 있으면 응답의 프로필·통과 단원으로 학습자 표를 열거할 수 있다."""
        if req.learner_id is not None and not expose_learners:
            raise HTTPException(status_code=403, detail=LEARNERS_OFF)
        return _learner_input(req, allow_none=allow_none)

    @app.post("/api/recommend")
    def recommend(req: RecommendRequest):
        return wrap(lambda: svc.recommend(learner_of(req), k=req.k, algorithm=req.algorithm, guard=guard(req.guardrail),
                                          topic_cap=req.topic_cap, overrides=req.overrides, assume_passed=req.assume_passed))

    @app.post("/api/serve")
    def serve(req: ServeRequest):
        """운영 서빙: 현재 운영 정책 + 마지막 칸 탐색. 보인 단원마다 노출 확률을 붙여 기록하고 request_id를 돌려준다.
        추천 화면의 미리보기·what-if(/api/recommend)는 탐색·기록을 하지 않는다."""
        o = ops_sync()
        rid = uuid.uuid4().hex
        learner = learner_of(req)
        r = wrap(lambda: svc.recommend(learner, k=req.k, exploration=o["exploration"], request_id=rid))
        slate = r.pop("exploration", None)
        if slate and slate["items"]:
            o["log"].append_impressions([impression_record(slate, svc.serve_week, req.learner_id, o["reg"].champion, req.k,
                                                            r["candidates"], "api")])
        r.update(request_id=rid, policy=public_spec(o["reg"].champion),
                 exploration=dict(epsilon=o["exploration"].epsilon, method=o["exploration"].method,
                                  explored=bool(slate and slate["explored"]), slot=(slate or {}).get("slot")))
        return r

    @app.post("/api/feedback")
    def feedback(req: FeedbackRequest):
        """학습 반응(view·complete·quiz_pass·save). 같은 주의 노출과 묶여 OPE 보상이 된다."""
        o = ops_sync()
        if req.learner_id is not None and not expose_learners:
            raise HTTPException(status_code=403, detail=LEARNERS_OFF)
        if req.event not in EVENTS or req.item >= bundle.catalog.n_items:
            raise HTTPException(422, f"event는 {list(EVENTS)} 중 하나, item은 0~{bundle.catalog.n_items - 1}이어야 합니다")
        wrap(lambda: o["log"].append_feedback([dict(week=svc.serve_week, user_ref=req.learner_id, item=req.item, event=req.event,
                                                      request_id=req.request_id, source="api")]))
        return {"ok": True, "week": svc.serve_week}

    @app.get("/api/ops/status")
    def ops_status():
        o = ops_sync()
        reg = o["reg"]; hist = reg.history()
        last = next((h for h in reversed(hist) if h.get("week") is not None), None)
        return json_safe(dict(champion=public_spec(reg.champion), frozen=reg.frozen, freeze_reason=reg.state.get("freeze_reason"),
                              exploration=o["exploration"].as_dict(), serving_week=svc.serve_week, this_week=o["log"].counts(svc.serve_week),
                              last_decision=(dict(week=last["week"], event=last["event"], reason=last.get("reason")) if last else None),
                              history_records=len(hist), history_ok=reg.verify()["ok"]))

    @app.get("/api/ops/history")
    def ops_history(limit: int = Query(20, ge=1, le=200)):
        o = ops_sync()
        keep = ("seq", "ts", "event", "week", "reason", "hash")
        out = []
        for h in o["reg"].history()[-limit:]:
            row = {k: h.get(k) for k in keep}
            row.update(champion_after=(h.get("champion_after") or {}).get("name"), challenger=(h.get("challenger") or {}).get("name"),
                       failed=(h.get("gate") or {}).get("failed"))
            out.append(row)
        return json_safe(out)

    @app.post("/api/compare")
    def compare(req: CompareRequest):
        return wrap(lambda: svc.compare(learner_of(req), k=req.k, methods=req.methods, guard=guard(req.guardrail),
                                        topic_cap=req.topic_cap, overrides=req.overrides, assume_passed=req.assume_passed))

    @app.post("/api/recommend-new")
    def recommend_new(req: NewUserRequest):
        return wrap(lambda: svc.recommend_new(req.topics, req.level, req.k, req.mobile, req.goal, req.horizon, req.risk))

    @app.post("/api/roadmap")
    def roadmap(req: RoadmapRequest):
        return wrap(lambda: svc.roadmap(learner_of(req), assume_passed=req.assume_passed, overrides=req.overrides))

    @app.post("/api/types")
    def types(req: TypesRequest):
        return wrap(lambda: svc.types(learner_of(req, allow_none=True), goal=req.goal, risk=req.risk, assume_passed=req.assume_passed))

    @app.get("/api/quiz")
    def quiz():
        return svc.quiz_questions()

    @app.post("/api/quiz/score")
    def quiz_score(req: QuizAnswers):
        return wrap(lambda: svc.quiz_score({str(k): v for k, v in req.answers.items() if v is not None}))

    @app.get("/api/sources")
    def sources():
        return svc.sources()

    @app.get("/api/goals")
    def goals():
        from .config import GOALS, HORIZONS
        from .taxonomy import ROADMAP_TEMPLATES
        return {"goals": GOALS, "horizons": HORIZONS, "templates": {g: dict(types=t["types"]) for g, t in ROADMAP_TEMPLATES.items()}}

    @app.post("/api/parse-log")
    def parse_log(req: LogText):
        """학습 로그 CSV 텍스트 → 이벤트 목록. item 번호 또는 title 열을 받는다."""
        return wrap(lambda: json_safe(parse_history_csv(req.csv_text, bundle.catalog)))

    @app.get("/api/evaluation")
    def evaluation():
        return svc.evaluation()

    # ---- 저장한 설계 ----
    def _safe_name(name: str) -> str:
        s = re.sub(r"[^0-9A-Za-z가-힣_\- ]", "", name).strip()[:60]
        if not s:
            raise HTTPException(422, "설계 이름이 비어 있습니다")
        return s

    def _read_design(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def _visible(d: dict) -> bool:
        """학습자 조회를 켠 서버에서 저장한 설계(기준 학습자 선택·프로필 복사가 들어 있을 수 있음)는 꺼진 서버가 내려보내지 않는다.
        표시가 없는 이전 파일도 켠 서버에서 저장한 것으로 본다."""
        return bool(expose_learners) or d.get("saved_with_learners") is False

    @app.get("/api/designs")
    def list_designs():
        out = []
        for fn in sorted(os.listdir(designs_dir)):
            if fn.endswith(".json"):
                d = _read_design(os.path.join(designs_dir, fn))               # 읽지 못하는 파일 하나가 목록 전체를 막지 않게
                if _visible(d):
                    out.append(dict(name=d.get("name", fn[:-5]), saved_at=d.get("saved_at"),
                                    summary=svc.scrub_design({"summary": str(d.get("summary", ""))})["summary"]))
        return out

    @app.post("/api/designs")
    def save_design(d: Design):
        """쓰기 전에 서버가 만든 출력(추천·로드맵 결과: 학습자 프로필·통과 단원·학습 카드가 들어 있음)을 버리고, 연령·연소득 원값을 구간 코드로
        바꾸고, 설계 이름과 모든 문자열의 연령·소득 표현을 구간 이름으로 가린다(etfrec.privacy.strip_outputs·scrub_design·scrub_text).
        이름·주소 같은 그 밖의 개인 표현은 가리지 못하므로 입력하지 않는다."""
        name = _safe_name(svc.scrub_design({"name": d.name})["name"])          # 파일 이름에도 연령·소득이 남지 않게
        target = os.path.join(designs_dir, name + ".json")
        if os.path.exists(target) and not _visible(_read_design(target)):     # 이 서버가 볼 수 없는 설계는 덮어쓰지 않는다
            raise HTTPException(409, "같은 이름의 설계가 있어 저장하지 않았습니다. 다른 이름을 쓰세요")
        clean = svc.scrub_design(strip_outputs(d.payload))
        payload = dict(name=name, saved_at=time.strftime("%Y-%m-%d %H:%M:%S"), payload=clean,
                       summary=str(clean.get("summary", ""))[:120], saved_with_learners=bool(expose_learners),
                       privacy="추천·로드맵 결과는 저장하지 않음, 연령·연소득은 구간 코드로만 저장, 문자열의 연령·소득 표현은 구간 이름으로 가림"
                               "(이름 등 그 밖의 표현은 가리지 못함)")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"saved": name, "saved_at": payload["saved_at"]}

    @app.get("/api/designs/{name}")
    def get_design(name: str):
        """불러오기: 서버 출력과 원값을 다시 지우고(이전 파일 대비) state.learner의 연령·소득 입력란은 구간 대표값으로 채운다(원값 복원 아님)."""
        p = os.path.join(designs_dir, _safe_name(name) + ".json")
        if not os.path.exists(p):
            raise HTTPException(404, "저장된 설계가 없습니다")
        d = _read_design(p)
        if not _visible(d):
            raise HTTPException(404, "저장된 설계가 없습니다")
        if isinstance(d.get("payload"), dict):
            d["payload"] = svc.load_design(strip_outputs(d["payload"]))
        d["summary"] = svc.scrub_design({"summary": str(d.get("summary", ""))})["summary"]
        return d

    @app.delete("/api/designs/{name}")
    def delete_design(name: str):
        p = os.path.join(designs_dir, _safe_name(name) + ".json")
        if os.path.exists(p):
            if not _visible(_read_design(p)):                                  # 볼 수 없는 설계는 지우지도 못한다
                raise HTTPException(404, "저장된 설계가 없습니다")
            os.remove(p)
        return {"deleted": name}

    # ---- 정적 UI ----
    if os.path.isdir(UI_DIR):
        app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(os.path.join(UI_DIR, "index.html"))

    return app
