#!/usr/bin/env python3
"""Resumable Qwen direct-vs-grounded hypothesis pilot on frozen Aug event cases."""
import hashlib,json,os,re,time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
OUT=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927'
BASE=os.getenv('LLM_BASE_URL','http://10.63.0.82:31518/v1').rstrip('/')
MODEL=os.getenv('LLM_MODEL','Qwen3.5-4B')
raw_path=OUT/'llm_raw.jsonl'
FEATURES=['evt_7d','evt_30d','evt_90d','active_days_30d','distinct_cp_30d','new_cp_rate_30d','cp_entropy_30d','top_cp_share_30d','reciprocal_pairs_30d','out_share_30d','token_share_30d','trace_share_30d','days_since_last_event']
cases=[json.loads(x) for x in (OUT/'cases.jsonl').read_text().splitlines()]
cases=[x for x in cases if x['llm_sample']]
assert len(cases)==80 and set(x['split'] for x in cases)=={'test'}
completed={}
if raw_path.exists():
    for line in raw_path.read_text().splitlines():
        try:
            x=json.loads(line); completed[(x['case_id'],x['arm'])]=x
        except Exception:pass

def parse(text):
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip(),flags=re.I|re.S)
    try:return json.loads(text)
    except Exception:
        m=re.search(r'\{.*\}',text,re.S)
        if m:
            try:return json.loads(m.group(0))
            except Exception:pass
    return None

def prompt(c,arm):
    feat='\n'.join(f'{k}={c["features"][k]:.5g}' if isinstance(c['features'][k],float) else f'{k}={c["features"][k]}' for k in FEATURES)
    common=f'''Cutoff UTC: {c['cutoff']} 00:00:00. Task: forecast whether this wallet will interact with at least one counterparty not observed before the cutoff during the next 7 days in the observed dataset. Answer NEW, NONE, or ABSTAIN. Only pre-cutoff evidence is supplied.\nPast-only features:\n{feat}\n'''
    if arm=='direct':
        return common+'''Return JSON only: {"prediction":"NEW|NONE|ABSTAIN","reason":"one short sentence"}. Do not infer identity, motive, crime, or investment intent.'''
    events='\n'.join(f"{e['evidence_id']} {e['time']} {e['direction']} {e['family']} {e['counterparty']}" for e in c['evidence'])
    return common+f'''Last {len(c['evidence'])} observed pre-cutoff events, with stable counterparty aliases:\n{events}\nPropose a falsifiable behavioral hypothesis, cite 1-3 listed evidence IDs, and supply an executable one-feature rule. Allowed feature: one of {', '.join(FEATURES)}. Allowed op: >= or <. The rule predicts NEW when its condition is true or false as specified; use NONE for the alternative. If evidence is insufficient, ABSTAIN. Return JSON only: {{"prediction":"NEW|NONE|ABSTAIN","hypothesis":"...","evidence_ids":["E1"],"rule":{{"feature":"evt_7d","op":">=","threshold":2,"forecast_if_true":"NEW","forecast_if_false":"NONE"}}}}. Do not invent events or infer identity, motive, crime, or investment intent.'''

def call(p):
    t=time.time()
    payload={'model':MODEL,'messages':[{'role':'system','content':'You are an as-of temporal graph analyst. Use only supplied past events. Return JSON only.'},{'role':'user','content':p}],
             'temperature':0,'max_tokens':360,'stream':False}
    r=requests.post(BASE+'/chat/completions',json=payload,timeout=150)
    dt=time.time()-t;r.raise_for_status();j=r.json()
    return {'response':j['choices'][0]['message'].get('content',''),'usage':j.get('usage',{}),'elapsed_s':dt,'status':r.status_code}

with raw_path.open('a') as f:
    for c in cases:
        for arm in ['direct','hypothesis']:
            key=(c['case_id'],arm)
            if key in completed:continue
            p=prompt(c,arm)
            try:
                out=call(p);out['parsed']=parse(out['response'])
            except Exception as e:
                out={'error':type(e).__name__+': '+str(e),'parsed':None}
            rec={'case_id':c['case_id'],'arm':arm,'prompt':p,**out}
            f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
            completed[key]=rec
            print('done',c['case_id'],arm,'ok' if rec['parsed'] else 'error',flush=True)

