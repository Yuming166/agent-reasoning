#!/usr/bin/env python3
import argparse,json,os,time,hashlib,re
from pathlib import Path
import pandas as pd, requests

BASE=os.environ.get('LLM_BASE_URL','http://10.63.0.82:31518/v1').rstrip('/')
MODEL=os.environ.get('LLM_MODEL','Qwen3.5-4B')

def parse_json(text):
    text=text.strip()
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S).strip()
    try:return json.loads(text)
    except Exception:
        m=re.search(r'\{.*\}',text,re.S)
        if m:
            try:return json.loads(m.group(0))
            except Exception:pass
    return None

def call(messages, timeout=120):
    payload={'model':MODEL,'messages':messages,'temperature':0,'max_tokens':220,'stream':False}
    headers={}
    if os.environ.get('LLM_BEARER'): headers['Authorization']='Bearer '+os.environ['LLM_BEARER']
    t=time.time(); r=requests.post(BASE+'/chat/completions',json=payload,headers=headers,timeout=timeout); dt=time.time()-t
    r.raise_for_status(); j=r.json(); c=j.get('choices',[{}])[0].get('message',{}).get('content','')
    return {'content':c,'usage':j.get('usage',{}),'model':j.get('model'), 'elapsed_s':dt, 'status':r.status_code}

def context(r):
    return (f"cutoff_utc={r.snapshot_date.isoformat()}\n"
            f"pre_cutoff_90d_event_count={int(r.evt_cnt_90d)}\n"
            f"pre_cutoff_active_days_90d={int(r.active_days_90d)}\n"
            f"pre_cutoff_counterparty_entropy={float(r.cp_entropy_90d):.4f}\n"
            f"pre_cutoff_new_counterparty_rate_30d={float(r.cp_new_rate_30d):.4f}\n"
            f"pre_cutoff_global_activity_weight={float(r.pop_weight):.4f}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--n',type=int,default=40); ap.add_argument('--seed',type=int,default=20260927); args=ap.parse_args()
    root=Path(args.root); base=root/'artifacts/motif_hypothesis_pilot_20260927'; out=base/'llm_arm'; out.mkdir(parents=True,exist_ok=True)
    d=pd.read_csv(base/'sample_verification_rows.csv'); d['snapshot_date']=pd.to_datetime(d.snapshot_date,utc=True)
    # fixed sample: prioritize holdout and retain deterministic order
    d=d.sort_values(['split','event_id']).head(args.n).copy()
    system='''You analyze only the supplied pre-cutoff on-chain aggregate evidence. Do not infer owner identity or intent. Predict whether the next observed event within 7 days will involve a new or repeat counterparty. You may abstain. Return JSON only.'''
    raw=[]; rows=[]
    for _,r in d.iterrows():
        ctx=context(r)
        prompts={
          'direct':f'''{ctx}\nTask: give one prediction (new, repeat, or abstain) and a short natural-language behavioral hypothesis. Return {{"prediction":"new|repeat|abstain","hypothesis":"...","confidence":0.0,"evidence_fields":["..."]}}.''',
          'constrained':f'''{ctx}\nTask: construct a falsifiable hypothesis using only the named fields, express it as a simple IF/THEN DSL, choose new/repeat/abstain, and list the exact supplied fields used. Do not invent transaction IDs. Return {{"prediction":"new|repeat|abstain","hypothesis":"...","dsl":"...","confidence":0.0,"evidence_fields":["..."]}}.'''
        }
        rec={'event_id':r.event_id,'split':r.split,'outcome_new':int(r.outcome_new),'outcome':'new' if r.outcome_new else 'repeat','calls':{}}
        for arm,p in prompts.items():
            try:
                z=call([{'role':'system','content':system},{'role':'user','content':p}])
                parsed=parse_json(z['content']); z['parsed']=parsed; z['parse_ok']=parsed is not None
            except Exception as e:
                z={'error':type(e).__name__+': '+str(e),'parse_ok':False,'elapsed_s':None,'usage':{}}
            rec['calls'][arm]=z
            raw.append({'event_id':r.event_id,'arm':arm,**z})
        rows.append(rec)
    pd.DataFrame([{'event_id':x['event_id'],'split':x['split'],'outcome':x['outcome'],'arm':a,'parse_ok':x['calls'][a].get('parse_ok',False),'prediction':(x['calls'][a].get('parsed') or {}).get('prediction'),'hypothesis':(x['calls'][a].get('parsed') or {}).get('hypothesis'),'dsl':(x['calls'][a].get('parsed') or {}).get('dsl'),'confidence':(x['calls'][a].get('parsed') or {}).get('confidence'),'evidence_fields':json.dumps((x['calls'][a].get('parsed') or {}).get('evidence_fields',[]),ensure_ascii=False)} for x in rows for a in ['direct','constrained']]).to_csv(out/'llm_predictions.csv',index=False)
    (out/'raw_responses.jsonl').write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in raw)+'\n')
    summary={'model':MODEL,'base_url':BASE,'sample_n':len(d),'calls_expected':len(d)*2,'calls_completed':sum('error' not in x for x in raw),'generated_utc':pd.Timestamp.now('UTC').isoformat(),'new_network_requests':len(raw),'paid_queries':0,'arms':{}}
    pred=pd.read_csv(out/'llm_predictions.csv')
    for arm in ['direct','constrained']:
        q=pred[pred.arm==arm]; q=q[q.parse_ok & q.prediction.isin(['new','repeat','abstain'])]
        fired=q[q.prediction!='abstain']; correct=(fired.prediction==fired.outcome).sum()
        summary['arms'][arm]={'n':len(q),'parse_rate':float(len(q)/len(pred[pred.arm==arm])),'coverage':float(len(fired)/len(pred[pred.arm==arm])),'accuracy_when_fired':float(correct/len(fired)) if len(fired) else None,'correct':int(correct),'usage_prompt_tokens':int(sum((x.get('usage') or {}).get('prompt_tokens',0) for x in raw if x['arm']==arm)),'usage_completion_tokens':int(sum((x.get('usage') or {}).get('completion_tokens',0) for x in raw if x['arm']==arm)),'elapsed_s':float(sum(x.get('elapsed_s') or 0 for x in raw if x['arm']==arm))}
    summary['raw_sha256']=hashlib.sha256((out/'raw_responses.jsonl').read_bytes()).hexdigest()
    (out/'llm_report.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
