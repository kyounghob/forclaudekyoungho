"""규칙을 공개한 모의 학습 로그 생성기.

- 버전 1: 노트북 B 원본과 같은 난수 순서(노트북 기록과의 일치 검사용). 투자 목적은 난수를 쓰지 않고 프로필에서 규칙으로 정한다.
- 버전 2(기본): 투자 목적·투자 기간을 별도 난수 흐름으로 뽑아 주제 선호를 기울이고, 선수 단원을 통과하지 않은 단원은
  완료·퀴즈 통과 확률이 낮아진다(선수 관계가 데이터에 실제로 들어간다).
여기서 넣은 연령·소득·위험성향·성별·목적 효과는 현실의 사실이 아니라 가상 세계의 가정이다. ``effect``는 주제 선호·수준 민감도 등에 들어가는
인구통계 효과의 배율이다. ``effect=0``이어도 위약 세계는 아니다: 연령·소득이 목적·경험·위험성향·기기를 거쳐 행동에 남는다.
위약 점검은 인구통계 열을 학습자 사이에서 섞는 scripts/placebo_check.py로 한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .catalog import Catalog
from .config import EFFECT_SCALE, GENDER_EFFECT, GENERATOR_VERSION, GOAL_KEYS, HORIZON_KEYS, N_WEEKS, SEED
from .taxonomy import GOAL_TOPIC_AFFINITY

LOG_COLUMNS = ["user", "item", "week", "day", "hour", "complete", "quiz", "quiz_pass", "save", "drop", "replay", "minute"]
BOOL_COLUMNS = ["complete", "quiz", "quiz_pass", "save", "drop", "replay"]
GOAL_EFFECT = 0.8          # 버전 2: 목적 친화도가 주제 선호 로짓에 더해지는 크기
PREREQ_PENALTY = 0.8       # 버전 2: 미이수 선수 단원 1개당 완료·통과 로짓 감소(최대 2개까지)


def affinity_matrix(catalog: Catalog) -> np.ndarray:
    """(목적 수, 주제 수) 친화도 행렬."""
    A = np.zeros((len(GOAL_KEYS), catalog.n_topics))
    for g, key in enumerate(GOAL_KEYS):
        for t, w in GOAL_TOPIC_AFFINITY[key].items():
            if t in catalog.ti:
                A[g, catalog.ti[t]] = w
    return A


def rule_goal(age, risk, income_q, exp_) -> np.ndarray:
    """버전 1용: 난수 없이 프로필에서 목적을 정한다(55세 이상 연금, 젊고 적극 성향은 단기, 고소득 중년은 인컴, 그 외 장기/분산)."""
    goal = np.full(len(age), 2)                                  # long_term
    goal[(exp_ == 0) & (risk == 0)] = 4                          # diversify
    goal[(income_q >= 3) & (age >= 40) & (age < 55)] = 1          # income
    goal[(risk == 2) & (age < 35)] = 3                            # trading
    goal[age >= 55] = 0                                           # pension
    return goal


def sample_goal(rg: np.random.Generator, age, risk, income_q, exp_) -> np.ndarray:
    """버전 2용: 프로필에 따라 확률을 기울인 다항 추출."""
    n = len(age)
    logit = np.zeros((n, 5))
    logit[:, 0] += 1.2 * (age >= 50) + 0.6 * (age >= 40) - 0.8 * (age < 30)            # pension
    logit[:, 1] += 0.7 * (income_q >= 3) + 0.4 * (age >= 40) + 0.3 * (exp_ >= 1)         # income
    logit[:, 2] += 0.6 + 0.3 * (exp_ == 0)                                                # long_term
    logit[:, 3] += 1.0 * (risk == 2) + 0.6 * (age < 35) - 1.0 * (risk == 0)               # trading
    logit[:, 4] += 0.5 * (risk == 0) + 0.3 * (exp_ == 0)                                  # diversify
    p = np.exp(logit); p /= p.sum(1, keepdims=True)
    u = rg.random(n)
    return (u[:, None] > np.cumsum(p, 1)).sum(1).clip(0, 4)


def sample_horizon(rg: np.random.Generator, goal) -> np.ndarray:
    """목적별 투자 기간: 연금·장기 → 5년 이상이 많고, 단기 매매 → 1년 미만이 많다."""
    P = np.array([[0.05, 0.25, 0.70], [0.15, 0.55, 0.30], [0.05, 0.35, 0.60], [0.60, 0.35, 0.05], [0.15, 0.55, 0.30]])
    u = rg.random(len(goal))
    return (u[:, None] > np.cumsum(P[goal], 1)).sum(1).clip(0, 2)


def make_world(n: int, catalog: Catalog, seed: int = SEED, effect: float = EFFECT_SCALE,
               gender_effect: float = GENDER_EFFECT, n_weeks: int = N_WEEKS, version: int = GENERATOR_VERSION,
               goal_effect: float = GOAL_EFFECT, prereq_penalty: float = PREREQ_PENALTY) -> dict:
    """학습자 n명의 프로필과 n_weeks주 학습 로그를 만든다."""
    r = np.random.default_rng(seed)
    v2 = int(version) >= 2
    I_TOPIC, I_LEVEL, I_SHORT, N_ITEMS, N_TOP, TI = (catalog.item_topic, catalog.item_level, catalog.item_short,
                                                      catalog.n_items, catalog.n_topics, catalog.ti)
    gender = r.integers(0, 2, n)
    age = np.clip(np.round(r.normal(40, 12, n)), 19, 75).astype(int)
    log_inc = np.log(3500) + 0.5 * np.exp(-((age - 47) / 14) ** 2) + r.normal(0, 0.5, n)
    income = np.round(np.exp(log_inc) / 10) * 10
    z_inc = (log_inc - log_inc.mean()) / log_inc.std()
    exp_ = np.digitize(r.normal(0.4 * z_inc + 0.02 * (age - 40), 1.0, n), [-0.2, 0.9])        # 0 없음 1 1~3년 2 3년+
    risk = np.digitize(r.normal(0.5 * exp_ - 0.03 * (age - 40), 1.0, n), [-0.4, 0.6])
    mobile = (r.random(n) < 1 / (1 + np.exp(-(2.0 - 0.06 * (age - 35))))).astype(int)
    hour_p = r.dirichlet([2, 1.5, 3, 1.5], n)
    activity = r.lognormal(0, 0.7, n)
    diligence = r.normal(0, 1, n)
    L_true = np.clip(exp_ + 1 + (r.random(n) < 0.15) * r.choice([-1, 1], n), 1, 3)
    placement = np.clip(L_true + r.choice([-1, 0, 1], n, p=[0.1, 0.8, 0.1]), 1, 3)
    income_q = np.digitize(income, np.quantile(income, [0.2, 0.4, 0.6, 0.8]))
    # ---------- 투자 목적·기간 (버전 1: 규칙, 버전 2: 별도 난수 흐름) ----------
    if v2:
        rg = np.random.default_rng(seed + 17)
        goal = sample_goal(rg, age, risk, income_q, exp_)
        horizon = sample_horizon(rg, goal)
    else:
        goal = rule_goal(age, risk, income_q, exp_)
        horizon = np.where(goal == 3, 0, np.where(np.isin(goal, [0, 2]), 2, 1))
    z_age = (age - 42) / 12
    B = np.zeros((n, N_TOP))
    for t in ["채권 ETF", "분배금", "연금계좌 ETF", "자산배분", "리츠 ETF"]:
        B[:, TI[t]] += effect * 0.8 * z_age
    for t in ["섹터 ETF", "해외 ETF", "테마 ETF", "레버리지·인버스", "ESG ETF"]:
        B[:, TI[t]] -= effect * 0.6 * z_age
    for t in ["해외 ETF", "연금계좌 ETF", "환헤지", "자산배분"]:
        B[:, TI[t]] += effect * 0.5 * z_inc
    for t in ["레버리지·인버스", "섹터 ETF", "테마 ETF", "액티브 ETF"]:
        B[:, TI[t]] += effect * 0.6 * (risk - 1)
    for t in ["채권 ETF", "금 ETF", "자산배분", "리밸런싱"]:
        B[:, TI[t]] -= effect * 0.4 * (risk - 1)
    g_eff = np.random.default_rng(seed + 7).normal(0, gender_effect, N_TOP)
    B += effect * np.where(gender[:, None] == 1, 0.5, -0.5) * g_eff
    if v2:
        B += goal_effect * affinity_matrix(catalog)[goal]        # 목적이 주제 선호를 기울인다
    p = np.exp(B); p /= p.sum(1, keepdims=True)
    th = r.gamma(20 * p); theta = th / th.sum(1, keepdims=True)
    interests = np.argsort(-(np.log(theta + 1e-9) + r.gumbel(size=theta.shape)), 1)[:, :2]   # 온보딩 관심 주제 2개
    sgm = lambda x: 1 / (1 + np.exp(-x))
    b_topic = 1.0 * (1 + effect * (0.9 * sgm((age - 42) / 8) - 0.45))
    b_pop = 1.2 * (1 + effect * (0.6 - 1.2 * sgm((age - 35) / 8)))
    lv_pen = 1.4 * (1 + effect * np.array([0.5, 0.0, -0.4])[exp_])
    grp = np.digitize(age, [30, 40, 50, 60]) * 5 + np.digitize(income, np.quantile(income, [0.2, 0.4, 0.6, 0.8]))
    ra = np.random.default_rng(seed + 11)
    z_grp = ra.normal(0, 0.5 * effect, (25, N_ITEMS))
    z_gen = ra.normal(0, 0.2 * effect, (2, N_ITEMS))
    appeal = ra.normal(0, 0.4, N_ITEMS)
    understood = np.zeros((n, N_ITEMS), bool)
    seen = np.zeros((n, N_ITEMS), bool)
    pop_prev = np.ones(N_ITEMS) / N_ITEMS
    P_T = catalog.prereq_matrix.T.astype(np.int32)                 # (선수, 단원)
    recs = []
    for w in range(n_weeks):
        act = r.random(n) < (1 - np.exp(-0.6 * activity)) * (0.97 ** w)
        u = np.flatnonzero(act)
        n_s = np.minimum(1 + r.poisson(2.0 * activity[u]), 8)
        lvgap = I_LEVEL[None, :] - L_true[u][:, None]
        pop_norm = (pop_prev - pop_prev.min()) / (pop_prev.max() - pop_prev.min() + 1e-12)
        util = (b_topic[u][:, None] * np.log(theta[u][:, I_TOPIC] + 0.02) - lv_pen[u][:, None] * np.maximum(lvgap, 0)
                - 0.5 * np.maximum(-lvgap, 0) + b_pop[u][:, None] * pop_norm[None, :] + appeal[None, :]
                + z_grp[grp[u]] + z_gen[gender[u]] + 0.8 * (I_TOPIC[None, :, None] == interests[u][:, None, :]).any(-1)
                + 0.3 * (mobile[u][:, None] * I_SHORT[None, :]) - 3.0 * understood[u] - 0.7 * (seen[u] & ~understood[u]))
        keys = util + r.gumbel(size=util.shape)
        order = np.argsort(-keys, 1)
        week_recs = []
        sched_days = r.integers(0, 7, size=(len(u), 8))
        sched_hb = np.minimum((r.random((len(u), 8, 1)) > np.cumsum(hour_p[u], 1)[:, None, :]).sum(-1), 3)
        sched_min = np.sort(sched_days * 1440 + np.array([8, 12, 20, 23])[sched_hb] * 60 + r.integers(0, 50, size=(len(u), 8)), axis=1)
        for k in range(8):
            m = n_s > k
            uu, ii = u[m], order[m, k]
            gap = np.maximum(I_LEVEL[ii] - L_true[uu], 0)
            pen = 0.0
            if v2:                                                 # 선수 단원을 모르면 완료·통과가 어렵다
                missing = np.minimum(((~understood[uu]).astype(np.int32) * P_T[:, ii].T).sum(1), 2)
                pen = prereq_penalty * missing
            comp = r.random(len(uu)) < sgm(0.8 + 0.8 * diligence[uu] - 1.4 * gap - pen)
            quiz = comp & (r.random(len(uu)) < 0.7)
            qpass = quiz & (r.random(len(uu)) < sgm(1.5 + 0.6 * diligence[uu] - 1.8 * gap - pen))
            save = r.random(len(uu)) < 0.08 + 0.1 * (theta[uu, I_TOPIC[ii]] > 0.1)
            drop = ~comp & (r.random(len(uu)) < 0.8)
            replay = seen[uu, ii] & qpass
            minute = sched_min[m, k]
            day = minute // 1440
            hb = np.digitize((minute % 1440) // 60, [10, 15, 22])
            week_recs.append(np.stack([uu, ii, np.full(len(uu), w), day, hb, comp, quiz, qpass, save, drop, replay, minute], 1))
            seen[uu, ii] = True
            understood[uu, ii] |= qpass
            up_ = qpass & (I_LEVEL[ii] >= L_true[uu]) & (L_true[uu] < 3) & (r.random(len(uu)) < 0.25)
            L_true[uu[up_]] += 1
        R = np.concatenate(week_recs)
        recs.extend(week_recs)
        pop_prev = np.bincount(R[:, 1], weights=(R[:, 5] | R[:, 7]).astype(float), minlength=N_ITEMS) + 1
    R = np.concatenate(recs)
    log = pd.DataFrame(R, columns=LOG_COLUMNS)
    for c in BOOL_COLUMNS:
        log[c] = log[c].astype(bool)
    log["score"] = np.maximum.reduce([np.ones(len(log)), 2 * log.complete.values, 3 * log.quiz_pass.values, 3 * log.save.values])
    log["understood"] = log.quiz_pass
    profiles = pd.DataFrame({"user": np.arange(n), "gender": gender, "age": age, "income": income, "exp": exp_,
                             "risk": risk, "mobile": mobile, "interest1": interests[:, 0], "interest2": interests[:, 1],
                             "placement": placement, "goal": np.array(GOAL_KEYS)[goal], "horizon": np.array(HORIZON_KEYS)[horizon]})
    return dict(n=n, profiles=profiles, log=log, g_eff=g_eff, theta=theta, L_true=L_true, version=int(version))
