#!/usr/bin/env python3
from __future__ import annotations
import csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from run_google_coverage_validation import BigQueryClient
from bq_openworld import job_summary
PROJECT='ictdata-507912'; TABLE=f'`{PROJECT}.exgraph.target_event_sequences_20220301_20220901`'; LABEL=f'`{PROJECT}.exgraph.openworld_wash_labels_v1`'
SQL=f'''SELECT l.tx_hash,l.nft_name,l.token_id,l.from_addr,l.to_addr,MIN(s.block_timestamp) AS first_timestamp,MAX(s.block_timestamp) AS last_timestamp,COUNT(*) AS sequence_rows,COUNT(DISTINCT s.target_exgraph_node_id) AS target_nodes,ARRAY_AGG(DISTINCT s.event_family ORDER BY s.event_family) AS event_families FROM {LABEL} l JOIN {TABLE} s ON LOWER(s.transaction_hash)=LOWER(l.tx_hash) WHERE s.block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00') AND s.block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00') GROUP BY l.tx_hash,l.nft_name,l.token_id,l.from_addr,l.to_addr ORDER BY first_timestamp,tx_hash'''
def rows(r):
 out=[]; cols=[f['name'] for f in r.get('schema',{}).get('fields',[])]
 for row in r.get('rows',[]):
  vals=[]
  for f,x in zip(r['schema']['fields'],row['f']):
   if f.get('mode')=='REPEATED': vals.append('|'.join(y.get('v','') for y in x.get('v',[])))
   else: vals.append(x.get('v'))
  out.append(dict(zip(cols,vals)))
 return out
client=BigQueryClient(PROJECT,'/storage/gaoym/tools/google-cloud-sdk/bin/gcloud')
dry=client.query(SQL,dry_run=True,max_bytes=20_000_000_000); actual=client.query(SQL,dry_run=False,max_bytes=20_000_000_000)
out=Path(__file__).resolve().parents[1]/'results'/'label_matches_compact.csv'; rs=rows(actual)
with out.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rs[0]) if rs else ['tx_hash']); w.writeheader(); w.writerows(rs)
meta={'experiment_id':'OW-001','dry_run':job_summary(dry),'actual':job_summary(actual),'rows':len(rs),'csv':str(out)}
(Path(__file__).resolve().parents[1]/'results'/'label_matches_compact_manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta,indent=2)); print('months',sorted({x['first_timestamp'][:7] for x in rs if x['first_timestamp']}))
