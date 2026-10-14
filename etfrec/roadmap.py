"""단계별 학습 로드맵: 진단 → 필수 기초 → 목적별 핵심 → 심화·리스크 → ETF 유형 연결.

입력은 투자 목적·위험성향·투자 기간·추정 수준·통과 단원이고, 출력은 선수 관계로 정렬된 단계별 단원 목록과
각 단원의 상태(통과·가능·잠김)다. 추천 엔진은 로드맵을 신호(r:roadmap)와 가드레일(prereq_block)로 쓴다.
"""
from __future__ import annotations

import numpy as np

from .catalog import Catalog
from .taxonomy import COMMON_CORE, ROADMAP_TEMPLATES, TYPE_BY_KEY, goal_label, horizon_label, types_for_goal

STAGE_DEFS = [("diagnosis", "진단"), ("core", "필수 기초 개념"), ("goal", "목적별 핵심 개념"), ("advanced", "심화·리스크"), ("connect", "ETF 유형 연결")]


def _closure(catalog: Catalog, items: list) -> list:
    """선수 단원을 재귀적으로 더한다(순서는 뒤에서 정렬)."""
    out, stack = [], list(items)
    seen = set()
    while stack:
        i = stack.pop()
        if i is None or i in seen:
            continue
        seen.add(i); out.append(i)
        stack.extend(catalog.prereqs.get(i, []))
    return out


def _topo(catalog: Catalog, items: list) -> list:
    """선수 단원이 먼저 오도록 정렬(동률은 수준 → 주제 순)."""
    items = sorted(set(items), key=lambda i: (int(catalog.item_level[i]), int(catalog.item_topic[i])))
    placed, out = set(), []
    remaining = list(items)
    while remaining:
        progressed = False
        for i in list(remaining):
            if all((p in placed) or (p not in items) for p in catalog.prereqs.get(i, [])):
                out.append(i); placed.add(i); remaining.remove(i); progressed = True
        if not progressed:                      # 순환이 있으면 남은 것을 그대로 붙인다(정의상 없어야 한다)
            out.extend(remaining); break
    return out


def _units(catalog: Catalog, pairs) -> list:
    return [u for u in (catalog.unit(t, l) for t, l in pairs) if u is not None]


