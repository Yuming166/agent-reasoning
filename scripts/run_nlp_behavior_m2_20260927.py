#!/usr/bin/env python3
"""Run the leakage-audited language-state arm on the complete frozen test split."""
import hashlib,json,os,re,time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, brier_score_loss

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC=ROOT/'artifacts/nlp_behavior_setup_20260927/nlp_inputs.jsonl'
CASES=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl'
OUT=ROOT/'artifacts/nlp_behavior_setup_20260927'
BASE=os.getenv('LLM_BASE_URL','http://10.63.0.82:31518/v1').rstrip('/')
MODEL=os.getenv('LLM_MODEL','Qwen3.5-4B')
raw_path=OUT/'m2_llm_raw.jsonl'
inputs=[json.loads(x) for x in SRC.read_text().splitlines() if x.strip()]
cases={r['case_id']:r for r in (json.loads(x) for x in CASES.read_text().splitlines() if x.strip())}
inputs=[x for x in inputs if x['split']=='test']
completed={}
if raw_path.exists():
    for line in raw_path.read_text().splitlines():
        try:
            r=json.loads(line); completed[r['case_id']]=r
        except Exception: pass

def parse_json(text):
    if not isinstance(text,str): return None
    s=re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$','',text.strip(),flags=re.I|re.S)
    try:return json.loads(s)
    except Exception:
        m=re.search(r'\{.*\}',s,re.S)
        if m:
            try:return json.loads(m.group(0))
            except Exception:return None
    return None

def validate(parsed, c):
    if not isinstance(parsed,dict): return {'valid':False,'reason':'not_object'}
    state=str(parsed.get('state','')).lower()
    forecast=str(parsed.get('forecast','')).upper()
    allowed={'dormant','reactivation','stable_repeat','exploration','expansion','consolidation','routing'}
    reasons=[]
    if state not in allowed: reasons.append('invalid_state')
    if forecast not in {'NEW','NONE','ABSTAIN'}: reasons.append('invalid_forecast')
    try:
        conf=float(parsed.get('confidence'))
        if not (0<=conf<=1): reasons.append('invalid_confidence')
    except Exception: reasons.append('invalid_confidence')
    ids=parsed.get('evidence_ids',[])
    if not isinstance(ids,list) or not all(isinstance(x,str) for x in ids): reasons.append('invalid_evidence_ids')
    else:
        valid_ids={e['evidence_id'] for e in c['evidence']}
        if len(ids)>3: reasons.append('too_many_evidence_ids')
        if not all(x in valid_ids for x in ids): reasons.append('unknown_evidence_id')
    if not str(parsed.get('uncertainty','')).strip(): reasons.append('missing_uncertainty')
    if not isinstance(parsed.get('abstain'),bool): reasons.append('invalid_abstain')
    # Keep a prediction only when schema is fully valid; abstention is a valid output.
    return {'valid':not reasons,'reason':';'.join(reasons)}

def call(prompt):
    payload={'model':MODEL,'messages':[{'role':'system','content':'You are an as-of temporal graph analyst. Use only supplied pre-cutoff evidence. Return JSON only and cite at most 3 evidence ids.'},{'role':'user','content':prompt}], 'temperature':0,'max_tokens':420,'stream':False}
    t=time.time(); r=requests.post(BASE+'/chat/completions',json=payload,timeout=150); elapsed=time.time()-t
    r.raise_for_status(); j=r.json()
    return {'request':payload,'response':j,'elapsed_s':elapsed}

with raw_path.open('a') as f:
    for i,x in enumerate(inputs,1):
        if x['case_id'] in completed: continue
        try:
            o=call(x['state_prompt']); content=o['response']['choices'][0]['message'].get('content',''); parsed=parse_json(content)
            rec={'case_id':x['case_id'],'status':'ok','model':MODEL,'base_url':BASE,'response':o['response'],'parsed':parsed,'validation':validate(parsed,cases[x['case_id']]),'elapsed_s':o['elapsed_s']}
        except Exception as e:
            rec={'case_id':x['case_id'],'status':'error','model':MODEL,'base_url':BASE,'error':type(e).__name__+': '+str(e),'parsed':None,'validation':{'valid':False,'reason':'request_error'}}
        f.write(json.dumps(rec,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno()); completed[x['case_id']]=rec
        print(f'{i}/{len(inputs)} {x["case_id"]} {rec["status"]} valid={rec["validation"]["valid"]}',flush=True)

rows=[]
for x in inputs:
    rec=completed[x['case_id']]; c=cases[x['case_id']]; p=rec.get('parsed') or {}; valid=bool(rec.get('validation',{}).get('valid'))
    forecast=str(p.get('forecast','')).upper() if valid else 'INVALID'
    fired=valid and forecast in {'NEW','NONE'}
    pred=int(forecast=='NEW') if fired else None
    rows.append({'case_id':x['case_id'],'wallet':x['wallet'],'label':int(c['label_any_new_cp_7d']),'numeric_pred':int(c['numeric_pred']),'numeric_prob':float(c['numeric_prob']),'state':p.get('state') if valid else None,'forecast':forecast,'fired':fired,'parse_valid':valid,'validation_reason':rec.get('validation',{}).get('reason',''),'confidence':p.get('confidence') if valid else None,'evidence_ids':p.get('evidence_ids') if valid else None,'abstain':p.get('abstain') if valid else None,'latency_s':rec.get('elapsed_s')})
df=pd.DataFrame(rows); df.to_csv(OUT/'m2_llm_predictions.csv',index=False)

def ece(y,p,bins=10):
    y=np.asarray(y);p=np.asarray(p); z=0.
    for lo,hi in zip(np.linspace(0,1,bins+1)[:-1],np.linspace(0,1,bins+1)[1:]):
        m=(p>=lo)&(p<(hi if hi<1 else hi+1e-9))
        if m.any(): z += m.mean()*abs(y[m].mean()-p[m].mean())
    return float(z)
metrics={'model':'M2_language_state','model_name':MODEL,'base_url':BASE,'test_n':len(df),'valid_schema_rate':float(df.parse_valid.mean()),'error_rate':float((~df.parse_valid).mean()),'state_counts':df.state.value_counts(dropna=False).to_dict(),'forecast_counts':df.forecast.value_counts(dropna=False).to_dict()}
fired=df[df.fired].copy()
if len(fired):
    y=fired.label.to_numpy(); lp=(fired.forecast=='NEW').astype(int).to_numpy(); bp=fired.numeric_pred.to_numpy(); diff=(lp==y).astype(int)-(bp==y).astype(int)
    rng=np.random.default_rng(20260927); boots=[]
    for _ in range(5000):
        ix=rng.integers(0,len(fired),len(fired)); boots.append(float(diff[ix].mean()))
    metrics['fired']={'n':len(fired),'coverage':float(len(fired)/len(df)),'accuracy':float(accuracy_score(y,lp)),'balanced_accuracy':float(balanced_accuracy_score(y,lp)),'f1_new':float(f1_score(y,lp,zero_division=0)),'same_subset_numeric_accuracy':float(accuracy_score(y,bp)),'paired_difference':float(diff.mean()),'paired_bootstrap_95ci':[float(v) for v in np.quantile(boots,[.025,.975])], 'mean_confidence':float(pd.to_numeric(fired.confidence).mean())}
else: metrics['fired']={'n':0,'coverage':0.0}
(OUT/'m2_llm_metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(metrics,indent=2,ensure_ascii=False))
