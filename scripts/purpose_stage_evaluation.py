"""Re-score saved no-neural bundles under a fixed service policy.

This does not retrain MF/MLP or claim a newly held-out human-user experiment.
Purpose-stage alignment is conformance to the authored roadmap, not a validated
measurement of educational benefit or an independent expert judgement.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from etfrec.config import K, GuardrailConfig
from etfrec.data import Dataset
from etfrec.evaluation import bootstrap_ci, make_select, primary_eval, row_metrics
from etfrec.pipeline import Bundle
from etfrec.roadmap import build_roadmap
from etfrec.signals import SignalBank, build_signals
from etfrec.zoo import score_algo


def stage_membership(catalog, lb):
    """Return current-stage eligible masks, stage labels and authored-roadmap masks."""
    masks = np.zeros((lb.R, catalog.n_items), dtype=bool)
    whole = np.zeros_like(masks)
    stages = np.empty(lb.R, dtype=object)
    cache = {}
    for row in range(lb.R):
        key = (str(lb.goal[row]), int(lb.risk[row]), str(lb.horizon[row]),
               int(lb.level[row]), np.asarray(lb.und[row],bool).tobytes())
        if key not in cache:
            roadmap = build_roadmap(catalog, key[0], key[1], key[2], key[3], lb.und[row])
            current = roadmap['current_stage']
            mask = np.zeros(catalog.n_items, bool)
            all_mask = np.zeros(catalog.n_items, bool)
            for stage in roadmap['stages']:
                for unit in stage['units']:
                    all_mask[unit['item']] = True
                    if stage['key'] == current and unit['status'] == 'available':
                        mask[unit['item']] = True
            cache[key] = (mask, current, all_mask)
        masks[row], stages[row], whole[row] = cache[key]
    return masks, stages, whole


def alignment_counts(items, masks, whole, stages):
    """One request per row; padded -1 is excluded from the display denominator."""
    valid = items >= 0
    safe = np.maximum(items, 0)
    row = np.arange(len(items))[:, None]
    match = masks[row, safe] & valid
    in_roadmap = whole[row, safe] & valid
    shown = valid.sum(1)
    aligned = match.sum(1)
    macro = np.divide(aligned, shown, out=np.zeros(len(items),float), where=shown>0)
    return dict(shown=shown, aligned=aligned, macro=macro,
                roadmap=in_roadmap.sum(1), stages=stages)


def aggregate(counts, mask=None):
    mask = np.ones(len(counts['shown']), bool) if mask is None else np.asarray(mask,bool)
    n = int(mask.sum())
    shown = int(counts['shown'][mask].sum())
    aligned = int(counts['aligned'][mask].sum())
    return dict(users=n, displayed_items=shown, aligned_items=aligned,
                alignment_rate=(aligned/shown if shown else None),
                macro_alignment_zero_request_as_zero=(float(counts['macro'][mask].mean()) if n else None),
                zero_display_requests=int((counts['shown'][mask]==0).sum()))


def paired_ratio_ci(a, b, seed, n=500):
    """Paired user bootstrap for pooled displayed-item proportions."""
    rng=np.random.default_rng(seed)
    values=[]
    nuser=len(a['shown'])
    for start in range(0,n,25):
        ix=rng.integers(0,nuser,size=(min(25,n-start),nuser))
        ad=a['shown'][ix].sum(1);bd=b['shown'][ix].sum(1)
        an=a['aligned'][ix].sum(1);bn=b['aligned'][ix].sum(1)
        ok=(ad>0)&(bd>0)
        values.extend((an[ok]/ad[ok]-bn[ok]/bd[ok]).tolist())
    return tuple(float(x) for x in np.percentile(values,[2.5,97.5])) if values else (None,None)


def selected_comparators(bundle):
    jobs=bundle.validation_jobs.set_index('job_id')
    pure=[a.aid for a in bundle.algos if a.family=='UCF' and a.params.get('demo')=='none']
    # Behaviour-only group statistics are a comparison baseline, not an operational input.
    behaviour=[a.aid for a in bundle.algos if a.family=='SEGPOP'
               and set(a.V).issubset({'click_tier','pref_cluster'})]
    def best(ids):
        if not ids:raise ValueError('Expected comparator configurations unavailable')
        return int(jobs.loc[ids,'ndcg'].idxmax())
    fam=bundle.selection['families']
    return {
        'GlobalPopularity':bundle.algos[fam['POP']],
        'BehaviourGroupPopularity':bundle.algos[best(behaviour)],
        'Content':bundle.algos[fam['CONTENT']],
        'UserCFPure':bundle.algos[best(pure)],
        'ItemCF':bundle.algos[fam['ICF']],
        'LegacyValidatedRule':bundle.algos[fam['RULE']],
    }


def audit_neural_artifacts(bundle, original_project, original_archive=None):
    model_sizes={key:len(getattr(bundle.models,key,{})) for key in ['mf','mf_bpr','observed']}
    extensions={'.pkl','.pickle','.pt','.pth','.npy','.npz','.safetensors'}
    original_files=([str(p.relative_to(original_project)) for p in Path(original_project).rglob('*')
                     if p.is_file() and p.suffix.lower() in extensions]
                    if original_project and Path(original_project).is_dir() else [])
    archived=[]
    candidate_score_files=[]
    if original_archive and original_archive.is_file():
        with zipfile.ZipFile(original_archive) as archive:
            archived=[n for n in archive.namelist() if Path(n).suffix.lower() in extensions]
            candidate_score_files=[n for n in archive.namelist() if any(token in Path(n).name.lower()
                                   for token in ('candidate_score','raw_score','per_user_score','logit'))]
    return dict(saved_model_cache_counts=model_sizes, saved_model_training_audit=len(bundle.models.audit),
                original_saved_weight_files=original_files, original_archive_weight_files=archived,
                original_archive_candidate_score_files=candidate_score_files,
                neural_families_in_this_saved_bundle=sorted({a.family for a in bundle.algos if a.family.startswith('MF') or a.family.startswith('MLP')}),
                available_postfilter_reuse='Stored candidate scores or weights would permit post-filtering without retraining. Non-neural scores here are recomputed from saved reference features.',
                unavailable_neural_reason='The imported archive has no model-weight/candidate-score file and this explicit no-neural bundle has empty MF/BPR/observed caches. Torch is unavailable, so the missing neural scores cannot be reconstructed. Filtering itself does not require retraining.')


def run(bundle_path:Path, output:Path, original_project:Path, original_archive:Path|None):
    from etfrec.purpose_policy import purpose_stage_algorithm
    output.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    bundle=Bundle.load(str(bundle_path))
    seed=int(bundle.config.seed)
    # The fixed generator/seed regenerates labels that are not included in the serving log.
    # No observed future label is used to construct inputs or the roadmap.
    dataset=Dataset.synthetic(bundle.config)
    assert dataset.summary()['study_attempts']==bundle.dataset_summary['study_attempts']
    guard=GuardrailConfig(prereq_block=True)
    cands,lb=primary_eval(bundle.config.test_week,bundle.store,dataset.log,bundle.catalog,guard)
    assert np.array_equal(cands.users,bundle.test_users)
    methods=selected_comparators(bundle)
    methods={'PurposeStageRule':purpose_stage_algorithm(),**methods}
    bank=SignalBank(cands)
    build_signals(bank,bundle.reference,lb,bundle.catalog,bundle.models,
                  needed={sig for algo in methods.values() for sig in algo.signals})
    select=make_select(cands,lb,bundle.catalog,K,guard)
    masks,stages,whole=stage_membership(bundle.catalog,lb)
    oracle_select=select(masks[np.arange(cands.R)[:,None],cands.cand0].astype(float)+cands.jitter)
    _,_,_,oracle_items=row_metrics(oracle_select,cands,bundle.catalog.item_topic,K)
    oracle_counts=alignment_counts(oracle_items,masks,whole,stages)
    upper_bound=aggregate(oracle_counts)
    missing=bundle.catalog.missing_prereq_count(lb.und)
    result=[];groups=[];scores={};alignment={};choices={}
    records=[]
    for name,algo in methods.items():
        selections=select(score_algo(algo,bank,lb.nu))
        nd,hit,div,items=row_metrics(selections,cands,bundle.catalog.item_topic,K)
        ndcg=cands.per_user(nd)
        counts=alignment_counts(items,masks,whole,stages)
        shown=items>=0
        viol=(missing[np.arange(len(items))[:,None],np.maximum(items,0)]>0)&shown
        summary=aggregate(counts)
        result.append(dict(method=name,algorithm_id=int(algo.aid),algorithm_name=algo.name,
                           selection_rule=('fixed authored operational policy; not chosen by this test' if name=='PurposeStageRule'
                                           else 'highest validation NDCG in the declared comparator family/subset'),
                           users=len(cands.users),ndcg=float(ndcg.mean()),
                           ndcg_positive_target_users=float(ndcg[cands.full_relevant_count>0].mean()),
                           purpose_current_stage_alignment=summary['alignment_rate'],
                           alignment_user_mean_zero_request_as_zero=summary['macro_alignment_zero_request_as_zero'],
                           short_list_rate=float((counts['shown']<K).mean()),
                           zero_display_requests=summary['zero_display_requests'],
                           displayed_items=summary['displayed_items'],aligned_items=summary['aligned_items'],
                           prerequisite_violation_rate=float(viol.sum()/max(shown.sum(),1)),
                           prerequisite_violation_count=int(viol.sum()),
                           mean_topic_diversity=float(div.mean())))
        scores[name]=ndcg;alignment[name]=counts;choices[name]=items
        prior_key={'GlobalPopularity':'POP','Content':'CONTENT','ItemCF':'ICF','LegacyValidatedRule':'RULE'}.get(name)
        if prior_key in bundle.per_user:
            assert np.allclose(ndcg,bundle.per_user[prior_key],rtol=0,atol=1e-12), f'Saved-bundle parity failed: {name}'
        assert counts['aligned'].sum() <= upper_bound['aligned_items']
        for label,mask in [('All',np.ones(len(items),bool)),('CommonCore',stages=='core'),
                           ('GoalOrAdvanced',np.isin(stages,['goal','advanced'])),('Goal',stages=='goal'),
                           ('Advanced',stages=='advanced'),('Connect',stages=='connect'),
                           ('NoHistory',lb.nu==0),('HasHistory',lb.nu>0)]:
            ag=aggregate(counts,mask)
            groups.append(dict(method=name,subgroup=label,**ag,
                               ndcg=(float(ndcg[mask].mean()) if mask.any() else None)))
        for r,u in enumerate(cands.users):
            records.append(dict(user=int(u),method=name,stage=str(stages[r]),ndcg=float(ndcg[r]),
                                shown=int(counts['shown'][r]),aligned=int(counts['aligned'][r]),
                                no_history=bool(lb.nu[r]==0),items=';'.join(map(str,items[r][items[r]>=0]))))
    comparisons=[]
    for name in methods:
        if name=='PurposeStageRule':continue
        delta=scores['PurposeStageRule']-scores[name]
        lo,hi=bootstrap_ci(delta,500,seed)
        alo,ahi=paired_ratio_ci(alignment['PurposeStageRule'],alignment[name],seed,500)
        a=aggregate(alignment['PurposeStageRule'])['alignment_rate'];b=aggregate(alignment[name])['alignment_rate']
        comparisons.append(dict(reference=name,ndcg_difference=float(delta.mean()),ndcg_ci_low=lo,ndcg_ci_high=hi,
                                alignment_difference=a-b if a is not None and b is not None else None,
                                alignment_ci_low=alo,alignment_ci_high=ahi,
                                bootstrap_resamples=500,unit='paired evaluation-week users',
                                interpretation='conditional user resampling within the same synthetic generator; no causal, multiple-search or independent-human-judgement claim'))
    pd.DataFrame(result).to_csv(output/'Purpose_Stage_Method_Comparison.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(groups).to_csv(output/'Purpose_Stage_Subgroup_Comparison.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(records).to_csv(output/'Purpose_Stage_Per_User.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(comparisons).to_csv(output/'Purpose_Stage_Paired_Comparison.csv',index=False,encoding='utf-8-sig')
    np.savez_compressed(output/'Purpose_Stage_Recommendations.npz',users=cands.users,**choices)
    neural=audit_neural_artifacts(bundle,original_project,original_archive)
    (output/'Neural_Postfilter_Feasibility.json').write_text(json.dumps(neural,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(seed=seed,elapsed_seconds=time.perf_counter()-started,
                 reused_saved_bundle=str(bundle_path),neural_retrained=False,any_model_retrained=False,
                 input_protocol='Saved test snapshot and reference reused; synthetic full log regenerated using recorded seed only to recover evaluation-week targets.',
                 evaluation_protocol=cands.audit,
                 alignment_definition='Displayed unpassed, prerequisite-available units that belong to the user-specific authored roadmap current first-incomplete stage / all displayed units. Padded -1 is not displayed. Zero-display requests contribute zero denominator and are separately reported; per-user-zero-as-zero mean is diagnostic.',
                 alignment_scope_limit='Conformance to the same authored roadmap used as a scoring signal. This cannot independently establish actual purpose suitability, learning effectiveness, or recommendation novelty. The common risk core is separately reported.',
                 current_stage_counts={str(k):int(v) for k,v in zip(*np.unique(stages,return_counts=True))},
                 attainable_stage_alignment_with_same_display_count_constraints=upper_bound,
                 candidate_count_summary=dict(minimum=int(cands.valid.sum(1).min()),maximum=int(cands.valid.sum(1).max()),
                                              mean=float(cands.valid.sum(1).mean())),
                 observed_units_per_user=dict(full_four_week_distinct_pair_mean=dataset.summary()['distinct_pairs']/dataset.n_users,
                                              prior_test_snapshot_mean=float(bundle.reference.Rw.getnnz(axis=1).mean())),
                 prerequisite_blocked_fraction_of_positive_targets=(cands.audit['prerequisite_blocked_positive_items']/cands.audit['eligible_positive_items']),
                 saved_bundle_prediction_parity='POP, CONTENT, ICF and historical RULE per-user NDCG vectors exactly agree to atol 1e-12 after score-only reconstruction.',
                 methods=result,paired_comparisons=comparisons,neural_artifact_audit=neural)
    (output/'purpose_stage_evaluation_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(pd.DataFrame(result)[['method','ndcg','purpose_current_stage_alignment','short_list_rate','prerequisite_violation_rate']].to_string(index=False))
    print('stage counts',summary['current_stage_counts'])
    print('elapsed seconds',summary['elapsed_seconds'])
    return summary


def selfcheck():
    # Two aligned of three displayed units; -1 is not a fourth displayed unit.
    items=np.array([[0,1,-1],[2,-1,-1],[-1,-1,-1]])
    masks=np.array([[True,False,False],[False,False,True],[True,False,False]])
    counts=alignment_counts(items,masks,np.ones_like(masks),np.array(['core','goal','core']))
    a=aggregate(counts)
    assert a['displayed_items']==3 and a['aligned_items']==2 and a['alignment_rate']==2/3
    assert a['zero_display_requests']==1 and np.isclose(a['macro_alignment_zero_request_as_zero'],.5)
    assert aggregate(counts,np.zeros(3,bool))['alignment_rate'] is None


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--original-project',type=Path,default=None,
                        help='(선택) 신경망 가중치 파일 유무를 대조할 이전 프로젝트 폴더')
    parser.add_argument('--original-archive',type=Path)
    args=parser.parse_args()
    selfcheck()
    run(args.bundle,args.out,args.original_project,args.original_archive)
