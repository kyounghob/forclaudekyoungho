"""신호 계산: 후보(행 × 후보) 점수표를 교안 공식으로 만든다.

- ``CandidateBatch``: 행마다 후보 목록(−1 = 빈칸)과 정답 표시.
- ``LearnerBatch``: 질의 쪽 학습자 특징(행 단위). 기준 저장소의 사용자이거나(``user ≥ 0``)
  서비스에 들어온 임의 학습자(``user = −1``)일 수 있다.
- ``Reference``: 학습·이웃 쪽 기준 데이터(스냅샷의 전체 학습자).
- ``SignalBank``: 신호 이름 → (행 × 후보) 정규화 점수표.
"""
from __future__ import annotations

import hashlib
import itertools
import time
from dataclasses import dataclass, field, replace

import numpy as np
import scipy.sparse as sp

from .catalog import Catalog, onehot
from .config import (BPR_GRID, CONTENT_GRID, ICF_GRID, MAX_REFERENCE_USERS, MF_GRID, SEED, SEG_KO, SEG_LAMS, SEG_VARS,
                     UCF_DEMOS, UCF_GRID)
from .features import DEMO_USES, FeatureStore, confidence, demo_sets
from .roadmap import roadmap_priority_rows
from . import neural


# ============================ 교안 공식 ============================
def shrink_similarity(sim, n_common, lambda_value=10):
    """[교안 5-3] 공통 반응 수가 적은 유사도는 n/(n+λ)를 곱해 줄인다."""
    return (n_common / (n_common + lambda_value)) * sim


def shrink_to_parent(value, n, parent_value, lambda_value):
    """[교안 5-3]의 n/(n+λ)를 세그먼트 값에 적용: 표본이 적을수록 상위 세그먼트 값 쪽으로 당긴다."""
    w = n / (n + lambda_value) if lambda_value > 0 else np.ones_like(np.asarray(n, dtype=float))
    return w * value + (1 - w) * parent_value


def alpha_u(n_u, lam):
    """사용자별 혼합 비율 α_u = n_u/(n_u+λ): 반응이 쌓일수록 협업 필터링 비중이 커진다."""
    return n_u / (n_u + lam)


def build_user_profile(R, X):
    """[교안 4-1] user_profile = Σ r·x / Σ r"""
    R = sp.csr_matrix(R)
    den = np.asarray(R.sum(1)).ravel()
    den[den == 0] = 1.0
    num = R @ X
    num = num.toarray() if sp.issparse(num) else np.asarray(num)
    return num / den[:, None]


def l2_rows(X):
    """[교안 4-2] 코사인의 분모 — 행을 단위 길이로."""
    if sp.issparse(X):
        n = np.sqrt(np.asarray(X.multiply(X).sum(1)).ravel())
        n[n == 0] = 1.0
        return sp.diags(1 / n) @ X
    n = np.linalg.norm(X, axis=1)
    n[n == 0] = 1.0
    return X / n[:, None]


def group_key(codes, cols, radix):
    key = np.zeros(len(codes), np.int64)
    for c in cols:
        key = key * int(radix[c]) + codes[:, c].astype(np.int64)
    return key


def n_groups(cols, radix):
    return int(np.prod([radix[c] for c in cols])) if cols else 1


SEG_V_ALL = [V for r in range(1, len(SEG_VARS) + 1) for V in itertools.combinations(SEG_VARS, r)]   # 31개 조합


def seg_name(V, lam=20):
    return "pop" if not V else f"seg:{'+'.join(V)}:{lam}"


def seg_label(V):
    return "+".join(SEG_KO[v] for v in V) if V else "전체"


