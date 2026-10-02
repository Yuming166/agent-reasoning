#!/usr/bin/env python3
"""Evaluate a deterministic sequence-aware baseline before any LLM calls."""
import json, math
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, log_loss, brier_score_loss

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl'
OUT=ROOT/'artifacts/nlp_behavior_setup_20260927'
cases=[json.loads(x) for x in SRC.read_text().splitlines() if x.strip()]

def make_row(c):
    ev=c['evidence']; f=c['features']
    row={'case_id':c['case_id'],'wallet':c['wallet'],'cutoff':c['cutoff'],'split':{'2022-06-01':'train','2022-07-01':'dev','2022-08-01':'test'}[c['cutoff']], 'label':int(c['label_any_new_cp_7d'])}
    # Existing numeric context, included only as a control feature group.
    for k,v in f.items(): row['num_'+k]=float(v)
    # Sequence features from the last observed pre-cutoff events only.
    fam=Counter(str(e['family']) for e in ev); direc=Counter(str(e['direction']) for e in ev); cp=Counter(str(e['counterparty']) for e in ev)
    for k in ['native_transaction','token_transfer','internal_trace']:
        row['seq_family_'+k]=fam.get(k,0)/max(1,len(ev))
    for k in ['incoming','outgoing']:
        row['seq_dir_'+k]=direc.get(k,0)/max(1,len(ev))
    row['seq_unique_cp']=len(cp)/max(1,len(ev))
    row['seq_top_cp_share']=max(cp.values())/max(1,len(ev))
    row['seq_new_cp_transitions']=sum(1 for a,b in zip(ev,ev[1:]) if a['counterparty']!=b['counterparty'])
    row['seq_family_transitions']=sum(1 for a,b in zip(ev,ev[1:]) if a['family']!=b['family'])
    row['seq_direction_transitions']=sum(1 for a,b in zip(ev,ev[1:]) if a['direction']!=b['direction'])
    times=pd.to_datetime([e['time'] for e in ev],utc=True)
    gaps=np.diff(times.view('int64'))/86400e9 if len(times)>1 else np.array([])
    row['seq_gap_mean']=float(gaps.mean()) if len(gaps) else 30.
    row['seq_gap_std']=float(gaps.std()) if len(gaps) else 0.
    row['seq_gap_last']=float(gaps[-1]) if len(gaps) else 30.
    row['seq_gap_min']=float(gaps.min()) if len(gaps) else 30.
    row['seq_recent_3_events']=len(ev[-3:])
    for i,e in enumerate(ev[-3:],1):
        row[f'last{i}_family_native']=int(e['family']=='native_transaction')
        row[f'last{i}_family_token']=int(e['family']=='token_transfer')
        row[f'last{i}_family_trace']=int(e['family']=='internal_trace')
        row[f'last{i}_incoming']=int(e['direction']=='incoming')
        row[f'last{i}_outgoing']=int(e['direction']=='outgoing')
    return row

df=pd.DataFrame(make_row(c) for c in cases)
feature_cols=[c for c in df.columns if c.startswith(('num_','seq_','last'))]
train=df[df.split=='train']; dev=df[df.split=='dev']; test=df[df.split=='test']
# Development threshold is selected only on dev; model fit remains train only.
model=HistGradientBoostingClassifier(max_iter=250,max_leaf_nodes=15,learning_rate=.05,l2_regularization=1.0,random_state=20260927)
model.fit(train[feature_cols],train.label)
dev_prob=model.predict_proba(dev[feature_cols])[:,1]
thresholds=np.linspace(.1,.9,161)
def ba(y,p,t): return balanced_accuracy_score(y,(p>=t).astype(int))
best_t=max(thresholds,key=lambda t:ba(dev.label,dev_prob,t))
test_prob=model.predict_proba(test[feature_cols])[:,1]; test_pred=(test_prob>=best_t).astype(int)

def ece(y,p,bins=10):
    y=np.asarray(y);p=np.asarray(p); out=0.
    for lo,hi in zip(np.linspace(0,1,bins+1)[:-1],np.linspace(0,1,bins+1)[1:]):
        mask=(p>=lo)&(p<(hi if hi<1 else hi+1e-9))
        if mask.any(): out += mask.mean()*abs(y[mask].mean()-p[mask].mean())
    return float(out)
metrics={'model':'M1_sequence_deterministic','train_n':len(train),'dev_n':len(dev),'test_n':len(test),'feature_count':len(feature_cols),'best_dev_threshold':float(best_t),'test':{
    'accuracy':float(accuracy_score(test.label,test_pred)),
    'balanced_accuracy':float(balanced_accuracy_score(test.label,test_pred)),
    'f1_new':float(f1_score(test.label,test_pred,zero_division=0)),
    'brier':float(brier_score_loss(test.label,test_prob)),
    'logloss':float(log_loss(test.label,test_prob,labels=[0,1])),
    'ece':ece(test.label,test_prob),
    'prevalence':float(test.label.mean())}}
result=test[['case_id','wallet','cutoff','label']].copy(); result['prob']=test_prob; result['pred']=test_pred
result.to_csv(OUT/'m1_sequence_predictions.csv',index=False)
(OUT/'m1_sequence_metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+'\n')
(OUT/'m1_sequence_feature_names.json').write_text(json.dumps(feature_cols,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(metrics,indent=2,ensure_ascii=False))
