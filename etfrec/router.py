"""[교안 5-3] 계층 수축 세그먼트 라우터.

세그먼트 g의 설정 a 점수 = n_g/(n_g+λ)·(g 안 평균 NDCG) + λ/(n_g+λ)·(상위 세그먼트의 수축 점수).
세그먼트마다 수축 점수 1위를 챔피언으로 두고, 학습자는 자기 잎 세그먼트(없으면 가장 깊은 상위)의
챔피언으로 간다. 표본이 MIN_ROUTER_USERS 미만인 세그먼트는 상위 추정값을 그대로 쓴다. 이 규칙은 잎 크기를 보장하지
않는다(20명 미만 잎이 생긴다. 실제 크기는 etfrec.privacy.router_leaf_audit가 번들 privacy에 기록). 경로 출력(path)은
노드 크기를 구간('20명 미만'·'20~49명'·'50~99명'·'100~199명'·'200~499명'·'500명 이상')으로만 내보내고 노드의 원시 평균은 내보내지
않는다. 정확한 n과 원시 평균을 함께 내면 부모 − 표시된 형제의 차분으로 숨긴 노드의 n·평균이 복원되기 때문이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp

from .config import MIN_ROUTER_USERS, SEED, SEG_VARS
from .privacy import MIN_LEAF_DISPLAY
from .signals import shrink_to_parent


SIZE_BANDS = (20, 50, 100, 200, 500)


def size_band(n: int, min_display: int = MIN_LEAF_DISPLAY) -> str:
    """노드 크기 → 구간 이름('20명 미만', '20~49명', …, '500명 이상'). 정확한 값을 내보내지 않는다."""
    if n < min_display:
        return f"{min_display}명 미만"
    edges = [b for b in SIZE_BANDS if b >= min_display]
    for lo, hi in zip(edges, edges[1:]):
        if lo <= n < hi:
            return f"{lo}~{hi - 1}명"
    return f"{edges[-1]}명 이상"


class ShrinkRouter:
    def __init__(self, lam=50, order=tuple(SEG_VARS), top=10, min_users=MIN_ROUTER_USERS):
        self.lam, self.order, self.top, self.min_users = lam, tuple(order), top, min_users
        self.cols = [SEG_VARS.index(v) for v in self.order]
        self.levels = []

    def _key(self, codes, lv):
        key = np.zeros(len(codes), np.int64)
        for c in self.cols[:lv]:
            key = key * 16 + codes[:, c].astype(np.int64)
        return key

    def fit(self, M, codes, allowed=None):
        M = np.asarray(M, np.float64)
        codes = np.asarray(codes)
        if M.ndim != 2 or M.shape[0] == 0 or M.shape[1] == 0 or not np.isfinite(M).all():
            raise ValueError("라우터 학습 점수는 비어 있지 않은 유한한 2차원 배열이어야 합니다")
        if codes.ndim != 2 or codes.shape != (len(M), len(SEG_VARS)):
            raise ValueError("라우터 세그먼트 코드 모양이 학습 점수와 다릅니다")
        if allowed is not None:
            allowed = np.asarray(allowed, dtype=bool)
            if allowed.shape != (M.shape[1],) or not allowed.any():
                raise ValueError("라우터에 선택 가능한 설정이 하나 이상 있어야 합니다")
        if self.lam < 0 or np.isnan(self.lam):
            raise ValueError("라우터 수축 계수는 0 이상이어야 합니다")
        self.levels, prev_est, prev_keys = [], None, None
        for lv in range(len(self.cols) + 1):
            key = self._key(codes, lv)
            uk, first, inv = np.unique(key, return_index=True, return_inverse=True)
            N = np.bincount(inv, minlength=len(uk)).astype(float)
            ind = sp.csr_matrix((np.ones(len(inv)), (inv, np.arange(len(inv)))), shape=(len(uk), len(inv)))
            mean = np.asarray(ind @ M) / N[:, None]
            if lv == 0:
                est, pidx = mean, None
            else:
                pidx = np.searchsorted(prev_keys, self._key(codes[first], lv - 1))
                est = shrink_to_parent(mean, N[:, None], prev_est[pidx], self.lam)
                est[N < self.min_users] = prev_est[pidx][N < self.min_users]
            E = est if allowed is None else np.where(allowed[None, :], est, -np.inf)
            champ = E.argmax(1)
            top = np.argsort(-E, 1)[:, :self.top]
            Er = mean if allowed is None else np.where(allowed[None, :], mean, -np.inf)
            raw_champ = Er.argmax(1)
            self.levels.append(dict(keys=uk, N=N, champ=champ, est=E[np.arange(len(uk)), champ], top=top, raw_champ=raw_champ,
                                    raw_best=Er[np.arange(len(uk)), raw_champ], top_est=np.take_along_axis(E, top, 1),
                                    raw=mean[np.arange(len(uk)), champ], pidx=pidx, codes=codes[first][:, self.cols[:lv]]))
            prev_est, prev_keys = est, uk
        return self

    def route(self, codes):
        codes = np.asarray(codes)
        champ = np.full(len(codes), self.levels[0]["champ"][0])
        depth = np.zeros(len(codes), int)
        node = np.zeros(len(codes), int)
        for lv in range(1, len(self.levels)):
            L = self.levels[lv]
            key = self._key(codes, lv)
            pos = np.minimum(np.searchsorted(L["keys"], key), len(L["keys"]) - 1)
            found = (L["keys"][pos] == key) & np.all((codes[:, self.cols[:lv]] >= 0) & (codes[:, self.cols[:lv]] < 16), axis=1)
            champ[found], depth[found], node[found] = L["champ"][pos[found]], lv, pos[found]
        return champ, depth, node

    def path(self, code_row, min_display: int = MIN_LEAF_DISPLAY):
        """학습자 한 명이 거친 세그먼트 경로(수준별 표본 수 구간·챔피언·수축 추정 NDCG). 정확한 표본 수(n)와 노드만의 원시 평균
        (raw·raw_champ·raw_best)은 모든 노드에서 비우고, 크기는 n_label 구간으로만 내보낸다(차분으로 작은 노드를 복원하지 못하게).
        수축 추정(est·top_est)은 표본이 min_users 미만이면 상위 노드 값과 같다."""
        out = []
        code_row = np.asarray(code_row)
        for lv in range(len(self.levels)):
            L = self.levels[lv]
            key = self._key(code_row[None, :], lv)[0]
            pos = np.searchsorted(L["keys"], key)
            if np.any(code_row[self.cols[:lv]] < 0) or pos >= len(L["keys"]) or L["keys"][pos] != key:
                break
            n = int(L["N"][pos])
            out.append(dict(level=lv, var=None if lv == 0 else self.order[lv - 1], n=None, n_label=size_band(n, min_display),
                            champ=int(L["champ"][pos]), est=float(L["est"][pos]), raw=None, raw_champ=None, raw_best=None,
                            top=L["top"][pos].tolist(), top_est=np.round(L["top_est"][pos], 4).tolist()))
        return out


def tune_router(M, codes, lams=(0, 20, 100, 500, 3000, 1e9), reps=2, order=tuple(SEG_VARS), allowed=None, seed=SEED):
    """λ 선택: 검증 사용자를 반으로 나눠 한쪽으로 챔피언을 고르고 다른 쪽에서 점수를 본다(교차, reps회)."""
    M, codes = np.asarray(M), np.asarray(codes)
    if M.ndim != 2 or len(M) < 2:
        raise ValueError("라우터 교차검증에는 평가 사용자 2명 이상이 필요합니다")
    if reps < 1 or not len(lams):
        raise ValueError("라우터 반복 수와 수축 후보 목록은 비어 있을 수 없습니다")
    rng = np.random.default_rng(seed)
    rows = []
    for r in range(reps):
        half = rng.random(len(M)) < 0.5
        if not half.any() or half.all():
            half = np.zeros(len(M), dtype=bool)
            half[rng.permutation(len(M))[:max(1, len(M) // 2)]] = True
        for lam in lams:
            for fit_mask in (half, ~half):
                rt = ShrinkRouter(lam, order).fit(M[fit_mask], codes[fit_mask], allowed)
                ch, _, _ = rt.route(codes[~fit_mask])
                rows.append(dict(rep=r, lam=lam, score=float(M[~fit_mask][np.arange((~fit_mask).sum()), ch].mean())))
    return pd.DataFrame(rows).groupby("lam").score.agg(["mean", "std"]).reset_index()
