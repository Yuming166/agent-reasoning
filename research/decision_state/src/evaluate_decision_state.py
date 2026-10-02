#!/usr/bin/env python3
"""Evaluate B0-B4 decision-state baselines after the LLM panel is frozen."""
from __future__ import annotations
import os

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES = ROOT / 'research/decision_state/results'
CLASSES = ['down', 'same', 'up']
TARGETS = ['activity', 'active_days', 'counterparty_breadth', 'new_counterparties']
VARIANTS = ['full', 'minus_self', 'minus_market', 'placebo']


def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def parse_jsonl(path):
    by={}
    with open(path) as f:
        for line in f:
            if not line.strip(): continue
            r=json.loads(line)
            by[(r['case_id'],r['variant'])]=r
    return by


def normalize(p):
    p=np.asarray(p,dtype=float)
    p=np.where(np.isfinite(p) & (p>=0), p, 0.0)
    s=p.sum()
    return p/s if s>0 else np.ones(len(p))/len(p)


def hypothesis_list(record):
    if not record or not record.get('parse_valid') or not isinstance(record.get('parsed'),dict):
        return []
    hs=record['parsed'].get('hypotheses',[])
    valid=[]
    for h in hs[:3]:
        if not isinstance(h,dict): continue
        try: p=float(h.get('probability',0.0))
        except Exception: continue
        cons=h.get('consequences')
        if not isinstance(cons,dict): continue
        if any(cons.get(t) not in CLASSES for t in TARGETS): continue
        ev=h.get('evidence_ids',[])
        if not isinstance(ev,list): ev=[]
        valid.append({'id':str(h.get('id','')), 'probability':max(0.0,p), 'consequences':cons, 'evidence_ids':set(ev)})
    if not valid: return []
    ps=normalize([x['probability'] for x in valid])
    for x,p in zip(valid,ps): x['probability']=float(p)
    return valid


def consequence_dist(hs, target, keep=None):
    if keep is not None: hs=[h for h in hs if keep(h)]
    if not hs: return np.ones(3)/3
    out=np.zeros(3)
    mass=0.0
    for h in hs:
        p=float(h['probability'])
        out[CLASSES.index(h['consequences'][target])] += p
        mass += p
    if mass<=0: return np.ones(3)/3
    return out/mass


def js(p,q):
    p=normalize(p); q=normalize(q); m=(p+q)/2
    def kl(a,b):
        return float(np.sum(np.where(a>0,a*np.log2(a/np.maximum(b,1e-12)),0.0)))
    return 0.5*kl(p,m)+0.5*kl(q,m)


def fixed_metric(y,p):
    y=np.asarray(y); p=np.asarray(p)
    valid=pd.notna(y)
    y=y[valid]; p=p[valid]
    yi=np.array([CLASSES.index(x) for x in y])
    pred=np.array([CLASSES[i] for i in np.argmax(p,axis=1)])
    return {
        'n':int(len(y)),
        'log_loss':float(log_loss(yi,p,labels=[0,1,2])),
        'balanced_accuracy':float(balanced_accuracy_score(y,pred)),
        'macro_f1':float(f1_score(y,pred,labels=CLASSES,average='macro',zero_division=0)),
    }


def fit_predict(train, pred, features, target):
    X=train[features].replace([np.inf,-np.inf],np.nan)
    Xp=pred[features].replace([np.inf,-np.inf],np.nan)
    med=X.median(numeric_only=True).fillna(0.0)
    X=X.fillna(med).fillna(0.0); Xp=Xp.fillna(med).fillna(0.0)
    y=train[f'y_{target}']
    model=HistGradientBoostingClassifier(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=42)
    model.fit(X,y)
    raw=model.predict_proba(Xp)
    out=np.full((len(pred),3),1e-8)
    for j,c in enumerate(model.classes_): out[:,CLASSES.index(c)]=raw[:,j]
    return out/out.sum(axis=1,keepdims=True)


