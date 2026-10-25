"""행렬분해·MLP 학습(학습에만 torch가 필요하고, 추론은 NumPy로 한다).

- ``train_mf``: 6주차 내적 모델 + 9주차 음성 표본 확장(표본 0 = 확인된 비선호가 아니다).
- ``fit_observed_model``: 6주차 관측 점수 MF와 9주차 3차시 MLP(Embedding → concat → Linear → ReLU → Linear).
  학습 손실은 BCEWithLogitsLoss(MLP) / MSELoss(관측 MF)이며 추론에서만 sigmoid를 적용한다.
- ``ObservedWeights``: 학습된 가중치를 NumPy 배열로 들고 있어 torch 없이도 점수를 낼 수 있다.
- ``fold_in_user``: 새 학습자의 잠재 벡터를 ALS 한 단계(가중 릿지)로 구한다 — 프로젝트의 확장.
- ``train_mf_bpr``: BPR(Rendle 외, 2009) 쌍별 손실 −ln σ(x_ui − x_uj)로 학습하는 내적 MF — 미관측을 '거절'이 아니라
  '양성보다 뒤'로만 보는 암묵 피드백 순위 학습(중간 점검 지적 반영).
- ``fit_observed_model(kind="mlp9_bpr")``: 같은 9주차 MLP 구조를 관측 시도 안의 (통과 단원, 미통과 시도 단원) 쌍으로 학습.
- ``fit_observed_model(kind="mlp9_bpru")``: 같은 구조를 (통과 단원, 시도하지 않은 단원) 쌍으로 학습 — 지적이 처방한 BPR(양성 vs 미관측) 그대로.
- ``fit_observed_model(kind="mlp9_next", pairs=...)``: 목표 정렬 모델. 학습 주 w의 '그 주 통과 단원'을 양성,
  w 이전에 통과하지 않았고 w에도 통과하지 않은 단원을 음성으로 쌍을 만들어 평가 목표(다음 주 선택·통과)를 직접 학습한다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from scipy.special import expit

try:  # torch는 선택 의존성
    import torch
    import torch.nn as nn
    torch.set_num_threads(1)
    HAS_TORCH = True
except ImportError:  # pragma: no cover - 환경에 따라 다름
    torch = None
    nn = None
    HAS_TORCH = False


MLP_KINDS = ("mlp9", "mlp9_bpr", "mlp9_bpru", "mlp9_next")   # 9주차 MLP 구조를 쓰는 종류(손실·학습 쌍만 다름)


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
                 loss_first=losses[0], loss_last=losses[-1], learning_rate=float(min(lr, 0.02)),
                 target="observed user-item pair=1; sampled unobserved pair=0",
                 confidence="1 + conf_alpha * log1p(aggregated action score)")
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


def train_mf_bpr(rows, cols, n_users, n_items, k=16, lr=0.02, reg=0.01, epochs=15, neg=3, seed=42, batch=8192):
    """BPR 쌍별 손실로 학습하는 내적 MF. 관측 양성 (u,i)마다 그 사용자가 관측하지 않은 j를 neg개 뽑아
    −ln σ(p_u·q_i − p_u·q_j)를 줄인다. 점수의 절대값이 아니라 양성이 미관측보다 앞서는 '순위'만 학습한다."""
    require_torch("BPR 행렬분해 학습")
    rows = np.asarray(rows, dtype=np.int64); cols = np.asarray(cols, dtype=np.int64)
    rng = np.random.default_rng(seed + 11)
    known = np.unique(cols)
    positive = np.unique(rows * n_items + cols)
    nu = np.repeat(rows, neg); ni = np.repeat(cols, neg)

    def sample_negatives():
        """양성과 겹치지 않는 미관측 j를 뽑는다(겹치면 최대 30번 다시 뽑고, 남으면 그 쌍을 이번 에폭에서 뺀다)."""
        nj = rng.choice(known, size=len(nu)) if len(known) else np.empty(0, dtype=np.int64)
        collision = np.isin(nu * n_items + nj, positive)
        first = int(collision.sum())
        for _ in range(30):
            if not collision.any():
                break
            nj[collision] = rng.choice(known, size=int(collision.sum()))
            collision = np.isin(nu * n_items + nj, positive)
        keep = ~collision
        assert not np.isin(nu[keep] * n_items + nj[keep], positive).any()
        return nj, keep, first

    nj0, keep0, initially = sample_negatives()
    if not keep0.any():
        raise ValueError("BPR 학습용 미관측 음성 쌍이 없습니다. 관측 아이템 풀을 확인하세요.")
    with torch.random.fork_rng():
        torch.manual_seed(seed + 11)
        Pe, Qe = nn.Embedding(n_users, k), nn.Embedding(n_items, k)
        nn.init.normal_(Pe.weight, 0, 0.1); nn.init.normal_(Qe.weight, 0, 0.1)
        opt = torch.optim.Adam(list(Pe.parameters()) + list(Qe.parameters()), lr=lr)
        U_all = torch.from_numpy(nu); I_all = torch.from_numpy(ni)
        losses, n_pairs = [], 0
        for ep in range(epochs):
            nj, keep = (nj0, keep0) if ep == 0 else sample_negatives()[:2]      # 에폭마다 음성 재표본(LearnBPR 방식)
            kt = torch.from_numpy(keep)
            U, I, J = U_all[kt], I_all[kt], torch.from_numpy(nj[keep])
            n_pairs = int(keep.sum())
            order = rng.permutation(n_pairs); total = 0.0
            for start in range(0, n_pairs, batch):
                ix = torch.from_numpy(order[start:start + batch])
                p, qi, qj = Pe(U[ix]), Qe(I[ix]), Qe(J[ix])
                x = (p * (qi - qj)).sum(1)
                loss = -nn.functional.logsigmoid(x).mean() + reg * (p.square().mean() + qi.square().mean() + qj.square().mean())
                opt.zero_grad(); loss.backward(); opt.step()
                total += float(loss.detach()) * len(ix)
            losses.append(total / max(n_pairs, 1))
        P = Pe.weight.detach().numpy().copy(); Q = Qe.weight.detach().numpy().copy()
    P[np.bincount(rows, minlength=n_users) == 0] = 0
    Q[np.bincount(cols, minlength=n_items) == 0] = 0
    audit = dict(model="MF_BPR", factors=k, reg=reg, seed=seed + 11, positive_rows=int(len(rows)), pairs=n_pairs, epochs=epochs,
                 negative_resampling="per-epoch", initial_negative_collisions=initially, final_negative_collisions=0,
                 loss_first=losses[0], loss_last=losses[-1], learning_rate=float(lr),
                 positive_definition="observed user-item pair, not quiz-pass only")
    return P, Q, losses, audit


@dataclass
class ObservedWeights:
    """학습된 가중치(NumPy). padding_idx 0 = 학습되지 않은 사용자·아이템."""
    kind: str                      # MLP_KINDS 중 하나 | 'mf_observed'
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
        """uid·iid는 +1 이동된 번호(0 = 미학습). MLP는 sigmoid 점수, 관측 MF는 내적.
        쌍별 MLP의 sigmoid는 순서를 보존하는 변환이며 보정된 퀴즈 통과확률이 아니다."""
        eu, ei = self.user_emb[uid], self.item_emb[iid]
        if self.kind in MLP_KINDS:
            x = np.concatenate([eu, ei], axis=1)
            h = np.maximum(x @ self.W1.T + self.b1, 0)
            logit = (h @ self.W2.T + self.b2).ravel()
            return expit(logit)                     # 안정적 sigmoid: 큰 음수에서도 exp 오버플로 없음
        return (eu * ei).sum(1)


def fit_observed_model(u, i, y, score, n_users, n_items, kind: str, seed: int = 42, epochs: int = 12, pairs: dict = None,
                       pair_rows: dict = None, pair_cap: int = 400000) -> ObservedWeights:
    """관측된 (사용자, 아이템, 라벨) 행으로 학습한다(mlp9·mf_observed는 노출되지 않은 쌍을 만들어 넣지 않는다).
    쌍별 종류: mlp9_bpr(음성 = 시도했지만 미통과), mlp9_bpru(음성 = 시도하지 않은 단원), mlp9_next(목표 정렬 쌍을 pairs로 받음).
    쌍별 종류는 쌍에 한 번이라도 나온 사용자·단원만 '학습됨'(user_seen·item_seen)으로 표시한다. 쌍이 없는 사용자(예: 학습 주에
    통과가 없는 사용자)는 학습되지 않은 임베딩 대신 신호 계산 단계의 콘텐츠 유사도 대체 점수를 받는다(signals.build_signals).
    pair_rows: 학습 행을 부분표본으로 줄였을 때 쌍의 양성·음성 풀을 만들 전체 관측 행(u·i·y). 없으면 u·i·y를 쓴다."""
    require_torch("관측 모델 학습")
    u = np.asarray(u, np.int64); i = np.asarray(i, np.int64)
    y = np.asarray(y if kind in MLP_KINDS else score, np.float32)
    if len(u) == 0:
        raise ValueError("관측 학습 라벨이 없습니다")
    if not np.isfinite(y).all() or np.any((y < 0) | (y > 1)):
        raise ValueError("라벨은 [0, 1] 범위의 유한한 값이어야 합니다")
    user_seen = np.bincount(u, minlength=n_users) > 0; item_seen = np.bincount(i, minlength=n_items) > 0
    rng = np.random.default_rng(seed + 71); losses = []
    if kind in ("mlp9_bpr", "mlp9_bpru"):                       # 쌍별: (통과 단원, 미통과 시도 단원) 또는 (통과 단원, 시도하지 않은 단원)
        src = pair_rows if pair_rows is not None else dict(u=u, i=i, y=y)
        pairs = _observed_pairs(np.asarray(src["u"], np.int64), np.asarray(src["i"], np.int64), np.asarray(src["y"], np.float32), n_items, rng,
                                mode="observed" if kind == "mlp9_bpr" else "unobserved")
        if len(pairs["u"]) == 0:
            raise ValueError("쌍별 학습 쌍이 없습니다(학습 행에 통과가 없음)")
        if pair_cap and len(pairs["u"]) > pair_cap:                # 학습 배치만 줄인다(양성·음성 풀은 전체 행 기준)
            ix = np.sort(rng.choice(len(pairs["u"]), pair_cap, replace=False))
            pairs = {k: (v[ix] if isinstance(v, np.ndarray) else v) for k, v in pairs.items()}
    elif kind == "mlp9_next":
        if not pairs or len(pairs.get("u", [])) == 0:
            raise ValueError("목표 정렬 쌍(next_pairs)이 없습니다")
    else:
        pairs = None
    if pairs is not None:                                        # 쌍별 모델은 쌍에 나온 사용자·단원만 학습된다
        user_seen = np.bincount(pairs["u"], minlength=n_users) > 0
        item_seen = (np.bincount(pairs["i"], minlength=n_items) + np.bincount(pairs["j"], minlength=n_items)) > 0
    with torch.random.fork_rng():
        torch.manual_seed(seed + 71)
        if kind in MLP_KINDS:
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
        if pairs is not None:
            PU = torch.from_numpy(pairs["u"] + 1); PI = torch.from_numpy(pairs["i"] + 1); PJ = torch.from_numpy(pairs["j"] + 1)
            n_pairs = len(pairs["u"])
            for _ in range(epochs):
                order = rng.permutation(n_pairs); total = 0.0
                for start in range(0, n_pairs, 4096):
                    ix = torch.from_numpy(order[start:start + 4096])
                    x = forward(PU[ix], PI[ix]) - forward(PU[ix], PJ[ix])
                    loss = -nn.functional.logsigmoid(x).mean()
                    opt.zero_grad(); loss.backward(); opt.step(); total += float(loss.detach()) * len(ix)
                losses.append(total / max(n_pairs, 1))
        else:
            for _ in range(epochs):
                order = rng.permutation(len(u)); total = 0.0
                for start in range(0, len(u), 4096):
                    ix = torch.from_numpy(order[start:start + 4096]); out = forward(U[ix], I[ix]); loss = criterion(out, Y[ix])
                    opt.zero_grad(); loss.backward(); opt.step(); total += float(loss.detach()) * len(ix)
                losses.append(total / len(u))
        ue = user_emb.weight.detach().numpy().copy(); ie = item_emb.weight.detach().numpy().copy()
        if kind in MLP_KINDS:
            W1 = mlp[0].weight.detach().numpy().copy(); b1 = mlp[0].bias.detach().numpy().copy()
            W2 = mlp[2].weight.detach().numpy().copy(); b2 = mlp[2].bias.detach().numpy().copy()
        else:
            W1 = b1 = W2 = b2 = None
    blob = b"".join(a.tobytes() for a in [ue, ie] + ([W1, b1, W2, b2] if kind in MLP_KINDS else []))
    audit = dict(model=kind, training_rows=int(len(u)), positive=int(np.count_nonzero(y > 0)), zero=int(np.count_nonzero(y == 0)),
                 seed=seed + 71, epochs=epochs, loss_first=losses[0], loss_last=losses[-1],
                 state_sha256=hashlib.sha256(blob).hexdigest(), learning_rate=0.01,
                 prediction=("sigmoid score, not calibrated probability" if kind in MLP_KINDS else "normalized action-score estimate"))
    if pairs is not None:
        neg_desc = {"mlp9_bpr": "같은 사용자의 미통과 시도 단원(없으면 미시도 단원)", "mlp9_bpru": "같은 사용자가 시도하지 않은 단원",
                    "mlp9_next": "학습 주 w 이전에 통과하지 않았고 w에도 통과하지 않은 단원(양성 = w의 통과 단원)"}[kind]
        audit.update(pairs=int(len(pairs["u"])), pairs_with_observed_negative=int(np.asarray(pairs.get("observed_negative", np.zeros(0, bool))).sum()),
                     loss=f"BPR pairwise −ln σ(f(u,i) − f(u,j)); j = {neg_desc}", users_with_pairs=int(user_seen.sum()),
                     pair_users=int(len(np.unique(pairs["u"]))), items_with_pairs=int(item_seen.sum()),
                     pair_source_rows=int(len(pair_rows["u"])) if pair_rows is not None else int(len(u)))
    return ObservedWeights(kind, ue, ie, W1, b1, W2, b2, user_seen, item_seen, audit)


def _observed_pairs(u, i, y, n_items, rng, neg: int = 2, mode: str = "observed") -> dict:
    """쌍별 학습용 (u, i⁺, j⁻) 목록. mode="observed": j는 같은 사용자가 시도했지만 통과하지 못한 단원에서(없으면 시도하지 않은 단원),
    mode="unobserved": j는 항상 그 사용자가 시도하지 않은 단원에서 뽑는다(양성 vs 미관측의 표준 BPR)."""
    pos_by, neg_by, seen_by = {}, {}, {}
    for uu, ii, yy in zip(u.tolist(), i.tolist(), y.tolist()):
        seen_by.setdefault(uu, set()).add(ii)
        (pos_by if yy > 0 else neg_by).setdefault(uu, []).append(ii)
    pu, pi, pj, obs = [], [], [], []
    all_items = np.arange(n_items)
    for uu, plist in pos_by.items():
        negs = [x for x in set(neg_by.get(uu, [])) if x not in set(plist)] if mode == "observed" else []
        if negs:
            pool, from_obs = np.array(sorted(negs)), True
        else:
            pool, from_obs = np.setdiff1d(all_items, np.fromiter(seen_by[uu], dtype=np.int64)), False
            if len(pool) == 0:
                continue
        for ii in plist:
            js = rng.choice(pool, size=min(neg, len(pool)), replace=False)
            for jj in js:
                pu.append(uu); pi.append(ii); pj.append(int(jj)); obs.append(from_obs)
    return dict(u=np.asarray(pu, np.int64), i=np.asarray(pi, np.int64), j=np.asarray(pj, np.int64), observed_negative=np.asarray(obs, bool))
