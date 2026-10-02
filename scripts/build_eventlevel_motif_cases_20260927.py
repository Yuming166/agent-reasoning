#!/usr/bin/env python3
"""As-of wallet histories, complete observed 7-day windows and frozen numeric baseline."""
import json, math
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
OUT=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927'
raw=pd.read_json(OUT/'raw_events.jsonl',lines=True)
raw['block_timestamp']=pd.to_datetime(raw.block_timestamp,utc=True)
raw=raw.sort_values(['target_address','block_timestamp','target_sequence_index'])
selected=pd.read_csv(OUT/'frozen_wallets.csv')
qmap=dict(zip(selected.target_address.str.lower(),selected.q))
cutoffs=['2022-06-01','2022-07-01','2022-08-01']
rows=[]
for wallet,g in raw.groupby('target_address',sort=True):
    ev=[];aliases={}
    for r in g.itertuples(index=False):
        cp=str(r.counterparty_address).lower() if pd.notna(r.counterparty_address) else None
        if cp is not None and cp not in aliases: aliases[cp]='C'+str(len(aliases)+1)
        ev.append({'time':r.block_timestamp,'cp':cp,'cp_alias':aliases.get(cp),
                   'direction':str(r.direction),'family':str(r.event_family),
                   'tx_hash':str(r.transaction_hash),'event_index':None if pd.isna(r.event_index) else int(r.event_index),
                   'seq':int(r.target_sequence_index)})
    for date in cutoffs:
        cutoff=pd.Timestamp(date,tz='UTC'); end=cutoff+pd.Timedelta(days=7)
        hist=[e for e in ev if e['time']<cutoff]
        future=[e for e in ev if cutoff<=e['time']<end]
        prior30=[e for e in hist if e['time']>=cutoff-pd.Timedelta(days=30)]
        prior90=[e for e in hist if e['time']>=cutoff-pd.Timedelta(days=90)]
        prior7=[e for e in hist if e['time']>=cutoff-pd.Timedelta(days=7)]
        seen={e['cp'] for e in hist if e['cp'] is not None}
        before30={e['cp'] for e in hist if e['time']<cutoff-pd.Timedelta(days=30) and e['cp'] is not None}
        rolling_seen=set(before30);new30=0
        for e in prior30:
            if e['cp'] is not None and e['cp'] not in rolling_seen:new30+=1
            if e['cp'] is not None:rolling_seen.add(e['cp'])
        counts=Counter(e['cp'] for e in prior30 if e['cp'] is not None)
        ncp=sum(counts.values())
        entropy=-sum((v/ncp)*math.log(v/ncp) for v in counts.values()) if ncp else 0.
        dirs=defaultdict(set)
        for e in prior30:
            if e['cp'] is not None:dirs[e['cp']].add(e['direction'])
        features={
            'evt_7d':len(prior7),'evt_30d':len(prior30),'evt_90d':len(prior90),
            'active_days_30d':len({e['time'].date() for e in prior30}),
            'distinct_cp_30d':len(counts),'new_cp_rate_30d':new30/max(1,len(prior30)),
            'cp_entropy_30d':entropy,'top_cp_share_30d':max(counts.values())/ncp if ncp else 0.,
            'reciprocal_pairs_30d':sum({'incoming','outgoing'}<=v for v in dirs.values()),
            'out_share_30d':sum(e['direction']=='outgoing' for e in prior30)/max(1,len(prior30)),
            'token_share_30d':sum(e['family']=='token_transfer' for e in prior30)/max(1,len(prior30)),
            'trace_share_30d':sum(e['family']=='internal_trace' for e in prior30)/max(1,len(prior30)),
            'days_since_last_event':(cutoff-hist[-1]['time']).total_seconds()/86400 if hist else 90.,
        }
        evidence=[]
        for i,e in enumerate(hist[-12:],1):
            evidence.append({'evidence_id':'E'+str(i),'tx_hash':e['tx_hash'],'time':e['time'].isoformat(),
                             'counterparty':e['cp_alias'],'direction':e['direction'],
                             'family':e['family'],'event_index':e['event_index'],'sequence_index':e['seq']})
        novel={e['cp'] for e in future if e['cp'] is not None and e['cp'] not in seen}
        rows.append({'case_id':wallet+':'+date,'wallet':wallet,'activity_quartile':int(qmap[wallet]),
                     'cutoff':date,'split':{'2022-06-01':'train','2022-07-01':'dev','2022-08-01':'test'}[date],
                     'features':features,'evidence':evidence,'label_any_new_cp_7d':int(bool(novel)),
                     'future_event_count':len(future),'future_new_cp_count':len(novel),
                     'history_event_count':len(hist)})
flat=pd.DataFrame([{k:v for k,v in r.items() if k not in ['features','evidence']}|r['features'] for r in rows])
features=list(rows[0]['features'])
train=flat[flat.split=='train'];dev=flat[flat.split=='dev'];test=flat[flat.split=='test']
model=LogisticRegression(max_iter=2000,class_weight='balanced',random_state=20260927)
model.fit(train[features],train.label_any_new_cp_7d)
flat['numeric_prob']=model.predict_proba(flat[features])[:,1]
flat['numeric_pred']=(flat.numeric_prob>=.5).astype(int)
lookup=flat.set_index('case_id')[['numeric_prob','numeric_pred']].to_dict('index')
chosen=set(test.groupby('activity_quartile',group_keys=False).apply(lambda g:g.sample(n=min(20,len(g)),random_state=20260927),include_groups=False).case_id)
for r in rows:
    r.update({'numeric_prob':float(lookup[r['case_id']]['numeric_prob']),
              'numeric_pred':int(lookup[r['case_id']]['numeric_pred']),
              'llm_sample':r['case_id'] in chosen})
with (OUT/'cases.jsonl').open('w') as f:
    for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
flat.to_csv(OUT/'numeric_cases.csv',index=False)
metrics={}
for split,g in flat.groupby('split'):
    metrics[split]={'n':len(g),'prevalence':float(g.label_any_new_cp_7d.mean()),
                    'future_active_rate':float((g.future_event_count>0).mean()),
                    'numeric_accuracy':float(accuracy_score(g.label_any_new_cp_7d,g.numeric_pred)),
                    'numeric_balanced_accuracy':float(balanced_accuracy_score(g.label_any_new_cp_7d,g.numeric_pred)),
                    'numeric_f1_new':float(f1_score(g.label_any_new_cp_7d,g.numeric_pred,zero_division=0))}
summary={'source':str(OUT/'raw_events.jsonl'),'source_rows':len(raw),'wallets':raw.target_address.nunique(),
         'cases':len(rows),'cutoffs':cutoffs,'label':'Any observed new counterparty in next 7 days relative to all observed pre-cutoff events since 2022-03-01.',
         'source_boundary':'Materialized 2022 target-touching native, token and trace events; no unobserved-chain events; left-censored before 2022-03-01.',
         'sample_selection':'240 wallets frozen from 2022-06-01 as-of activity quartiles; 80 August cases, 20/quartile, selected without labels.',
         'features':features,'metrics':metrics,'llm_sample_n':len(chosen),
         'llm_sample_positive':int(sum(r['label_any_new_cp_7d'] for r in rows if r['llm_sample']))}
(OUT/'case_report.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(summary,indent=2,ensure_ascii=False))
