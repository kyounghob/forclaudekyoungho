"""Model and catalog regressions; runnable with stdlib unittest without torch/pytest.

Pure NumPy checks are actual execution. Mocked seed-plumbing checks are explicitly
separate from the optional real torch training checks, which skip if unavailable.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import scipy.sparse as sp

from etfrec import neural
from etfrec.catalog import Catalog, RADIX, find_prereq_cycle
from etfrec.config import TrainConfig
from etfrec.data import Dataset
from etfrec.features import build_features
from etfrec.signals import (ModelStore, Reference, next_week_pairs, supervised_from_log,
                            supervised_key)
from etfrec.synth import make_world


class CatalogInputTests(unittest.TestCase):
    def read_catalog(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.csv"
            path.write_text(text, encoding="utf-8")
            return Catalog.from_csv(path)

    def test_mixed_false_strings_are_not_truthy(self):
        cat = self.read_catalog("item,title,topic,level,short\n"
                                "0,Basic ETF,ETF 구조,1,False\n"
                                "1,Second ETF,ETF 구조,2,0\n")
        np.testing.assert_array_equal(cat.item_short, [False, False])

    def test_explicit_true_false_and_missing_optional_flag(self):
        cat = self.read_catalog("item,title,topic,level,short\n"
                                "0,One ETF,ETF 구조,1,true\n"
                                "1,Two ETF,ETF 구조,2,1\n"
                                "2,Three ETF,ETF 구조,3,\n")
        np.testing.assert_array_equal(cat.item_short, [True, True, False])

    def test_invalid_short_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "short"):
            self.read_catalog("item,title,topic,level,short\n0,Basic ETF,ETF 구조,1,maybe\n")

    def test_invalid_levels_are_not_silently_truncated(self):
        for value in ("1.8", "0", "4", "missing", ""):
            with self.subTest(level=value), self.assertRaisesRegex(ValueError, "level"):
                self.read_catalog(f"item,title,topic,level\n0,Basic ETF,ETF 구조,{value}\n")

    def test_empty_catalog_and_missing_text_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "1개 이상"):
            self.read_catalog("item,title,topic,level\n")
        for row, column in (("0,,ETF 구조,1", "title"), ("0,Basic ETF,,1", "topic")):
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, column):
                self.read_catalog("item,title,topic,level\n" + row + "\n")

    def test_default_catalog_roundtrip_preserves_units_and_flags(self):
        source = Catalog.default()
        frame = source.to_frame()[["item", "title", "topic", "level", "short", "prereqs", "sources"]]
        result = self.read_catalog(frame.to_csv(index=False))
        np.testing.assert_array_equal(source.item_short, result.item_short)
        np.testing.assert_array_equal(source.item_level, result.item_level)
        self.assertEqual(source.prereqs, result.prereqs)
        self.assertEqual(result.n_items, 66)

    def test_catalog_bottleneck_remains_explicit(self):
        cat = Catalog.default()
        self.assertEqual(sum(len(x) for x in cat.prereqs.values()), 80)
        self.assertEqual(len([i for i, parents in cat.prereqs.items() if not parents]), 4)
        self.assertEqual(find_prereq_cycle(cat.prereqs), [])


class GeneratorTests(unittest.TestCase):
    def test_single_learner_has_finite_preferences(self):
        with np.errstate(invalid="raise", divide="raise"):
            world = make_world(1, Catalog.default())
        self.assertTrue(np.isfinite(world["theta"]).all())
        np.testing.assert_allclose(world["theta"].sum(axis=1), 1.0)

    def test_invalid_population_and_week_count_fail_clearly(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(n=value), self.assertRaisesRegex(ValueError, "학습자 수"):
                make_world(value, Catalog.default())
        for value in (0, -1, True, 1.5):
            with self.subTest(n_weeks=value), self.assertRaisesRegex(ValueError, "주차 수"):
                make_world(10, Catalog.default(), n_weeks=value)

    def test_seed_reproducibility(self):
        cat = Catalog.default()
        first = make_world(80, cat, seed=42)
        second = make_world(80, cat, seed=42)
        pd.testing.assert_frame_equal(first["profiles"], second["profiles"])
        pd.testing.assert_frame_equal(first["log"], second["log"])
        np.testing.assert_array_equal(first["theta"], second["theta"])
        other = make_world(80, cat, seed=43)
        self.assertFalse(first["profiles"].equals(other["profiles"]))


class NumpyModelTests(unittest.TestCase):
    def test_extreme_sigmoid_inference_is_finite_without_overflow(self):
        embedding = np.array([[0.], [1.]])
        for scale, expected in ((-1000., 0.), (0., .5), (1000., 1.)):
            with self.subTest(scale=scale):
                model = neural.ObservedWeights("mlp9", embedding, embedding, np.array([[1., 0.]]),
                                               np.array([0.]), np.array([[scale]]), np.array([0.]))
                with np.errstate(over="raise", invalid="raise"):
                    score = model.score(np.array([1]), np.array([1]))
                np.testing.assert_allclose(score, [expected], atol=0)

    def test_observed_mf_numpy_inner_product(self):
        model = neural.ObservedWeights("mf_observed", np.array([[0., 0.], [2., 3.]]),
                                       np.array([[0., 0.], [4., 5.]]))
        np.testing.assert_allclose(model.score(np.array([0, 1]), np.array([1, 1])), [0., 23.])

    def test_fold_in_zero_history_and_one_dimensional_solution(self):
        factors = np.array([[1.], [1.]])
        np.testing.assert_array_equal(neural.fold_in_user(factors, [0., 0.]), [0.])
        observed_weight = 1 + 2 * np.log1p(3.)
        expected = observed_weight / (observed_weight + 3 + .1)
        np.testing.assert_allclose(neural.fold_in_user(factors, [3., 0.], reg=.1), [expected])

    def test_pair_negative_pools_exclude_known_positives(self):
        u = np.array([0, 0, 0, 1, 1]); i = np.array([0, 1, 0, 1, 2]); y = np.array([1, 0, 0, 1, 0])
        observed = neural._observed_pairs(u, i, y, 3, np.random.default_rng(7), mode="observed")
        self.assertTrue(observed["observed_negative"].all())
        known_positive = {(0, 0), (1, 1)}
        self.assertFalse(any((int(uu), int(jj)) in known_positive for uu, jj in zip(observed["u"], observed["j"])))
        unobserved = neural._observed_pairs(u, i, y, 3, np.random.default_rng(7), mode="unobserved")
        known_attempt = set(zip(u.tolist(), i.tolist()))
        self.assertFalse(unobserved["observed_negative"].any())
        self.assertFalse(any((int(uu), int(jj)) in known_attempt for uu, jj in zip(unobserved["u"], unobserved["j"])))

    def test_next_week_pairs_use_first_pass_and_training_weeks(self):
        log = pd.DataFrame({"user": [0, 0, 0], "item": [0, 0, 1], "week": [0, 1, 1], "quiz_pass": [True] * 3})
        pairs = next_week_pairs(log, 3, seed=42)
        positives = set(zip(pairs["i"].tolist(), pairs["w"].tolist()))
        self.assertEqual(positives, {(0, 0), (1, 1)})
        for item, week in zip(pairs["j"], pairs["w"]):
            passed = {0} if week == 0 else {0, 1}
            self.assertNotIn(item, passed)

    def test_empty_bpr_negative_pool_fails_before_model_construction(self):
        """Dependency gate bypassed only to execute the NumPy preflight; no torch training."""
        with patch.object(neural, "require_torch", return_value=None):
            with self.assertRaisesRegex(ValueError, "음성 쌍이 없습니다"):
                neural.train_mf_bpr(np.array([0, 0]), np.array([0, 1]), 1, 2, epochs=1)


class ModelCacheTests(unittest.TestCase):
    def setUp(self):
        self.dataset = Dataset.synthetic(TrainConfig(n_learners=40))
        self.log = self.dataset.log[self.dataset.log.week < 2]
        self.features = build_features(self.dataset.profiles, self.log, self.dataset.catalog, 2)
        self.sup = supervised_from_log(self.log, n_items=self.dataset.catalog.n_items)

    def test_same_reactions_with_different_labels_use_distinct_cache_keys(self):
        changed = dict(self.sup)
        changed["y"] = np.asarray(self.sup["y"]).copy()
        changed["y"][0] = 1.0 - changed["y"][0]
        first = Reference.from_store(self.features, self.dataset.catalog, RADIX, self.sup)
        second = Reference.from_store(self.features, self.dataset.catalog, RADIX, changed)
        self.assertNotEqual(first.snapshot_key, second.snapshot_key)
        self.assertEqual(supervised_key(self.sup), supervised_key(dict(self.sup)))

    def test_label_description_is_not_a_training_cache_input(self):
        changed = dict(self.sup, label="another human-readable description")
        self.assertEqual(supervised_key(self.sup), supervised_key(changed))

    def test_requested_neural_missing_dependency_is_not_silent(self):
        with patch.object(neural, "HAS_TORCH", False):
            with self.assertRaisesRegex(RuntimeError, "--no-neural"):
                ModelStore(enable_neural=True)
            self.assertFalse(ModelStore(enable_neural=False).enable_neural)

    def test_seed_is_forwarded_to_trainers_mocked(self):
        """Argument-plumbing test only; this does not execute or validate torch training."""
        ref = Reference.from_store(self.features, self.dataset.catalog, RADIX, self.sup)
        p = np.zeros((ref.n_users, 2)); q = np.zeros((ref.n_items, 2))
        with patch.object(neural, "HAS_TORCH", True):
            store = ModelStore(seed=17)
        with patch.object(neural, "train_mf", return_value=(p.copy(), q.copy(), [1.], {})) as fit:
            store.get_mf(ref, 2, .1)
            self.assertEqual(fit.call_args.kwargs["seed"], 17)
        with patch.object(neural, "train_mf_bpr", return_value=(p.copy(), q.copy(), [1.], {})) as fit:
            store.get_mf_bpr(ref, 2, .1)
            self.assertEqual(fit.call_args.kwargs["seed"], 17)
        with patch.object(neural, "fit_observed_model", return_value=SimpleNamespace(audit={})) as fit:
            store.get_observed(ref, "mlp9")
            store.get_observed(ref, "mlp9")
            self.assertEqual(fit.call_count, 1)
            self.assertEqual(fit.call_args.kwargs["seed"], 17)


@unittest.skipUnless(neural.HAS_TORCH, "torch unavailable: actual neural training is not executed")
class TorchTrainingTests(unittest.TestCase):
    def setUp(self):
        self.u = np.array([0, 0, 1, 1, 2, 2]); self.i = np.array([0, 1, 1, 2, 0, 2])
        self.y = np.array([1., 0., 1., 0., 0., 1.], np.float32)

    def test_actual_sampled_and_bpr_mf_training(self):
        for kind, fitter in (("sampled", neural.train_mf), ("bpr", neural.train_mf_bpr)):
            with self.subTest(kind=kind):
                args = (self.u, self.i, np.ones(len(self.u)), 3, 4) if kind == "sampled" else (self.u, self.i, 3, 4)
                p, q, losses, audit = fitter(*args, k=2, epochs=2, neg=1, seed=17)
                self.assertTrue(np.isfinite(p).all() and np.isfinite(q).all())
                self.assertEqual(len(losses), 2)
                self.assertEqual(audit["final_negative_collisions"], 0)

    def test_actual_observed_model_families_and_repeatability(self):
        for kind in ("mf_observed",) + neural.MLP_KINDS:
            with self.subTest(kind=kind):
                pairs = dict(u=np.array([0, 1, 2]), i=np.array([0, 1, 2]), j=np.array([3, 3, 3]), w=np.array([0, 0, 1]))
                model = neural.fit_observed_model(self.u, self.i, self.y, self.y, 3, 4, kind,
                                                  seed=17, epochs=2, pairs=pairs)
                repeated = neural.fit_observed_model(self.u, self.i, self.y, self.y, 3, 4, kind,
                                                     seed=17, epochs=2, pairs=pairs)
                self.assertEqual(model.audit["state_sha256"], repeated.audit["state_sha256"])
                self.assertTrue(np.isfinite(model.score(np.array([1, 2]), np.array([1, 2]))).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
