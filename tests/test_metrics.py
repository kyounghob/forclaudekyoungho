import numpy as np

from etfrec.catalog import Catalog
from etfrec.config import GuardrailConfig
from etfrec.evaluation import (candidate_items, hit_at_k, ndcg_at_k, row_metrics, select_topk, simple_diversity)
from etfrec.signals import CandidateBatch


def test_vectorized_metrics_match_lecture_functions():
    rng = np.random.default_rng(0)
    cat = rng.integers(0, 4, 12)
    for _ in range(50):
        L = 12
        cand = np.tile(np.arange(L), (3, 1))
        cand[rng.random(cand.shape) < 0.2] = -1                       # 빈칸
        rel = rng.random(cand.shape) < 0.3
        cb = CandidateBatch(np.array([0, 1, 2]), cand, rel)
        sel = np.full((3, 5), -1)
        for r in range(3):
            cols = np.flatnonzero(cb.valid[r]); k = rng.integers(0, min(5, len(cols)) + 1)
            sel[r, :k] = rng.choice(cols, size=k, replace=False)
        nd, ht, dv, items = row_metrics(sel, cb, cat)
        for r in range(3):
            rec = items[r][items[r] >= 0].tolist(); truth = np.flatnonzero(cb.rel[r]).tolist()
            assert np.isclose(nd[r], ndcg_at_k(rec, truth, 5))
            assert np.isclose(ht[r], hit_at_k(rec, truth, 5))
            assert np.isclose(dv[r], simple_diversity(rec, cat))


def test_select_topk_padding_and_guardrails():
    out = select_topk(np.array([[1., 2., 3.]]), k=5)
    assert out.shape == (1, 5) and (out[0, 3:] == -1).all() and out[0, 0] == 2
    S = np.array([[0.9, 0.8, 0.7, 0.6, 0.5]])
    plus = np.array([[True, True, False, False, False]])
    assert select_topk(S, plus_one=plus, plus_one_max=1, k=3).tolist() == [[0, 2, 3]]
    assert select_topk(S, plus_one=plus, plus_one_max=2, k=3).tolist() == [[0, 1, 2]]
    assert select_topk(S, plus_one=plus, plus_one_max=0, k=3).tolist() == [[2, 3, 4]]
    block = np.array([[True, False, False, False, False]])
    assert select_topk(S, block=block, k=2).tolist() == [[1, 2]]
    grp = np.array([[0, 0, 0, 1, 1]])
    assert select_topk(S, cap_grp=grp, cap=2, k=4).tolist() == [[0, 1, 3, 4]]


def test_candidate_items_exclude_passed_and_two_levels_up():
    cat = Catalog.default()
    und = np.zeros(cat.n_items, bool); und[0] = True
    ca = candidate_items(und, 1, cat, GuardrailConfig())
    assert 0 not in ca and not np.any(cat.item_level[ca] >= 3) and np.any(cat.item_level[ca] == 2)
    ca3 = candidate_items(und, 1, cat, GuardrailConfig(block_gap=3))
    assert np.any(cat.item_level[ca3] == 3)
    ca_all = candidate_items(und, 3, cat, GuardrailConfig(exclude_passed=False))
    assert 0 in ca_all and len(ca_all) == cat.n_items
