"""추천 후보와 평가 정답을 분리하고 서비스 조건에서 선택하는 회귀 검사."""
from dataclasses import replace

import numpy as np
import pandas as pd
import unittest


from etfrec.catalog import Catalog
from etfrec.config import GuardrailConfig, TrainConfig
from etfrec.data import score_attempts
from etfrec.evaluation import primary_eval, row_metrics
from etfrec.features import feature_store, income_quintile
from etfrec.router import ShrinkRouter, tune_router
from etfrec.signals import CandidateBatch


def _fixed_example():
    catalog = Catalog.default()
    profiles = pd.DataFrame(dict(
        user=[0, 1, 2], gender=[0, 1, 0], age=[30, 40, 50], income=[100., 100., 100.],
        exp=[0, 0, 0], risk=[1, 1, 1], mobile=[1, 1, 1], interest1=[0, 0, 0],
        interest2=[1, 1, 1], placement=[1, 1, 1]))

    def attempt(user, item, week, passed=False):
        return dict(user=user, item=item, week=week, day=0, hour=0, minute=0,
                    complete=passed, quiz=passed, quiz_pass=passed, save=False, drop=False, replay=False)

    # u0: 0번 기통과의 재통과·1번 중복 통과·수준 차단 2번 통과. u1: 평가주 조회만.
    # u2: 과거에만 학습한 사용자이므로 평가 모집단에 들어가지 않는다.
    log = score_attempts(pd.DataFrame([
        attempt(0, 0, 0, True), attempt(2, 0, 0, True), attempt(0, 0, 3, True),
        attempt(0, 1, 3, True), attempt(0, 1, 3, True), attempt(0, 2, 3, True),
        attempt(1, 9, 3, False)]))
    return catalog, profiles, log