# ============================ 데이터 묶음 ============================
@dataclass
class CandidateBatch:
    """행 = (학습자, 후보 목록, 정답 표시)."""
    user: np.ndarray                 # (R,) 기준 사용자 번호 또는 −1
    cand: np.ndarray                 # (R, L) 아이템 번호, −1 = 빈칸
    rel: np.ndarray = None           # (R, L) 정답(다음 주 퀴즈 통과)

    def __post_init__(self):
        self.user = np.asarray(self.user, dtype=np.int64)
        self.cand = np.asarray(self.cand, dtype=np.int64)
        if self.cand.ndim != 2 or len(self.user) != len(self.cand):
            raise ValueError("후보 배열의 모양이 잘못되었습니다")
        if self.rel is None:
            self.rel = np.zeros(self.cand.shape, bool)
        self.rel = np.asarray(self.rel, dtype=bool)
        if self.rel.shape != self.cand.shape:
            raise ValueError("정답 배열의 모양이 후보 배열과 다릅니다")
        self.valid = self.cand >= 0
        self.cand0 = np.where(self.valid, self.cand, 0)
        self.rel = self.rel & self.valid
        self.users, self.uix = np.unique(self.user, return_inverse=True)
        self.R, self.L = self.cand.shape
        uid = np.where(self.user < 0, 2_000_000_000, self.user).astype(np.uint64)
        h = (uid[:, None] * np.uint64(2654435761) + self.cand0.astype(np.uint64) * np.uint64(2246822519)) % np.uint64(1000003)
        self.jitter = (h.astype(float) / 1000003 * 1e-7).astype(np.float32)   # 동점 순서 고정(재현성)
        self.n_pool = int(np.unique(self.cand[self.valid]).size)
        self.full_relevant_count = None
        self.audit = {}

    def per_user(self, row_values):
        """행 지표 → 사용자 평균."""
        s = np.bincount(self.uix, weights=row_values, minlength=len(self.users))
        n = np.bincount(self.uix, minlength=len(self.users))
        return s / np.maximum(n, 1)


@dataclass
class LearnerBatch:
    """질의 쪽 학습자 특징(행 단위). 기준 저장소의 행이거나 임의 학습자."""
    user: np.ndarray                 # (R,) 기준 사용자 번호 또는 −1
    codes: np.ndarray                # (R, 5)
    Rw: sp.csr_matrix                # (R, n_items)
    Rw_conf: sp.csr_matrix
    nu: np.ndarray                   # (R,)
    level: np.ndarray                # (R,)
    interests: np.ndarray            # (R, 2)
    top2: np.ndarray                 # (R, 2)
    risk: np.ndarray                 # (R,)
    mobile: np.ndarray               # (R,)
    und: np.ndarray                  # (R, n_items) bool
    blocks: dict                     # 원-핫 블록(행 단위)
    goal: np.ndarray = None          # (R,) 투자 목적 키
    horizon: np.ndarray = None       # (R,) 투자 기간 키

    def __post_init__(self):
        n = len(self.user)
        if self.goal is None:
            self.goal = np.full(n, "long_term", dtype=object)
        if self.horizon is None:
            self.horizon = np.full(n, "mid", dtype=object)

    @property
    def demo(self) -> dict:
        return demo_sets(self.blocks)

    @property
    def R(self) -> int:
        return len(self.user)

    @classmethod
    def from_store(cls, F: FeatureStore, users, as_reference_users: bool = True) -> "LearnerBatch":
        users = np.asarray(users, dtype=np.int64)
        return cls(user=users if as_reference_users else np.full(len(users), -1, np.int64),
                   codes=F.codes[users].copy(), Rw=F.Rw[users], Rw_conf=F.Rw_conf[users], nu=F.nu[users].copy(),
                   level=F.level[users].copy(), interests=F.interests[users].copy(), top2=F.top2[users].copy(),
                   risk=F.risk[users].copy(), mobile=F.mobile[users].copy(), und=F.und[users].copy(),
                   blocks={k: v[users].copy() for k, v in F.blocks.items()},
                   goal=(np.asarray(F.goal, dtype=object)[users].copy() if F.goal is not None else None),
                   horizon=(np.asarray(F.horizon, dtype=object)[users].copy() if F.horizon is not None else None))

    def with_codes(self, codes: np.ndarray) -> "LearnerBatch":
        """what-if: 세그먼트 코드를 바꾸면 인구통계 원-핫도 같이 바뀐다."""
        bl = {k: v.copy() for k, v in self.blocks.items()}
        bl["age"], bl["inc"], bl["gender"] = onehot(codes[:, 2], 5), onehot(codes[:, 3], 5), onehot(codes[:, 4], 2)
        return replace(self, codes=np.asarray(codes).copy(), blocks=bl)


def snapshot_key(F: FeatureStore, prefix: str = "B", seed: int = SEED) -> str:
    R = F.Rw.tocsr()
    h = hashlib.sha256()
    for x in (R.data, R.indices, R.indptr):
        h.update(np.asarray(x).tobytes())
    return f"{prefix}:{seed}:{R.shape}:{F.week}:{h.hexdigest()[:20]}"