records=list(completed.values())
case_map={c['case_id']:c for c in cases}
rows=[]
for rec in records:
    c=case_map.get(rec['case_id'])
    if c is None:continue
    p=rec.get('parsed') or {}
    pred=str(p.get('prediction','')).upper()
    if pred not in ['NEW','NONE','ABSTAIN']:pred='INVALID'
    cited=p.get('evidence_ids',[]) if isinstance(p.get('evidence_ids',[]),list) else []
    evidence_ids={x['evidence_id'] for x in c['evidence']}
    citation_valid=bool(cited) and all(isinstance(x,str) and x in evidence_ids for x in cited)
    rule=p.get('rule') if isinstance(p.get('rule'),dict) else {}
    rule_valid=False;rule_pred=None
    if rec['arm']=='hypothesis':
        try:
            ft=rule['feature'];op=rule['op'];thr=float(rule['threshold'])
            yes=str(rule['forecast_if_true']).upper();no=str(rule['forecast_if_false']).upper()
            if ft in FEATURES and op in ['>=','<'] and {yes,no}=={'NEW','NONE'} and np.isfinite(thr):
                truth=c['features'][ft]>=thr if op=='>=' else c['features'][ft]<thr
                rule_pred=yes if truth else no
                rule_valid=True
        except Exception:pass
    rows.append({'case_id':c['case_id'],'wallet':c['wallet'],'arm':rec['arm'],'prediction':pred,
                 'label':int(c['label_any_new_cp_7d']),'numeric_pred':int(c['numeric_pred']),
                 'parse_ok':bool(rec.get('parsed')),'citation_valid':citation_valid,
                 'n_cited':len(cited),'rule_valid':rule_valid,'rule_pred':rule_pred,
                 'rule_consistent':bool(rule_valid and rule_pred==pred),
                 'latency_s':rec.get('elapsed_s'),
                 'prompt_tokens':(rec.get('usage') or {}).get('prompt_tokens',0),
                 'completion_tokens':(rec.get('usage') or {}).get('completion_tokens',0)})
df=pd.DataFrame(rows).sort_values(['case_id','arm'])
df.to_csv(OUT/'llm_predictions.csv',index=False)
report={'model':MODEL,'base_url':BASE,'sample_n':len(cases),'calls_expected':len(cases)*2,'calls_recorded':len(records),
        'raw_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),'arms':{}}
for arm,g in df.groupby('arm'):
    fired=g[g.prediction.isin(['NEW','NONE'])].copy()
    y=fired.label.to_numpy();lp=(fired.prediction=='NEW').astype(int).to_numpy();bp=fired.numeric_pred.to_numpy()
    diff=(lp==y).astype(int)-(bp==y).astype(int)
    rng=np.random.default_rng(20260927);boots=[]
    for _ in range(5000):
        idx=rng.integers(0,len(fired),len(fired));boots.append(float(diff[idx].mean()))
    report['arms'][arm]={'n':len(g),'parse_rate':float(g.parse_ok.mean()),'coverage':float(len(fired)/len(g)),
                         'llm_accuracy_fired':float((lp==y).mean()),
                         'numeric_accuracy_same_fired':float((bp==y).mean()),
                         'paired_difference':float(diff.mean()),
                         'paired_bootstrap_95ci':[float(x) for x in np.quantile(boots,[.025,.975])],
                         'valid_citation_rate':float(g.citation_valid.mean()) if arm=='hypothesis' else None,
                         'valid_rule_rate':float(g.rule_valid.mean()) if arm=='hypothesis' else None,
                         'rule_prediction_consistency_rate':float(g.rule_consistent.mean()) if arm=='hypothesis' else None,
                         'prompt_tokens':int(g.prompt_tokens.sum()),'completion_tokens':int(g.completion_tokens.sum()),
                         'elapsed_s':float(g.latency_s.fillna(0).sum())}
(OUT/'llm_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(report,indent=2,ensure_ascii=False))
