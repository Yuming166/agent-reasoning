#!/usr/bin/env python3
"""Observed-subgraph, event-level pilot. G3 is partial and historical."""
import json, zipfile
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
OUT=ROOT/'artifacts/motif_hypothesis_g3_20260927'
OUT.mkdir(parents=True,exist_ok=True)
ZIP=ROOT/'data/raw/ethereum_partial_transaction_dataset.zip'
NAME='Ethereum Partial Transaction Dataset/EthereumG3/LPsubG3_0.5_TransEdgelist.txt'
with zipfile.ZipFile(ZIP) as z, z.open(NAME) as f:
    raw=pd.read_csv(f,header=None,names=['src','dst','value','ts'])
raw['event_id']=['g3:'+str(i) for i in range(len(raw))]
by_wallet=defaultdict(list)
for row in raw.itertuples(index=False):
    by_wallet[int(row.src)].append((int(row.ts),int(row.dst),'out',float(row.value),row.event_id))
    if row.src!=row.dst:
        by_wallet[int(row.dst)].append((int(row.ts),int(row.src),'in',float(row.value),row.event_id))
for seq in by_wallet.values(): seq.sort(key=lambda x:(x[0],x[4]))
base_ts=int(pd.Timestamp('2015-12-01T00:00:00Z').timestamp())
eligible={w:sum(ev[0]<base_ts for ev in seq) for w,seq in by_wallet.items()}
eligible={w:n for w,n in eligible.items() if n>=10}
frame=pd.DataFrame([(w,n) for w,n in eligible.items()],columns=['wallet','pre_dec_events'])
frame['quartile']=pd.qcut(frame.pre_dec_events.rank(method='first'),4,labels=False)
wallets=[]
for _,g in frame.groupby('quartile'):
    wallets.extend(g.sample(n=min(60,len(g)),random_state=20260927).wallet.tolist())
wallets=sorted(wallets)
cutoffs=['2016-01-01','2016-02-01','2016-03-01','2016-04-01','2016-05-01']
rows=[]
for wallet in wallets:
    seq=by_wallet[wallet]
    for date in cutoffs:
        cutoff=int(pd.Timestamp(date,tz='UTC').timestamp())
        hist=[e for e in seq if e[0]<cutoff]
        if len(hist)<10: continue
        future=[e for e in seq if cutoff<=e[0]<cutoff+7*86400]
        seen={e[1] for e in hist}
        recent30=[e for e in hist if e[0]>=cutoff-30*86400]
        recent90=[e for e in hist if e[0]>=cutoff-90*86400]
        seen_before30={e[1] for e in hist if e[0]<cutoff-30*86400}
        new30=[]; seen_progress=set(seen_before30)
        for e in recent30:
            new30.append(e[1] not in seen_progress)
            seen_progress.add(e[1])
        cp=Counter(e[1] for e in recent30)
        directions=defaultdict(set)
        for e in recent30: directions[e[1]].add(e[2])
        feat={
            'evt_30d':len(recent30),'evt_90d':len(recent90),
            'distinct_cp_30d':len(cp),
            'new_cp_rate_30d':float(np.mean(new30)) if new30 else 0.,
            'top_cp_share_30d':max(cp.values())/len(recent30) if recent30 else 0.,
            'reciprocal_pairs_30d':sum(len(v)==2 for v in directions.values()),
            'out_share_30d':sum(e[2]=='out' for e in recent30)/len(recent30) if recent30 else 0.,
            'active_days_30d':len({e[0]//86400 for e in recent30}),
            'days_since_last_event':(cutoff-hist[-1][0])/86400,
        }
        top_cp=cp.most_common(1)[0][0] if cp else None
        evidence=[{'id':e[4], 'time':pd.Timestamp(e[0],unit='s',tz='UTC').isoformat(), 'direction':e[2], 'counterparty':e[1], 'value':round(e[3],6)} for e in hist[-12:]]
        rows.append({'case_id':f'g3:{wallet}:{date}','wallet':wallet,'cutoff':date,'features':feat,'evidence':evidence,
                     'label_any_new_7d':int(any(e[1] not in seen for e in future)),
                     'future_event_count':len(future),'future_new_cp_count':sum(e[1] not in seen for e in future),
                     'future_top_cp_count':sum(e[1]==top_cp for e in future) if top_cp is not None else 0,
                     'future_out_count':sum(e[2]=='out' for e in future),
                     'history_event_count':len(hist)})
features=list(rows[0]['features'])
d=pd.DataFrame([{**{k:r[k] for k in ['case_id','wallet','cutoff','label_any_new_7d','future_event_count','future_new_cp_count','future_top_cp_count','future_out_count','history_event_count']},**r['features']} for r in rows])
train=d[d.cutoff.isin(['2016-01-01','2016-02-01'])].copy()
dev=d[d.cutoff.eq('2016-03-01')].copy()
test=d[d.cutoff.isin(['2016-04-01','2016-05-01'])].copy()
model=LogisticRegression(max_iter=2000, class_weight='balanced',random_state=20260927)
model.fit(train[features],train.label_any_new_7d)
d['numeric_prob']=model.predict_proba(d[features])[:,1]
d['numeric_pred']=(d.numeric_prob>=0.5).astype(int)
train=d[d.cutoff.isin(['2016-01-01','2016-02-01'])].copy()
dev=d[d.cutoff.eq('2016-03-01')].copy()
test=d[d.cutoff.isin(['2016-04-01','2016-05-01'])].copy()
pred_lookup=d.set_index('case_id').numeric_pred.to_dict()
# Select without looking at test labels; fixed wallet/cutoff random sample.
chosen=set(test.sample(n=min(80,len(test)),random_state=20260927).case_id)
for r in rows:
    r['split']='train' if r['cutoff'] in ['2016-01-01','2016-02-01'] else 'dev' if r['cutoff']=='2016-03-01' else 'test'
    r['numeric_pred']=int(pred_lookup[r['case_id']])
    r['llm_sample']=r['case_id'] in chosen
with (OUT/'cases.jsonl').open('w') as f:
    for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
d.to_csv(OUT/'numeric_cases.csv',index=False)
summary={'source':'EthereumG3/LPsubG3_0.5_TransEdgelist.txt in existing public 2019 partial Ethereum transaction zip',
         'partial_graph_warning':'Only observed edges in the published partial ego subgraph; missing edges cannot be treated as non-events.',
         'date_range':['2015-07-30','2016-07-16'],'wallets':len(wallets),'cases':len(d),
         'train_n':len(train),'dev_n':len(dev),'test_n':len(test),'llm_sample_n':len(chosen),
         'features':features,'label':'Any observed new counterparty within next 7 days relative to all observed pre-cutoff edges.',
         'model':'class-weighted logistic regression trained on Jan-Feb, fixed threshold 0.5',
         'metrics':{split:{'n':len(x),'prevalence':float(x.label_any_new_7d.mean()),
                           'accuracy':float(accuracy_score(x.label_any_new_7d,x.numeric_pred)),
                           'balanced_accuracy':float(balanced_accuracy_score(x.label_any_new_7d,x.numeric_pred)),
                           'f1':float(f1_score(x.label_any_new_7d,x.numeric_pred,zero_division=0))}
                    for split,x in [('train',train),('dev',dev),('test',test)]},
         'selection':'240 wallets frozen using only events before 2015-12-01, 60 per pre-Dec activity quartile; 80 LLM test cases selected without labels.'}
(OUT/'dataset_report.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(summary,indent=2,ensure_ascii=False))
