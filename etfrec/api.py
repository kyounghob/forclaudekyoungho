"""FastAPI 애플리케이션: REST API + 정적 UI.

실행: ``python -m etfrec serve --bundle artifacts/bundle_v1 --port 8000`` 후 http://localhost:8000
모든 추천은 미리 학습된 번들로 계산하며 요청 중 재학습은 없다.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
from typing import Optional, Union

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import GuardrailConfig
from .nlparse import EXAMPLES, parse_onboarding
from .pipeline import Bundle
from .service import EVENT_FIELDS, LearnerInput, RecommendationService
from .util import json_safe

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")


class Guardrail(BaseModel):
    block_gap: int = Field(2, ge=1, le=3)
    plus_one_max: int = Field(1, ge=0, le=5)
    exclude_passed: bool = True


class Event(BaseModel):
    item: int
    week: int = 0
    day: int = 0
    hour: int = 0
    minute: int = 0
    complete: bool = False
    quiz: bool = False
    quiz_pass: bool = False
    save: bool = False
    drop: bool = False
    replay: bool = False


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


class ParseRequest(BaseModel):
    text: str


class NewUserRequest(BaseModel):
    topics: list[int] = []
    level: int = Field(1, ge=1, le=3)
    k: int = Field(5, ge=1, le=20)
    mobile: int = Field(1, ge=0, le=1)


class LogText(BaseModel):
    csv_text: str


class Design(BaseModel):
    name: str
    payload: dict


def _learner_input(req: RecommendRequest) -> Union[int, LearnerInput]:
    if req.learner_id is not None:
        return int(req.learner_id)
    if req.learner is None:
        raise HTTPException(422, "learner_id 또는 learner 가운데 하나는 있어야 합니다")
    d = req.learner.model_dump()
    d["events"] = [e if isinstance(e, dict) else e.model_dump() for e in d["events"]]
    return LearnerInput(**d)


def create_app(bundle: Union[Bundle, str], designs_dir: str = None) -> FastAPI:
    bundle = Bundle.load(bundle) if isinstance(bundle, str) else bundle
    svc = RecommendationService(bundle)
    designs_dir = designs_dir or os.path.join(os.getcwd(), "artifacts", "designs")
    os.makedirs(designs_dir, exist_ok=True)
    app = FastAPI(title="ETF 교육 콘텐츠 추천 시스템", version=__version__,
                  description="교육 콘텐츠 추천 시연기. 특정 ETF의 매수·매도를 권유하지 않습니다.")
    app.state.service = svc

    def guard(g: Optional[Guardrail]) -> GuardrailConfig:
        return GuardrailConfig(**g.model_dump()) if g else bundle.config.guardrail

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
        return svc.meta()

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

    @app.get("/api/learners")
    def learners(q: str = "", limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
        return svc.learners(q, limit, offset)

    @app.get("/api/learners/{uid}")
    def learner(uid: int):
        return wrap(lambda: svc.learner(uid))

    @app.post("/api/recommend")
    def recommend(req: RecommendRequest):
        return wrap(lambda: svc.recommend(_learner_input(req), k=req.k, algorithm=req.algorithm, guard=guard(req.guardrail),
                                          topic_cap=req.topic_cap, overrides=req.overrides, assume_passed=req.assume_passed))

    @app.post("/api/compare")
    def compare(req: CompareRequest):
        return wrap(lambda: svc.compare(_learner_input(req), k=req.k, methods=req.methods, guard=guard(req.guardrail),
                                        topic_cap=req.topic_cap, overrides=req.overrides, assume_passed=req.assume_passed))

    @app.post("/api/recommend-new")
    def recommend_new(req: NewUserRequest):
        return wrap(lambda: svc.recommend_new(req.topics, req.level, req.k, req.mobile))

    @app.post("/api/parse-log")
    def parse_log(req: LogText):
        """학습 로그 CSV 텍스트 → 이벤트 목록. item 번호 또는 title 열을 받는다."""
        try:
            df = pd.read_csv(io.StringIO(req.csv_text))
        except Exception as e:
            raise HTTPException(422, f"CSV를 읽지 못했습니다: {e}")
        cat = bundle.catalog
        title_to_item = {t: i for i, t in enumerate(cat.item_title)}
        events, warnings = [], []
        for idx, row in df.iterrows():
            item = None
            if "item" in df.columns and pd.notna(row.get("item")):
                try:
                    item = int(str(row["item"]).lstrip("Ee"))
                except ValueError:
                    item = None
            if item is None and "title" in df.columns:
                item = title_to_item.get(str(row["title"]).strip())
            if item is None or not 0 <= item < cat.n_items:
                warnings.append(f"{idx + 2}행: 단원을 찾지 못했습니다"); continue
            e = dict(item=item)
            for f in EVENT_FIELDS[1:]:
                if f in df.columns and pd.notna(row[f]):
                    v = row[f]
                    e[f] = bool(int(v)) if f in ("complete", "quiz", "quiz_pass", "save", "drop", "replay") and str(v).strip() in ("0", "1", "True", "False", "true", "false") \
                        else (bool(v) if isinstance(v, (bool,)) else (int(v) if f in ("week", "day", "hour", "minute") else bool(v)))
            events.append(e)
        return json_safe(dict(events=events, warnings=warnings, rows=int(len(df))))

    @app.get("/api/evaluation")
    def evaluation():
        return svc.evaluation()

    # ---- 저장한 설계 ----
    def _safe_name(name: str) -> str:
        s = re.sub(r"[^0-9A-Za-z가-힣_\- ]", "", name).strip()[:60]
        if not s:
            raise HTTPException(422, "설계 이름이 비어 있습니다")
        return s

    @app.get("/api/designs")
    def list_designs():
        out = []
        for fn in sorted(os.listdir(designs_dir)):
            if fn.endswith(".json"):
                with open(os.path.join(designs_dir, fn), encoding="utf-8") as f:
                    d = json.load(f)
                out.append(dict(name=d.get("name", fn[:-5]), saved_at=d.get("saved_at"), summary=d.get("summary", "")))
        return out

    @app.post("/api/designs")
    def save_design(d: Design):
        name = _safe_name(d.name)
        payload = dict(name=name, saved_at=time.strftime("%Y-%m-%d %H:%M:%S"), payload=d.payload,
                       summary=str(d.payload.get("summary", ""))[:120])
        with open(os.path.join(designs_dir, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"saved": name, "saved_at": payload["saved_at"]}

    @app.get("/api/designs/{name}")
    def get_design(name: str):
        p = os.path.join(designs_dir, _safe_name(name) + ".json")
        if not os.path.exists(p):
            raise HTTPException(404, "저장된 설계가 없습니다")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    @app.delete("/api/designs/{name}")
    def delete_design(name: str):
        p = os.path.join(designs_dir, _safe_name(name) + ".json")
        if os.path.exists(p):
            os.remove(p)
        return {"deleted": name}

    # ---- 정적 UI ----
    if os.path.isdir(UI_DIR):
        app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(os.path.join(UI_DIR, "index.html"))

    return app
