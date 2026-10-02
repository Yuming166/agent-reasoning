#!/usr/bin/env python3
"""As-of candidate retrieval audit on the complete offline EX-Graph event panel."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import csv, hashlib, json
import pandas as pd

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SOURCE=ROOT/'artifacts/offline_chain_events_v1_20260929_full'
OUT=ROOT/'artifacts/fullpanel_candidate_coverage_v1_20260929'
K_VALUES=(5,50,500,2000)
COLS=['target_address','counterparty_address','direction','event_family','block_timestamp',
      'block_number','transaction_index','transaction_hash','receipt_status']

def sha256(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def rank_recent(h):
 return h.sort_values(['block_timestamp','block_number','transaction_index','transaction_hash'],ascending=False).drop_duplicates('counterparty_address').counterparty_address.tolist()

def rank_frequency(h):
 c=h.counterparty_address.value_counts()
 return sorted(c.index.tolist(),key=lambda x:(-int(c[x]),x))

def main():
 if OUT.exists(): raise SystemExit(f'refusing to overwrite {OUT}')
 OUT.mkdir(parents=True)
 parts=[]
 for p in sorted(SOURCE.glob('2022-??.parquet')):
  d=pd.read_parquet(p,columns=COLS)
  d=d[(d.event_family=='external_tx')&(d.direction=='outgoing')&d.counterparty_address.notna()].copy()
  parts.append(d)
  print(json.dumps({'loaded_month':p.stem,'outgoing_external_rows':len(d)}),flush=True)
 ext=pd.concat(parts,ignore_index=True)
 ext.sort_values(['block_timestamp','block_number','transaction_index','transaction_hash'],inplace=True)
 cases=pd.read_csv(ROOT/'artifacts/pure_chain_next_recipient_v1_20260929_run02/wallet_cutoff_labels.csv',dtype={'wallet':str,'cutoff':str})
 rows=[]; summaries=[]
 for cutoff in sorted(cases.cutoff.unique()):
  t=pd.Timestamp(cutoff,tz='UTC'); end=t+pd.Timedelta(days=7)
  case_wallets=cases[cases.cutoff==cutoff].wallet.tolist()
  for policy in ('attempted','success_only'):
   relevant=ext if policy=='attempted' else ext[ext.receipt_status.eq(1)]
   hist=relevant[relevant.block_timestamp.lt(t)]
   fut=relevant[relevant.block_timestamp.ge(t)&relevant.block_timestamp.lt(end)&relevant.target_address.isin(case_wallets)]
   first=fut.drop_duplicates('target_address').set_index('target_address')
   global_freq=rank_frequency(hist)
   global_pool=set(global_freq)
   local_hist={w:g for w,g in hist[hist.target_address.isin(case_wallets)].groupby('target_address',sort=False)}
   global_top={k:set(global_freq[:k]) for k in K_VALUES}
   for w in case_wallets:
    h=local_hist.get(w)
    if h is None: h=hist.iloc[:0]
    recent=rank_recent(h); freq=rank_frequency(h)
    own_pool=set(recent)
    if w in first.index:
     y=first.loc[w,'counterparty_address']; status=int(first.loc[w,'receipt_status'])
     first_hash=first.loc[w,'transaction_hash']
    else:
     y=None; status=None; first_hash=None
    r={'wallet':w,'cutoff':cutoff,'policy':policy,'active':bool(y),'first_target':y,
       'first_tx_hash':first_hash,'first_receipt_status':status,
       'wallet_hist_candidate_count':len(own_pool),'global_hist_candidate_count':len(global_pool),
       'old_for_wallet':y in own_pool if y else None,
       'seen_in_global_history':y in global_pool if y else None}
    for k in K_VALUES:
     r[f'global_popular_hit_{k}']=bool(y in global_top[k]) if y else None
     r[f'wallet_recent_hit_{k}']=bool(y in set(recent[:k])) if y else None
     r[f'wallet_frequency_hit_{k}']=bool(y in set(freq[:k])) if y else None
     hybrid=list(dict.fromkeys(recent[:(k+1)//2]+global_freq[:k]))[:k]
     r[f'hybrid_hit_{k}']=bool(y in set(hybrid)) if y else None
    rows.append(r)
   active=[r for r in rows if r['cutoff']==cutoff and r['policy']==policy and r['active']]
   summary={'cutoff':cutoff,'policy':policy,'cases':len(case_wallets),'active':len(active),
            'global_pool_size':len(global_pool),'global_seen':sum(x['seen_in_global_history'] for x in active),
            'wallet_old':sum(x['old_for_wallet'] for x in active)}
   for name in ('global_popular','wallet_recent','wallet_frequency','hybrid'):
    for k in K_VALUES:
     summary[f'{name}_hits_{k}']=sum(x[f'{name}_hit_{k}'] for x in active)
   summaries.append(summary)
   print(json.dumps(summary),flush=True)
 fields=list(rows[0]);
 with (OUT/'case_level.csv').open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(rows)
 with (OUT/'summary.csv').open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(summaries[0]));wr.writeheader();wr.writerows(summaries)
 manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(SOURCE),
           'source_manifest_sha256':sha256(SOURCE/'manifest.json'),
           'rows_loaded_outgoing_external':len(ext),'cases':len(rows),
           'definition':'strict as-of history; canonical first outgoing external target; attempted and receipt_status=1 policies; no future targets injected into candidates',
           'status':'complete'}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'output':str(OUT),'status':'complete'}),flush=True)

if __name__=='__main__': main()
