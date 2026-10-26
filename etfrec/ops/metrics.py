"""게이트 지표: NDCG@K(사용자 평균), 현재 단계 정합률, 선수 위반률, 같은 변수 안 심화 노출 격차.

정합률 정의는 scripts/purpose_stage_evaluation.py와 같다: 보인 단원 가운데 학습자 로드맵의 현재 단계에서
지금 학습 가능한(선수 충족·미통과) 단원의 비율(표시 단원 합 기준, 빈칸 −1 제외).
"""
from __future__ import annotations

import numpy as np

from ..config import SEG_VARS
from ..evaluation import bootstrap_ci, row_metrics
from ..roadmap import build_roadmap

AUDIT_VARS = ("gender", "age_band", "income_q")      # 운영 순위에는 쓰지 않고 격차 점검에만 쓴다


def stage_masks(catalog, lb) -> np.ndarray:
    masks = np.zeros((lb.R, catalog.n_items), dtype=bool)
    cache = {}
    for row in range(lb.R):
        key = (str(lb.goal[row]), int(lb.risk[row]), str(lb.horizon[row]), int(lb.level[row]), np.asarray(lb.und[row], bool).tobytes())
        if key not in cache:
            rm = build_roadmap(catalog, key[0], key[1], key[2], key[3], lb.und[row])
            mask = np.zeros(catalog.n_items, bool)
            for stage in rm["stages"]:
                if stage["key"] == rm["current_stage"]:
                    for unit in stage["units"]:
                        if unit["status"] == "available":
                            mask[unit["item"]] = True
            cache[key] = mask
        masks[row] = cache[key]
    return masks


def alignment(items: np.ndarray, masks: np.ndarray) -> dict:
    valid = items >= 0
    match = masks[np.arange(len(items))[:, None], np.maximum(items, 0)] & valid
    shown, aligned = valid.sum(1), match.sum(1)
    total = int(shown.sum())
    return dict(rate=(float(aligned.sum() / total) if total else None), shown=shown, aligned=aligned)


def paired_alignment_ci(a: dict, b: dict, n: int = 500, seed: int = 0) -> tuple:
    """사용자 단위 짝 부트스트랩: (a의 정합률 − b의 정합률)."""
    rng = np.random.default_rng(seed); vals = []; m = len(a["shown"])
    for start in range(0, n, 25):
        ix = rng.integers(0, m, size=(min(25, n - start), m))
        ad, bd = a["shown"][ix].sum(1), b["shown"][ix].sum(1)
        ok = (ad > 0) & (bd > 0)
        vals.extend((a["aligned"][ix].sum(1)[ok] / ad[ok] - b["aligned"][ix].sum(1)[ok] / bd[ok]).tolist())
    return tuple(float(x) for x in np.percentile(vals, [2.5, 97.5])) if vals else (None, None)


def prereq_violation_rate(items: np.ndarray, und: np.ndarray, catalog) -> float:
    valid = items >= 0
    if not valid.any():
        return 0.0
    missing = catalog.missing_prereq_count(np.asarray(und, bool))
    viol = (missing[np.arange(len(items))[:, None], np.maximum(items, 0)] > 0) & valid
    return float(viol.sum() / valid.sum())


def exposure_gaps(items: np.ndarray, codes: np.ndarray, catalog, min_group: int = 30) -> dict:
    """변수별 집단의 Top-K 중 심화·레버리지 비율과 최대 격차. 사용자 min_group명 미만 집단은 격차 계산에서 뺀다."""
    valid = items >= 0
    adv = catalog.advanced[np.maximum(items, 0)] & valid
    out, worst = {}, 0.0
    for var in AUDIT_VARS:
        c = np.asarray(codes)[:, SEG_VARS.index(var)]
        shares = {}
        for g in np.unique(c):
            m = c == g
            if m.sum() >= min_group and valid[m].sum() > 0:
                shares[int(g)] = float(adv[m].sum() / valid[m].sum())
        gap = (max(shares.values()) - min(shares.values())) if len(shares) >= 2 else 0.0
        out[var] = dict(shares=shares, gap=float(gap)); worst = max(worst, gap)
    out["max_gap"] = float(worst)
    return out


def cols_to_items(cols: np.ndarray, cands) -> np.ndarray:
    """선택 결과(후보 열 번호, −1 = 빈칸) → 단원 번호(−1 = 빈칸)."""
    cols = np.asarray(cols, dtype=int)
    return np.where(cols >= 0, np.take_along_axis(cands.cand0, np.maximum(cols, 0), 1), -1)


def policy_metrics(cols: np.ndarray, cands, lb, catalog, masks: np.ndarray, codes: np.ndarray, k: int) -> dict:
    """한 정책의 선택 결과(행 = cands 행, 후보 열 번호)를 게이트 지표로 요약. per_user NDCG는 짝 비교에 쓴다."""
    items = cols_to_items(cols, cands)
    nd, hit, div, _ = row_metrics(cols, cands, catalog.item_topic, k)
    per_user = cands.per_user(nd)
    al = alignment(items, masks)
    return dict(ndcg=float(per_user.mean()), per_user_ndcg=per_user, hit=float(cands.per_user(hit).mean()),
                diversity=float(cands.per_user(div).mean()), alignment=al["rate"], alignment_counts=al,
                prereq_violation=prereq_violation_rate(items, lb.und, catalog), exposure=exposure_gaps(items, codes, catalog),
                users=int(len(cands.users)), items=items)


def paired_ndcg(new: dict, old: dict, n: int = 500, seed: int = 0) -> dict:
    d = new["per_user_ndcg"] - old["per_user_ndcg"]
    lo, hi = bootstrap_ci(d, n=n, seed=seed)
    return dict(diff=float(d.mean()), ci_low=lo, ci_high=hi)
