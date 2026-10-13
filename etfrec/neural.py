"""행렬분해·MLP 학습(학습에만 torch가 필요하고, 추론은 NumPy로 한다).

- ``train_mf``: 6주차 내적 모델 + 9주차 음성 표본 확장(표본 0 = 확인된 비선호가 아니다).
- ``fit_observed_model``: 6주차 관측 점수 MF와 9주차 3차시 MLP(Embedding → concat → Linear → ReLU → Linear).
  학습 손실은 BCEWithLogitsLoss(MLP) / MSELoss(관측 MF)이며 추론에서만 sigmoid를 적용한다.
- ``ObservedWeights``: 학습된 가중치를 NumPy 배열로 들고 있어 torch 없이도 점수를 낼 수 있다.
- ``fold_in_user``: 새 학습자의 잠재 벡터를 ALS 한 단계(가중 릿지)로 구한다 — 프로젝트의 확장.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

try:  # torch는 선택 의존성
    import torch
    import torch.nn as nn
    torch.set_num_threads(1)
    HAS_TORCH = True
except ImportError:  # pragma: no cover - 환경에 따라 다름
    torch = None
    nn = None
    HAS_TORCH = False


def require_torch(what: str):
    if not HAS_TORCH:
        raise RuntimeError(f"{what}에는 torch가 필요합니다. `pip install torch` 후 다시 학습하거나, "
                           f"MF·MLP 없이 학습하려면 --no-neural 옵션을 쓰세요.")


def train_mf(rows, cols, vals, n_users, n_items, k=16, lr=0.05, reg=0.01, epochs=15,
             neg=3, conf_alpha=2.0, seed=42, batch=8192):
    """관측 양성 + 표본 0으로 학습하는 내적 MF. 모든 관측 양성은 음성 표본에서 제외한다."""
    require_torch("행렬분해 학습")
    rows = np.asarray(rows, dtype=np.int64); cols = np.asarray(cols, dtype=np.int64)
    vals = np.asarray(vals, dtype=np.float32)
    rng = np.random.default_rng(seed)
    known = np.unique(cols)
    positive = np.unique(rows * n_items + cols)
    nu = np.repeat(rows, neg)
    ni = rng.choice(known, size=len(nu)) if len(known) else np.empty(0, dtype=np.int64)
    collision = np.isin(nu * n_items + ni, positive)
    initially = int(collision.sum())
    for _ in range(30):
        if not collision.any():
            break
        ni[collision] = rng.choice(known, size=int(collision.sum()))
        collision = np.isin(nu * n_items + ni, positive)
    nu, ni = nu[~collision], ni[~collision]
    assert not np.isin(nu * n_items + ni, positive).any()
    uu = np.r_[rows, nu]; ii = np.r_[cols, ni]
    yy = np.r_[np.ones(len(rows)), np.zeros(len(nu))].astype(np.float32)
    ww = np.r_[1 + conf_alpha * np.log1p(np.maximum(vals, 0)), np.ones(len(nu))].astype(np.float32)
    with torch.random.fork_rng():
        torch.manual_seed(seed)
        model = nn.ModuleDict({"u": nn.Embedding(n_users, k), "i": nn.Embedding(n_items, k)})
        for emb in model.values():
            nn.init.normal_(emb.weight, 0, 0.1)
        opt = torch.optim.Adam(model.parameters(), lr=min(lr, 0.02))
        U = torch.from_numpy(uu); I = torch.from_numpy(ii); Y = torch.from_numpy(yy); C = torch.from_numpy(ww)
        losses = []
        for _ in range(epochs):
            order = rng.permutation(len(uu)); total = 0.0
            for start in range(0, len(uu), batch):
                ix = torch.from_numpy(order[start:start + batch])
                p, q = model["u"](U[ix]), model["i"](I[ix])
                mse = (C[ix] * ((p * q).sum(1) - Y[ix]).square()).mean()
                penalty = reg * (p.square().mean() + q.square().mean())
                loss = mse + penalty
                opt.zero_grad(); loss.backward(); opt.step()
                total += float(loss.detach()) * len(ix)
            losses.append(total / max(len(uu), 1))
        P = model["u"].weight.detach().numpy().copy(); Q = model["i"].weight.detach().numpy().copy()
    P[np.bincount(rows, minlength=n_users) == 0] = 0
    Q[np.bincount(cols, minlength=n_items) == 0] = 0
    audit = dict(model="MF_sampled", factors=k, reg=reg, seed=seed, positive_rows=len(rows), negative_rows=len(nu),
                 initial_negative_collisions=initially, final_negative_collisions=0,
                 loss_first=losses[0], loss_last=losses[-1])
    return P, Q, losses, audit


def fold_in_user(Q: np.ndarray, r_row: np.ndarray, reg: float = 0.01, conf_alpha: float = 2.0, neg: int = 3) -> np.ndarray:
    """새 학습자의 잠재 벡터: 고정된 Q에 대해 가중 릿지 회귀 한 단계(ALS 사용자 단계).
    관측 양성은 y=1·가중치 1+α·log1p(r), 나머지 아이템은 y=0·가중치 neg·n_pos/n_zero(학습 때 표본 비율과 맞춤)."""
    r_row = np.asarray(r_row, dtype=np.float64).ravel()
    pos = r_row > 0
    n_pos = int(pos.sum())
    if n_pos == 0:
        return np.zeros(Q.shape[1])
    w = np.where(pos, 1 + conf_alpha * np.log1p(r_row), neg * n_pos / max((~pos).sum(), 1))
    y = pos.astype(float)
    A = (Q * w[:, None]).T @ Q + reg * n_pos * np.eye(Q.shape[1])
    b = (Q * w[:, None]).T @ y
    return np.linalg.solve(A, b)


@dataclass
class ObservedWeights:
    """학습된 가중치(NumPy). padding_idx 0 = 학습되지 않은 사용자·아이템."""
    kind: str                      # 'mlp9' | 'mf_observed'
    user_emb: np.ndarray           # (n_users+1, d)
    item_emb: np.ndarray           # (n_items+1, d)
    W1: np.ndarray = None          # (hidden, 2d)
    b1: np.ndarray = None
    W2: np.ndarray = None          # (1, hidden)
    b2: np.ndarray = None
    user_seen: np.ndarray = None
    item_seen: np.ndarray = None
    audit: dict = None

    def score(self, uid: np.ndarray, iid: np.ndarray) -> np.ndarray:
        """uid·iid는 +1 이동된 번호(0 = 미학습). MLP는 sigmoid 확률, 관측 MF는 내적."""
        eu, ei = self.user_emb[uid], self.item_emb[iid]
        if self.kind == "mlp9":
            x = np.concatenate([eu, ei], axis=1)
            h = np.maximum(x @ self.W1.T + self.b1, 0)
            logit = (h @ self.W2.T + self.b2).ravel()
            return 1 / (1 + np.exp(-logit))
        return (eu * ei).sum(1)


def fit_observed_model(u, i, y, score, n_users, n_items, kind: str, seed: int = 42, epochs: int = 12) -> ObservedWeights:
    """관측된 (사용자, 아이템, 라벨) 행만으로 학습한다. 노출되지 않은 쌍은 만들어 넣지 않는다."""
    require_torch("관측 모델 학습")
    u = np.asarray(u, np.int64); i = np.asarray(i, np.int64)
    y = np.asarray(y if kind == "mlp9" else score, np.float32)
    if len(u) == 0:
        raise ValueError("관측 학습 라벨이 없습니다")
    if not np.isfinite(y).all() or np.any((y < 0) | (y > 1)):
        raise ValueError("라벨은 [0, 1] 범위의 유한한 값이어야 합니다")
    user_seen = np.bincount(u, minlength=n_users) > 0; item_seen = np.bincount(i, minlength=n_items) > 0
    rng = np.random.default_rng(seed + 71); losses = []
    with torch.random.fork_rng():
        torch.manual_seed(seed + 71)
        if kind == "mlp9":
            d, hdim = 8, 16
            user_emb = nn.Embedding(n_users + 1, d, padding_idx=0); item_emb = nn.Embedding(n_items + 1, d, padding_idx=0)
            mlp = nn.Sequential(nn.Linear(d * 2, hdim), nn.ReLU(), nn.Linear(hdim, 1))
            nn.init.normal_(user_emb.weight, 0, 0.05); nn.init.normal_(item_emb.weight, 0, 0.05)
            params = list(user_emb.parameters()) + list(item_emb.parameters()) + list(mlp.parameters())
            forward = lambda uu, ii: mlp(torch.cat([user_emb(uu), item_emb(ii)], dim=1)).squeeze(1)
            criterion = nn.BCEWithLogitsLoss()
        else:
            d = 16
            user_emb = nn.Embedding(n_users + 1, d, padding_idx=0); item_emb = nn.Embedding(n_items + 1, d, padding_idx=0)
            nn.init.normal_(user_emb.weight, 0, 0.1); nn.init.normal_(item_emb.weight, 0, 0.1)
            params = list(user_emb.parameters()) + list(item_emb.parameters())
            forward = lambda uu, ii: (user_emb(uu) * item_emb(ii)).sum(1)
            criterion = nn.MSELoss()
        with torch.no_grad():
            user_emb.weight[0].zero_(); item_emb.weight[0].zero_()
        opt = torch.optim.Adam(params, lr=0.01, weight_decay=0.0001)
        U = torch.from_numpy((u + 1).copy()); I = torch.from_numpy((i + 1).copy()); Y = torch.from_numpy(y.copy())
        for _ in range(epochs):
            order = rng.permutation(len(u)); total = 0.0
            for start in range(0, len(u), 4096):
                ix = torch.from_numpy(order[start:start + 4096]); out = forward(U[ix], I[ix]); loss = criterion(out, Y[ix])
                opt.zero_grad(); loss.backward(); opt.step(); total += float(loss.detach()) * len(ix)
            losses.append(total / len(u))
        ue = user_emb.weight.detach().numpy().copy(); ie = item_emb.weight.detach().numpy().copy()
        if kind == "mlp9":
            W1 = mlp[0].weight.detach().numpy().copy(); b1 = mlp[0].bias.detach().numpy().copy()
            W2 = mlp[2].weight.detach().numpy().copy(); b2 = mlp[2].bias.detach().numpy().copy()
        else:
            W1 = b1 = W2 = b2 = None
    blob = b"".join(a.tobytes() for a in [ue, ie] + ([W1, b1, W2, b2] if kind == "mlp9" else []))
    audit = dict(model=kind, training_rows=int(len(u)), positive=int(np.count_nonzero(y > 0)), zero=int(np.count_nonzero(y == 0)),
                 seed=seed + 71, epochs=epochs, loss_first=losses[0], loss_last=losses[-1],
                 state_sha256=hashlib.sha256(blob).hexdigest())
    return ObservedWeights(kind, ue, ie, W1, b1, W2, b2, user_seen, item_seen, audit)
