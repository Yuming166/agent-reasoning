#!/usr/bin/env python3
"""Fuse audited language-state features with numeric/sequence features.

Train/dev/test are fixed by cutoff. The LLM forecast itself is evaluated separately;
M3's primary arm uses state/evidence/uncertainty features, not the direct forecast.
"""
import json
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, brier_score_loss, log_loss

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis'); OUT=ROOT/'artifacts/nlp_behavior_setup_20260927'
CASES={r['case_id']:r for r in (json.loads(x) for x in (ROOT/'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl').read_text().splitlines() if x.strip())}
RAWS={r['case_id']:r for r in (json.loads(x) for x in (OUT/'m2_llm_all_raw.jsonl').read_text().splitlines() if x.strip())}
STATES=['dormant','reactivation','stable_repeat','exploration','expansion','consolidation','routing']

def row(c, rec):
    ev=c['evidence']; f=c['features']; r=rec.get('parsed') or {}; valid=bool(rec.get('validation',{}).get('valid'))
    d={'case_id':c['case_id'],'wallet':c['wallet'],'cutoff':c['cutoff'],'split':{'2022-06-01':'train','2022-07-01':'dev','2022-08-01':'test'}[c['cutoff']], 'label':int(c['label_any_new_cp_7d'])}
    for k,v in f.items(): d['num_'+k]=float(v)
    fam=Counter(str(e['family']) for e in ev); direc=Counter(str(e['direction']) for e in ev); cp=Counter(str(e['counterparty']) for e in ev)
    for k in ['native_transaction','token_transfer','internal_trace']: d['seq_family_'+k]=fam.get(k,0)/max(1,len(ev))
    for k in ['incoming','outgoing']: d['seq_dir_'+k]=direc.get(k,0)/max(1,len(ev))
    d.update({'seq_unique_cp':len(cp)/max(1,len(ev)),'seq_top_cp_share':max(cp.values())/max(1,len(ev)),'seq_new_cp_transitions':sum(a['counterparty']!=b['counterparty'] for a,b in zip(ev,ev[1:])),'seq_family_transitions':sum(a['family']!=b['family'] for a,b in zip(ev,ev[1:])),'seq_direction_transitions':sum(a['direction']!=b['direction'] for a,b in zip(ev,ev[1:]))})
    times=pd.to_datetime([e['time'] for e in ev],utc=True); gaps=np.diff(times.view('int64'))/86400e9 if len(times)>1 else np.array([])
    d.update({'seq_gap_mean':float(gaps.mean()) if len(gaps) else 30.,'seq_gap_std':float(gaps.std()) if len(gaps) else 0.,'seq_gap_last':float(gaps[-1]) if len(gaps) else 30.,'seq_gap_min':float(gaps.min()) if len(gaps) else 30.})
    for i,e in enumerate(ev[-3:],1):
        d[f'last{i}_family_native']=int(e['family']=='native_transaction'); d[f'last{i}_family_token']=int(e['family']=='token_transfer'); d[f'last{i}_family_trace']=int(e['family']=='internal_trace'); d[f'last{i}_incoming']=int(e['direction']=='incoming'); d[f'last{i}_outgoing']=int(e['direction']=='outgoing')
    state=str(r.get('state','')).lower() if valid else 'invalid'; transition=str(r.get('transition','')).lower() if valid else 'invalid'
    for s in STATES: d['lang_state_'+s]=int(state==s)
    for t in ['stable_repeat_to_exploration','exploration_to_expansion','expansion_to_consolidation','dormant_to_reactivation','none']:
        d['lang_transition_'+t]=int(transition==t)
    try: conf=float(r.get('confidence')) if valid else 0.0
    except Exception: conf=0.0
    ids=r.get('evidence_ids',[]) if valid and isinstance(r.get('evidence_ids',[]),list) else []
    d.update({'lang_valid':int(valid),'lang_confidence':conf,'lang_evidence_count':len(ids),'lang_abstain':int(bool(r.get('abstain'))) if valid else 1,'lang_forecast_new_conf':conf if valid and str(r.get('forecast','')).upper()=='NEW' else 0.0,'lang_forecast_none_conf':conf if valid and str(r.get('forecast','')).upper()=='NONE' else 0.0})
    return d

df=pd.DataFrame(row(CASES[k],RAWS[k]) for k in sorted(CASES))
base_cols=[c for c in df.columns if c.startswith(('num_','seq_','last'))]
lang_cols=[c for c in df.columns if c.startswith('lang_')]

def fit_eval(cols,name):
    tr=df[df.split=='train']; dv=df[df.split=='dev']; te=df[df.split=='test']
    model=HistGradientBoostingClassifier(max_iter=350,max_leaf_nodes=15,learning_rate=.04,l2_regularization=1.5,random_state=20260927)
    model.fit(tr[cols],tr.label)
    dp=model.predict_proba(dv[cols])[:,1]; ts=np.linspace(.1,.9,161); threshold=max(ts,key=lambda t:balanced_accuracy_score(dv.label,(dp>=t).astype(int)))
    tp=model.predict_proba(te[cols])[:,1]; pred=(tp>=threshold).astype(int)
    m={'model':name,'features':len(cols),'threshold_dev':float(threshold),'test_n':len(te),'accuracy':float(accuracy_score(te.label,pred)),'balanced_accuracy':float(balanced_accuracy_score(te.label,pred)),'f1_new':float(f1_score(te.label,pred,zero_division=0)),'brier':float(brier_score_loss(te.label,tp)),'logloss':float(log_loss(te.label,tp,labels=[0,1]))}
    pd.DataFrame({'case_id':te.case_id,'label':te.label,'prob':tp,'pred':pred}).to_csv(OUT/f'{name}_predictions.csv',index=False)
    return m

results=[fit_eval(base_cols,'M3_numeric_sequence_control'),fit_eval(base_cols+lang_cols,'M3_state_fusion')]
# A separate direct-forecast feature arm is reported as a post-hoc ensemble ablation, not the primary M3 claim.
results.append(fit_eval(base_cols+[c for c in lang_cols if c not in ['lang_forecast_new_conf','lang_forecast_none_conf']]+['lang_forecast_new_conf','lang_forecast_none_conf'],'M3_state_plus_direct_forecast'))
report={'models':results,'base_feature_count':len(base_cols),'language_feature_count':len(lang_cols),'source_raw':str(OUT/'m2_llm_all_raw.jsonl'),'split_counts':df.split.value_counts().to_dict()}
(OUT/'m3_fusion_metrics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report,indent=2,ensure_ascii=False))
