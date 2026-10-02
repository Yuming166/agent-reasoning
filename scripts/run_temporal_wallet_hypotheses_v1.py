#!/usr/bin/env python3
"""v1 typed temporal-wallet hypothesis smoke: deterministic executor + Qwen arms."""
import argparse, csv, hashlib, json, os, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
import requests

BASE=os.environ.get('LLM_BASE_URL','http://10.63.0.82:31518/v1').rstrip('/')
MODEL=os.environ.get('LLM_MODEL','Qwen3.5-4B')
VERSION='temporal_wallet_hypotheses_v1_20260928'

ONTOLOGY={
 'new_exploration':'recent 30d exploration/new-counterparty intensity',
 'repeat_concentration':'recent 30d concentration on a dominant counterparty',
 'reciprocal_change':'recent 30d reciprocal/bidirectional interaction change',
}

def dt(x):
    z=pd.Timestamp(x)
    if z.tzinfo is None: z=z.tz_localize('UTC')
    return z.to_pydatetime().astimezone(timezone.utc)

def stable_hash(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def parse_json(text):
    text=(text or '').strip(); text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S).strip()
    try:return json.loads(text)
    except Exception:
        m=re.search(r'\{.*\}',text,re.S)
        if m:
            try:return json.loads(m.group(0))
            except Exception:return None
    return None

def call(messages, timeout=120):
    payload={'model':MODEL,'messages':messages,'temperature':0,'max_tokens':420,'stream':False}
    headers={}
    if os.environ.get('LLM_BEARER'): headers['Authorization']='Bearer '+os.environ['LLM_BEARER']
    t=time.time()
    r=requests.post(BASE+'/chat/completions',json=payload,headers=headers,timeout=timeout)
    elapsed=time.time()-t; r.raise_for_status(); j=r.json()
    return {'content':j.get('choices',[{}])[0].get('message',{}).get('content',''),'usage':j.get('usage',{}),'model':j.get('model'), 'elapsed_s':elapsed,'status':r.status_code}

def load_data(root):
    cases_p=root/'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl'
    raw_p=root/'artifacts/motif_hypothesis_eventlevel_20260927/raw_events.jsonl'
    cases=[json.loads(x) for x in cases_p.open()]
    events=[json.loads(x) for x in raw_p.open()]
    by_wallet=defaultdict(list)
    for e in events: by_wallet[e['target_address'].lower()].append(e)
    for w in by_wallet: by_wallet[w].sort(key=lambda e:(e['block_timestamp'],e.get('target_sequence_index',-1)))
    return cases,by_wallet,cases_p,raw_p

def metrics(events, cutoff):
    c=dt(cutoff); pre=[e for e in events if dt(e['block_timestamp'])<c]
    def win(lo,hi):
        return [e for e in pre if c-timedelta(days=hi) <= dt(e['block_timestamp']) < c-timedelta(days=lo)]
    def calc(es):
        cps=[e.get('counterparty_address') for e in es if e.get('counterparty_address')]
        n=len(es); uniq=set(cps); counts=Counter(cps)
        out={ 'n':n, 'distinct_cp':len(uniq), 'top_share':(max(counts.values())/n if n else 0.0),
              'new_rate':(len(uniq)/n if n else None), 'reciprocal_pairs':0 }
        dirs=defaultdict(set)
        for e in es: dirs[e.get('counterparty_address')].add(e.get('direction'))
        out['reciprocal_pairs']=sum('incoming' in v and 'outgoing' in v for v in dirs.values())
        return out
    r=calc(win(0,30)); p=calc(win(30,60));
    r['exploration_delta']=(r['new_rate']-p['new_rate']) if r['new_rate'] is not None and p['new_rate'] is not None else None
    r['reciprocal_delta']=r['reciprocal_pairs']-p['reciprocal_pairs']
    r['valid']=bool(r['n']>0)
    return r,pre

def choose_thresholds(cases):
    # thresholds are selected from train only; deliberately fixed and auditable.
    train=[c for c in cases if c.get('split')=='train']
    vals={
      'new_rate':sorted(float(c['features'].get('new_cp_rate_30d',0)) for c in train),
      'top_share':sorted(float(c['features'].get('top_cp_share_30d',0)) for c in train),
      'reciprocal':sorted(float(c['features'].get('reciprocal_pairs_30d',0)) for c in train),
    }
    def q(a,p): return a[min(len(a)-1,max(0,int((len(a)-1)*p)))]
    return {'new_rate':max(0.5, q(vals['new_rate'],.70)), 'top_share':max(.5,q(vals['top_share'],.70)), 'reciprocal':max(1.0,q(vals['reciprocal'],.70))}

