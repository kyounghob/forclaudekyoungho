"""기록된 노출 확률로 다른 정책의 Top-K 성과를 추정한다(오프 폴리시 평가).

포함 확률 추정량: 요청 i에서 목표 정책의 목록 T_i 가운데 실제로 보인 단원 a마다 r(a)/p(a)를 더한다.
p(a)는 기록 정책에서 a가 보였을 확률(앞 칸 1, 마지막 칸 1−ε 또는 ε·q)이다. 보상이 함께 보인 다른 단원과
위치에 따라 달라지지 않는다는 가정 아래 E[Σ_{a∈T} r(a)](목록 안 성공 수)의 불편 추정량이다.
목표 단원이 기록 정책에서 보일 수 없었으면(p=0) 추정할 수 없으므로 지지 범위(support)를 함께 보고한다.
"""
from __future__ import annotations

import math

import numpy as np

from .exploration import inclusion_probability


def attach_rewards(impressions, feedback, event: str = "quiz_pass") -> list:
    """같은 주에 같은 학습자가 보인 단원에 event를 남기면 보상 1. user_ref가 없는 요청은 다시 계산할 수 없어 뺀다."""
    hit = {(int(r["user_ref"]), int(r["item"])) for r in feedback if r.get("event") == event and r.get("user_ref") is not None}
    out = []
    for imp in impressions:
        if imp.get("user_ref") is None:
            continue
        u = int(imp["user_ref"])
        out.append({**imp, "rewards": [1.0 if (u, int(it)) in hit else 0.0 for it in imp["items"]]})
    return out


def _request_terms(imp: dict, target, k: int):
    """한 요청의 (추정 기여, 맞은 가중치 목록, 지지된 목표 수, 목표 수, 탐색으로 맞은 가중치)."""
    T = [int(a) for a in list(target)[:k]]
    shown = {int(it): (float(p), float(r)) for it, p, r in zip(imp["items"], imp["propensity"], imp["rewards"])}
    explored_item = int(imp["items"][imp["slot"]]) if imp.get("explored") and imp.get("slot") is not None else None
    c, w_all, w_exp, supported = 0.0, [], [], 0
    for a in T:
        if inclusion_probability(a, imp) > 0:
            supported += 1
        if a in shown:
            p, r = shown[a]
            c += r / p; w_all.append(1.0 / p)
            if a == explored_item:
                w_exp.append(1.0 / p)
    return c, w_all, supported, len(T), w_exp


def policy_value(logged, targets: dict, k: int) -> dict:
    """targets: request_id → 목표 정책의 Top-K 단원 목록. 반환 값은 요청당 목록 안 성공 수의 추정치."""
    contrib, w_all, w_exp, supported, total = [], [], [], 0, 0
    for imp in logged:
        T = targets.get(imp["request_id"])
        if T is None:
            continue
        c, wa, s, t, we = _request_terms(imp, T, k)
        contrib.append(c); w_all += wa; w_exp += we; supported += s; total += t
    n = len(contrib)
    if n == 0:
        return dict(n=0, ips=None, se=None, ci_low=None, ci_high=None, snips=None, support=None, explore_matches=0, ess_explore=0.0)
    x = np.asarray(contrib)
    ips = float(x.mean())
    se = float(x.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    W = float(np.sum(w_all))
    snips = float(x.sum() / W * supported / n) if W > 0 else None
    we = np.asarray(w_exp)
    ess = float(we.sum() ** 2 / (we ** 2).sum()) if len(we) else 0.0
    return dict(n=n, ips=ips, se=se, ci_low=ips - 1.96 * se, ci_high=ips + 1.96 * se, snips=snips,
                support=float(supported / total) if total else None, explore_matches=int(len(we)), ess_explore=ess)


def paired_difference(logged, targets_new: dict, targets_old: dict, k: int) -> dict:
    """같은 요청에서 두 정책의 추정 기여 차이(새 − 기존)의 평균과 정규 근사 95% 구간.
    unique_matches: 새 정책에만 있는 단원이 탐색으로 실제 보인 횟수(차이를 뒷받침하는 표본)."""
    d, unique = [], 0
    for imp in logged:
        a, b = targets_new.get(imp["request_id"]), targets_old.get(imp["request_id"])
        if a is None or b is None:
            continue
        ca = _request_terms(imp, a, k)[0]; cb = _request_terms(imp, b, k)[0]
        d.append(ca - cb)
        only_new = set(int(x) for x in list(a)[:k]) - set(int(x) for x in list(b)[:k])
        unique += sum(1 for it in imp["items"] if int(it) in only_new)
    n = len(d)
    if n < 2:
        return dict(n=n, diff=None, se=None, ci_low=None, ci_high=None, unique_matches=unique)
    x = np.asarray(d); m = float(x.mean()); se = float(x.std(ddof=1) / math.sqrt(n))
    return dict(n=n, diff=m, se=se, ci_low=m - 1.96 * se, ci_high=m + 1.96 * se, unique_matches=int(unique))


def logged_value(logged) -> float:
    """기록 정책이 실제로 보인 목록의 요청당 성공 수(관측값)."""
    return float(np.mean([sum(imp["rewards"]) for imp in logged])) if logged else float("nan")