def next_week_pairs(log_before, n_items: int, seed: int = SEED, neg: int = 3, cap: int = 400000) -> dict:
    """목표 정렬 학습 쌍(확장): 학습 주 w마다 (사용자 u, w에 처음 통과한 단원 i, w가 끝날 때까지 통과하지 않은 단원 j).
    평가 정답(다음 주에 고르고 통과한 미통과 단원)과 같은 정의를 학습 주들에 적용한다. 평가 주의 기록은 쓰지 않는다."""
    lg = log_before[log_before.quiz_pass.astype(bool)]
    empty = dict(u=np.zeros(0, np.int64), i=np.zeros(0, np.int64), j=np.zeros(0, np.int64), w=np.zeros(0, np.int64),
                 positives=0, label="first quiz-pass in training week w vs. units not passed by end of w")
    if len(lg) == 0:
        return empty
    first = lg.groupby(["user", "item"]).week.min().reset_index()            # 사용자·단원별 첫 통과 주
    fkeys = first.user.values.astype(np.int64) * n_items + first.item.values.astype(np.int64)
    order = np.argsort(fkeys); fk = fkeys[order]; fw = first.week.values.astype(np.int64)[order]

    def first_week(keys):
        idx = np.minimum(np.searchsorted(fk, keys), len(fk) - 1)
        return np.where(fk[idx] == keys, fw[idx], np.iinfo(np.int64).max)

    rng = np.random.default_rng(seed + 29)
    pu = first.user.values.astype(np.int64); pi = first.item.values.astype(np.int64); pw = first.week.values.astype(np.int64)
    nu, ni, nw = np.repeat(pu, neg), np.repeat(pi, neg), np.repeat(pw, neg)
    nj = rng.integers(0, n_items, len(nu))
    bad = first_week(nu * n_items + nj) <= nw                                 # j가 w까지 통과된 단원이면 음성이 아니다
    for _ in range(30):
        if not bad.any():
            break
        nj[bad] = rng.integers(0, n_items, int(bad.sum()))
        bad = first_week(nu * n_items + nj) <= nw
    keep = ~bad
    nu, ni, nj, nw = nu[keep], ni[keep], nj[keep], nw[keep]
    if len(nu) > cap:
        ix = np.sort(rng.choice(len(nu), cap, replace=False)); nu, ni, nj, nw = nu[ix], ni[ix], nj[ix], nw[ix]
    return dict(u=nu, i=ni, j=nj, w=nw, positives=int(len(pu)), label=empty["label"])


def supervised_from_log(log_before, cap: int = 200000, seed: int = SEED, n_items: int = None) -> dict:
    """관측된 학습 시도 행만으로 MF·MLP 라벨을 만든다(퀴즈 통과 = 1). 목표 정렬 쌍(next_pairs)도 함께 만든다."""
    u = log_before.user.values; i = log_before.item.values; y = log_before.quiz_pass.astype(np.float32).values
    score = np.minimum(log_before.score.values / 3., 1).astype(np.float32)
    original = len(u)
    n_items = int(n_items if n_items is not None else (int(i.max()) + 1 if len(i) else 0))
    pairs = next_week_pairs(log_before, n_items, seed) if n_items else None
    pair_rows = None
    if len(u) > cap:                         # 점별 학습 행만 줄인다. 쌍별 모델의 양성·음성 풀은 전체 관측 행(pair_rows)으로 만든다
        pair_rows = dict(u=u.astype(np.int64), i=i.astype(np.int64), y=y)
        ix = np.sort(np.random.default_rng(seed + 23).choice(len(u), cap, replace=False))
        u, i, y, score = u[ix], i[ix], y[ix], score[ix]
    return dict(u=u.astype(np.int64), i=i.astype(np.int64), y=y, score=score, label="quiz-pass during observed study attempt",
                source_rows=int(original), used_rows=int(len(u)), seed=seed + 23, next_pairs=pairs, pair_rows=pair_rows)


