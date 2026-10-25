"""torch 없이 쓰는 행렬분해·MLP (NumPy 구현, 보고서 표 9의 MF·MLP 행).

- ``implicit_als``: 암묵 피드백 ALS(Hu, Koren, Volinsky, 2008). 반응 r_ui > 0을 선호 1, 신뢰도 1 + α·r_ui로 두고
  미관측 칸은 신뢰도 1의 0으로 둔다(비선호로 확정하지 않는다). 사용자·단원 인자를 번갈아 닫힌 해로 푼다.
- ``bpr_mf``: BPR(Rendle 외, 2009) 쌍별 손실 −ln σ(x_ui − x_uj)로 학습하는 내적 MF. j는 사용자가 반응하지 않은 단원.
- ``PairMLP``: 9주차 MLP 구조(사용자·단원 임베딩 8차원 → 결합 → 은닉 16 ReLU → 출력 1)를 BPR 쌍 손실과 Adam으로 학습.

학습 기록이 없는 사용자의 벡터는 0으로 둔다(학습되지 않음). 이런 사용자는 모든 후보 점수가 같거나
단원 쪽 항으로만 정해지며, 평가에서는 다른 기본형 CF와 같이 고정 동점 순서를 따른다.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.special import expit


def _positive_matrix(R) -> sp.csr_matrix:
    R = sp.csr_matrix(R, dtype=np.float64)
    R.data = np.where(R.data > 0, R.data, 0.0)
    R.eliminate_zeros()
    return R


def _outer_rows(M: np.ndarray) -> np.ndarray:
    k = M.shape[1]
    return (M[:, :, None] * M[:, None, :]).reshape(len(M), k * k)


def _als_half(C1: sp.csr_matrix, B: np.ndarray, lam: float) -> np.ndarray:
    """한쪽 인자 풀기. C1 = 관측 칸의 (c − 1), B = 고정한 반대쪽 인자.
    (BᵀB + Σ(c−1)·b bᵀ + λI) x = Σ c·b  (선호 p = 1인 관측 칸만 우변에 들어간다)."""
    n, k = C1.shape[0], B.shape[1]
    A = np.asarray(C1 @ _outer_rows(B)).reshape(n, k, k) + (B.T @ B + lam * np.eye(k))
    C = C1.copy()
    C.data = C.data + 1.0
    rhs = np.asarray(C @ B)
    return np.linalg.solve(A, rhs[:, :, None])[:, :, 0]


def implicit_als(R, k: int = 16, lam: float = 1.0, alpha: float = 5.0, iters: int = 15, seed: int = 42):
    """반환: (사용자 인자 X, 단원 인자 Y). 점수 = X[u] · Y[i]."""
    R = _positive_matrix(R)
    C1 = R.copy()
    C1.data = alpha * C1.data
    C1T = C1.T.tocsr()
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 0.01, (R.shape[0], k))
    Y = rng.normal(0, 0.01, (R.shape[1], k))
    for _ in range(iters):
        X = _als_half(C1, Y, lam)
        Y = _als_half(C1T, X, lam)
    X[np.diff(R.indptr) == 0] = 0.0                     # 반응이 없는 사용자: 해가 0이다(수치 오차 정리)
    return X, Y


class _Adam:
    def __init__(self, params: dict, lr: float = 0.01, weight_decay: float = 0.0, b1: float = 0.9, b2: float = 0.999, eps: float = 1e-8):
        self.p, self.lr, self.wd, self.b1, self.b2, self.eps, self.t = params, lr, weight_decay, b1, b2, eps, 0
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}

    def step(self, grads: dict):
        self.t += 1
        c1, c2 = 1 - self.b1 ** self.t, 1 - self.b2 ** self.t
        for k, g in grads.items():
            if self.wd:
                g = g + self.wd * self.p[k]
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * g
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * g * g
            self.p[k] -= self.lr * (self.m[k] / c1) / (np.sqrt(self.v[k] / c2) + self.eps)


def _sample_negatives(u, n_items, positive_keys, rng, tries: int = 30):
    """사용자 u가 반응하지 않은 단원 j를 뽑는다(양성 키와 겹치면 다시 뽑는다)."""
    j = rng.integers(0, n_items, len(u))
    keys = np.sort(positive_keys)

    def bad_mask(jj):
        q = u * n_items + jj
        idx = np.minimum(np.searchsorted(keys, q), len(keys) - 1)
        return keys[idx] == q
    bad = bad_mask(j)
    for _ in range(tries):
        if not bad.any():
            break
        j[bad] = rng.integers(0, n_items, int(bad.sum()))
        bad = bad_mask(j)
    return j, ~bad


def bpr_mf(R, k: int = 16, weight_decay: float = 1e-3, lr: float = 0.01, epochs: int = 30, seed: int = 42, batch: int = 4096):
    """반환: (P, Q, 에폭별 손실). 관측 반응 (u, i)마다 에폭마다 새 음성 j를 뽑는다."""
    R = _positive_matrix(R)
    n, m = R.shape
    u_all = np.repeat(np.arange(n), np.diff(R.indptr)).astype(np.int64)
    i_all = R.indices.astype(np.int64)
    keys = u_all * m + i_all
    rng = np.random.default_rng(seed)
    params = dict(P=rng.normal(0, 0.1, (n, k)), Q=rng.normal(0, 0.1, (m, k)))
    opt = _Adam(params, lr=lr, weight_decay=weight_decay)
    losses = []
    for _ in range(epochs):
        order = rng.permutation(len(u_all))
        uu, ii = u_all[order], i_all[order]
        jj, ok = _sample_negatives(uu, m, keys, rng)
        uu, ii, jj = uu[ok], ii[ok], jj[ok]
        total = 0.0
        for s in range(0, len(uu), batch):
            bu, bi, bj = uu[s:s + batch], ii[s:s + batch], jj[s:s + batch]
            P, Q = params["P"], params["Q"]
            pu, qi, qj = P[bu], Q[bi], Q[bj]
            x = np.sum(pu * (qi - qj), axis=1)
            total += float(np.logaddexp(0, -x).sum())
            g = -expit(-x)[:, None] / len(bu)                      # d(평균 손실)/dx
            gP, gQ = np.zeros_like(P), np.zeros_like(Q)
            np.add.at(gP, bu, g * (qi - qj))
            np.add.at(gQ, bi, g * pu)
            np.add.at(gQ, bj, -g * pu)
            opt.step(dict(P=gP, Q=gQ))
        losses.append(total / max(len(uu), 1))
    P, Q = params["P"], params["Q"]
    P[np.diff(R.indptr) == 0] = 0.0                                # 학습 쌍이 없는 사용자는 학습되지 않음
    return P, Q, losses


class PairMLP:
    """사용자·단원 임베딩(d) → 결합 → Linear(2d→h) → ReLU → Linear(h→1). BPR 쌍 손실로 학습한다."""

    def __init__(self, n_users: int, n_items: int, d: int = 8, h: int = 16, seed: int = 42):
        rng = np.random.default_rng(seed)
        b1, b2 = 1 / np.sqrt(2 * d), 1 / np.sqrt(h)
        self.p = dict(Eu=rng.normal(0, 0.05, (n_users, d)), Ei=rng.normal(0, 0.05, (n_items, d)),
                      W1=rng.uniform(-b1, b1, (h, 2 * d)), c1=rng.uniform(-b1, b1, h),
                      W2=rng.uniform(-b2, b2, h), c2=np.zeros(1))
        self.d, self.rng, self.losses = d, rng, []

    def _forward(self, u, i):
        x = np.concatenate([self.p["Eu"][u], self.p["Ei"][i]], axis=1)
        z = x @ self.p["W1"].T + self.p["c1"]
        a = np.maximum(z, 0)
        return a @ self.p["W2"] + self.p["c2"][0], (x, z, a)

    def _backward(self, cache, u, i, df, grads):
        x, z, a = cache
        grads["W2"] += a.T @ df
        grads["c2"] += df.sum()
        dz = (df[:, None] * self.p["W2"][None, :]) * (z > 0)
        grads["W1"] += dz.T @ x
        grads["c1"] += dz.sum(0)
        dx = dz @ self.p["W1"]
        np.add.at(grads["Eu"], u, dx[:, :self.d])
        np.add.at(grads["Ei"], i, dx[:, self.d:])

    def fit(self, u, i, j, epochs: int = 12, lr: float = 0.01, weight_decay: float = 1e-4, batch: int = 4096):
        u, i, j = (np.asarray(a, np.int64) for a in (u, i, j))
        opt = _Adam(self.p, lr=lr, weight_decay=weight_decay)
        for _ in range(epochs):
            order = self.rng.permutation(len(u))
            total = 0.0
            for s in range(0, len(u), batch):
                ix = order[s:s + batch]
                bu, bi, bj = u[ix], i[ix], j[ix]
                fi, ci = self._forward(bu, bi)
                fj, cj = self._forward(bu, bj)
                x = fi - fj
                total += float(np.logaddexp(0, -x).sum())
                g = -expit(-x) / len(ix)
                grads = {k: np.zeros_like(v) for k, v in self.p.items()}
                self._backward(ci, bu, bi, g, grads)
                self._backward(cj, bu, bj, -g, grads)
                opt.step(grads)
            self.losses.append(total / max(len(u), 1))
        seen_u = np.bincount(u, minlength=len(self.p["Eu"])) > 0
        seen_i = (np.bincount(i, minlength=len(self.p["Ei"])) + np.bincount(j, minlength=len(self.p["Ei"]))) > 0
        self.p["Eu"][~seen_u] = 0.0                                  # 학습 쌍이 없는 사용자·단원은 0 벡터
        self.p["Ei"][~seen_i] = 0.0
        return self

    def score(self, u, i) -> np.ndarray:
        return self._forward(np.asarray(u, np.int64), np.asarray(i, np.int64))[0]
