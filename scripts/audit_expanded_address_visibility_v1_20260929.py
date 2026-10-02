#!/usr/bin/env python3
"""Audit next-target visibility in all pre-cutoff offline event address fields."""
from pathlib import Path
from collections import defaultdict
import json
import pandas as pd

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SOURCE=ROOT/'artifacts/offline_chain_events_v1_20260929_full'
OUT=ROOT/'artifacts/expanded_address_visibility_v1_20260929'
if OUT.exists(): raise SystemExit(f'refusing to overwrite {OUT}')
OUT.mkdir(parents=True)
cases=pd.read_csv(ROOT/'artifacts/fullpanel_candidate_coverage_v1_20260929/case_level.csv')
cases=cases[cases.policy.eq('attempted')]
cutoffs=sorted(cases.cutoff.unique())
wallets=set(cases.wallet.unique())
fields=['target_address','counterparty_address','from_address','to_address',
        'token_contract_address','receipt_contract_address']
global_sets={c:{k:set() for k in fields} for c in cutoffs}
wallet_sets={c:defaultdict(set) for c in cutoffs}
for path in sorted(SOURCE.glob('2022-??.parquet')):
 d=pd.read_parquet(path,columns=['block_timestamp']+fields)
 for cutoff in cutoffs:
  h=d[d.block_timestamp.lt(pd.Timestamp(cutoff,tz='UTC'))]
  if h.empty: continue
  for k in fields:
   global_sets[cutoff][k].update(h[k].dropna().unique().tolist())
  w=h[h.target_address.isin(wallets)]
  for wallet,g in w.groupby('target_address'):
   wallet_sets[cutoff][wallet].update(g.counterparty_address.dropna().unique().tolist())
 print(json.dumps({'month_loaded':path.stem,'rows':len(d)}),flush=True)
rows=[]
for _,r in cases.iterrows():
 if not r.active: continue
 c=r.cutoff; y=r.first_target; gs=global_sets[c]
 rec={'cutoff':c,'wallet':r.wallet,'target':y,
      'global_any_endpoint':any(y in gs[k] for k in ['target_address','counterparty_address','from_address','to_address']),
      'global_token_contract':y in gs['token_contract_address'],
      'global_created_contract':y in gs['receipt_contract_address'],
      'wallet_any_counterparty':y in wallet_sets[c].get(r.wallet,set()),
      'prior_external_destination':bool(r.seen_in_global_history),
      'old_external_for_wallet':bool(r.old_for_wallet)}
 rec['global_any_field']=rec['global_any_endpoint'] or rec['global_token_contract'] or rec['global_created_contract']
 rows.append(rec)
result=pd.DataFrame(rows)
result.to_csv(OUT/'active_case_visibility.csv',index=False)
summary=[]
for cutoff,g in result.groupby('cutoff'):
 x={'cutoff':cutoff,'active':len(g)}
 for col in result.columns[3:]: x[col+'_count']=int(g[col].sum())
 summary.append(x)
pd.DataFrame(summary).to_csv(OUT/'summary.csv',index=False)
(OUT/'manifest.json').write_text(json.dumps({'source':str(SOURCE),'status':'complete','note':'all address visibility is relative to EX-Graph target-touching panel and its left-censored March 2022 start'},indent=2)+'\n')
print(json.dumps(summary),flush=True)
