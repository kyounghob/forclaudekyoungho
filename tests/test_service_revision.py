"""서비스 입력·선수 정책 회귀 점검. unittest만으로 실행 가능하며 HTTP 실행을 대신한다고 주장하지 않는다."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from etfrec.catalog import Catalog
from etfrec.config import TrainConfig
from etfrec.data import Dataset, normalize_event_flags, parse_history_csv, score_attempts
from etfrec.pipeline import train
from etfrec.quiz import QUESTIONS, score_quiz
from etfrec.service import LearnerInput, RecommendationService


class InputRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.default()

    def test_string_false_is_not_a_pass(self):
        log = pd.DataFrame([dict(complete="false", quiz="False", quiz_pass="0", save="0.0", drop="true", replay="0")])
        clean, _ = normalize_event_flags(log)
        self.assertFalse(bool(clean.quiz_pass.iloc[0]))
        self.assertTrue(bool(clean["drop"].iloc[0]))
        self.assertEqual(score_attempts(clean).score.tolist(), [1.0])

    def test_invalid_boolean_is_rejected(self):
        log = pd.DataFrame([dict(complete=False, quiz=False, quiz_pass="maybe", save=False, drop=False, replay=False)])
        with self.assertRaisesRegex(ValueError, "quiz_pass"):
            normalize_event_flags(log)

    def test_csv_mixed_boolean_representations(self):
        out = parse_history_csv("item,quiz_pass,save\n0,False,0\n1,0,true\n2,1,false\n", self.catalog)
        self.assertEqual([e["quiz_pass"] for e in out["events"]], [False, False, True])
        self.assertEqual([e["save"] for e in out["events"]], [False, True, False])
        self.assertFalse(out["warnings"])

    def test_csv_invalid_value_is_not_interpreted_as_pass(self):
        out = parse_history_csv("item,quiz_pass\n0,maybe\n1,1\n", self.catalog)
        self.assertEqual([e["item"] for e in out["events"]], [1])
        self.assertEqual(len(out["warnings"]), 1)

    def test_csv_invalid_time_is_a_row_warning(self):
        out = parse_history_csv("item,week\n0,not-a-week\n1,0\n", self.catalog)
        self.assertEqual([e["item"] for e in out["events"]], [1])
        self.assertIn("2행", out["warnings"][0])

    def test_csv_integral_float_item_and_title(self):
        out = parse_history_csv("item,quiz_pass\n0.0,0\n1.0,1\n", self.catalog)
        self.assertEqual([e["item"] for e in out["events"]], [0, 1])
        title = self.catalog.item_title[0]
        self.assertEqual(parse_history_csv(f"title,save\n{title},1\n", self.catalog)["events"][0]["item"], 0)

    def test_csv_fractional_item_and_time_bounds(self):
        for csv in ("item\n0.5\n", "item,day\n0,7\n", "item,hour\n0,4\n", "item,minute\n0,-1\n"):
            with self.subTest(csv=csv):
                out = parse_history_csv(csv, self.catalog)
                self.assertFalse(out["events"])
                self.assertEqual(len(out["warnings"]), 1)

    def test_csv_missing_identity_column(self):
        with self.assertRaisesRegex(ValueError, "item 또는 title"):
            parse_history_csv("week,save\n0,1\n", self.catalog)

    def test_quiz_invalid_choices_are_rejected(self):
        for bad in (True, 1.8, [], {}, -1, 4, "maybe", float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "보기 번호"):
                score_quiz({"q07": bad}, self.catalog)

    def test_quiz_integer_string_compatibility(self):
        self.assertEqual(score_quiz({"q07": "1"}, self.catalog)["correct"], 1)

    def test_twenty_questions_do_not_mean_twenty_mastered_units(self):
        full = score_quiz({q["id"]: q["answer"] for q in QUESTIONS}, self.catalog)
        self.assertEqual(len(QUESTIONS), 20)
        self.assertEqual(sum(q.get("marks_pass", True) for q in QUESTIONS), 19)
        self.assertEqual(len(full["events"]), 17)
        self.assertEqual(len({e["item"] for e in full["events"]}), 17)
        self.assertEqual(full["level"], 3)


class ServiceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = TrainConfig(n_learners=120, seed=42, router_reps=1, bootstrap_n=10, n_workers=1)
        cls.bundle = train(Dataset.synthetic(cfg), cfg, enable_neural=False, log=lambda *a, **k: None)
        cls.service = RecommendationService(cls.bundle)

    def test_initial_recommendations_obey_prerequisites(self):
        cat = self.bundle.catalog
        out = self.service.recommend_new([cat.ti["레버리지·인버스"]], level=3, k=5)
        passed = np.zeros(cat.n_items, bool)
        self.assertTrue(out["guardrail"]["prereq_block"])
        self.assertTrue(all(not cat.missing_prereqs(i["item"], passed) for i in out["items"]))
        self.assertEqual(out["shortfall"], 5 - len(out["items"]))
        self.assertEqual(out["candidates"], 4)

    def test_initial_recommendation_boolean_k_is_invalid(self):
        with self.assertRaisesRegex(ValueError, "k는"):
            self.service.recommend_new(k=True)

    def test_direct_event_string_false_is_not_mastery(self):
        log = self.service._adhoc_log(LearnerInput(events=[dict(item=0, quiz_pass="false", save="0")]))
        self.assertFalse(bool(log.quiz_pass.iloc[0]))
        self.assertEqual(log.score.tolist(), [1.0])

    def test_direct_invalid_history_inputs_are_rejected(self):
        for e in (dict(item=0, quiz_pass="maybe"), dict(item=0.5), dict(item=0, hour=-1)):
            with self.subTest(event=e), self.assertRaises(ValueError):
                self.service._adhoc_log(LearnerInput(events=[e]))

    def test_invalid_what_if_level_is_rejected(self):
        for bad in ([], "high", 1.5, True, 0, 4):
            with self.subTest(level=bad), self.assertRaisesRegex(ValueError, "수준 what-if"):
                self.service.recommend(0, overrides={"level": bad})

    def test_empty_candidate_response_is_complete(self):
        out = self.service.recommend(LearnerInput(), assume_passed=list(range(self.bundle.catalog.n_items)))
        self.assertEqual(out["items"], [])
        self.assertEqual(out["candidates"], 0)
        self.assertEqual(out["shortfall"], 5)
        self.assertIn("latency_ms", out)
        self.assertTrue(out["checks"])

    def test_invalid_goal_does_not_silently_change_purpose(self):
        with self.assertRaisesRegex(ValueError, "goal"):
            self.service.types(goal="invalid")


if __name__ == "__main__":
    unittest.main()