def execute(rule, m):
    if not isinstance(rule,dict) or rule.get('op')!='threshold': return {'status':'invalid','metric':None,'value':None,'threshold':None,'certificate':None}
    metric=rule.get('metric'); op=rule.get('operator','>='); th=rule.get('threshold')
    metric_map={'new_rate_30d':'new_rate','top_cp_share_30d':'top_share','reciprocal_pairs_30d':'reciprocal_pairs','exploration_delta_30d':'exploration_delta','reciprocal_delta_30d':'reciprocal_delta'}
    key=metric_map.get(metric)
    if key is None or not isinstance(th,(int,float)) or m.get(key) is None: return {'status':'insufficient','metric':metric,'value':m.get(key),'threshold':th,'certificate':None}
    v=float(m[key]); ok=(v>=float(th)) if op=='>=' else (v>float(th) if op=='>' else (v<=float(th) if op=='<=' else v<float(th)))
    cert={'metric':metric,'value':v,'operator':op,'threshold':float(th),'window':'pre-cutoff 30d; comparison uses preceding 30d where applicable','denominator_events_30d':m['n'],'valid_history':m['valid']}
    return {'status':'supported' if ok else 'unsupported','metric':metric,'value':v,'threshold':float(th),'certificate':cert}

def template(c, thresholds):
    f=c['features'];
    if c['history_event_count']<3: return {'abstain':True,'claim_type':None,'prediction':'abstain','rule':None,'witness_ids':[],'reason':'low_event_count'}
    if float(f.get('new_cp_rate_30d',0))>=thresholds['new_rate']:
        return {'abstain':False,'claim_type':'new_exploration','prediction':'new','rule':{'op':'threshold','metric':'new_rate_30d','operator':'>=','threshold':thresholds['new_rate']},'witness_ids':['E1'],'reason':'template'}
    if float(f.get('top_cp_share_30d',0))>=thresholds['top_share']:
        return {'abstain':False,'claim_type':'repeat_concentration','prediction':'repeat','rule':{'op':'threshold','metric':'top_cp_share_30d','operator':'>=','threshold':thresholds['top_share']},'witness_ids':['E1'],'reason':'template'}
    return {'abstain':True,'claim_type':None,'prediction':'abstain','rule':None,'witness_ids':[],'reason':'no_v1_condition'}

def prompt(c, mode, feedback=None):
    f=c['features'];
    allowed='new_exploration, repeat_concentration, reciprocal_change'
    base=f'''cutoff={c['cutoff']}\npre-cutoff features only: history_event_count={c['history_event_count']}; evt_30d={f.get('evt_30d')}; distinct_cp_30d={f.get('distinct_cp_30d')}; new_cp_rate_30d={f.get('new_cp_rate_30d')}; top_cp_share_30d={f.get('top_cp_share_30d')}; reciprocal_pairs_30d={f.get('reciprocal_pairs_30d')}; active_days_30d={f.get('active_days_30d')}\nAllowed claim_type: {allowed}. Allowed metrics: new_rate_30d, top_cp_share_30d, reciprocal_pairs_30d, exploration_delta_30d, reciprocal_delta_30d.\nDo not invent transaction IDs. Witness IDs may be selected only from E1..E12 if present. The executor, not you, computes the certificate.''' 
    if mode=='free': ins='Return JSON with claim_type, prediction(new/repeat/abstain), rule, witness_ids, abstain, rationale.'
    else: ins='Return JSON only. rule must be {"op":"threshold","metric":...,"operator":">=","threshold":number}; claim_type must match metric; abstain when evidence is insufficient.'
    if feedback: ins += '\nExecutor feedback from the first proposal: '+json.dumps(feedback,ensure_ascii=False)+'\nRevise or abstain; do not write a certificate.'
    return base+'\n'+ins

def normalize(obj):
    if not isinstance(obj,dict): return {'abstain':True,'prediction':'abstain','claim_type':None,'rule':None,'witness_ids':[],'parse_valid':False}
    pred=obj.get('prediction','abstain'); abst=bool(obj.get('abstain',pred=='abstain')) or pred=='abstain'
    return {'abstain':abst,'prediction':'abstain' if abst else pred,'claim_type':obj.get('claim_type'),'rule':obj.get('rule'),'witness_ids':obj.get('witness_ids',[]) if isinstance(obj.get('witness_ids',[]),list) else [],'rationale':obj.get('rationale',''),'parse_valid':True}