def deterministic_features(df, targets):
    out=pd.DataFrame(index=df.index)
    # Same fixed trend construction as B1 baseline.
    for target in targets:
        if target=='activity':
            cur=pd.to_numeric(df['event_count_7d'],errors='coerce'); prior=(pd.to_numeric(df['event_count_30d'],errors='coerce')-cur).clip(lower=0)*7/23
        elif target=='active_days':
            cur=pd.to_numeric(df['active_days_7d'],errors='coerce'); prior=(pd.to_numeric(df['active_days_30d'],errors='coerce')-cur).clip(lower=0)*7/23
        elif target=='counterparty_breadth':
            cur=pd.to_numeric(df['score_unique_counterparties_7d'],errors='coerce'); prior=(pd.to_numeric(df['unique_counterparties_30d'],errors='coerce')-cur).clip(lower=0)*7/23
        else:
            cur=pd.to_numeric(df['new_counterparties_7d'],errors='coerce'); prior=pd.to_numeric(df['unique_counterparties_30d'],errors='coerce').clip(lower=0)*7/30
        ratio=(cur+0.5)/(prior+0.5)
        out[f'b1_{target}_ratio']=ratio.replace([np.inf,-np.inf],np.nan)
        direction=np.where(ratio>1.10,'up',np.where(ratio<1/1.10,'down','same'))
        for c in CLASSES: out[f'b1_{target}_p_{c}']=(direction==c).astype(float)
    return out


def build_llm_features(case_ids, records):
    rows=[]
    for cid in case_ids:
        full=hypothesis_list(records.get((cid,'full')))
        variants={v:hypothesis_list(records.get((cid,v))) for v in VARIANTS}
        row={'case_id':cid}
        row['llm_full_valid']=float(bool(full))
        row['llm_full_n_hyp']=float(len(full))
        raw_full=records.get((cid,'full'),{})
        parsed=raw_full.get('parsed') if raw_full else {}
        try: row['llm_abstain']=float(parsed.get('abstain_probability',0.0))
        except Exception: row['llm_abstain']=0.0
        # B2 top hypothesis and B3 full mixture.
        top=full[:1]
        for target in TARGETS:
            b2=consequence_dist(top,target)
            b3=consequence_dist(full,target)
            for j,c in enumerate(CLASSES):
                row[f'b2_{target}_p_{c}']=float(b2[j])
                row[f'b3_{target}_p_{c}']=float(b3[j])
        # Intervention distances per target and relevance/alignment.
        relevant_margins=[]; kept_mass=[]; align_flags=[]
        for target in TARGETS:
            qfull=consequence_dist(full,target)
            qself=consequence_dist(variants['minus_self'],target)
            qmarket=consequence_dist(variants['minus_market'],target)
            qplace=consequence_dist(variants['placebo'],target)
            row[f'js_{target}_self']=js(qfull,qself)
            row[f'js_{target}_market']=js(qfull,qmarket)
            row[f'js_{target}_placebo']=js(qfull,qplace)
        for h in full:
            r=[]
            if 'E_SELF' in h['evidence_ids']:
                r.append(row[f'js_{"activity"}_self'])
            if 'E_MARKET' in h['evidence_ids']:
                r.append(row[f'js_{"activity"}_market'])
            # evidence group relevance is summarized across four consequence slots
            all_r=[]
            if 'E_SELF' in h['evidence_ids']:
                all_r.extend(row[f'js_{t}_self'] for t in TARGETS)
            if 'E_MARKET' in h['evidence_ids']:
                all_r.extend(row[f'js_{t}_market'] for t in TARGETS)
            placebo=np.mean([row[f'js_{t}_placebo'] for t in TARGETS])
            rel=float(np.mean(all_r)) if all_r else 0.0
            margin=rel-placebo
            relevant_margins.append((h,float(margin)))
            kept_mass.append(h['probability'] if margin>0 else 0.0)
            align_flags.append(float(margin>0))
        total_mass=sum(h['probability'] for h in full) or 1.0
        row['b4_alignment_rate']=float(sum(h['probability']*a for (h,_),a in zip(relevant_margins,align_flags))/total_mass) if full else 0.0
        row['b4_relevant_minus_placebo']=float(sum(h['probability']*m for h,m in relevant_margins)/total_mass) if full else 0.0
        row['b4_kept_mass']=float(sum(kept_mass)/total_mass) if full else 0.0
        row['b4_gate_pass']=float(bool(full) and row['b4_kept_mass']>0)
        # B4 consequence mixture after keeping hypotheses whose claimed evidence
        # was more responsive than placebo. If all fail, uniform is used.
        for target in TARGETS:
            def keep(h):
                all_r=[]
                if 'E_SELF' in h['evidence_ids']: all_r.extend(row[f'js_{target}_self'] for _ in [0])
                if 'E_MARKET' in h['evidence_ids']: all_r.extend(row[f'js_{target}_market'] for _ in [0])
                rel=float(np.mean(all_r)) if all_r else 0.0
                return rel > row[f'js_{target}_placebo']
            b4=consequence_dist(full,target,keep=keep)
            for j,c in enumerate(CLASSES): row[f'b4_{target}_p_{c}']=float(b4[j])
        rows.append(row)
    return pd.DataFrame(rows)


