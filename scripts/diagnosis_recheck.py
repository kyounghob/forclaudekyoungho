"""Explicit synthetic diagnosis sensitivity and reproducible teaching personas.

The generated quiz answers are assumptions, not observed participants. No future
test-week outcomes are read when answers or recognised units are generated.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from etfrec.pipeline import Bundle
from etfrec.quiz import QUESTIONS, score_quiz
from etfrec.catalog import Catalog
from etfrec.config import GuardrailConfig, TrainConfig
from etfrec.data import Dataset
from etfrec.evaluation import candidate_items, choose_items
from etfrec.roadmap import build_roadmap
from etfrec.service import LearnerInput, RecommendationService
from etfrec.signals import CandidateBatch, LearnerBatch
from etfrec.util import json_safe


SCENARIOS = {
    'conservative': [[.40,.25,.25], [.65,.45,.25], [.80,.65,.45]],
    'central': [[.60,.30,.25], [.80,.60,.35], [.90,.80,.60]],
    'optimistic': [[.75,.45,.30], [.90,.75,.50], [.97,.90,.75]],
}


def write_json(path, value):
    path.write_text(json.dumps(json_safe(value), ensure_ascii=False, indent=2), encoding='utf-8')


def candidate_capacity(catalog, und, levels):
    """Number of displayed units is score-independent with only the +1 cap."""
    rows = len(und)
    gap = catalog.item_level[None,:] - np.asarray(levels)[:,None]
    available = (~und) & (gap < 2) & (catalog.missing_prereq_count(und) == 0)
    counts = available.sum(1)
    displayed = np.minimum(5, (available & (gap <= 0)).sum(1) + np.minimum(1,(available & (gap == 1)).sum(1)))
    assert counts.shape == displayed.shape == (rows,)
    return counts, displayed, available


def cohort_summary(label, counts, displayed, cohort, diag_n=None, old_levels=None, levels=None):
    c = np.asarray(cohort, bool)
    row = dict(cohort=label, users=int(c.sum()), candidate_mean=float(counts[c].mean()),
               candidate_median=float(np.median(counts[c])), short_list_users=int((displayed[c] < 5).sum()),
               short_list_rate=float((displayed[c] < 5).mean()), displayed_mean=float(displayed[c].mean()),
               empty_users=int((displayed[c] == 0).sum()), four_units_users=int((displayed[c] == 4).sum()))
    if diag_n is not None: row['diagnosis_recognised_units_mean'] = float(diag_n[c].mean())
    if levels is not None: row['level_increased_users'] = int((levels[c] > old_levels[c]).sum())
    return row


def diagnosis_sensitivity(bundle, out):
    started = time.perf_counter()
    catalog, F = bundle.catalog, bundle.store
    users = np.asarray(bundle.test_users, dtype=int)
    old_und, old_levels = F.und[users].copy(), F.level[users].copy()
    historical_no_history = F.nu[users] == 0
    profiles = bundle.profiles
    placements = profiles.placement.values[users].astype(int)
    cohorts = {'all':np.ones(len(users),bool), 'no_study_history':historical_no_history, 'has_study_history':~historical_no_history}
    counts0, display0, available0 = candidate_capacity(catalog, old_und, old_levels)
    expected = np.mean(np.sum(np.asarray(bundle.predictions['RouterNoGender']) >= 0, axis=1) < 5)
    assert np.isclose(float((display0 < 5).mean()), expected), (float((display0 < 5).mean()), expected)
    # Directly compare the capacity formula against real select_topk through choose_items.
    sample = np.arange(min(100,len(users)))
    cands = CandidateBatch(users[sample], np.where(available0[sample],np.arange(catalog.n_items),-1))
    lb = LearnerBatch.from_store(F, users[sample])
    selected = choose_items(cands, lb, catalog, np.ones(cands.cand.shape), guard=GuardrailConfig(prereq_block=True))
    assert np.array_equal((selected >= 0).sum(1), display0[sample])
    # Recreate outcomes only for target-definition diagnostics, after baseline
    # answer inputs have been fixed. They never affect generated quiz answers.
    ds = Dataset.synthetic(TrainConfig(n_learners=15000, seed=42))
    assert ds.summary()['study_attempts'] == 109674
    assert np.array_equal(ds.profiles.placement.values, profiles.placement.values)
    future = np.zeros((F.n, catalog.n_items),bool)
    lg = ds.log[(ds.log.week == 3) & ds.log.quiz_pass]
    future[lg.user.values,lg.item.values] = True
    future = future[users]
    old_targets = future & ~old_und & (catalog.item_level[None,:] - old_levels[:,None] < 2)
    assert int(old_targets.sum()) == 5826
    qlevel = np.array([q['level'] for q in QUESTIONS],int)
    uniforms = np.random.default_rng(20261023 + 729).random((len(users),len(QUESTIONS)))
    old_stages = np.asarray([build_roadmap(catalog,str(F.goal[u]),int(F.risk[u]),str(F.horizon[u]),int(old_levels[r]),old_und[r])['current_stage']
                             for r,u in enumerate(users)],dtype=object)
    baseline = []
    for name,mask in cohorts.items():
        stage_counts={f'current_stage_{stage}_users':int((old_stages[mask] == stage).sum()) for stage in ['core','goal','advanced','connect']}
        baseline.append(dict(scenario='no_diagnosis', **cohort_summary(name,counts0,display0,mask,
                        np.zeros(len(users)),old_levels,old_levels), **stage_counts))
    stats, user_rows, response_rows = list(baseline), [], []
    target_rows = []
    for name, probability in SCENARIOS.items():
        p = np.asarray(probability)[placements[:,None]-1,qlevel[None,:]-1]
        right = uniforms < p
        recognised = np.zeros_like(old_und)
        levels = old_levels.copy()
        correct_n = np.zeros(len(users),int)
        diag_n = np.zeros(len(users),int)
        for r, uid in enumerate(users):
            answers = {q['id']:int(q['answer'] if right[r,j] else (q['answer'] + 1) % 4) for j,q in enumerate(QUESTIONS)}
            result = score_quiz(answers,catalog)
            ids = [int(e['item']) for e in result['events']]
            recognised[r,ids] = True
            levels[r] = max(int(old_levels[r]),int(result['level']))
            correct_n[r],diag_n[r] = int(result['correct']),len(ids)
            response_rows.append(dict(scenario=name,user=int(uid),placement=int(placements[r]),
                                      **answers, correct=int(correct_n[r]),diagnosis_level=int(result['level']),
                                      recognised_items=';'.join(map(str,ids))))
        assert recognised.sum(1).max() <= 17
        und = old_und | recognised
        counts, displayed, available = candidate_capacity(catalog,und,levels)
        stages = np.asarray([build_roadmap(catalog,str(F.goal[u]),int(F.risk[u]),str(F.horizon[u]),int(levels[r]),und[r])['current_stage']
                             for r,u in enumerate(users)],dtype=object)
        for cohort,mask in cohorts.items():
            stage_counts={f'current_stage_{stage}_users':int((stages[mask] == stage).sum()) for stage in ['core','goal','advanced','connect']}
            stats.append(dict(scenario=name,**cohort_summary(cohort,counts,displayed,mask,diag_n,old_levels,levels),**stage_counts))
        targets = future & ~und & (catalog.item_level[None,:] - levels[:,None] < 2)
        target_rows.append(dict(scenario=name, baseline_targets=int(old_targets.sum()),
                                after_diagnosis_targets=int(targets.sum()),
                                baseline_targets_removed_as_diagnosis_known=int((old_targets & recognised).sum()),
                                newly_level_eligible_future_targets=int((targets & ~old_targets).sum()),
                                prerequisite_blocked_remaining_targets=int((targets & ~available).sum()),
                                caution='Target membership changes after recognition; no NDCG improvement is computed or causally compared.'))
        for r,u in enumerate(users):
            user_rows.append(dict(scenario=name,user=int(u),historical_no_study_history=bool(historical_no_history[r]),
                                  original_level=int(old_levels[r]),diagnosis_merged_level=int(levels[r]),
                                  current_stage_after=str(stages[r]),
                                  correct_questions=int(correct_n[r]),recognised_units=int(diag_n[r]),
                                  newly_recognised_units=int((recognised[r] & ~old_und[r]).sum()),
                                  candidates_before=int(counts0[r]),candidates_after=int(counts[r]),
                                  displayed_before=int(display0[r]),displayed_after=int(displayed[r])))
    pd.DataFrame(stats).to_csv(out/'Diagnosis_Shortlist_Sensitivity.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(user_rows).to_csv(out/'Diagnosis_User_Comparison.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(response_rows).to_csv(out/'Synthetic_Diagnosis_Answers.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(target_rows).to_csv(out/'Diagnosis_Target_Definition_Impact.csv',index=False,encoding='utf-8-sig')
    summary = dict(
        execution='completed', evaluation_users=len(users), synthetic_population=15000, seed=42,
        response_seed=20261023+729, questions=20, unique_pass_eligible_units=17,
        assumptions=dict(probability_rows='original placement 1,2,3; columns question level 1,2,3',
                         correct_probability=SCENARIOS, all_questions_answered=True,
                         wrong_option='(correct_option+1) mod 4',
                         common_random_uniforms=True,
                         diagnosis_merge='und OR recognised; level=max(existing study-derived level, diagnosis level)',
                         no_prerequisite_backfill=True,
                         behaviour_matrix_unchanged=True,
                         cohort='no_study_history means no study attempts before recommendation, before adding diagnostic recognition'),
        leakage_control='Answers use only original placement and independent random uniforms. Neither generated future quiz outcomes nor future study records enter answers. theta in the generator is topic preference, not mastery, and was not used.',
        limitation='Hypothetical sensitivity only. This does not estimate real diagnostic item accuracy, real service shortlist frequency, diagnosis validity, or learning effects. Independent question correctness and recognition of every correct answer can falsely credit guessing; no latent knowledge truth is available to quantify that error. No pass is inferred for an untested prerequisite.',
        decision='Do not automatically add entry units because of the old 52% rate. Re-measure on actual diagnosis-plus-study records in pilot; expand reviewed introductory units only if genuine shortages remain.',
        baseline=baseline, scenarios=stats[len(baseline):], target_definition=target_rows,
        checks=dict(baseline_reproduced=True, displayed_capacity_matches_real_selection_100_users=True,
                    max_recognised_units_at_most_17=True, no_ndcg_reinterpretation=True),
        elapsed_seconds=time.perf_counter()-started)
    write_json(out/'Diagnosis_Sensitivity_Summary.json',summary)
    return summary


def persona_inputs(catalog):
    specs = [
        dict(key='A',label='A 연금 준비 직장인',age=45,gender=0,income=None,exp=0,risk=0,mobile=1,
             goal='pension',horizon='long',interests=['연금계좌 ETF','자산배분'],
             correct_ids=['q01','q02','q04','q06','q07','q08','q17']),
        dict(key='B',label='B 분배금 관심 중급자',age=38,gender=1,income=None,exp=1,risk=1,mobile=1,
             goal='income',horizon='mid',interests=['분배금','커버드콜 ETF'],
             correct_ids=['q01','q02','q03','q04','q05','q06','q07','q09','q10','q11','q12','q15','q17']),
        dict(key='C',label='C 단기 매매 입문자',age=27,gender=0,income=None,exp=0,risk=2,mobile=1,
             goal='trading',horizon='short',interests=['섹터 ETF','유동성'],
             correct_ids=['q01','q02','q06','q07','q15','q20']),
    ]
    return specs


def persona_examples(bundle,out):
    service=RecommendationService(bundle)
    cat=bundle.catalog
    full_minutes=sum(cat.item_info(i)['minutes'] for i in range(cat.n_items))
    records, response_rows, recommendation_rows, time_rows = [],[],[],[]
    for spec in persona_inputs(cat):
        answer={q['id']:int(q['answer'] if q['id'] in spec['correct_ids'] else (q['answer']+1)%4) for q in QUESTIONS}
        diagnosis=score_quiz(answer,cat)
        profile={k:spec[k] for k in ['age','gender','income','exp','risk','mobile','goal','horizon','label']}
        profile['interests']=[cat.ti[t] for t in spec['interests']]
        profile['placement']=diagnosis['level']
        profile['diagnosis']=diagnosis
        diagnostic_events=[dict(e) for e in diagnosis['events']]
        li=LearnerInput(**profile,events=diagnostic_events)
        initial=service.recommend(li,k=5,algorithm='PurposeStageRule')
        passed=np.zeros(cat.n_items,bool)
        passed[[e['item'] for e in diagnostic_events]]=True
        roadmap=build_roadmap(cat,spec['goal'],spec['risk'],spec['horizon'],diagnosis['level'],passed,diagnosis)
        core=[u['item'] for stage in roadmap['stages'] if stage['key']=='core' for u in stage['units']]
        new_core=[i for i in core if not passed[i]]
        study_events=[dict(item=int(i),week=1,day=0,hour=2,minute=j,complete=True,quiz=True,quiz_pass=True,
                           save=False,drop=False,replay=False,source='study_example') for j,i in enumerate(new_core)]
        li_after=LearnerInput(**profile,events=diagnostic_events+study_events)
        after=service.recommend(li_after,k=5,algorithm='PurposeStageRule')
        all_roads=[u for stage in roadmap['stages'] for u in stage['units']]
        recognised_in_goal=[u for u in all_roads if u['status']=='passed']
        recognised_minutes=sum(u['minutes'] for u in recognised_in_goal)
        diag_all_minutes=sum(cat.item_info(e['item'])['minutes'] for e in diagnostic_events)
        time_row=dict(persona=spec['key'],full_fixed_curriculum_units=cat.n_items,full_fixed_curriculum_minutes=full_minutes,
                      full_curriculum_after_diagnosis_minutes=full_minutes-diag_all_minutes,
                      purpose_roadmap_units=roadmap['units_total'],purpose_roadmap_total_minutes=roadmap['minutes_total'],
                      purpose_scope_difference_minutes=full_minutes-roadmap['minutes_total'],
                      diagnosis_recognised_units_all=len(diagnostic_events),diagnosis_recognised_minutes_all=diag_all_minutes,
                      diagnosis_recognised_units_within_roadmap=len(recognised_in_goal),diagnosis_recognised_minutes_within_roadmap=recognised_minutes,
                      purpose_roadmap_minutes_remaining=roadmap['minutes_left'],
                      interpretation='Minutes are catalogue assumptions (8 or 15 per unit); differences are scope and recognition arithmetic, not measured learning-time savings.')
        assert time_row['purpose_roadmap_total_minutes']-recognised_minutes==time_row['purpose_roadmap_minutes_remaining']
        time_rows.append(time_row)
        for q in diagnosis['results']:
            response_rows.append(dict(persona=spec['key'],question=q['id'],chosen=answer[q['id']],correct=q['correct'],item=q['item'],marks_pass=q['marks_pass']))
        for snapshot,response in [('after_diagnosis',initial),('after_common_core',after)]:
            for i in response['items']:
                recommendation_rows.append(dict(persona=spec['key'],snapshot=snapshot,rank=i['rank'],item=i['item'],title=i['title'],
                                                topic=i['topic'],level=i['level'],score=i['score'],current_stage=response['roadmap']['current_stage'],
                                                in_current_stage=i['in_current_stage'],candidate_count=response['candidates'],shortfall=response['shortfall'],
                                                stage_progress=response['roadmap']['progress'],prerequisite_missing=len(i['missing_prereqs'])))
        records.append(dict(persona=spec['key'],input=spec,answers=answer,diagnosis=diagnosis,initial=initial,
                            after_common_core=after,added_actual_study_units=new_core,time_comparison=time_row,
                            snapshots_note='All personas use the same reference bundle week3. after_common_core is a separate illustrative study snapshot (week1 events) before the same serving week; it is not diagnosis-only or observed pilot progress.'))
    assert [(r['diagnosis']['correct'],len(r['diagnosis']['events'])) for r in records] == [(7,6),(13,13),(6,5)]
    pd.DataFrame(response_rows).to_csv(out/'Persona_Diagnosis_Answers.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(recommendation_rows).to_csv(out/'Persona_Recommendation_Lists.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(time_rows).to_csv(out/'Curriculum_Time_Comparison.csv',index=False,encoding='utf-8-sig')
    summary=dict(full_fixed_curriculum_units=cat.n_items,full_fixed_curriculum_minutes=full_minutes,
                 source='Catalog.item_info minutes: 8 short, 15 otherwise; deterministic seed42 catalogue',
                 catalogue_duration_not_observed_time=True,
                 personas=records,
                 common_core_explanation='Leverage and inverse introductory material is compulsory risk literacy for every goal, not permission or encouragement to include these products in an IRP account. Personalisation is demonstrated by simultaneous ranked lists after distinguishing the common risk-literacy stage.',
                 diagnostic_mapping_explanation='A: q08 correct but q19 incorrect so the shared pension unit is not recognised (7 correct, 6 units). B: 13 correct pass-eligible questions map to 13 different units. C: q20 is correct but diagnostic-only, so 6 correct yields 5 recognised units. No unasked prerequisite is inferred as passed.',
                 checks=dict(exact_question_to_unit_counts=True,all_recommendations_have_zero_missing_prerequisites=all(row['prerequisite_missing']==0 for row in recommendation_rows),
                             time_components_reconcile=True),
                 service_diagnosis_behaviour_note='The revised service adds diagnosis-pass events to known units only, excluding them from behaviour rows, topic preference, view counts and empirical pass rates. The candidate sensitivity follows this recognition-only separation; it is not a full re-training of historical reference models.')
    write_json(out/'Persona_Examples.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--part',choices=['diagnosis','personas','all'],default='all')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    bundle=Bundle.load(str(args.bundle))
    if int(bundle.store.n) != 15000 or int(bundle.config.seed) != 42 or not bundle.config.guardrail.prereq_block:
        raise ValueError('This exact audit expects the verified n=15000, seed=42, prerequisite-required v2 bundle; other worlds need a separately declared protocol.')
    if args.part in ['diagnosis','all']:
        s=diagnosis_sensitivity(bundle,args.out);print(json.dumps({'diagnosis_seconds':s['elapsed_seconds'],'cohort_rows':s['baseline']+s['scenarios']},ensure_ascii=False))
    if args.part in ['personas','all']:
        s=persona_examples(bundle,args.out);print(json.dumps({'full_minutes':s['full_fixed_curriculum_minutes'],'personas':[{k:r[k] for k in ['persona','time_comparison']} for r in s['personas']]},ensure_ascii=False))

if __name__=='__main__':main()