def build_roadmap(catalog: Catalog, goal: str, risk: int, horizon: str, level: int, passed: np.ndarray, diagnosis: dict = None) -> dict:
    goal = goal if goal in ROADMAP_TEMPLATES else "long_term"
    tpl = ROADMAP_TEMPLATES[goal]
    passed = np.asarray(passed, bool)
    core = _closure(catalog, _units(catalog, COMMON_CORE))
    goal_units = [u for u in _closure(catalog, _units(catalog, tpl["core"])) if u not in core]
    adv_pairs = list(tpl["advanced"])
    if risk == 0:                               # 안정 성향: 레버리지 심화는 로드맵에서 뺀다(위험 인지 단원은 공통 기초에 남는다)
        adv_pairs = [(t, l) for t, l in adv_pairs if not (t == "레버리지·인버스" and l >= 2)]
    if horizon == "short":
        adv_pairs.append(("유동성", 2))
    if horizon == "long":
        adv_pairs.append(("리밸런싱", 2))
    adv = [u for u in _closure(catalog, _units(catalog, adv_pairs)) if u not in core and u not in goal_units]
    stage_items = {"core": _topo(catalog, core), "goal": _topo(catalog, goal_units), "advanced": _topo(catalog, adv)}
    stages, current, next_unit, total_min, left_min = [], None, None, 0, 0
    for key, name in STAGE_DEFS:
        if key == "diagnosis":
            d = diagnosis or {}
            stages.append(dict(key=key, name=name, units=[], passed=1 if d else 0, total=1, minutes_left=0, done=bool(d) or int(passed.sum()) > 0,
                               note=(f"진단 수준 {d.get('level')} · 맞힌 문항 {d.get('correct')}/{d.get('total')}" if d else
                                     f"추정 수준 {level} (학습 기록 {int(passed.sum())}개 통과)")))
            continue
        if key == "connect":
            keys = types_for_goal(goal, risk)
            stages.append(dict(key=key, name=name, units=[], passed=0, total=len(keys), minutes_left=0, done=False,
                               types=[dict(key=k, name=TYPE_BY_KEY[k]["name"], risk=TYPE_BY_KEY[k]["risk"],
                                           concepts_passed=int(sum(passed[u] for u in _units(catalog, TYPE_BY_KEY[k]["concepts"]))),
                                           concepts_total=len(_units(catalog, TYPE_BY_KEY[k]["concepts"]))) for k in keys],
                               note="단계별 개념을 통과하면 유형 안내 카드가 열린다"))
            continue
        units = []
        n_pass = 0
        for i in stage_items[key]:
            info = catalog.item_info(i)
            missing = catalog.missing_prereqs(i, passed)
            status = "passed" if passed[i] else ("locked" if missing else "available")
            n_pass += int(passed[i])
            total_min += info["minutes"]
            if not passed[i]:
                left_min += info["minutes"]
            units.append(dict(item=i, item_id=info["item_id"], title=info["title"], topic=info["topic"], level=info["level"], status=status,
                              minutes=info["minutes"], missing_prereqs=[catalog.item_title[p] for p in missing], sources=info["sources"],
                              concepts=info["concepts"], lesson=info.get("lesson")))
            if current is None and status == "available" and next_unit is None:
                next_unit = i
        done = n_pass == len(units)
        if current is None and not done:
            current = key
        stages.append(dict(key=key, name=name, units=units, passed=n_pass, total=len(units),
                           minutes_left=sum(u["minutes"] for u in units if u["status"] != "passed"), done=done))
    if current is None:
        current = "connect"
    n_units = sum(len(s["units"]) for s in stages)
    n_passed = sum(s["passed"] for s in stages if s["units"])
    return dict(goal=goal, goal_label=goal_label(goal), horizon=horizon, horizon_label=horizon_label(horizon), risk=int(risk), level=int(level),
                stages=stages, current_stage=current, next_unit=(catalog.item_info(next_unit) if next_unit is not None else None),
                units_total=n_units, units_passed=n_passed, progress=(n_passed / n_units if n_units else 0.0),
                minutes_total=total_min, minutes_left=left_min, types=types_for_goal(goal, risk))


def roadmap_priority(catalog: Catalog, roadmap: dict) -> np.ndarray:
    """(n_items,) 로드맵 우선순위: 현재 단계의 학습 가능 단원 1.0, 다음 단계 0.7, 선수 미이수 0.4, 로드맵 밖 0."""
    pr = np.zeros(catalog.n_items, np.float32)
    current = roadmap["current_stage"]
    seen_current = False
    for s in roadmap["stages"]:
        if not s["units"]:
            continue
        is_current = s["key"] == current
        for u in s["units"]:
            if u["status"] == "passed":
                continue
            if u["status"] == "locked":
                pr[u["item"]] = 0.4
            else:
                pr[u["item"]] = 1.0 if (is_current or not seen_current) else 0.7
        if is_current:
            seen_current = True
    return pr


def roadmap_priority_rows(catalog: Catalog, goals, risks, horizons, levels, passed_rows: np.ndarray) -> np.ndarray:
    """행마다 로드맵을 만들어 (R, n_items) 우선순위 행렬을 돌려준다(평가·신호 계산용)."""
    cache = {}
    out = np.zeros((len(goals), catalog.n_items), np.float32)
    for r in range(len(goals)):
        key = (goals[r], int(risks[r]), horizons[r], int(levels[r]), passed_rows[r].tobytes())
        if key not in cache:
            cache[key] = roadmap_priority(catalog, build_roadmap(catalog, goals[r], int(risks[r]), horizons[r], int(levels[r]), passed_rows[r]))
        out[r] = cache[key]
    return out
