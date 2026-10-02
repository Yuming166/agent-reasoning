#!/usr/bin/env python3
"""Bounded extract from the already materialized 2022 target event sequence table."""
import argparse, hashlib, json, os
from pathlib import Path
import pandas as pd
from google.cloud import bigquery

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
OUT=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927'
OUT.mkdir(parents=True,exist_ok=True)
MAX_BYTES=6_000_000_000
SOURCE='ictdata-507912.exgraph.target_event_sequences_20220301_20220901'
SQL=f'''SELECT target_address, counterparty_address, direction, event_family,
block_timestamp, transaction_hash, event_index, target_sequence_index,
value_lossless, quantity, token_contract_address
FROM `{SOURCE}`
WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
AND block_timestamp < TIMESTAMP('2022-08-09 00:00:00+00')
AND target_address IN UNNEST(@wallets)
ORDER BY target_address, block_timestamp, target_sequence_index'''

ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
panel=pd.read_parquet(ROOT/'research/phase2/dynamic_influence_dataset.parquet')
panel['snapshot_date']=pd.to_datetime(panel.snapshot_date,utc=True)
june=panel[panel.snapshot_date.eq(pd.Timestamp('2022-06-01',tz='UTC'))].copy()
june=june[june.evt_cnt_90d.between(10,300)].drop_duplicates('target_address')
june['q']=pd.qcut(june.evt_cnt_90d.rank(method='first'),4,labels=False)
selected=pd.concat([g.sample(n=min(60,len(g)),random_state=20260927) for _,g in june.groupby('q')])
wallets=sorted(set(selected.target_address.str.lower()))
assert len(wallets)==240, len(wallets)
selected[['target_address','evt_cnt_90d','q']].to_csv(OUT/'frozen_wallets.csv',index=False)
(OUT/'query.sql').write_text(SQL+'\n')
client=bigquery.Client(project='ictdata-507912')
params=[bigquery.ArrayQueryParameter('wallets','STRING',wallets)]
dry_cfg=bigquery.QueryJobConfig(query_parameters=params,dry_run=True,use_query_cache=False,maximum_bytes_billed=MAX_BYTES)
dry=client.query(SQL,job_config=dry_cfg,location='US')
meta={'source':SOURCE,'wallet_count':len(wallets),'selection':'240 wallets stratified on June 1 as-of 90d event count, 10-300 events; no future fields used.',
      'window':['2022-03-01','2022-08-09'],'dry_run_bytes_processed':int(dry.total_bytes_processed),
      'max_bytes_billed':MAX_BYTES,'executed':False}
(OUT/'extract_manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
print('DRY_RUN',json.dumps(meta))
if not args.execute:raise SystemExit(0)
if dry.total_bytes_processed>MAX_BYTES:raise SystemExit('dry run exceeds byte cap')
run_cfg=bigquery.QueryJobConfig(query_parameters=params,maximum_bytes_billed=MAX_BYTES,use_query_cache=True)
job=client.query(SQL,job_config=run_cfg,location='US')
output=OUT/'raw_events.jsonl'
n=0;hasher=hashlib.sha256()
with output.open('wb') as f:
    for row in job.result(page_size=10000):
        obj=dict(row.items())
        if obj['block_timestamp'] is not None:obj['block_timestamp']=obj['block_timestamp'].isoformat()
        for k in ['value_lossless','quantity']:
            if obj.get(k) is not None:obj[k]=str(obj[k])
        line=(json.dumps(obj,ensure_ascii=False,sort_keys=True)+'\n').encode()
        f.write(line);hasher.update(line);n+=1
meta.update({'executed':True,'job_id':job.job_id,'rows':n,'sha256':hasher.hexdigest(),
             'total_bytes_processed':int(job.total_bytes_processed or 0),
             'total_bytes_billed':int(job.total_bytes_billed or 0),'cache_hit':bool(job.cache_hit)})
(OUT/'extract_manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
print('COMPLETE',json.dumps(meta))
