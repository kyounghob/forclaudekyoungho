"""후보 생성, 가드레일 선택, 지표, 배치 평가.

지표는 강의의 ``ndcg_at_k``·``hit_at_k``·``simple_diversity``와 같은 정의를 벡터화한 것이며,
정상·짧은 목록·빈칸 사례에서 원래 함수와 대조하는 검사가 tests에 있다.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .catalog import Catalog
from .config import K, SEED, GuardrailConfig
from .features import FeatureStore
from .signals import CandidateBatch, LearnerBatch
from .zoo import Algo, score_algo


# ---------- [교안 7-2·7-3] 원래 함수 그대로 ----------
def hit_at_k(rec, rel, k):
    return 1 if len(set(rec[:k]) & set(rel)) > 0 else 0


def dcg_at_k(rec, rel, k):
    return sum((1 if it in rel else 0) / np.log2(i + 2) for i, it in enumerate(rec[:k]))


def ndcg_at_k(rec, rel, k):
    ideal = min(len(rel), k)
    idcg = sum(1 / np.log2(i + 2) for i in range(ideal))
    return 0 if idcg == 0 else dcg_at_k(rec, rel, k) / idcg


def simple_diversity(rec_list, item_category):
    if len(rec_list) < 2:
        return 0
    sims = [1 if item_category[rec_list[i]] == item_category[rec_list[j]] else 0
            for i in range(len(rec_list)) for j in range(i + 1, len(rec_list))]
    return 1 - np.mean(sims)


# ---------- 후보 생성·가드레일 ----------
def candidate_items(und_row: np.ndarray, level: int, catalog: Catalog, guard: GuardrailConfig) -> np.ndarray:
    """통과하지 않은 단원 가운데 추정 수준 + block_gap 미만인 단원(평가 라벨은 읽지 않는다)."""
    ok = catalog.item_level - int(level) < guard.block_gap
    if guard.exclude_passed:
        ok &= ~und_row
    if getattr(guard, "prereq_block", False):                       # 선수 단원을 통과하지 않은 단원은 제외
        ok &= catalog.missing_prereq_count(np.asarray(und_row, bool)[None, :])[0] == 0
    return np.flatnonzero(ok)


def select_topk(S, block=None, plus_one=None, plus_one_max=1, cap_grp=None, cap=None, k=K):
    """고정 (행, k) 출력; −1은 빈칸이며 추천 아이템이 아니다. 짧은 목록은 짧게 둔다."""
    if not isinstance(k, (int, np.integer)) or k < 1:
        raise ValueError("k는 양의 정수여야 합니다")
    S = np.asarray(S, dtype=float)
    if S.ndim != 2:
        raise ValueError("점수는 2차원이어야 합니다")
    n, L = S.shape; out = np.full((n, k), -1, dtype=int)
    if not L:
        return out
    S = S.copy(); S[~np.isfinite(S)] = -np.inf
    if block is not None:
        S[np.asarray(block, dtype=bool)] = -np.inf
    if plus_one is not None:
        plus_one = np.asarray(plus_one, dtype=bool) & np.isfinite(S)
        if plus_one_max <= 0:
            S[plus_one] = -np.inf
        else:                                                      # 한 단계 위 단원은 점수순으로 최대 plus_one_max개만 남긴다
            masked = np.where(plus_one, S, -np.inf)
            rank = np.argsort(np.argsort(-masked, axis=1, kind="stable"), axis=1)
            S[plus_one & (rank >= plus_one_max)] = -np.inf
    order = np.argsort(-S, axis=1, kind="stable")
    valid = np.isfinite(np.take_along_axis(S, order, 1))
    if cap_grp is not None:
        g = np.take_along_axis(np.maximum(np.asarray(cap_grp, dtype=int), 0), order, 1)
        counts = np.zeros((n, int(g.max()) + 1), dtype=np.int32)
        limits = np.broadcast_to(np.asarray(cap, dtype=int), (n,)); ar = np.arange(n)
        if np.any(limits < 1):
            raise ValueError("상한은 양수여야 합니다")
        for j in range(L):
            take = valid[:, j] & (counts[ar, g[:, j]] < limits)
            valid[:, j] = take; counts[ar, g[:, j]] += take
    first = np.argsort(~valid, axis=1, kind="stable")[:, :min(k, L)]
    chosen = np.take_along_axis(order, first, 1)
    chosen[~np.take_along_axis(valid, first, 1)] = -1
    out[:, :chosen.shape[1]] = chosen
    return out


def choose_items(cands: CandidateBatch, lb: LearnerBatch, catalog: Catalog, S, rows=None, k=K,
                 guard: GuardrailConfig = None, topic_cap: int = None):
    """B안 후처리: 두 단계 위 차단, 한 단계 위 최대 n개, (선택) 같은 주제 상한."""
    guard = guard or GuardrailConfig()
    rr = np.arange(cands.R) if rows is None else np.asarray(rows)
    ca = cands.cand0[rr]
    gap = catalog.item_level[ca] - lb.level[rr, None]
    block = (gap >= guard.block_gap) | ~cands.valid[rr]
    grp = catalog.item_topic[ca] if topic_cap else None
    return select_topk(S, block=block, plus_one=gap == 1, plus_one_max=guard.plus_one_max, cap_grp=grp, cap=topic_cap, k=k)


def make_select(cands: CandidateBatch, lb: LearnerBatch, catalog: Catalog, k=K, guard: GuardrailConfig = None):
    return lambda S, rows=None: choose_items(cands, lb, catalog, S, rows, k, guard)


# ---------- 지표 ----------
def row_metrics(sel, cands: CandidateBatch, item_cat, k=K):
    """행별 NDCG@k(이진), Hit@k, Diversity@k(실제 표시된 쌍만), 선택 아이템."""
    if not isinstance(k, (int, np.integer)) or k < 1:
        raise ValueError("k는 양의 정수여야 합니다")
    sel = np.asarray(sel, dtype=int)
    if sel.ndim != 2 or sel.shape[0] != cands.R:
        raise ValueError("선택 배열은 후보와 같은 행 수의 2차원 배열이어야 합니다")
    sel = sel[:, :k]
    width = sel.shape[1]
    valid = (sel >= 0) & (sel < cands.L); s0 = np.where(valid, sel, 0)
    if cands.L == 0:
        z = np.zeros(cands.R); return z, z.copy(), z.copy(), np.full((cands.R, width), -1)
    valid &= np.take_along_axis(cands.valid, s0, 1)
    gains = np.take_along_axis(cands.rel, s0, 1) & valid
    disc = 1 / np.log2(np.arange(2, width + 2))
    dcg = (gains * disc).sum(1)
    nrel = cands.rel.sum(1) if cands.full_relevant_count is None else np.asarray(cands.full_relevant_count)
    if nrel.shape != (cands.R,) or not np.isfinite(nrel).all() or (nrel < 0).any():
        raise ValueError("IDCG 정답 수는 행별 유한한 비음수여야 합니다")
    nrel = np.minimum(nrel, k).astype(int)
    # 표시 길이가 k보다 짧아도 IDCG는 요청된 k와 고정 정답 수를 기준으로 한다.
    cs = np.r_[0, np.cumsum(1 / np.log2(np.arange(2, k + 2)))]; idcg = cs[nrel]
    nd = np.divide(dcg, idcg, out=np.zeros_like(dcg), where=idcg > 0)
    items = np.where(valid, np.take_along_axis(cands.cand0, s0, 1), -1)
    cats = np.asarray(item_cat)[np.maximum(items, 0)]
    same = np.zeros(cands.R); pairs = np.zeros(cands.R)
    for a in range(width):
        for b in range(a + 1, width):
            pair = valid[:, a] & valid[:, b]
            pairs += pair; same += pair & (cats[:, a] == cats[:, b])
    div = np.divide(pairs - same, pairs, out=np.zeros_like(pairs), where=pairs > 0)
    return nd, gains.any(1).astype(float), div, items


def bootstrap_ci(x, n=500, seed=SEED):
    """사용자 단위 짝 부트스트랩 95% 구간(같은 가상 세계 안의 기술 통계)."""
    x = np.asarray(x, dtype=float); x = x[np.isfinite(x)]
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed); means = []
    for start in range(0, n, 25):
        means.extend(x[rng.integers(0, len(x), size=(min(25, n - start), len(x)))].mean(1).tolist())
    return tuple(float(v) for v in np.percentile(means, [2.5, 97.5]))


# ---------- 평가 자료 ----------
def primary_eval(week: int, F: FeatureStore, log: pd.DataFrame, catalog: Catalog, guard: GuardrailConfig) -> tuple:
    """평가 주에 시도한 사용자만 평가한다(전체 가입자나 A/B 배정자가 아님).

    정답 집합은 추천 직전 미통과·수준 조건을 충족한 단원의 다음 주 통과다.
    선수 조건은 추천 후보만 제한한다. 선수 필터로 정답을 지우지 않고 동일한
    full_relevant_count로 IDCG를 계산하므로 필터 전후 지표를 비교할 수 있다.
    같은 주 여러 번 통과한 단원은 한 정답이고, 이전 주 기통과의 재통과는 제외한다.
    """
    from dataclasses import replace

    if F.week != week:
        raise ValueError("특징 스냅샷과 평가 주가 다릅니다")
    wk = log[log.week == week]
    if "source" in wk.columns:                       # 진단 퀴즈의 이수 인정은 추천에 대한 반응이 아니므로 정답·평가 대상에서 뺀다
        wk = wk[wk["source"] != "diagnosis"]
    users = np.unique(wk.user.values)
    if len(users) == 0:
        raise ValueError(f"평가 주 {week}에 학습 로그가 없습니다")
    C = np.full((len(users), catalog.n_items), -1, dtype=int)
    R = np.zeros_like(C, dtype=bool)
    passed = np.zeros((F.n, catalog.n_items), bool)
    lg = wk[wk.quiz_pass]
    passed[lg.user.values, lg.item.values] = True
    reference_guard = replace(guard, prereq_block=False)
    reference_count = np.zeros(len(users), dtype=int)
    for r, u in enumerate(users):
        base = candidate_items(F.und[u], F.level[u], catalog, reference_guard)
        reference_count[r] = passed[u, base].sum()
        ca = base if not guard.prereq_block else candidate_items(F.und[u], F.level[u], catalog, guard)
        C[r, :len(ca)] = ca
        R[r, :len(ca)] = passed[u, ca]
    cands = CandidateBatch(users, C, R)
    cands.full_relevant_count = reference_count
    selectable_count = R.sum(1)
    cands.audit = dict(
        mode="next-week observed quiz-pass; targets fixed before prerequisite filtering",
        week=int(week), rows=int(len(users)), population="users with at least one attempt in the evaluation week",
        dataset_users=int(F.n), zero_observed_target=int((reference_count == 0).sum()),
        zero_selectable_target=int((selectable_count == 0).sum()),
        raw_positive_items=int(passed.sum()), eligible_positive_items=int(reference_count.sum()),
        selectable_positive_items=int(selectable_count.sum()),
        prerequisite_blocked_positive_items=int(reference_count.sum() - selectable_count.sum()),
        raw_positive_users=int(passed[users].any(1).sum()),
        eligible_positive_users=int((reference_count > 0).sum()),
        selectable_positive_users=int((selectable_count > 0).sum()),
        eligible_min=int(cands.valid.sum(1).min()), eligible_max=int(cands.valid.sum(1).max()),
        guardrail=dict(guard.__dict__),
        target_policy="unique evaluation-week quiz passes, unpassed and level-eligible at snapshot; prerequisite filter excluded from target definition",
        idcg_policy="sum of 1/log2(rank+1) through min(full_relevant_count, k); unchanged by prerequisite filtering",
        repeat_pass_policy="deduplicate within evaluation week; previously passed units excluded when exclude_passed=True",
        zero_target_policy="retain as NDCG=0; also report positive-target-user mean",
        short_list_policy="pad with -1; padded ranks have zero gain; fixed k IDCG",
        aggregation="one request per evaluation-week active user; arithmetic user mean",
    )
    lb = LearnerBatch.from_store(F, users)
    return cands, lb


def evaluate_algos(aids, algos, bank, nu_rows, select, item_cat) -> dict:
    out = {}
    cands = bank.cands
    for aid in aids:
        sel = select(score_algo(algos[aid], bank, nu_rows))
        nd, ht, dv, items = row_metrics(sel, cands, item_cat)
        out[aid] = dict(ndcg=cands.per_user(nd), hit=cands.per_user(ht), div=dv,
                        cov=np.unique(items[items >= 0]).size / max(cands.n_pool, 1), items=items, row_ndcg=nd)
    return out


def evaluate_zoo(algos: list, bank, nu_rows, select, item_cat, n_workers: int = 2, log=None):
    """모든 설정을 같은 후보·후처리로 평가(스레드 배치). 학습은 이미 끝나 있고 여기서는 점수만 계산한다."""
    cands = bank.cands
    U = len(cands.users); A = len(algos)
    M = np.zeros((U, A), np.float32); H = np.zeros_like(M); rows = []; st = time.time()

    def work(aid):
        t1 = time.perf_counter()
        sel = select(score_algo(algos[aid], bank, nu_rows))
        nd, ht, dv, items = row_metrics(sel, cands, item_cat)
        cov = np.unique(items[items >= 0]).size / max(cands.n_pool, 1)
        return aid, cands.per_user(nd), cands.per_user(ht), float(dv.mean()), float(cov), (time.perf_counter() - t1) * 1000

    with ThreadPoolExecutor(max_workers=max(1, n_workers)) as pool:
        for aid, nd, ht, dv, cov, ms in pool.map(work, range(A)):
            a = algos[aid]; M[:, aid] = nd; H[:, aid] = ht
            rows.append(dict(job_id=aid, family=a.family, name=a.name, V="+".join(a.V), ndcg=float(nd.mean()), hit=float(ht.mean()),
                             diversity=dv, coverage=cov, ms=ms, t=time.time() - st))
            if log and len(rows) % 200 == 0:
                log(f"  설정 {len(rows)}/{A} 평가, 최고 NDCG {max(x['ndcg'] for x in rows):.4f}")
    return M, H, pd.DataFrame(rows)
