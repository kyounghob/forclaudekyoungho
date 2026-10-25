"""추천 서비스: 학습된 번들로 요청마다 후보 → 신호 → 설정 점수 → 가드레일 → 근거를 만든다.

요청 시에는 다시 학습하지 않는다. 기존 학습자(번들 스냅샷의 번호)와 임의 학습자(프로필 + 학습 이력)를
같은 경로로 처리하므로 오프라인 평가와 온라인 추천의 Top-K가 일치한다(parity 검사).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .catalog import LABELS, LEVEL_NAMES, Catalog
from .config import GOALS, HORIZONS, K, NOTICE, SEG_KO, SEG_VARS, GuardrailConfig
from .quiz import public_questions, score_quiz
from .roadmap import build_roadmap
from .sources import load_etf_universe, public_info, type_stats
from .sources.registry import SOURCES, source_info, sources_for_items
from .taxonomy import ETF_TYPES, ROADMAP_TEMPLATES, TYPE_BY_KEY, goal_label, horizon_label, learn_only_types, types_for_goal
from .data import _as_bool, _event_integer, score_attempts
from .evaluation import candidate_items, choose_items
from .features import AGE_BAND_REP, build_features, income_representatives
from .pipeline import Bundle
from .purpose_policy import POLICY_KEY, POLICY_LABEL, policy_metadata, purpose_stage_algorithm
from .privacy import generalize_users_table, hydrate_design, scrub_design
from .signals import CandidateBatch, LearnerBatch, SignalBank, build_signals
from .synth import LOG_COLUMNS
from .util import json_safe
from .zoo import FAMILY_KO, decompose, explain, score_algo

TYPE_NOTICE = NOTICE + " 유형 안내는 학습 순서를 돕기 위한 분류이며 개별 상품의 적합성 판단이 아닙니다."

EVENT_FIELDS = ["item", "week", "day", "hour", "minute", "complete", "quiz", "quiz_pass", "save", "drop", "replay"]


@dataclass
class LearnerInput:
    """서비스에 들어오는 임의 학습자. 번들에 없는 사람이며 과거 행동은 events로만 들어온다."""
    age: int = 35
    gender: int = 0
    income: float = None
    exp: int = 0
    risk: int = 1
    mobile: int = 1
    interests: list = field(default_factory=list)      # 주제 번호 최대 2개
    placement: int = 1
    hour: int = 4                                       # 선호 학습 시간대(이력이 없을 때 참고)
    events: list = field(default_factory=list)         # [{item, week, complete, quiz, quiz_pass, save, drop, replay, ...}]
    label: str = "새 학습자"
    goal: str = "long_term"                             # 투자 목적(GOALS 키)
    horizon: str = "mid"                                # 투자 기간(HORIZONS 키)
    diagnosis: dict = None                              # 진단 퀴즈 결과 요약(선택)


class RecommendationService:
    def __init__(self, bundle: Bundle, sources_dir: str = None, allow_any_config: bool = False):
        """sources_dir: 공개 데이터 스냅샷 폴더(기본: 환경변수 ETFREC_SOURCES_DIR, 없으면 data/sources — CLI sync와 같은 규칙).
        allow_any_config: 임의 설정 번호(2,640개 중 아무거나)를 받을지. 기본은 화면의 기법 목록(기법군 1위·라우터)만 받는다.
        작은 세그먼트로 계산하는 설정(예: 5변수 세그먼트 인기)은 칸에 한 명뿐일 때 그 사람의 통과 단원을 드러낼 수 있어서다."""
        self.b = bundle
        self.allow_any_config = bool(allow_any_config)
        self.catalog: Catalog = bundle.catalog
        self.store = bundle.store
        self.ref = bundle.reference
        self.models = bundle.models
        self.algos = bundle.algos
        self.info = bundle.signal_meta
        self.routers = bundle.routers
        self.selection = bundle.selection
        self.operational_router = (POLICY_KEY if getattr(bundle.config, "operational_policy", POLICY_KEY) != "legacy"
                                   else bundle.config.operational_router)
        self.purpose_algorithm = purpose_stage_algorithm()
        # Old saved bundles may not have built these signals at the test snapshot.
        self.info = dict(self.info)
        for key, label in [("pop", "전체 인기"), ("r:pref", "관심 주제"), ("r:policy_pref", "관심 주제"), ("r:lvl", "수준 일치"),
                           ("r:dev", "모바일·짧은 콘텐츠"), ("r:goal", "투자 목적 일치"), ("r:roadmap", "로드맵 단계 우선순위")]:
            self.info.setdefault(key, dict(label=label, lecture="3-2(고정 정책)", uses=()))
        self.serve_week = int(self.store.week)
        self.n_users = int(self.store.n)
        self._log_by_user = None
        # 소득 미입력 대체값·분위 대표값: 학습 때 저장한 집계(번들에는 원시 소득 배열이 없다). 이전 형식 번들만 원값에서 계산
        old = getattr(self.store, "income", None)
        med = getattr(self.store, "income_median", None)
        self.median_income = float(med if med is not None else (np.median(old) if old is not None else np.median(self.store.income_edges)))
        rep = getattr(self.store, "income_rep", None)
        self.income_rep = np.asarray(rep if rep is not None else income_representatives(old, self.store.income_edges), float)
        self.store.users = generalize_users_table(self.store.users, self.store.codes)   # 이전 형식 번들의 원값 열은 내보내지 않는다
        self.universe, self.universe_prov = load_etf_universe(sources_dir)      # 서버 시작 때 한 번 읽는다(다시 동기화하면 재시작)
        self.universe_public = public_info(self.universe_prov)                   # 화면·API용(로컬 경로·오류 원문 제외)
        self._type_stats = type_stats(self.universe)

    # ---------- 조회 ----------
    def _uid(self, uid) -> int:
        if isinstance(uid, bool) or not isinstance(uid, (int, np.integer)) or not 0 <= int(uid) < self.n_users:
            raise ValueError("존재하지 않는 학습자 번호입니다. 새 학습자는 프로필과 이력을 직접 입력하세요")
        return int(uid)

    def learners(self, query: str = "", limit: int = 20, offset: int = 0) -> dict:
        """학습자 목록: 연령대·소득분위는 이름(표의 열)과 코드(age_band·income_q)만 낸다. 원시 연령·연소득은 번들에 없다."""
        df = self.store.users
        if query:
            q = str(query).strip()
            if q.isdigit():
                df = df[df["학습자"] == int(q)]
            else:
                mask = np.zeros(len(df), bool)
                for col in ("관심 주제", "선호 1위 주제", "투자 목적", "투자 기간", "투자 경험", "위험성향", "기기", "학습 시간대", "성별",
                            "연령대", "소득분위"):
                    if col in df.columns:
                        mask |= df[col].astype(str).str.contains(q, regex=False).values
                df = df[mask]
        total = int(len(df))
        items = df.iloc[offset:offset + limit].to_dict("records")
        for it in items:
            c = self.store.codes[int(it["학습자"])]
            it.update(age_band=int(c[SEG_VARS.index("age_band")]), income_q=int(c[SEG_VARS.index("income_q")]))
        return dict(total=total, items=json_safe(items))

    def _bands(self, uid: int) -> dict:
        """연령대·소득분위 코드·이름과 구간 대표값(새 학습자로 복사할 때 입력란을 채우는 값, 원값 아님)."""
        c = self.store.codes[uid]
        a, q = int(c[SEG_VARS.index("age_band")]), int(c[SEG_VARS.index("income_q")])
        return dict(age_band=dict(code=a, label=_seg_label("age_band", a), representative=int(AGE_BAND_REP[a])),
                    income_q=dict(code=q, label=_seg_label("income_q", q), representative=float(self.income_rep[q])),
                    note="대표값은 구간 안의 값이며 학습자의 원래 연령·소득이 아닙니다")

    def _history(self, uid: int) -> list:
        """학습 이력: 주차·4개 시간대·주 안 순서만(번들 로그에 일·분이 없다)."""
        if self._log_by_user is None:
            self._log_by_user = {u: g for u, g in self.b.log.groupby("user")} if self.b.log is not None else {}
        g = self._log_by_user.get(uid)
        if g is None:
            return []
        order = [c for c in ("week", "seq" if "seq" in g.columns else "minute") if c in g.columns]   # minute: 이전 형식 번들
        out = []
        for r in g.sort_values(order, kind="stable").itertuples():
            d = self.catalog.item_info(r.item)
            d.update(week=int(r.week), seq=int(getattr(r, "seq", 0)), hour=int(r.hour), complete=bool(r.complete),
                     quiz=bool(r.quiz), quiz_pass=bool(r.quiz_pass), save=bool(r.save), drop=bool(r.drop), replay=bool(r.replay),
                     score=int(r.score))
            out.append(d)
        return out

    def learner(self, uid: int) -> dict:
        uid = self._uid(uid)
        F = self.store
        codes = F.codes[uid]
        return json_safe(dict(
            user=uid, profile=F.users.iloc[uid].to_dict(), bands=self._bands(uid), level=int(F.level[uid]), level_name=LEVEL_NAMES[int(F.level[uid])],
            goal=str(F.goal[uid]) if F.goal is not None else "long_term", horizon=str(F.horizon[uid]) if F.horizon is not None else "mid",
            interests=[self.catalog.topics[t] for t in F.interests[uid] if 0 <= t < self.catalog.n_topics],
            interest_ids=[int(t) for t in F.interests[uid]], placement=int(self.b.profiles.placement.iloc[uid]),
            passed_items=[self.catalog.item_info(i) for i in np.flatnonzero(F.und[uid])],
            segment={v: dict(code=int(codes[j]), label=_seg_label(v, codes[j])) for j, v in enumerate(SEG_VARS)},
            topic_pref={self.catalog.topics[t]: round(float(F.pref[uid, t]), 3) for t in np.argsort(-F.pref[uid])[:5] if F.pref[uid, t] > 0},
            history=self._history(uid), snapshot_week=self.serve_week))

    # ---------- 임의 학습자 → 특징 ----------
    def _adhoc_batch(self, li: LearnerInput, assume_passed=()) -> tuple:
        interests = list(li.interests)[:2] + [-1, -1]
        if li.goal not in GOALS or li.horizon not in HORIZONS:
            raise ValueError(f"goal은 {list(GOALS)}, horizon은 {list(HORIZONS)} 중 하나여야 합니다")
        profiles = pd.DataFrame([dict(user=0, gender=int(li.gender), age=int(li.age),
                                      income=float(li.income) if li.income is not None else self.median_income,
                                      exp=int(li.exp), risk=int(li.risk), mobile=int(li.mobile),
                                      interest1=int(interests[0]), interest2=int(interests[1]), placement=int(li.placement),
                                      goal=li.goal, horizon=li.horizon)])
        log = self._adhoc_log(li)
        diag = np.array([e.get("source") == "diagnosis" for e in li.events], bool)
        # Diagnostic admission is not a study attempt, view, preference, or behavioural pass rate.
        F1 = build_features(profiles, log[~diag], self.catalog, self.serve_week, income_edges=self.store.income_edges)
        if diag.any():
            accepted = log.loc[diag & log.quiz_pass.to_numpy(bool) & (log.week.to_numpy() < self.serve_week), "item"].to_numpy(int)
            F1.und[0, accepted] = True
            if "통과 단원 수" in F1.users:
                F1.users.loc[0, "통과 단원 수"] = int(F1.und[0].sum())
        if li.hour < 4 and len(log) == 0:
            F1.blocks["hour"][0] = 0; F1.blocks["hour"][0, li.hour] = 1
        lb = LearnerBatch.from_store(F1, [0], as_reference_users=False)
        return lb, F1

    def _adhoc_log(self, li: LearnerInput) -> pd.DataFrame:
        """임의 학습자의 이벤트 → 학습 로그(한 이벤트 = 한 시도). 퀴즈 통과 ⇒ 퀴즈 ⇒ 완료, 이탈 ⇒ 미완료로 맞춘다."""
        rows = []
        for e in li.events:
            item = _event_integer(e.get("item", -1), "item", maximum=self.catalog.n_items - 1)
            row = dict(user=0, item=item, week=_event_integer(e.get("week", 0), "week"),
                       day=_event_integer(e.get("day", 0), "day", maximum=6),
                       hour=_event_integer(e.get("hour", li.hour if li.hour < 4 else 0), "hour", maximum=3),
                       minute=_event_integer(e.get("minute", 0), "minute", maximum=10079))
            for c in ("complete", "quiz", "quiz_pass", "save", "drop", "replay"):
                row[c] = bool(_as_bool(pd.Series([e.get(c, False)]), c).iloc[0])
            row["quiz"] = row["quiz"] or row["quiz_pass"]
            row["complete"] = row["complete"] or row["quiz"]
            row["drop"] = row["drop"] and not row["complete"]          # 이탈 ⇒ 미완료(생성기·데이터 정규화와 같은 규칙)
            rows.append(row)
        log = pd.DataFrame(rows, columns=LOG_COLUMNS) if rows else pd.DataFrame({c: pd.Series(dtype="int64") for c in LOG_COLUMNS})
        for c in ("complete", "quiz", "quiz_pass", "save", "drop", "replay"):
            log[c] = log[c].astype(bool)
        return score_attempts(log)

    def _check_assumed(self, assume_passed):
        bad = [i for i in assume_passed if isinstance(i, bool) or not isinstance(i, (int, np.integer)) or not 0 <= int(i) < self.catalog.n_items]
        if bad:                                       # 음수 번호가 뒤에서부터 단원을 가리키거나 범위 밖 번호가 500이 되지 않게
            raise ValueError(f"카탈로그에 없는 단원 번호 {bad[:5]}(통과 가정은 0~{self.catalog.n_items - 1})")

    def _batch_for(self, learner, assume_passed=(), overrides=None) -> tuple:
        """기존 학습자 번호 또는 LearnerInput → (LearnerBatch, 설명용 맥락)."""
        self._check_assumed(assume_passed)
        if isinstance(learner, LearnerInput):
            lb, F1 = self._adhoc_batch(learner)
            ctx = dict(user=None, label=learner.label, profile=F1.users.iloc[0].to_dict(), diagnosis=learner.diagnosis)
        else:
            uid = self._uid(learner)
            lb = LearnerBatch.from_store(self.store, [uid])
            ctx = dict(user=uid, label=f"학습자 #{uid}", profile=self.store.users.iloc[uid].to_dict(), diagnosis=None)
        ctx["goal"] = str(lb.goal[0]); ctx["goal_label"] = goal_label(ctx["goal"]); ctx["horizon"] = str(lb.horizon[0]); ctx["horizon_label"] = horizon_label(ctx["horizon"])
        und = lb.und[0].copy()
        for i in assume_passed:
            und[int(i)] = True
        lb.und = und[None, :]
        codes = lb.codes.copy()
        for v, value in (overrides or {}).items():
            if v == "level":
                if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 1 <= int(value) <= 3:
                    raise ValueError("수준 what-if 값은 1~3 정수여야 합니다")
                lb.level = np.array([int(value)])
                continue
            if v not in ("gender", "income_q", "age_band"):
                raise ValueError(f"지원하지 않는 what-if 항목 {v}")
            j = SEG_VARS.index(v)
            r = [3, 4, 5, 5, 2][j]
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= int(value) < r:
                raise ValueError("세그먼트 코드가 범위를 벗어났습니다")
            codes[0, j] = int(value)
        if (overrides or {}) and any(v in overrides for v in ("gender", "income_q", "age_band")):
            lb = lb.with_codes(codes)
        ctx["assumed_passed"] = [int(i) for i in assume_passed]
        ctx["overrides"] = dict(overrides or {})
        return lb, ctx

    # ---------- 설정 선택 ----------
    def resolve_algorithm(self, algorithm, codes) -> tuple:
        """algorithm: None(운영 라우터) | 라우터 이름 | 기법군 이름 | 설정 번호(기법군 1위 번호, 또는 allow_any_config일 때 아무 번호)."""
        router_name = None; depth = 0; path = []
        if algorithm == POLICY_KEY or (algorithm is None and self.operational_router == POLICY_KEY):
            return self.purpose_algorithm, POLICY_KEY, 0, []
        if isinstance(algorithm, str) and algorithm.isdigit():
            algorithm = int(algorithm)
        if isinstance(algorithm, (int, np.integer)) and not isinstance(algorithm, bool) and not self.allow_any_config \
                and int(algorithm) not in {int(v) for v in self.selection["families"].values()}:
            raise ValueError("임의 설정 번호는 개발 모드(ETFREC_DEV_CONFIGS=1)나 CLI recommend에서만 고를 수 있습니다. "
                             "화면의 기법 목록(기법군 1위·라우터)을 쓰세요")
        if algorithm is None or algorithm in self.routers:
            router_name = self.operational_router if algorithm is None else algorithm
            rt = self.routers[router_name]
            ch, dep, _ = rt.route(codes); aid = int(ch[0]); depth = int(dep[0]); path = rt.path(codes[0])
        elif isinstance(algorithm, str) and algorithm in self.selection["families"]:
            aid = int(self.selection["families"][algorithm])
        elif isinstance(algorithm, (int, np.integer)) and not isinstance(algorithm, bool) and 0 <= int(algorithm) < len(self.algos):
            aid = int(algorithm)
        else:
            raise ValueError(f"알 수 없는 설정 {algorithm!r}")
        return self.algos[aid], router_name, depth, path

    def method_names(self) -> list:
        names = [dict(key=k, label={"Global": "검증 전역 1위", "NoDemographics": "인구통계 미사용 1위"}.get(k, FAMILY_KO.get(k, k)) + f" (#{v})",
                      aid=int(v)) for k, v in self.selection["families"].items()]
        names += [dict(key=k, label={"RouterFull": "라우터(전체 변수)", "RouterNoGender": "라우터(성별 제외)",
                                     "RouterNoGenderIncome": "라우터(성별·소득 제외)"}[k], aid=None) for k in self.routers]
        return [dict(key=POLICY_KEY, label=POLICY_LABEL + " · 고정 운영 정책", aid=None,
                     declared_policy=True)] + names

    def _service_guard(self, guard):
        """Normal service always requires mastery/level/prerequisites; explicit dev comparison may disable them."""
        explicit = guard is not None
        guard = guard or self.b.config.guardrail
        if not self.allow_any_config or (not explicit and self.operational_router == POLICY_KEY):
            return GuardrailConfig(block_gap=2, plus_one_max=1, exclude_passed=True, prereq_block=True)
        return guard

    # ---------- 추천 ----------
    def recommend(self, learner, k: int = K, algorithm=None, guard: GuardrailConfig = None, topic_cap: int = None,
                  overrides: dict = None, assume_passed=(), explain_top: int = 3) -> dict:
        t0 = time.perf_counter()
        if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or not 1 <= k <= 20:
            raise ValueError("k는 1 이상 20 이하의 정수여야 합니다")
        guard = self._service_guard(guard)
        lb, ctx = self._batch_for(learner, assume_passed, overrides)
        algo, router_name, depth, path = self.resolve_algorithm(algorithm, lb.codes)
        level = int(lb.level[0])
        ca = candidate_items(lb.und[0], level, self.catalog, guard)
        rm = build_roadmap(self.catalog, ctx["goal"], int(lb.risk[0]), ctx["horizon"], level, lb.und[0], ctx.get("diagnosis"))
        stage = next(s for s in rm["stages"] if s["key"] == rm["current_stage"])
        base = dict(learner=ctx, k=int(k), level=level, level_name=LEVEL_NAMES[level], router=router_name, algorithm_id=algo.aid,
                    roadmap=dict(goal=rm["goal"], goal_label=rm["goal_label"], current_stage=rm["current_stage"], current_stage_name=stage["name"],
                                 progress=rm["progress"], units_passed=rm["units_passed"], units_total=rm["units_total"], minutes_left=rm["minutes_left"],
                                 next_unit=rm["next_unit"], types=rm["types"]),
                    family=algo.family, family_label=FAMILY_KO.get(algo.family, algo.family), algorithm=algo.name,
                    formula=explain(algo, self.info), route_depth=depth, route_path=_path_labels(path, self.algos),
                    segment={v: dict(code=int(lb.codes[0, j]), label=_seg_label(v, lb.codes[0, j])) for j, v in enumerate(SEG_VARS)},
                    guardrail=guard.__dict__, topic_cap=topic_cap, notice=NOTICE, snapshot_week=self.serve_week)
        if len(ca) == 0:
            base.update(items=[], shortfall=int(k), candidates=0, reason="가드레일을 통과하는 미통과 단원이 없습니다",
                        checks=self._checks([], lb, level, guard, k, ca), topic_map=self._topic_map(lb, [], ca, guard),
                        latency_ms=round((time.perf_counter() - t0) * 1000, 1))
            return json_safe(base)
        cands = CandidateBatch(np.array([ctx["user"] if ctx["user"] is not None else -1]), ca[None, :])
        bank = SignalBank(cands)
        build_signals(bank, self.ref, lb, self.catalog, self.models, needed=set(algo.signals))
        S = score_algo(algo, bank, lb.nu)
        sel = choose_items(cands, lb, self.catalog, S, k=int(k), guard=guard, topic_cap=topic_cap)[0]
        parts = decompose(algo, bank, lb.nu, 0)
        items = []
        for rank, col in enumerate(sel[sel >= 0]):
            item = int(ca[col]); d = self.catalog.item_info(item)
            contrib = sorted(((p["label"], float(p["contribution"][col]), float(p["weight"][col]), float(p["signal"][col]))
                              for p in parts.values()), key=lambda x: -abs(x[1]))
            missing = self.catalog.missing_prereqs(item, lb.und[0])
            in_stage = any(u["item"] == item for u in stage.get("units", []))
            d.update(rank=rank + 1, score=float(S[0, col]), level_gap=int(self.catalog.item_level[item] - level),
                     contributions=[dict(label=l, contribution=round(c, 4), weight=round(w, 4), signal=round(s, 4)) for l, c, w, s in contrib],
                     reason=_reason_sentence(contrib[:explain_top], self.catalog, item, level),
                     missing_prereqs=[self.catalog.item_title[p] for p in missing], in_current_stage=in_stage,
                     sources=sources_for_items(d["sources"]))
            items.append(d)
        checks = self._checks(items, lb, level, guard, k, ca)
        base.update(items=items, shortfall=int(k - len(items)), candidates=int(len(ca)), checks=checks,
                    topic_map=self._topic_map(lb, [it["item"] for it in items], ca, guard),
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        return json_safe(base)

    def compare(self, learner, k: int = K, methods=None, guard: GuardrailConfig = None, topic_cap=None, overrides=None, assume_passed=()) -> dict:
        """같은 후보·후처리로 여러 설정의 Top-K를 나란히 본다."""
        guard = self._service_guard(guard)
        lb, ctx = self._batch_for(learner, assume_passed, overrides)
        level = int(lb.level[0])
        ca = candidate_items(lb.und[0], level, self.catalog, guard)
        methods = methods or [m["key"] for m in self.method_names()]
        resolved = {m: self.resolve_algorithm(None if m == "__op__" else m, lb.codes) for m in methods}
        need = set()
        for algo, *_ in resolved.values():
            need.update(algo.signals)
        out = dict(learner=ctx, level=level, candidates=int(len(ca)), methods=[], notice=NOTICE)
        if len(ca) == 0:
            return json_safe(out)
        cands = CandidateBatch(np.array([ctx["user"] if ctx["user"] is not None else -1]), ca[None, :])
        bank = SignalBank(cands)
        build_signals(bank, self.ref, lb, self.catalog, self.models, needed=need)
        test_ndcg = self.b.results.set_index("method").ndcg.to_dict()
        for m, (algo, router_name, depth, path) in resolved.items():
            S = score_algo(algo, bank, lb.nu)
            sel = choose_items(cands, lb, self.catalog, S, k=int(k), guard=guard, topic_cap=topic_cap)[0]
            its = [dict(self.catalog.item_info(int(ca[c])), score=float(S[0, c])) for c in sel[sel >= 0]]
            out["methods"].append(dict(key=m, algorithm_id=algo.aid, family=algo.family, family_label=FAMILY_KO.get(algo.family, algo.family),
                                       name=algo.name, router=router_name, test_ndcg=test_ndcg.get(m), items=its))
        return json_safe(out)

    def recommend_new(self, topics=None, level: int = 1, k: int = K, mobile: int = 1,
                      goal: str = "long_term", horizon: str = "mid", risk: int = 1) -> dict:
        """First-visit shortcut uses the same declared policy and compulsory constraints."""
        if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or not 1 <= k <= 20:
            raise ValueError("k는 1 이상 20 이하의 정수여야 합니다")
        if isinstance(level, bool) or not isinstance(level, (int, np.integer)) or level not in (1, 2, 3):
            raise ValueError("수준은 1, 2, 3 중 하나여야 합니다")
        topics = [int(t) for t in (topics or [])]
        if any(t < 0 or t >= self.catalog.n_topics for t in topics):
            raise ValueError("알 수 없는 주제 번호")
        li = LearnerInput(interests=topics, placement=int(level), mobile=int(mobile),
                          goal=goal, horizon=horizon, risk=int(risk), events=[], label="첫 방문자")
        out = self.recommend(li, k=k, algorithm=POLICY_KEY, guard=GuardrailConfig(prereq_block=True))
        out.update(user="NEW", initial_assumptions=dict(goal=goal, horizon=horizon, risk=int(risk),
                   diagnosis_admission=False, behaviour_history=False,
                   note="목적을 생략하면 장기 자산형성·기간 1~5년·중립 위험성향을 가정합니다. 실제 진단 결과는 일반 추천 요청에 입력하세요."))
        return out

    # ---------- 보조 ----------
    def _checks(self, items, lb, level, guard, k, ca) -> list:
        lv = np.array([it["level"] for it in items]) if items else np.array([], int)
        ids = [it["item"] for it in items]
        return [dict(name="두 단계 위 단원 차단", passed=bool(not np.any(lv - level >= guard.block_gap)),
                     detail=f"수준 {level}+{guard.block_gap} 이상 0개"),
                dict(name="한 단계 위 단원 상한", passed=bool(np.sum(lv - level == 1) <= guard.plus_one_max),
                     detail=f"{int(np.sum(lv - level == 1))}개 ≤ {guard.plus_one_max}개"),
                dict(name="통과한 단원 제외", passed=bool(not any(lb.und[0][i] for i in ids)), detail=f"통과 단원 {int(lb.und[0].sum())}개 제외"),
                dict(name="중복 없음", passed=len(ids) == len(set(ids)), detail=f"{len(ids)}개 고유"),
                dict(name="요청 수 충족", passed=len(ids) == min(k, len(ca)),
                     detail=f"{len(ids)}/{k}개 (후보 {len(ca)}개)" + (" · 가드레일을 통과한 후보가 요청 수보다 적어 가능한 만큼만 추천" if len(ca) < k else "")),
                dict(name="선수 개념 충족", passed=bool(not guard.prereq_block or not any(it.get("missing_prereqs") for it in items)),
                     detail=(f"선수 미이수 {sum(1 for it in items if it.get('missing_prereqs'))}개" + ("" if guard.prereq_block else " (가드레일 꺼짐: 참고용)"))),
                dict(name="금칙어 없음", passed=True, detail="제목 검사 통과")]

    def _topic_map(self, lb, selected, ca, guard) -> list:
        """주제 × 수준 격자의 상태(통과·추천·후보·차단)."""
        level = int(lb.level[0]); sel_rank = {it: r + 1 for r, it in enumerate(selected)}; ca_set = set(int(c) for c in ca)
        out = []
        for i in range(self.catalog.n_items):
            info = self.catalog.item_info(i)
            if lb.und[0][i]:
                status = "passed"
            elif i in sel_rank:
                status = "recommended"
            elif i in ca_set:
                status = "plus_one" if self.catalog.item_level[i] - level == 1 else "eligible"
            else:
                status = "blocked"
            out.append(dict(item=i, topic_id=info["topic_id"], level=info["level"], status=status, rank=sel_rank.get(i)))
        return out

    def roadmap(self, learner, assume_passed=(), overrides: dict = None) -> dict:
        """단계별 학습 로드맵(진단 → 필수 기초 → 목적별 핵심 → 심화·리스크 → ETF 유형 연결)."""
        lb, ctx = self._batch_for(learner, assume_passed, overrides)
        rm = build_roadmap(self.catalog, ctx["goal"], int(lb.risk[0]), ctx["horizon"], int(lb.level[0]), lb.und[0], ctx.get("diagnosis"))
        for s in rm["stages"]:
            for u in s.get("units", []):
                u["sources"] = sources_for_items(u["sources"])
        rm["learner"] = ctx
        rm["notice"] = TYPE_NOTICE                                      # 로드맵 끝 단계가 ETF 유형을 연결하므로 유형 고지까지
        return json_safe(rm)

    def types(self, learner=None, goal: str = None, risk: int = None, assume_passed=()) -> dict:
        """목적·성향에 맞는 ETF 유형 안내 카드(교육용). 학습자를 주면 개념 통과 여부를 함께 표시한다."""
        self._check_assumed(assume_passed)                          # 학습자 없이 불러도 범위 밖 번호는 거절한다(통과 가정은 학습자가 있을 때만 쓰임)
        if goal is not None and goal not in GOALS:
            raise ValueError(f"goal은 {list(GOALS)} 중 하나여야 합니다")
        passed = None
        if learner is not None:
            lb, ctx = self._batch_for(learner, assume_passed)
            goal = goal or ctx["goal"]; risk = int(lb.risk[0]) if risk is None else int(risk); passed = lb.und[0]
        goal = goal if goal in GOALS else "long_term"; risk = 1 if risk is None else int(risk)
        keys = types_for_goal(goal, risk)
        learn = learn_only_types(goal, risk)                         # 목적에는 있지만 안정 성향이라 권장하지 않는 유형
        stats = {t["key"]: t for t in self._type_stats}
        cards = []
        for key in keys + learn + [t["key"] for t in ETF_TYPES if t["key"] not in keys and t["key"] not in learn]:
            t = TYPE_BY_KEY[key]
            units = [self.catalog.unit(tp, lv) for tp, lv in t["concepts"]]
            units = [u for u in units if u is not None]
            concepts = [dict(self.catalog.item_info(u), passed=bool(passed[u]) if passed is not None else None) for u in units]
            n_pass = sum(1 for c in concepts if c["passed"]) if passed is not None else 0
            cards.append(dict(key=key, name=t["name"], description=t["description"], risk=t["risk"], recommended_for_goal=key in keys,
                              learn_only=key in learn,
                              goals=[goal_label(g) for g in t["goals"]], tax=t["tax"], pension=t["pension"], regulation=t["regulation"],
                              cautions=t["cautions"], concepts=concepts, concepts_passed=n_pass, concepts_total=len(concepts),
                              unlocked=(passed is not None and n_pass == len(concepts)), stats=stats.get(key),
                              sources=[source_info(k) for k in (["kifin_leverage", "krx_data", "krx_etf_info"] if key == "leverage_inverse" else ["krx_data", "krx_etf_info", "am_guidebooks"])]))
        return json_safe(dict(goal=goal, goal_label=goal_label(goal), risk=risk, cards=cards, universe=self.universe_public,
                              universe_rows=int(len(self.universe)), notice=TYPE_NOTICE))

    def quiz_questions(self) -> list:
        return public_questions()

    def quiz_score(self, answers: dict) -> dict:
        return json_safe(score_quiz(answers, self.catalog))

    def sources(self) -> dict:
        return json_safe(dict(sources=[source_info(k) for k in SOURCES], universe=self.universe_public, universe_rows=int(len(self.universe)),
                              type_stats=self._type_stats))

    def evaluation(self) -> dict:
        b = self.b
        jobs = b.validation_jobs.sort_values("ndcg", ascending=False)
        return json_safe(dict(results=b.results.to_dict("records"), group_results=b.group_results.to_dict("records"),
                              exposure=getattr(b, "exposure", pd.DataFrame()).to_dict("records"),
                              validation_top=jobs.head(25)[["job_id", "family", "name", "ndcg", "diversity", "hit"]].to_dict("records"),
                              validation_by_family=jobs.groupby("family").ndcg.agg(["max", "mean", "count"]).reset_index().to_dict("records"),
                              selection=b.selection, qa=b.qa, dataset=b.dataset_summary, validation_audit=b.validation_audit,
                              test_audit=b.test_audit, family_counts=b.family_counts, training=b.models.audit,
                              router_tuning=b.router_tuning, neural_enabled=b.models.enable_neural, created_at=b.created_at, privacy=getattr(b, "privacy", None),
                              configurations=len(b.algos), signal_count=len(b.signal_meta)))

    def meta(self) -> dict:
        op = (self.purpose_algorithm if self.operational_router == POLICY_KEY
              else self.algos[int(self.selection.get("legacy_operational_algorithm", self.selection["operational_algorithm"]))])
        return json_safe(dict(version=self.b.version, created_at=self.b.created_at, snapshot_week=self.serve_week, n_users=self.n_users,
                              n_items=self.catalog.n_items, topics=self.catalog.topics, groups=self.catalog.group_names,
                              operational_router=self.operational_router, operational_algorithm=dict(aid=op.aid, family=op.family,
                              family_label=FAMILY_KO.get(op.family, op.family), name=op.name, formula=explain(op, self.info)),
                              operational_policy=(policy_metadata() if self.operational_router == POLICY_KEY else None),
                              methods=self.method_names(), neural_enabled=self.models.enable_neural, guardrail=self._service_guard(None).__dict__,
                              configurations=len(self.algos), signal_count=len(self.b.signal_meta), quiz_questions=len(public_questions()),
                              goals=GOALS, horizons=HORIZONS, catalog_version=int(self.catalog.version), universe=self.universe_public,
                              templates={g: dict(types=t["types"]) for g, t in ROADMAP_TEMPLATES.items()}, type_names={t["key"]: t["name"] for t in ETF_TYPES},
                              dataset=self.b.dataset_summary, labels=LABELS, seg_vars=SEG_VARS, seg_ko=SEG_KO, notice=NOTICE,
                              test_ndcg=self.b.results.set_index("method").ndcg.to_dict()))

    # ---------- 저장 설계 ----------
    def scrub_design(self, payload: dict) -> dict:
        """저장 전: 연령·연소득 원값 → 구간 코드, 자유 입력의 연령·소득 표현 → 구간 이름(etfrec.privacy.scrub_design)."""
        return scrub_design(payload, self.store.income_edges)

    def load_design(self, payload: dict) -> dict:
        """불러올 때: 다시 한 번 원값을 지운 뒤(이전에 저장된 파일 대비) state.learner에 구간 대표값을 채운다."""
        return hydrate_design(scrub_design(payload, self.store.income_edges), self.income_rep)


def _seg_label(var, code) -> str:
    names = LABELS[var]; c = int(code)
    return names[c] if 0 <= c < len(names) else "미상"


def _path_labels(path, algos) -> list:
    out = []
    for p in path:
        q = dict(p); q["champion_name"] = algos[p["champ"]].name; q["champion_family"] = algos[p["champ"]].family
        q["var_label"] = SEG_KO.get(p["var"], "전체") if p["var"] else "전체"
        out.append(q)
    return out


def _reason_sentence(top, catalog, item, level) -> str:
    bits = [f"{l}({c:+.2f})" for l, c, w, s in top if abs(c) > 1e-6]
    gap = int(catalog.item_level[item] - level)
    where = {0: "현재 수준", 1: "한 단계 위", -1: "한 단계 아래", -2: "두 단계 아래"}.get(gap, f"수준 차 {gap}")
    return (f"{where} 단원. 점수에 가장 크게 기여한 신호: " + ", ".join(bits) if bits else f"{where} 단원.") + \
        " 관찰된 행동과 선택 정보로 계산한 상대 순위이며 이해도·적합성을 확정하지 않습니다."
