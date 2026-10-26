"""운영 후보 정책: 선언 정책(PurposeStageRule), 가중치 변형, 자격 조건을 만족하는 기존 설정.

정책은 JSON으로 저장할 수 있는 명세(spec)로 다룬다. terms = [[신호, [규칙...]], ...] 이고 규칙은 zoo.Algo와 같다
(["c", w] | ["a", λ, w] | ["1-a", λ, w]). hash는 신호·규칙을 정렬해 계산하므로 같은 식이면 같은 값이다.
자격 조건은 purpose_policy.replacement_rule을 따른다: 연령·소득·성별을 쓰지 않고, 목적·로드맵 항을 반드시 포함한다.
"""
from __future__ import annotations

import hashlib
import itertools
import json

from ..purpose_policy import POLICY_KEY, POLICY_LABEL, POLICY_VERSION, POLICY_WEIGHTS
from ..zoo import ALIASES, Algo

PROTECTED = ("gender", "age", "income")
GOAL_SIGNAL, ROADMAP_SIGNAL = "r:goal", "r:roadmap"
# 운영 근거로 쓰지 않는 신호: r:pref는 행동 기록이 없는 학습자에게도 정렬상 임의의 상위 두 주제를 관심으로 본다(purpose_policy)
NON_OPERATIONAL = {"r:pref": "행동 기록 없는 학습자의 임의 상위 주제를 관심으로 보는 신호(운영은 r:policy_pref)"}
DEFAULT_GRID = {"pop": (3.0, 5.0, 7.0), "r:policy_pref": (2.0, 3.0, 4.0), "r:lvl": (1.0, 2.0, 3.0),
                "r:dev": (0.0, 1.0), "r:goal": (1.0, 2.0, 3.0), "r:roadmap": (1.0, 2.0, 3.0)}
SHORT = {"pop": "인기", "r:policy_pref": "관심", "r:lvl": "수준", "r:dev": "모바일", "r:goal": "목적", "r:roadmap": "로드맵"}


def _canon_terms(terms) -> list:
    return [[str(s), [spec[0]] + [float(x) for x in spec[1:]]] for s, spec in terms]


def spec_hash(terms) -> str:
    body = json.dumps(sorted(_canon_terms(terms)), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def make_spec(key: str, name: str, family: str, terms, source: str, version: str = None, zoo_aid: int = None) -> dict:
    t = _canon_terms(terms)
    h = spec_hash(t)
    return dict(key=key, name=name, family=family, terms=t, source=source, version=version or f"ops-{h[:10]}", hash=h,
                zoo_aid=zoo_aid)


def declared_spec() -> dict:
    return make_spec(POLICY_KEY, POLICY_LABEL, "PURPOSE_STAGE", [(s, ("c", w)) for s, w in POLICY_WEIGHTS], "declared",
                     version=POLICY_VERSION)


def algo_from_spec(spec: dict) -> Algo:
    terms = [(s, tuple(rule)) for s, rule in spec["terms"]]
    aid = int(spec["zoo_aid"]) if spec.get("zoo_aid") is not None else -1
    return Algo(aid, spec.get("family", "PURPOSE_STAGE"), spec["name"], terms, (), "운영 루프",
                dict(policy_key=spec["key"], policy_version=spec["version"], policy_hash=spec["hash"], source=spec["source"]))


def spec_from_algo(algo: Algo, source: str = "zoo") -> dict:
    return make_spec(f"zoo-{algo.aid}", algo.name, algo.family, algo.terms, source, zoo_aid=int(algo.aid))


def variant_specs(grid: dict = None) -> list:
    """선언 정책 신호의 가중치 격자. 목적·로드맵 가중치는 격자에서도 0이 될 수 없다(필수 항)."""
    grid = grid or DEFAULT_GRID
    names = list(grid)
    out = []
    for ws in itertools.product(*(grid[n] for n in names)):
        terms = [(n, ("c", float(w))) for n, w in zip(names, ws) if w > 0]
        label = "·".join(f"{SHORT.get(n, n)}{w:g}" for n, w in zip(names, ws))
        out.append(make_spec(f"PSR-{spec_hash(terms)[:8]}", f"목적 단계 규칙 변형({label})", "PURPOSE_STAGE", terms, "variant"))
    return out


def term_weight(spec: dict, signal: str) -> float:
    """상수 가중치 항의 가중치(없으면 0). 학습량에 따라 바뀌는 α 규칙 항은 상수 보장이 없어 0으로 본다."""
    return float(sum(rule[1] for s, rule in spec["terms"] if s == signal and rule[0] == "c"))


def uses_of(spec: dict, info: dict) -> set:
    used = set()
    for s, rule in spec["terms"]:
        if s not in info:
            continue
        used.update(ALIASES.get(v, v) for v in info[s].get("uses", ()))
        if rule[0] in ("a", "1-a"):
            used.add("clicks")
    return used


def eligibility(spec: dict, info: dict, min_goal: float = 1.0, min_roadmap: float = 1.0) -> list:
    """자격 미달 사유 목록(빈 목록 = 자격 있음)."""
    reasons = []
    missing = [s for s, _ in spec["terms"] if s not in info]
    if missing:
        reasons.append(f"신호 없음: {missing}")
    bad = sorted(uses_of(spec, info) & set(PROTECTED))
    if bad:
        reasons.append(f"보호 변수 사용: {bad}")
    for s, _ in spec["terms"]:
        if s in NON_OPERATIONAL:
            reasons.append(f"{s}: {NON_OPERATIONAL[s]}")
    if term_weight(spec, GOAL_SIGNAL) < min_goal:
        reasons.append(f"목적 항 가중치 {term_weight(spec, GOAL_SIGNAL):g} < {min_goal:g}")
    if term_weight(spec, ROADMAP_SIGNAL) < min_roadmap:
        reasons.append(f"로드맵 항 가중치 {term_weight(spec, ROADMAP_SIGNAL):g} < {min_roadmap:g}")
    return reasons


def candidate_pool(champion: dict, algos=None, info: dict = None, grid: dict = None, include_zoo: bool = True) -> list:
    """현재 정책 + 선언 정책 + 가중치 변형 + (선택) 기존 설정 가운데 목적·로드맵 항이 있는 것. 같은 식(hash)은 하나만."""
    pool, seen = [], set()
    for spec in [champion, declared_spec()] + variant_specs(grid):
        if spec["hash"] not in seen:
            seen.add(spec["hash"]); pool.append(spec)
    if include_zoo and algos:
        for a in algos:
            if any(s == GOAL_SIGNAL for s, _ in a.terms) and any(s == ROADMAP_SIGNAL for s, _ in a.terms):
                spec = spec_from_algo(a)
                if spec["hash"] not in seen:
                    seen.add(spec["hash"]); pool.append(spec)
    return pool


def public_spec(spec: dict) -> dict:
    """이력·API에 남기는 요약(계산식 포함)."""
    return {k: spec.get(k) for k in ("key", "name", "family", "version", "hash", "source", "zoo_aid", "terms")}