def bootstrap_diffs(case_level, a, b, n=2000, seed=42):
    rng=np.random.default_rng(seed)
    x=case_level[a].to_numpy(float); y=case_level[b].to_numpy(float)
    d=x-y
    means=[]
    for _ in range(n): means.append(float(np.mean(d[rng.integers(0,len(d),len(d))])))
    return {'estimate':float(np.mean(d)),'ci_low':float(np.quantile(means,.025)),'ci_high':float(np.quantile(means,.975)),'n':int(len(d))}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--panel',default='hypothesis_panel_full.jsonl'); ap.add_argument('--bootstrap',type=int,default=2000); args=ap.parse_args()
    prompt=pd.read_csv(RES/'decision_state_prompt_cases.csv',low_memory=False)
    ev=pd.read_csv(RES/'decision_state_eval_cases.csv',low_memory=False)
    df=prompt.merge(ev[['case_id']+[f'y_{t}' for t in TARGETS]],on='case_id',validate='one_to_one')
    manifest=json.loads((RES/'decision_state_case_manifest.json').read_text())
    m1=[c for c in manifest['m1_features'] if c in df.columns]
    for c in m1: df[c]=pd.to_numeric(df[c],errors='coerce')
    records=parse_jsonl(RES/args.panel)
    llm=build_llm_features(df.case_id.tolist(),records)
    b1=deterministic_features(df,TARGETS)
    work=df.merge(llm,on='case_id',validate='one_to_one').join(b1)
    llm.to_csv(RES/'decision_state_llm_features.csv',index=False)
    # Prepare model feature families.
    b1cols=list(b1.columns)
    b2cols=[c for c in llm.columns if c.startswith('b2_') or c in ['llm_full_valid','llm_full_n_hyp','llm_abstain']]
    b3cols=[c for c in llm.columns if c.startswith('b3_') or c in ['llm_full_valid','llm_full_n_hyp','llm_abstain']]
    b4cols=b3cols+[c for c in llm.columns if c.startswith('js_') or c.startswith('b4_')]
    fam={'B0_M1':m1,'B1_M1_DETERMINISTIC':m1+b1cols,'B2_M1_SINGLE_LLM':m1+b2cols,'B3_M1_MULTI_LLM':m1+b3cols,'B4_M1_VERIFIED_LLM':m1+b4cols}
    pred_rows=work[['case_id','anchor_wallet','cutoff_date','split','activity_bin']].copy()
    metric_rows=[]
    loss_rows=[]
    for name,feats in fam.items():
        for target in TARGETS:
            pdev=fit_predict(work[work.split=='train'],work[work.split=='dev'],feats,target)
            ptest=fit_predict(work[work.split.isin(['train','dev'])],work[work.split=='test'],feats,target)
            for split,sub,p in [('dev',work[work.split=='dev'],pdev),('test',work[work.split=='test'],ptest)]:
                met=fixed_metric(sub[f'y_{target}'],p); met.update({'model':name,'target':target,'split':split})
                metric_rows.append(met)
            for split,sub,p in [('dev',work[work.split=='dev'],pdev),('test',work[work.split=='test'],ptest)]:
                idx=pred_rows.case_id.isin(sub.case_id)
                for j,c in enumerate(CLASSES): pred_rows.loc[idx,f'{name}__{target}__p_{c}']=p[:,j]
                pred_rows.loc[idx,f'{name}__{target}__ll']=-(np.log(np.maximum(p[np.arange(len(p)),[CLASSES.index(x) for x in sub[f'y_{target}']]],1e-12)))
    # Direct LLM descriptive metrics (not primary B0-B4 head).
    for name,prefix in [('B2_DIRECT_SINGLE','b2'),('B3_DIRECT_MULTI','b3'),('B4_DIRECT_VERIFIED','b4')]:
        for target in TARGETS:
            cols=[f'{prefix}_{target}_p_{c}' for c in CLASSES]
            for split in ['dev','test']:
                sub=work[work.split==split]; met=fixed_metric(sub[f'y_{target}'],sub[cols].to_numpy()); met.update({'model':name,'target':target,'split':split,'descriptive_direct':True}); metric_rows.append(met)
    # Case-level mean log loss for paired bootstrap on test.
    test=pred_rows[pred_rows.split=='test'].copy()
    for name in fam:
        llcols=[f'{name}__{t}__ll' for t in TARGETS]
        test[name+'__case_ll']=test[llcols].mean(axis=1)
    for a,b in [('B0_M1','B4_M1_VERIFIED_LLM'),('B0_M1','B3_M1_MULTI_LLM'),('B2_M1_SINGLE_LLM','B4_M1_VERIFIED_LLM')]:
        r=bootstrap_diffs(test,a+'__case_ll',b+'__case_ll',n=args.bootstrap)
        r.update({'comparison':f'{a}_vs_{b}','metric':'case_mean_log_loss','better_positive':'A lower loss than B'})
        loss_rows.append(r)
    pred_rows.to_csv(RES/'decision_state_meta_predictions.csv',index=False)
    pd.DataFrame(metric_rows).to_csv(RES/'decision_state_metrics.csv',index=False)
    pd.DataFrame(loss_rows).to_csv(RES/'decision_state_bootstrap.csv',index=False)
    # Response/validity summary.
    panel_rows=sum(1 for r in records.values())
    valid=sum(bool(r.get('parse_valid')) for r in records.values())
    summary={
        'protocol':'decision_state_v1_with_meta_heads',
        'panel_file':str(RES/args.panel),
        'panel_sha256':sha256_file(RES/args.panel),
        'panel_records':panel_rows,'panel_valid':valid,'panel_valid_rate':valid/panel_rows if panel_rows else 0,
        'model_families':{k:len(v) for k,v in fam.items()},
        'metrics_file':'decision_state_metrics.csv','bootstrap_file':'decision_state_bootstrap.csv',
        'primary_test_comparison':next((x for x in loss_rows if x['comparison']=='B0_M1_vs_B4_M1_VERIFIED_LLM'),None),
        'n_test_cases':int((work.split=='test').sum()),
    }
    (RES/'decision_state_evaluation_manifest.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    print('\nTEST METRICS')
    print(pd.DataFrame(metric_rows).query("split=='test'").to_string(index=False))
    print('\nBOOTSTRAP')
    print(pd.DataFrame(loss_rows).to_string(index=False))

if __name__=='__main__': main()