@dataclass
class Reference:
    """학습·이웃 쪽 기준 데이터(스냅샷 전체 학습자)."""
    Rw: sp.csr_matrix
    Rw_conf: sp.csr_matrix
    codes: np.ndarray
    radix: np.ndarray
    ev_user: np.ndarray
    ev_item: np.ndarray
    ev_w: np.ndarray
    demo: dict
    n_u: np.ndarray
    item_cat: np.ndarray
    n_cat: int
    X_cat: np.ndarray
    X_txt: sp.csr_matrix
    snapshot_key: str
    supervised: dict = None
    demo_uses: dict = field(default_factory=lambda: DEMO_USES)

    @classmethod
    def from_store(cls, F: FeatureStore, catalog: Catalog, radix, supervised: dict = None, key: str = None) -> "Reference":
        return cls(Rw=F.Rw, Rw_conf=F.Rw_conf, codes=F.codes, radix=np.asarray(radix), ev_user=F.ev_user, ev_item=F.ev_item,
                   ev_w=np.ones(len(F.ev_user)), demo=F.demo, n_u=F.nu, item_cat=catalog.item_topic, n_cat=catalog.n_topics,
                   X_cat=catalog.X_cat, X_txt=catalog.X_txt, snapshot_key=key or snapshot_key(F), supervised=supervised)

    @property
    def n_users(self):
        return self.Rw.shape[0]

    @property
    def n_items(self):
        return self.Rw.shape[1]

    @property
    def item_support(self):
        return np.asarray((self.Rw > 0).sum(0)).ravel()

    @property
    def user_support(self):
        return np.asarray((self.Rw > 0).sum(1)).ravel()


class ModelStore:
    """스냅샷별 학습 모델 캐시(MF 요인, 관측 MF·MLP 가중치). 서빙 번들에 그대로 저장된다."""

    def __init__(self, enable_neural: bool = True):
        self.mf = {}
        self.mf_bpr = {}
        self.observed = {}
        self.audit = []
        self.enable_neural = enable_neural and neural.HAS_TORCH

    def get_mf(self, ref: Reference, f: int, reg: float):
        key = (ref.snapshot_key, f, reg)
        if key not in self.mf:
            coo = ref.Rw.tocoo()
            P, Q, _, audit = neural.train_mf(coo.row, coo.col, coo.data, ref.n_users, ref.n_items, k=f, reg=reg)
            unseen = ref.item_support == 0
            Q[unseen] = 0.0                                        # 학습에 한 번도 안 나온 단원은 0점
            audit.update(snapshot=ref.snapshot_key)
            self.audit.append(audit)
            self.mf[key] = (P, Q)
        return self.mf[key]

    def get_mf_bpr(self, ref: Reference, f: int, reg: float):
        """BPR 쌍별 손실 MF(확장). 같은 반응 행렬의 양성 쌍으로 학습하고 미관측은 '양성보다 뒤'로만 본다."""
        key = (ref.snapshot_key, f, reg)
        if key not in self.mf_bpr:
            coo = ref.Rw.tocoo()
            P, Q, _, audit = neural.train_mf_bpr(coo.row, coo.col, ref.n_users, ref.n_items, k=f, reg=reg)
            Q[ref.item_support == 0] = 0.0
            audit.update(snapshot=ref.snapshot_key)
            self.audit.append(audit)
            self.mf_bpr[key] = (P, Q)
        return self.mf_bpr[key]

    def get_observed(self, ref: Reference, kind: str) -> neural.ObservedWeights:
        key = (ref.snapshot_key, kind)
        if key not in self.observed:
            sup = ref.supervised
            if sup is None or len(sup["u"]) == 0:
                raise ValueError("관측 학습 라벨이 필요합니다")
            w = neural.fit_observed_model(sup["u"], sup["i"], sup["y"], sup["score"], ref.n_users, ref.n_items, kind, seed=SEED,
                                          pairs=sup.get("next_pairs") if kind == "mlp9_next" else None,
                                          pair_rows=sup.get("pair_rows") if kind in ("mlp9_bpr", "mlp9_bpru") else None)
            w.audit.update(snapshot=ref.snapshot_key)
            self.audit.append(w.audit)
            self.observed[key] = w
        return self.observed[key]


