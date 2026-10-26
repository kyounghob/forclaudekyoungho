"""Meaningful checks for the declared purpose/stage operational policy."""
from __future__ import annotations

import copy
import unittest

import numpy as np

from etfrec.config import GuardrailConfig, TrainConfig
from etfrec.data import Dataset
from etfrec.pipeline import train
from etfrec.purpose_policy import POLICY_KEY, POLICY_WEIGHTS, policy_metadata, purpose_stage_algorithm
from etfrec.service import LearnerInput, RecommendationService


class PurposePolicyRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = TrainConfig(n_learners=120, seed=42, router_reps=1, bootstrap_n=5, n_workers=1)
        cls.bundle = train(Dataset.synthetic(cfg), cfg, enable_neural=False, log=lambda _: None)
        cls.service = RecommendationService(cls.bundle)

    def test_declared_policy_has_both_required_positive_terms(self):
        algo = purpose_stage_algorithm()
        self.assertEqual(algo.aid, -1)
        self.assertEqual(dict(POLICY_WEIGHTS), {'pop':5., 'r:policy_pref':3., 'r:lvl':2., 'r:dev':1., 'r:goal':2., 'r:roadmap':2.})
        self.assertFalse(algo.params['selected_by_validation'])
        self.assertEqual(algo.V, ())

    def test_search_pool_and_declared_policy_are_separate(self):
        b = self.bundle
        self.assertEqual(len(b.algos), 1747)
        self.assertEqual(b.selection['exploration_configuration_count'], 1747)
        self.assertEqual(b.selection['declared_policy_count'], 1)
        self.assertEqual(b.selection['operational_algorithm'], -1)
        self.assertEqual(b.selection['operational_policy'], POLICY_KEY)
        self.assertIn(POLICY_KEY, b.predictions)
        self.assertTrue(b.selection['locked_before_test'])

    def test_default_service_uses_fixed_policy_even_if_validation_winner_changes(self):
        b = copy.copy(self.bundle)
        b.selection = copy.deepcopy(b.selection)
        b.selection['families']['RULE'] = 0
        actual = RecommendationService(b).recommend(1)
        self.assertEqual(actual['router'], POLICY_KEY)
        self.assertEqual(actual['algorithm_id'], -1)
        self.assertEqual([it['item'] for it in actual['items']], [it['item'] for it in self.service.recommend(1)['items']])

    def test_sensitive_group_codes_cannot_change_operational_scores(self):
        original = self.service.recommend(1)
        for values in ({'gender':0,'age_band':0,'income_q':0}, {'gender':1,'age_band':4,'income_q':4}):
            changed = self.service.recommend(1, overrides=values)
            self.assertEqual([i['item'] for i in original['items']], [i['item'] for i in changed['items']])
            np.testing.assert_array_equal([i['score'] for i in original['items']], [i['score'] for i in changed['items']])

    def test_optional_income_and_other_sensitive_raw_profiles_do_not_change_rank(self):
        outputs = [self.service.recommend(LearnerInput(age=a, income=inc, gender=g, goal='pension', horizon='long', risk=0,
                                                     interests=[3,6])) for a,inc,g in [(25,None,0),(65,100000.,1)]]
        self.assertEqual([i['item'] for i in outputs[0]['items']], [i['item'] for i in outputs[1]['items']])
        np.testing.assert_array_equal([i['score'] for i in outputs[0]['items']], [i['score'] for i in outputs[1]['items']])

    def test_goal_changes_scores_and_list_after_common_foundation(self):
        cat = self.bundle.catalog
        passed = np.flatnonzero(cat.item_level == 1).tolist()
        a = self.service.recommend(LearnerInput(goal='pension', horizon='long', risk=1, placement=2), assume_passed=passed)
        b = self.service.recommend(LearnerInput(goal='trading', horizon='long', risk=1, placement=2), assume_passed=passed)
        self.assertNotEqual([i['item'] for i in a['items']], [i['item'] for i in b['items']])
        self.assertTrue(any(any(c['label']=='투자 목적 일치' and c['contribution']>0 for c in i['contributions']) for i in a['items']))

    def test_explanation_addends_reproduce_scores(self):
        result = self.service.recommend(1)
        for item in result['items']:
            self.assertAlmostEqual(sum(p['contribution'] for p in item['contributions']), item['score'], delta=.001)
            labels = {p['label'] for p in item['contributions']}
            self.assertIn('투자 목적 일치', labels)
            self.assertIn('로드맵 단계 우선순위', labels)

    def test_normal_service_cannot_disable_required_constraints(self):
        result = self.service.recommend(1, guard=GuardrailConfig(block_gap=9, plus_one_max=8, exclude_passed=False, prereq_block=False))
        self.assertEqual(result['guardrail'], dict(block_gap=2,plus_one_max=1,exclude_passed=True,prereq_block=True))
        self.assertTrue(all(not i['missing_prereqs'] for i in result['items']))

    def test_explicit_development_comparison_can_keep_off_condition(self):
        svc = RecommendationService(self.bundle, allow_any_config=True)
        result = svc.recommend(1, algorithm='RULE', guard=GuardrailConfig(prereq_block=False))
        self.assertFalse(result['guardrail']['prereq_block'])

    def test_diagnostic_admission_is_not_behaviour_or_preference(self):
        event = dict(item=0,week=0,quiz_pass=True,source='diagnosis')
        lb, features = self.service._adhoc_batch(LearnerInput(placement=2, events=[event]))
        self.assertTrue(lb.und[0,0])
        self.assertEqual(int(lb.level[0]), 2)
        self.assertEqual(lb.Rw.nnz, 0)
        self.assertEqual(float(lb.nu[0]), 0.)
        self.assertEqual(float(features.stats['quiz_pass'][0]), 0.)

    def test_old_bundle_without_policy_fields_gets_declared_default(self):
        old = copy.copy(self.bundle)
        old.config = copy.copy(old.config)
        old.config.__dict__.pop('operational_policy', None)
        old.selection = copy.deepcopy(old.selection)
        old.selection['operational_algorithm'] = old.selection['legacy_operational_algorithm']
        old.selection.pop('operational_policy',None)
        old.results = old.results[old.results.method != POLICY_KEY].copy()
        svc = RecommendationService(old)
        self.assertEqual(svc.meta()['operational_router'], POLICY_KEY)
        self.assertNotIn(POLICY_KEY,svc.meta()['test_ndcg'])
        self.assertEqual(svc.recommend(1)['router'],POLICY_KEY)

    def test_replacement_rule_is_forward_looking_and_has_no_sensitive_inputs(self):
        meta = policy_metadata()
        self.assertEqual(meta['protected_inputs_used'], [])
        self.assertEqual(meta['replacement_rule']['min_ndcg_gain'],.005)
        self.assertIn('not retroactive',meta['replacement_rule']['applies_to'])
        self.assertTrue(meta['replacement_rule']['goal_and_roadmap_terms_required'])

    def test_empty_or_diagnostic_only_history_has_no_invented_interest(self):
        from etfrec.signals import CandidateBatch, SignalBank, build_signals
        for events in ([], [dict(item=0,week=0,quiz_pass=True,source='diagnosis')]):
            lb, _ = self.service._adhoc_batch(LearnerInput(interests=[],events=events))
            cands = CandidateBatch(np.array([-1]),np.arange(self.bundle.catalog.n_items)[None,:])
            bank = SignalBank(cands)
            build_signals(bank,self.bundle.reference,lb,self.bundle.catalog,self.bundle.models,needed={'r:policy_pref','r:pref'})
            self.assertFalse(bank.sig['r:policy_pref'].any())
            self.assertTrue(bank.sig['r:pref'].any())  # explicitly preserved historical quirk, not operational evidence
        li = LearnerInput(interests=[3],events=[])
        lb,_ = self.service._adhoc_batch(li)
        bank=SignalBank(CandidateBatch(np.array([-1]),np.arange(self.bundle.catalog.n_items)[None,:]))
        build_signals(bank,self.bundle.reference,lb,self.bundle.catalog,self.bundle.models,needed={'r:policy_pref'})
        np.testing.assert_array_equal(bank.sig['r:policy_pref'][0]>0,self.bundle.catalog.item_topic==3)

    def test_first_visit_shortcut_uses_same_policy_and_explicit_defaults(self):
        first=self.service.recommend_new(level=1)
        custom=self.service.recommend_new(level=1,goal='income',horizon='long',risk=0)
        self.assertEqual(first['router'],POLICY_KEY)
        self.assertEqual(first['initial_assumptions']['goal'],'long_term')
        self.assertEqual(first['initial_assumptions']['horizon'],'mid')
        self.assertEqual(custom['learner']['goal'],'income')
        self.assertEqual(first['candidates'],4)
        self.assertTrue(first['guardrail']['prereq_block'])

    def test_first_visit_schema_defaults_without_implying_http_execution(self):
        import ast
        from pathlib import Path
        from pydantic import BaseModel,Field
        tree=ast.parse((Path(__file__).resolve().parents[1]/'etfrec/api.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='NewUserRequest')
        ns=dict(BaseModel=BaseModel,Field=Field)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'<NewUserRequest AST>','exec'),ns)
        defaults=ns['NewUserRequest']().model_dump()
        self.assertEqual((defaults['goal'],defaults['horizon'],defaults['risk']),('long_term','mid',1))
        compile(tree,'<api syntax only>','exec')


if __name__ == '__main__':
    unittest.main()