def verify(proposal,c,events,cutoff):
    m,_=metrics(events,cutoff); ex=execute(proposal.get('rule'),m) if not proposal.get('abstain') else {'status':'abstain','certificate':None,'metric':None,'value':None,'threshold':None}
    ids={x.get('evidence_id') for x in c.get('evidence',[]) if x.get('evidence_id')}
    wit_ok=all(x in ids for x in proposal.get('witness_ids',[]))
    align=proposal.get('abstain') or (proposal.get('claim_type') in ONTOLOGY and isinstance(proposal.get('rule'),dict) and ((proposal['claim_type']=='new_exploration' and proposal['rule'].get('metric')=='new_rate_30d') or (proposal['claim_type']=='repeat_concentration' and proposal['rule'].get('metric')=='top_cp_share_30d') or (proposal['claim_type']=='reciprocal_change' and proposal['rule'].get('metric') in ('reciprocal_pairs_30d','reciprocal_delta_30d'))))
    verified=(proposal.get('abstain') or (ex['status'] in ('supported','unsupported') and wit_ok and align))
    return {'verified':bool(verified),'semantic_alignment':bool(align),'witness_valid':bool(wit_ok),'executor':ex,'metrics':m,'certificate':ex.get('certificate')}

def counterfactual(c,events,prop):
    # delete the latest pre-cutoff event named by the first valid witness; fallback latest event.
    cut=dt(c['cutoff']); hist=[e for e in events if dt(e['block_timestamp'])<cut]
    if len(hist)<3: return {'eligible':False,'reason':'too_few_history'}
    edited=list(hist[:-1])
    before=verify(prop,c,hist,c['cutoff'])
    after=verify(prop,c,edited,c['cutoff'])
    bs=before['executor']['status']; as_=after['executor']['status']
    if bs=='insufficient' or as_=='insufficient': label='WITHDRAW' if as_=='insufficient' else 'INVARIANT'
    elif bs!=as_: label='CHANGE'
    else: label='INVARIANT'
    return {'eligible':True,'edited_event_sequence':hist[-1].get('target_sequence_index'),'original_status':bs,'edited_status':as_,'revision':label,'before':before['executor'],'after':after['executor']}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--n',type=int,default=30); ap.add_argument('--no-llm',action='store_true'); args=ap.parse_args()
    root=Path(args.root); out=root/'artifacts/temporal_wallet_hypotheses_v1_20260928'; out.mkdir(parents=True,exist_ok=True)
    cases,by_wallet,cp,rp=load_data(root); thresholds=choose_thresholds(cases)
    audit=[]
    for c in cases:
        cut=dt(c['cutoff']); evs=by_wallet[c['wallet'].lower()]; pre=[e for e in evs if dt(e['block_timestamp'])<cut]; post=[e for e in evs if cut<=dt(e['block_timestamp'])<cut+timedelta(days=7)]
        bad=[e for e in pre if dt(e['block_timestamp'])>=cut]; audit.append({'case_id':c['case_id'],'split':c['split'],'pre_events':len(pre),'future_7d_events':len(post),'bad_pre_events':len(bad),'case_label':c.get('label_any_new_cp_7d'),'raw_hashes_in_future':sum(1 for x in c.get('evidence',[]) if x.get('tx_hash') in {e.get('transaction_hash') for e in post})})
    pd.DataFrame(audit).to_csv(out/'asof_audit.csv',index=False)
    dev=[c for c in cases if c.get('split')=='dev']; dev=sorted(dev,key=lambda c:c['case_id'])[:args.n]
    rows=[]; raw=[]; counters=Counter(); all_props=[]
    for c in dev:
        evs=by_wallet[c['wallet'].lower()]; t=template(c,thresholds); tv=verify(t,c,evs,c['cutoff']); cf=counterfactual(c,evs,t)
        arms={'template':(t,tv,cf)}
        if not args.no_llm:
            for mode in ['free','constrained']:
                try:
                    z=call([{'role':'system','content':'You propose a typed, falsifiable wallet hypothesis. Never provide a certificate; a deterministic executor will verify it.'},{'role':'user','content':prompt(c,mode)}]); obj=normalize(parse_json(z['content'])); z['parsed']=obj; z['parse_ok']=obj.get('parse_valid',False)
                except Exception as e: z={'error':type(e).__name__+': '+str(e),'parse_ok':False,'usage':{},'elapsed_s':None}; obj=normalize(None)
                raw.append({'case_id':c['case_id'],'arm':mode,'stage':'initial',**z}); v=verify(obj,c,evs,c['cutoff']); cf2=counterfactual(c,evs,obj); arms[mode]=(obj,v,cf2)
                if mode=='constrained':
                    try:
                        z2=call([{'role':'system','content':'Revise a typed wallet hypothesis after deterministic executor feedback. Never provide a certificate.'},{'role':'user','content':prompt(c,mode,{'verified':v['verified'],'executor_status':v['executor']['status'],'semantic_alignment':v['semantic_alignment']})}]); obj2=normalize(parse_json(z2['content'])); z2['parsed']=obj2; z2['parse_ok']=obj2.get('parse_valid',False)
                    except Exception as e: z2={'error':type(e).__name__+': '+str(e),'parse_ok':False,'usage':{},'elapsed_s':None}; obj2=normalize(None)
                    raw.append({'case_id':c['case_id'],'arm':'constrained_feedback','stage':'revision',**z2}); arms['constrained_feedback']=(obj2,verify(obj2,c,evs,c['cutoff']),counterfactual(c,evs,obj2))
        for arm,(p,v,cf) in arms.items():
            rec={'case_id':c['case_id'],'wallet':c['wallet'],'cutoff':c['cutoff'],'split':c['split'],'arm':arm,'gold_new':int(c.get('label_any_new_cp_7d',0)),'gold_future_events':c.get('future_event_count'),'abstain':bool(p.get('abstain')),'prediction':p.get('prediction'),'claim_type':p.get('claim_type'),'rule':json.dumps(p.get('rule'),ensure_ascii=False),'witness_ids':json.dumps(p.get('witness_ids',[])),'parse_valid':p.get('parse_valid',True),'verified':v['verified'],'semantic_alignment':v['semantic_alignment'],'witness_valid':v['witness_valid'],'executor_status':v['executor']['status'],'certificate':json.dumps(v.get('certificate'),ensure_ascii=False),'revision':cf.get('revision'),'revision_eligible':cf.get('eligible')}
            rows.append(rec); counters[(arm,'n')]+=1; counters[(arm,'abstain')]+=int(rec['abstain']); counters[(arm,'verified')]+=int(rec['verified'])
    pd.DataFrame(rows).to_csv(out/'dev_smoke_results.csv',index=False)
    (out/'raw_responses.jsonl').write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in raw)+'\n')
    summary={'version':VERSION,'generated_utc':datetime.now(timezone.utc).isoformat(),'sample_n':len(dev),'split':'dev','thresholds_train_only':thresholds,'arms':{},'input_hashes':{'cases.jsonl':stable_hash(cp),'raw_events.jsonl':stable_hash(rp)},'model':MODEL,'base_url':BASE,'seed':20260928,'paid_queries':0,'new_network_requests':len(raw)}
    df=pd.DataFrame(rows)
    for arm,g in df.groupby('arm'):
        fired=g[~g.abstain]; summary['arms'][arm]={'n':len(g),'abstention':int(g.abstain.sum()),'all_sample_verified_non_abstaining_coverage':float(((~g.abstain)&g.verified).sum()/len(g)),'conditional_verification':float(fired.verified.mean()) if len(fired) else None,'semantic_alignment_all':float(g.semantic_alignment.mean()),'revision_counts':g.revision.value_counts(dropna=False).to_dict(),'prediction_accuracy_when_fired':float((fired.prediction==fired.gold_new.map({0:'repeat',1:'new'})).mean()) if len(fired) else None}
    summary['audit']={'cases_total':len(cases),'audit_bad_pre_events':int(pd.DataFrame(audit).bad_pre_events.sum()),'future_evidence_id_matches':int(pd.DataFrame(audit).raw_hashes_in_future.sum()),'split_counts':Counter(c['split'] for c in cases)}
    summary['raw_sha256']=stable_hash(out/'raw_responses.jsonl')
    (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str)+'\n')
    (out/'README.md').write_text('# Temporal wallet hypotheses v1\n\nThis is a dev-only smoke run. Certificates are deterministic executor outputs, not LLM claims. August/test data remain untouched.\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2,default=str))
if __name__=='__main__': main()
