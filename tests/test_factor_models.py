"""NumPy 행렬분해·MLP(etfrec.factor_models) 검사: 기울기, 학습 방향, 학습되지 않은 사용자 처리."""
import numpy as np
import scipy.sparse as sp
from scipy.special import expit

from etfrec.factor_models import PairMLP, bpr_mf, implicit_als


def _block_matrix(seed=0):
    rng = np.random.default_rng(seed)
    R = np.zeros((40, 10))
    R[:20, :5] = rng.integers(0, 2, (20, 5)) * 2
    R[20:, 5:] = rng.integers(0, 2, (20, 5)) * 2
    R[39] = 0                                             # 반응이 없는 사용자
    return R


def test_implicit_als_separates_blocks_and_zeroes_empty_users():
    R = _block_matrix()
    X, Y = implicit_als(sp.csr_matrix(R), k=4, lam=0.1, alpha=5, iters=10)
    S = X @ Y.T
    assert S[:20, :5].mean() > S[:20, 5:].mean() + 0.3
    assert S[20:39, 5:].mean() > S[20:39, :5].mean() + 0.3
    assert np.allclose(X[39], 0)


def test_bpr_mf_loss_decreases_and_ranks_observed_first():
    R = _block_matrix()
    P, Q, losses = bpr_mf(sp.csr_matrix(R), k=4, weight_decay=1e-4, lr=0.05, epochs=40)
    S = P @ Q.T
    assert losses[-1] < losses[0] * 0.5
    assert S[:20, :5].mean() > S[:20, 5:].mean()
    assert np.allclose(P[39], 0)


def test_pair_mlp_gradient_matches_finite_difference():
    m = PairMLP(5, 4, d=3, h=4, seed=1)
    u, i, j = np.array([0, 1, 2, 0]), np.array([1, 2, 3, 0]), np.array([2, 0, 1, 3])

    def loss():
        fi, _ = m._forward(u, i)
        fj, _ = m._forward(u, j)
        return np.mean(np.logaddexp(0, -(fi - fj)))
    fi, ci = m._forward(u, i)
    fj, cj = m._forward(u, j)
    g = -expit(-(fi - fj)) / len(u)
    grads = {k: np.zeros_like(v) for k, v in m.p.items()}
    m._backward(ci, u, i, g, grads)
    m._backward(cj, u, j, -g, grads)
    for k, v in m.p.items():
        it = np.nditer(v, flags=["multi_index"])
        for _ in it:
            idx = it.multi_index
            old = v[idx]
            v[idx] = old + 1e-6
            lp = loss()
            v[idx] = old - 1e-6
            lm = loss()
            v[idx] = old
            assert abs((lp - lm) / 2e-6 - grads[k][idx]) < 1e-6, (k, idx)


def test_pair_mlp_learns_pairs_and_zeroes_unseen_users():
    R = _block_matrix()
    rng = np.random.default_rng(3)
    u, i = np.nonzero(R > 0)
    j = np.where(u < 20, rng.integers(5, 10, len(u)), rng.integers(0, 5, len(u)))
    m = PairMLP(40, 10, seed=3).fit(u, i, j, epochs=40, lr=0.02, batch=64)
    S = m.score(np.repeat(np.arange(40), 10), np.tile(np.arange(10), 40)).reshape(40, 10)
    assert m.losses[-1] < m.losses[0] * 0.5
    assert S[:20, :5].mean() > S[:20, 5:].mean()
    assert np.allclose(m.p["Eu"][39], 0)