class EvaluationRevisionTests(unittest.TestCase):
    def test_prerequisite_filter_keeps_same_targets_idcg_and_population(self):
        catalog, profiles, log = _fixed_example()
        store = feature_store(profiles, log, catalog, 3)
        base, _ = primary_eval(3, store, log, catalog, GuardrailConfig(prereq_block=False))
        required, _ = primary_eval(3, store, log, catalog, GuardrailConfig(prereq_block=True))
        assert base.users.tolist() == required.users.tolist() == [0, 1]
        assert base.full_relevant_count.tolist() == required.full_relevant_count.tolist() == [1, 0]
        assert base.rel.sum() == 1 and required.rel.sum() == 0
        assert required.audit['eligible_positive_items'] == 1
        assert required.audit['selectable_positive_items'] == 0
        assert required.audit['prerequisite_blocked_positive_items'] == 1
        assert required.audit['zero_observed_target'] == 1
        assert required.audit['eligible_positive_users'] == 1
        assert 0 not in base.cand[0] and 2 not in base.cand[0]  # 기통과·수준 차단은 정답에서도 제외
        assert 1 in base.cand[0] and 1 not in required.cand[0]  # 선수 단원3 미통과
        assert required.audit['repeat_pass_policy'].startswith('deduplicate')


    def test_primary_eval_rejects_wrong_snapshot_and_empty_evaluation_week(self):
        catalog, profiles, log = _fixed_example()
        store = feature_store(profiles, log, catalog, 3)
        with self.assertRaisesRegex(ValueError, '스냅샷'):
            primary_eval(2, store, log, catalog, GuardrailConfig())
        empty_store = feature_store(profiles, log, catalog, 2)
        with self.assertRaisesRegex(ValueError, '학습 로그가 없습니다'):
            primary_eval(2, empty_store, log, catalog, GuardrailConfig())


    def test_short_unpadded_list_does_not_shrink_requested_k_idcg(self):
        batch = CandidateBatch(np.array([0, 1]), np.array([[0, 1], [0, 1]]),
                               np.array([[True, True], [False, False]]))
        ndcg, hit, _, _ = row_metrics(np.array([[0], [0]]), batch, np.array([0, 1]), k=5)
        assert np.isclose(ndcg[0], 1 / (1 + 1 / np.log2(3)))
        assert ndcg[1] == 0 and hit.tolist() == [1., 0.]
        # 정답 없는 사용자를 0으로 포함한 평균과 정답 보유자 평균은 다르다.
        assert np.isclose(ndcg.mean(), ndcg[0] / 2)


    def test_target_outside_recommendable_pool_stays_in_idcg(self):
        batch = CandidateBatch(np.array([0]), np.array([[0, 1]]), np.array([[True, False]]))
        batch.full_relevant_count = np.array([2])  # 두 정답 중 하나는 필터로 추천 불가
        ndcg, _, _, _ = row_metrics(np.array([[0, 1, -1, -1, -1]]), batch, np.array([0, 1]))
        assert np.isclose(ndcg[0], 1 / (1 + 1 / np.log2(3)))


    def test_income_ties_are_not_split_and_continuous_codes_match_qcut(self):
        codes, edges = income_quintile(np.full(10, 3000.))
        assert len(edges) == 4 and np.unique(codes).tolist() == [0]
        values = np.arange(100., 120.)
        old_codes, old_edges = pd.qcut(values, 5, labels=False, retbins=True)
        codes, edges = income_quintile(values)
        np.testing.assert_array_equal(codes, old_codes)
        np.testing.assert_array_equal(edges, old_edges[1:-1])
        with self.assertRaises(ValueError):
            income_quintile(np.array([np.nan]))


    def test_router_two_users_never_creates_an_empty_fold(self):
        scores = np.array([[0.2, 0.1], [0.1, 0.3]])
        codes = np.zeros((2, 5), dtype=int)
        for seed in range(20):
            tuned = tune_router(scores, codes, lams=(0., 20.), reps=1, seed=seed)
            assert np.isfinite(tuned['mean']).all()
        with self.assertRaisesRegex(ValueError, '2명 이상'):
            tune_router(scores[:1], codes[:1])
        with self.assertRaisesRegex(ValueError, '선택 가능한'):
            ShrinkRouter().fit(scores, codes, np.array([False, False]))
        fitted = ShrinkRouter().fit(scores, codes, np.array([False, True]))
        assert (fitted.route(codes)[0] == 1).all()


    def test_training_defaults_match_service_prerequisite_policy(self):
        assert TrainConfig().guardrail.prereq_block is True
        assert TrainConfig(guardrail=GuardrailConfig(prereq_block=False)).guardrail.prereq_block is False
        with self.assertRaisesRegex(ValueError, 'test_week'):
            TrainConfig(val_week=3, test_week=2)



    def test_test_labels_cannot_change_validation_selected_operational_algorithm(self):
        from etfrec.data import Dataset, score_attempts
        from etfrec.pipeline import train
        cfg = TrainConfig(n_learners=60, seed=42, router_reps=1, bootstrap_n=5, n_workers=1)
        dataset = Dataset.synthetic(cfg)
        changed_log = dataset.log.copy()
        future = changed_log.week >= cfg.test_week
        changed_log.loc[future, "quiz_pass"] = False
        changed_log = score_attempts(changed_log)
        changed = Dataset(dataset.profiles.copy(), changed_log, dataset.catalog)
        original = train(dataset, cfg, enable_neural=False, log=lambda _: None)
        perturbed = train(changed, cfg, enable_neural=False, log=lambda _: None)
        assert original.selection["operational_algorithm"] == perturbed.selection["operational_algorithm"]
        assert original.selection["families"] == perturbed.selection["families"]
        assert original.selection["operational_champion_counts"] == perturbed.selection["operational_champion_counts"]
        assert original.selection["selection_guardrail"]["prereq_block"] is True
        assert original.validation_jobs.ndcg.equals(perturbed.validation_jobs.ndcg)
        assert (original.results.prereq_violation_rate == 0).all()
        assert (perturbed.results.ndcg == 0).all()
        assert perturbed.test_audit["zero_observed_target"] == len(perturbed.test_users)
        assert all(check["passed"] for check in perturbed.qa)
        assert original.evaluation_protocol["reported_extra_prerequisite_method_is_alias"] is True


if __name__ == "__main__":
    unittest.main()
