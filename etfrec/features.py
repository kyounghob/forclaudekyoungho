"""주간 스냅샷 특징 저장소.

기준 주 ``week`` 이전의 로그만 써서 사용자별 반응 행렬·수준·선호·세그먼트 코드를 만든다.
같은 함수가 (1) 기준 학습자 전체의 저장소와 (2) 서비스에 들어온 임의 학습자 한 명의 특징을
만들기 때문에 오프라인 평가와 온라인 추천의 입력이 같다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp

from .catalog import EXPS, HOURS, LABELS, RISKS, Catalog, onehot
from .config import CLICK_CUTS, GOALS, HORIZONS, SEG_VARS


def confidence(r, alpha=2.0):
    """[교안 2-2] confidence = 1 + alpha·log1p(r)"""
    return 1 + alpha * np.log1p(r)


def estimate_level(lg: pd.DataFrame, n: int, placement: np.ndarray, item_level: np.ndarray) -> np.ndarray:
    """모의 진단 수준에서 출발해 주차별로 갱신: 자기 수준보다 높은 퀴즈를 통과하면 +1,
    자기 수준 이하에서 두 번 떨어지면 −1 (원본 v1 규칙)."""
    lv = placement.copy()
    for w in sorted(lg.week.unique()):
        q = lg[(lg.week == w) & lg.quiz]
        il = item_level[q.item.values]
        up = np.zeros(n, bool)
        up[q.user.values[q.quiz_pass.values & (il > lv[q.user.values])]] = True
        fails = np.bincount(q.user.values[~q.quiz_pass.values & (il <= lv[q.user.values])], minlength=n)
        lv = np.clip(lv + up - (fails >= 2), 1, 3)
    return lv


AGE_CUTS = (30, 40, 50, 60)            # 연령대 경계: 29세 이하·30대·40대·50대·60세 이상
AGE_BAND_REP = (25, 35, 45, 55, 65)     # 연령대 대표값(화면 입력란 채우기용, 원값 아님)


def income_quintile(income: np.ndarray, edges: np.ndarray = None):
    """소득 분위 경계(20·40·60·80%)와 오른쪽 닫힌 구간 코드를 반환한다.

    연속 소득에서는 기존 qcut과 같다. 같은 소득이 많은 작은 집단에서도 네 경계를
    유지하고 같은 값은 같은 구간에 둔다. 동률을 임의 분할하지 않으므로 빈 분위가 가능하다.
    """
    values = np.asarray(income, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("소득은 비어 있지 않은 유한한 1차원 배열이어야 합니다")
    if edges is None:
        edges = np.quantile(values, [.2, .4, .6, .8])
    bounds = np.asarray(edges, dtype=float)
    if bounds.shape != (4,) or not np.isfinite(bounds).all() or np.any(np.diff(bounds) < 0):
        raise ValueError("소득 분위 경계는 오름차순의 유한한 값 4개여야 합니다")
    return np.searchsorted(bounds, values, side="left").astype(int), bounds


def income_representatives(income, edges) -> np.ndarray:
    """분위별 대표 소득(집계 5개): 분위수 10·30·50·70·90%를 10만원 단위로 반올림. 그 값이 자기 분위로 다시 분류되지 않거나
    원값이 없으면 분위 경계 사이 값을 쓴다. 기존 학습자를 새 학습자로 복사할 때 입력란을 채우는 데만 쓴다."""
    e = np.asarray(edges, float)
    mid = np.concatenate([[e[0]], (e[:-1] + e[1:]) / 2, [e[-1] + max((e[-1] - e[-2]) / 2, 1.0)]])
    if income is None:
        return mid
    rep = np.quantile(np.asarray(income, float), [0.1, 0.3, 0.5, 0.7, 0.9])
    rep = np.where(income_quintile(rep, e)[0] == np.arange(5), rep, mid)
    r10 = np.round(rep / 10) * 10
    return np.where(income_quintile(r10, e)[0] == np.arange(5), r10, rep)


@dataclass
class FeatureStore:
    """기준 주 이전 로그로 만든 사용자 특징(행 = 학습자). 원시 연령·연소득은 저장하지 않는다: 구간 코드(codes)와
    분위 경계·집계(income_edges·income_median·income_rep)만 남는다(etfrec.privacy)."""
    week: int
    n: int
    Rw: sp.csr_matrix                 # 반응 행렬(양수 점수 합)  [교안 2-2] preference = matrix > 0
    Rw_conf: sp.csr_matrix            # confidence 가중 반응 행렬
    nu: np.ndarray                    # 조회 수(α_u의 n_u)
    codes: np.ndarray                 # (n, 5) 세그먼트 코드 — SEG_VARS 순서
    pref: np.ndarray                  # (n, n_topics) 주제 선호 비중
    top2: np.ndarray                  # (n, 2) 기록상 선호 상위 2개 주제
    level: np.ndarray                 # (n,) 추정 수준 1~3
    und: np.ndarray                   # (n, n_items) 퀴즈 통과 여부
    blocks: dict                      # 인구통계·행동 원-핫 블록
    users: pd.DataFrame               # 화면 표시용 요약
    ev_user: np.ndarray               # 인기 이벤트(퀴즈 통과)의 사용자
    ev_item: np.ndarray
    interests: np.ndarray             # (n, 2) 온보딩 관심 주제
    risk: np.ndarray
    mobile: np.ndarray
    gender: np.ndarray
    income_edges: np.ndarray          # 소득 5분위 경계 4개(임의 학습자 분위 계산용)
    goal: np.ndarray = None           # (n,) 투자 목적 키
    horizon: np.ndarray = None        # (n,) 투자 기간 키
    stats: dict = field(default_factory=dict)
    income_median: float = None       # 소득 중앙값(집계) — 소득을 비운 임의 학습자의 대체값. 기준 집단에서만 채움
    income_rep: np.ndarray = None     # (5,) 분위별 대표 소득(집계). 기준 집단에서만 채움

    @property
    def demo(self) -> dict:
        return demo_sets(self.blocks)


DEMO_USES = {"all": ("age", "income", "gender", "experience", "risk", "device", "hour", "quiz", "completion", "drop", "level")}


def demo_sets(bl: dict) -> dict:
    """사용자 CF 인구통계 묶음."""
    return {"age": bl["age"], "age+inc": np.hstack([bl["age"], bl["inc"]]),
            "age+inc+gender": np.hstack([bl["age"], bl["inc"], bl["gender"]]),
            "all": np.hstack([bl[k] for k in ["age", "inc", "gender", "exp", "risk", "dev", "hour", "quiz", "comp", "drop", "level"]])}


def build_features(profiles: pd.DataFrame, log_before: pd.DataFrame, catalog: Catalog, week: int,
                   income_edges: np.ndarray = None, click_cuts=CLICK_CUTS, level_log: pd.DataFrame = None) -> FeatureStore:
    """profiles의 학습자들에 대해 log_before(기준 주 이전 시도)로 특징을 만든다. level_log를 주면 수준 갱신에는 그 로그만 쓴다
    (진단 퀴즈의 '진단 통과' 행은 통과 단원에는 들어가지만, 수준은 이미 퀴즈 판정에 반영되어 있어 다시 올리지 않는다)."""
    n = len(profiles)
    N_ITEMS, N_TOP = catalog.n_items, catalog.n_topics
    I_TOPIC, I_LEVEL = catalog.item_topic, catalog.item_level
    lg = log_before
    Rs = np.zeros((n, N_ITEMS)); np.add.at(Rs, (lg.user.values, lg.item.values), lg.score.values)
    Rpos = np.maximum(Rs, 0)
    Rw = sp.csr_matrix(Rpos)
    Rw_conf = sp.csr_matrix(np.where(Rpos > 0, confidence(Rpos), 0))
    views = np.bincount(lg.user, minlength=n)
    quiz = np.bincount(lg.user, weights=lg.quiz, minlength=n); qp = np.bincount(lg.user, weights=lg.quiz_pass, minlength=n)
    comp = np.bincount(lg.user, weights=lg.complete, minlength=n); saves = np.bincount(lg.user, weights=lg.save, minlength=n)
    drops = np.bincount(lg.user, weights=lg["drop"], minlength=n)
    qrate = np.where(quiz > 0, qp / np.maximum(quiz, 1), np.nan); crate = np.where(views > 0, comp / np.maximum(views, 1), np.nan)
    drate = np.where(views > 0, drops / np.maximum(views, 1), np.nan)
    tp = np.zeros((n, N_TOP)); np.add.at(tp, (lg.user.values, I_TOPIC[lg.item.values]), np.maximum(lg.score.values, 0))
    interests = profiles[["interest1", "interest2"]].values.astype(int)
    decl = np.zeros((n, N_TOP))
    for j in range(2):
        ok = (interests[:, j] >= 0) & (interests[:, j] < N_TOP)
        decl[np.flatnonzero(ok), interests[ok, j]] = 1
    pref = np.where(tp.sum(1, keepdims=True) > 0, tp / np.maximum(tp.sum(1, keepdims=True), 1e-9), decl / 2)
    g4 = np.stack([pref[:, catalog.topic_group == g].sum(1) for g in range(len(catalog.group_names))], 1)
    hc = np.zeros((n, 4)); np.add.at(hc, (lg.user.values, lg.hour.values), 1)
    hour = np.where(hc.sum(1) > 0, hc.argmax(1), 4)
    level = estimate_level(lg if level_log is None else level_log, n, profiles.placement.values.astype(int), I_LEVEL)
    und = np.zeros((n, N_ITEMS), bool)
    und[lg.user.values[lg.understood.values], lg.item.values[lg.understood.values]] = True
    top2 = np.argsort(-pref, 1)[:, :2]
    age = profiles.age.values.astype(int); income = profiles.income.values.astype(float)   # 원값은 구간 계산에만 쓰고 저장하지 않는다
    gender = profiles.gender.values.astype(int)
    age_band = np.digitize(age, AGE_CUTS)
    income_q, edges = income_quintile(income, income_edges)
    ref = income_edges is None                                     # 기준 집단(분위 경계를 여기서 만든다)일 때만 집계를 남긴다
    codes = np.stack([np.digitize(views, click_cuts), g4.argmax(1), age_band, income_q, gender], 1)
    bucket = lambda x: np.where(np.isnan(x), 3, np.digitize(np.nan_to_num(x), [1 / 3, 2 / 3]))
    exp_, risk, mobile = profiles.exp.values.astype(int), profiles.risk.values.astype(int), profiles.mobile.values.astype(int)
    blocks = dict(age=onehot(age_band, 5), inc=onehot(income_q, 5), gender=onehot(gender, 2), exp=onehot(exp_, 3),
                  risk=onehot(risk, 3), dev=onehot(mobile, 2), hour=onehot(hour, 5), quiz=onehot(bucket(qrate), 4),
                  comp=onehot(bucket(crate), 4), drop=onehot(bucket(drate), 4), level=onehot(level - 1, 3))
    goal = profiles["goal"].astype(str).values if "goal" in profiles.columns else np.full(n, "long_term")
    horizon = profiles["horizon"].astype(str).values if "horizon" in profiles.columns else np.full(n, "mid")
    TN = catalog.topics
    users = pd.DataFrame({"학습자": np.arange(n), "성별": np.array(LABELS["gender"])[gender],
                          "연령대": np.array(LABELS["age_band"])[age_band], "소득분위": np.array(LABELS["income_q"])[income_q],
                          "투자 목적": [GOALS.get(g, g) for g in goal], "투자 기간": [HORIZONS.get(h, h) for h in horizon],
                          "투자 경험": np.array(EXPS)[exp_], "위험성향": np.array(RISKS)[risk], "기기": np.where(mobile == 1, "모바일", "PC"),
                          "학습 시간대": np.array(HOURS + ["미상"])[hour],
                          "관심 주제": [" · ".join(TN[t] for t in it if 0 <= t < N_TOP) for it in interests],
                          "조회 수": views, "퀴즈 통과율": np.round(qrate, 2), "완료율": np.round(crate, 2), "저장 수": saves.astype(int),
                          "이탈률": np.round(drate, 2), "추정 수준": level, "선호 1위 주제": np.array(TN)[pref.argmax(1)],
                          "통과 단원 수": und.sum(1)})
    ev = lg[lg.understood]
    return FeatureStore(week=week, n=n, Rw=Rw, Rw_conf=Rw_conf, nu=views.astype(float), codes=codes, pref=pref, top2=top2,
                        level=level, und=und, blocks=blocks, users=users, ev_user=ev.user.values, ev_item=ev.item.values,
                        interests=interests, risk=risk, mobile=mobile, gender=gender,
                        income_edges=np.asarray(edges), goal=goal, horizon=horizon,
                        stats=dict(views=views, quiz=quiz, quiz_pass=qp, complete=comp, saves=saves, drops=drops, hour=hour),
                        income_median=float(np.median(income)) if ref else None,
                        income_rep=income_representatives(income, edges) if ref else None)


def feature_store(profiles: pd.DataFrame, log: pd.DataFrame, catalog: Catalog, week: int) -> FeatureStore:
    """기준 주 week의 추천·평가를 위한 저장소 = week 이전 로그만 사용."""
    return build_features(profiles, log[log.week < week], catalog, week)


def segment_label(codes_row, var: str) -> str:
    j = SEG_VARS.index(var)
    c = int(codes_row[j])
    names = LABELS[var]
    return names[c] if 0 <= c < len(names) else "미상"