# ============================ 신호 저장소 ============================
class SignalBank:
    """신호 = (행 × 후보) 점수표. 행마다 후보 안에서 min-max 정규화해 저장한다.
    [교안 3-3] personal_norm = personal_score / max_personal 처럼 척도를 맞춰야 가중합이 의미를 가진다."""
    CF_PREFIXES = ("icf:", "ucf:", "mf:", "mfbpr:")

    def __init__(self, cands: CandidateBatch, item_support: np.ndarray = None):
        self.cands = cands
        self.sig, self.info = {}, {}
        self.shape = cands.cand.shape
        self.item_support = item_support

    def add(self, name, M, label, lecture, uses=(), raw=False):
        M = np.nan_to_num(np.asarray(M, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        v = self.cands.valid
        norm_v = v
        if self.item_support is not None and name.startswith(self.CF_PREFIXES):
            norm_v = v & (self.item_support[self.cands.cand0] > 0)     # 반응 근거 없는 새 아이템의 0은 정규화 범위에서 제외
        if raw:
            out = np.where(v, M, 0.0)
        else:
            lo = np.where(norm_v, M, np.inf).min(1, keepdims=True)
            hi = np.where(norm_v, M, -np.inf).max(1, keepdims=True)
            with np.errstate(invalid="ignore", divide="ignore"):
                rng_ = hi - lo
                ok = np.isfinite(rng_) & (rng_ > 1e-12)
                out = np.where(norm_v & ok, (M - np.where(ok, lo, 0)) / np.where(ok, rng_, 1), 0.0)
        self.sig[name] = out.astype(np.float32)
        self.info[name] = dict(label=label, lecture=lecture, uses=tuple(uses))

    def __contains__(self, name):
        return name in self.sig


def build_signals(bank: SignalBank, ref: Reference, lb: LearnerBatch, catalog: Catalog, models: ModelStore,
                  needed=None, verbose=False) -> SignalBank:
    """공통 신호(인기·세그먼트 인기·개인화·콘텐츠·CF·MF·MLP)와 B안 규칙·맥락 신호를 bank에 넣는다.
    needed가 있으면 그 이름만 계산한다(서빙용)."""
    cands = bank.cands
    need = (lambda n: True) if needed is None else (lambda n: n in needed)
    t0 = time.time()
    cand = cands.cand0
    R_ = cands.R
    n_items = ref.n_items
    bank.item_support = ref.item_support
    items_needed = np.unique(cand)
    pos_in_needed = np.searchsorted(items_needed, cand)
    ar = np.arange(R_)
    row_codes = lb.codes
    # ---- [교안 3-1] 인기 + [교안 5-3] 세그먼트 인기(수축) ----
    ev_codes = ref.codes[ref.ev_user]
    c = np.bincount(ref.ev_item, weights=ref.ev_w, minlength=n_items)
    c_all, n_all = c[cand], np.full((R_, 1), c.sum())
    share_all = c_all / np.maximum(n_all, 1)
    if need("pop"):
        bank.add("pop", c_all, "인기", "3-1", uses=())
    for V in SEG_V_ALL:
        names = [seg_name(V, lam) for lam in SEG_LAMS]
        if not any(need(n) for n in names):
            continue
        cols = [SEG_VARS.index(v) for v in V]
        g_ev, g_row = group_key(ev_codes, cols, ref.radix), group_key(row_codes, cols, ref.radix)
        G = n_groups(cols, ref.radix)
        tab = np.bincount(g_ev * n_items + ref.ev_item, weights=ref.ev_w, minlength=G * n_items).reshape(G, n_items)
        c_gi = tab[g_row[:, None], cand]
        n_g = tab.sum(1)[g_row][:, None]
        share_g = c_gi / np.maximum(n_g, 1e-12)
        for lam, nm in zip(SEG_LAMS, names):
            if need(nm):
                bank.add(nm, shrink_to_parent(share_g, n_g, share_all, lam), f"세그먼트 인기[{seg_label(V)}](λ={lam})", "3-1·5-3", uses=V)
    # ---- [교안 3-3] personal_norm: 사용자의 주제 비중 ----
    if need("personal"):
        to_cat = sp.csr_matrix((np.ones(n_items), (np.arange(n_items), ref.item_cat)), shape=(n_items, ref.n_cat))
        Rc = np.asarray((lb.Rw @ to_cat).todense())
        personal_score = Rc / np.maximum(Rc.sum(1, keepdims=True), 1e-12)
        bank.add("personal", personal_score[ar[:, None], ref.item_cat[cand]], "개인 선호(주제 비중)", "3-3", uses=("pref",))
    # ---- [교안 4-1·4-2·4-3] 콘텐츠: 프로필 = Σ r·x / Σ r → 코사인 ----
    feats = {"cat": sp.csr_matrix(ref.X_cat), "txt": sp.csr_matrix(ref.X_txt)}
    feats["both"] = sp.hstack([l2_rows(feats["cat"]) * np.sqrt(0.3), l2_rows(feats["txt"]) * np.sqrt(0.7)]).tocsr()
    for x, cf in CONTENT_GRID:
        nm = f"cnt:{x}:{cf}"
        if not need(nm):
            continue
        Rq = lb.Rw_conf if cf else lb.Rw
        prof = l2_rows(build_user_profile(Rq, feats[x]))
        sim = np.asarray((sp.csr_matrix(prof) @ l2_rows(feats[x][items_needed]).T).todense())
        bank.add(nm, sim[ar[:, None], pos_in_needed],
                 f"콘텐츠[{ {'cat': '주제·수준', 'txt': 'TF-IDF', 'both': '주제·수준+TF-IDF'}[x] }]" + ("(가중)" if cf else ""),
                 "4-1·4-2·4-3" + ("·2-2" if cf else ""), uses=("pref",))
    # ---- [교안 5-2·5-3] 아이템 CF: shrink_similarity(cos, n_common, λ) ----
    if any(need(f"icf:{lam}:{cf}") for lam, cf in ICF_GRID):
        Bm = (ref.Rw > 0).astype(np.float64).tocsc()
        co = (Bm.T @ Bm).tocsr()
        diag = np.asarray(co.diagonal()).ravel()
        co_sub = co[:, items_needed].toarray()
        cos_sub = co_sub / (np.sqrt(np.maximum(diag, 1e-12))[:, None] * np.sqrt(np.maximum(diag[items_needed], 1e-12))[None, :])
        for lam, cf in ICF_GRID:
            nm = f"icf:{lam}:{cf}"
            if not need(nm):
                continue
            S = shrink_similarity(cos_sub, co_sub, lambda_value=lam) if lam > 0 else cos_sub.copy()
            S[items_needed, np.arange(len(items_needed))] = 0.0   # 자기 자신 제외
            W = lb.Rw_conf if cf else (lb.Rw > 0).astype(float)
            pred = np.asarray(W @ S)                              # 암묵 데이터: Σ_j s_ij·w_uj
            bank.add(nm, pred[ar[:, None], pos_in_needed], f"아이템 CF(λ={lam}{', confidence' if cf else ''})",
                     "5-2·5-3" + ("·2-2" if cf else ""), uses=("clicks",))
    # ---- [교안 5-1] 사용자 CF: 유사도 = (1−w)·행동 코사인 + w·인구통계 코사인(4-2) ----
    ucf_need = [(k, d, w) for (k, d, w) in UCF_GRID if need(f"ucf:{k}:{d}:{w}")]
    if ucf_need:
        Xb = l2_rows((ref.Rw > 0).astype(np.float64).tocsr())
        Rcand = (ref.Rw > 0).astype(np.float64).tocsr()[:, items_needed]
        demo_sets_ = sorted({d for _, d, _ in ucf_need if d != "none"})
        Xd = {d: l2_rows(np.asarray(ref.demo[d], dtype=np.float64)) for d in demo_sets_}
        lb_demo = lb.demo
        Xq = {d: l2_rows(np.asarray(lb_demo[d], dtype=np.float64)) for d in demo_sets_}
        Xq_b = l2_rows((lb.Rw > 0).astype(np.float64).tocsr())
        reference = np.flatnonzero(ref.user_support > 0)
        if len(reference) > MAX_REFERENCE_USERS:
            reference = np.sort(np.random.default_rng(SEED + 31).choice(reference, MAX_REFERENCE_USERS, replace=False))
        if len(reference) == 0:
            reference = np.arange(min(1, Xb.shape[0]))
        Xref = Xb[reference]; Rcand = Rcand[reference]
        Xd = {d: v[reference] for d, v in Xd.items()}
        n_all_u = len(reference)
        out = {key: np.zeros((R_, cands.L), np.float32) for key in ucf_need}
        chunk = max(64, int(1.2e7 // n_all_u))
        kmax = min(max(k for k, _, _ in ucf_need), n_all_u)
        for s in range(0, R_, chunk):
            rows = np.arange(s, min(s + chunk, R_))
            us = lb.user[rows]
            arr = np.arange(len(rows))
            sb = (Xq_b[rows] @ Xref.T).toarray().astype(np.float32)
            sd = {d: (Xq[d][rows] @ Xd[d].T).astype(np.float32) for d in demo_sets_}
            for (d, w) in sorted({(d, w) for _, d, w in ucf_need}):
                sim = sb.copy() if d == "none" else (1 - w) * sb + w * sd[d]
                sim[us[:, None] == reference[None, :]] = -np.inf                     # 자기 자신 제외
                idx = np.argpartition(-sim, max(kmax - 1, 0), axis=1)[:, :kmax]
                sv = np.take_along_axis(sim, idx, 1)
                o = np.argsort(-sv, 1)
                idx, sv = np.take_along_axis(idx, o, 1), np.maximum(np.take_along_axis(sv, o, 1), 0)
                for k in (20, 50, 100):
                    if (k, d, w) not in out:
                        continue
                    kk = min(k, kmax)
                    Wn = sp.csr_matrix((sv[:, :kk].ravel(), (np.repeat(arr, kk), idx[:, :kk].ravel())), shape=(len(rows), n_all_u))
                    den = sv[:, :k].sum(1, keepdims=True)
                    pred = np.asarray((Wn @ Rcand).todense()) / np.maximum(den, 1e-9)   # [교안 5-1] 이웃 유사도 가중 평균
                    out[(k, d, w)][rows] = np.take_along_axis(pred, pos_in_needed[rows], 1)
        for (k, d, w), pred in out.items():
            uses = (ref.demo_uses or {}).get(d, UCF_DEMOS[d])
            bank.add(f"ucf:{k}:{d}:{w}", pred, f"사용자 CF(k={k}" + ("" if d == "none" else f", 인구통계[{d}] w={w}") + ")",
                     "5-1" + ("" if d == "none" else "·4-2"), uses=("clicks",) + tuple(uses))
    # ---- [교안 6-1·6-2] 행렬분해 R ≈ PQᵀ ----
    for f, reg in MF_GRID:
        nm = f"mf:{f}:{reg}"
        if not need(nm):
            continue
        if not models.enable_neural:
            continue
        P, Q = models.get_mf(ref, f, reg)
        Pq = np.zeros((R_, P.shape[1]))
        known = lb.user >= 0
        Pq[known] = P[lb.user[known]]
        for r in np.flatnonzero(~known):                            # 새 학습자: ALS 한 단계로 잠재 벡터 추정(확장)
            Pq[r] = neural.fold_in_user(Q, lb.Rw[r].toarray().ravel(), reg=reg)
        bank.add(nm, (Pq[:, None, :] * Q[cand]).sum(-1), f"행렬분해(f={f}, reg={reg})", "6-1·6-2; 음성 표본 확장 9-3", uses=("clicks",))
    # ---- 확장: BPR 쌍별 손실 MF(암묵 피드백의 순위 학습; 미관측 = 거절이 아니라 '양성보다 뒤') ----
    for f, reg in BPR_GRID:
        nm = f"mfbpr:{f}:{reg}"
        if not need(nm) or not models.enable_neural:
            continue
        P, Q = models.get_mf_bpr(ref, f, reg)
        Pq = np.zeros((R_, P.shape[1]))
        known = lb.user >= 0
        Pq[known] = P[lb.user[known]]
        for r in np.flatnonzero(~known):                            # 새 학습자: 고정 Q에 대한 릿지 접기(근사)
            Pq[r] = neural.fold_in_user(Q, lb.Rw[r].toarray().ravel(), reg=reg)
        bank.add(nm, (Pq[:, None, :] * Q[cand]).sum(-1), f"BPR 행렬분해(f={f}, reg={reg})", "6-2(확장: 쌍별 순위 손실)", uses=("clicks",))
    # ---- [교안 6-2·9-3] 관측 점수 MF·MLP (+ 확장: 쌍별 손실 MLP) ----
    for name in ("mf_observed", "mlp9", "mlp9_bpr", "mlp9_bpru", "mlp9_next"):
        if not need(name) or not models.enable_neural:
            continue
        model = models.get_observed(ref, name)
        users = np.broadcast_to(lb.user[:, None], cand.shape)
        seen_u = (users >= 0) & model.user_seen[np.maximum(users, 0)]
        uid = np.where(seen_u, users + 1, 0).ravel().astype(np.int64)
        iid = np.where(model.item_seen[cand], cand + 1, 0).ravel().astype(np.int64)
        scores = np.zeros(uid.size, dtype=np.float32)
        for start in range(0, len(uid), 65536):
            scores[start:start + 65536] = model.score(uid[start:start + 65536], iid[start:start + 65536])
        cold = ~seen_u | ~model.item_seen[cand]
        scores = scores.reshape(cand.shape)
        if cold.any():                                               # 학습되지 않은 쌍은 관측 가능한 콘텐츠 유사도로 대체
            X = l2_rows(ref.X_cat)
            p = l2_rows(build_user_profile(lb.Rw, X))
            Xd_ = X.toarray() if sp.issparse(X) else np.asarray(X)
            pdense = p.toarray() if sp.issparse(p) else np.asarray(p)
            fallback = np.einsum("rd,rcd->rc", pdense, Xd_[cand], optimize=True)
            scores = np.where(cold, fallback, scores)
        label = {"mlp9": "Embedding + MLP (9-3)", "mlp9_bpr": "Embedding + MLP, 쌍별 손실·관측 음성(확장)",
                 "mlp9_bpru": "Embedding + MLP, 쌍별 손실·미관측 음성(확장)", "mlp9_next": "Embedding + MLP, 목표 정렬(다음 주 통과) 쌍별(확장)",
                 "mf_observed": "관측 점수 MF (6-2)"}[name]
        lecture = {"mlp9": "9-2/9-3", "mlp9_bpr": "9-3(확장)", "mlp9_bpru": "9-3(확장: 표준 BPR)", "mlp9_next": "9-3(확장: 목표 정렬)",
                   "mf_observed": "6-2"}[name]
        bank.add(name, scores, label, lecture, uses=("clicks", "pref"))
    add_plan_signals(bank, lb, catalog, need)
    if verbose:
        print(f"  신호 {len(bank.sig)}개 계산: {time.time() - t0:.1f}초")
    return bank


def add_plan_signals(bank: SignalBank, lb: LearnerBatch, catalog: Catalog, need) -> SignalBank:
    """[교안 3-2] calculate_rule_score의 가산점과 B안 맥락 신호(이어 배우기·수준 적합도)."""
    cands = bank.cands
    c0 = cands.cand0
    I_TOPIC, I_LEVEL, I_SHORT = catalog.item_topic, catalog.item_level, catalog.item_short
    tp = I_TOPIC[c0]
    interest = ((tp == lb.interests[:, :1]) | (tp == lb.interests[:, 1:2])          # 온보딩 관심 주제
                | (tp == lb.top2[:, :1]) | (tp == lb.top2[:, 1:2]))                  # 기록상 선호 상위 2개 주제
    lv = lb.level[:, None]
    ab, iq, rk = lb.codes[:, 2:3], lb.codes[:, 3:4], lb.risk[:, None]
    m = catalog.masks
    parts = {"r:pref": (interest, "관심 주제", ("interests", "pref")),
             "r:lvl": (I_LEVEL[c0] == lv, "수준 일치", ("level",)),
             "r:life": (((ab >= 3) & m["life_old"][c0]) | ((ab <= 1) & m["life_young"][c0]), "연령 생애주기 주제", ("age",)),
             "r:inc": (((iq >= 3) & m["inc_high"][c0]) | ((iq <= 1) & m["inc_low"][c0]), "소득 구간 주제", ("income",)),
             "r:risk": (((rk == 2) & m["risk_hi"][c0]) | ((rk == 0) & m["risk_lo"][c0]), "위험성향 주제", ("risk",)),
             "r:dev": ((lb.mobile[:, None] == 1) & I_SHORT[c0], "모바일·짧은 콘텐츠", ("device",))}
    for nm, (M, lab, uses) in parts.items():
        if need(nm):
            bank.add(nm, M.astype(float), lab, "3-2", uses=uses, raw=True)
    if need("ctx:next"):
        done_lv = np.zeros((lb.R, catalog.n_topics))
        for item in range(catalog.n_items):
            col = lb.und[:, item] * I_LEVEL[item]
            done_lv[:, I_TOPIC[item]] = np.maximum(done_lv[:, I_TOPIC[item]], col)
        bank.add("ctx:next", (I_LEVEL[c0] == done_lv[np.arange(lb.R)[:, None], tp] + 1).astype(float),
                 "이어 배우기(같은 주제 다음 수준)", "1-3", uses=("level", "pref"), raw=True)
    if need("ctx:lvlfit"):
        bank.add("ctx:lvlfit", 1 - np.abs(I_LEVEL[c0] - lv) / 2, "수준 적합도", "1-3", uses=("level",), raw=True)
    # ---- 프로젝트 확장: 투자 목적 친화도와 단계별 로드맵 우선순위 ----
    if need("r:goal"):
        from .synth import affinity_matrix
        from .config import GOAL_KEYS
        A = affinity_matrix(catalog)
        gidx = np.array([GOAL_KEYS.index(g) if g in GOAL_KEYS else 2 for g in lb.goal])
        bank.add("r:goal", A[gidx[:, None], tp], "투자 목적 일치", "3-2(확장)", uses=("goal",), raw=True)
    if need("r:roadmap"):
        pr = roadmap_priority_rows(catalog, list(lb.goal), lb.risk, list(lb.horizon), lb.level, lb.und)
        bank.add("r:roadmap", pr[np.arange(lb.R)[:, None], c0], "로드맵 단계 우선순위", "1-3(확장)", uses=("goal", "level", "pref"), raw=True)
    return bank
