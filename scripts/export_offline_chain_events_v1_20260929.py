#!/usr/bin/env python3
"""Export the already-materialized EX-Graph event panel to monthly local Parquet.

Each BigQuery query is dry-run first and guarded by maximum_bytes_billed.
A month is written to a temporary file and atomically renamed only after
all rows are received. Completed months are never silently overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from google.cloud import bigquery
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SOURCE = 'ictdata-507912.exgraph.target_event_sequences_20220301_20220901'
RECEIPTS = 'bigquery-public-data.crypto_ethereum.transactions'
MONTHS = [
    ('2022-03-01','2022-04-01'), ('2022-04-01','2022-05-01'),
    ('2022-05-01','2022-06-01'), ('2022-06-01','2022-07-01'),
    ('2022-07-01','2022-08-01'), ('2022-08-01','2022-09-01'),
]
CAP_BYTES = 10_000_000_000
TOTAL_DRY_RUN_CAP_BYTES = 30_000_000_000
SCHEMA = pa.schema([
    pa.field('target_address', pa.string()),
    pa.field('counterparty_address', pa.string()),
    pa.field('direction', pa.string()),
    pa.field('event_family', pa.string()),
    pa.field('block_timestamp', pa.timestamp('us', tz='UTC')),
    pa.field('block_number', pa.int64()),
    pa.field('transaction_index', pa.int64()),
    pa.field('transaction_hash', pa.string()),
    pa.field('event_index', pa.int64()),
    pa.field('target_sequence_index', pa.int64()),
    pa.field('from_address', pa.string()),
    pa.field('to_address', pa.string()),
    pa.field('value_lossless', pa.string()),
    pa.field('quantity', pa.string()),
    pa.field('token_contract_address', pa.string()),
    pa.field('trace_address_json', pa.string()),
    pa.field('error', pa.string()),
    pa.field('receipt_status', pa.int64()),
    pa.field('receipt_contract_address', pa.string()),
])


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sql_for(start: str, end: str, pilot: bool) -> str:
    wallet_filter = 'AND e.target_address IN UNNEST(@wallets)' if pilot else ''
    return f'''SELECT
 e.target_address, e.counterparty_address, e.direction, e.event_family,
 e.block_timestamp, e.block_number, e.transaction_index, e.transaction_hash,
 e.event_index, e.target_sequence_index, e.from_address, e.to_address,
 e.value_lossless, e.quantity, e.token_contract_address,
 TO_JSON_STRING(e.trace_address) AS trace_address_json, e.error,
 t.receipt_status, t.receipt_contract_address
FROM `{SOURCE}` AS e
LEFT JOIN `{RECEIPTS}` AS t
 ON e.event_family = 'external_tx'
 AND t.hash = e.transaction_hash
 AND t.block_timestamp >= TIMESTAMP('{start}')
 AND t.block_timestamp < TIMESTAMP('{end}')
WHERE e.block_timestamp >= TIMESTAMP('{start}')
 AND e.block_timestamp < TIMESTAMP('{end}')
 {wallet_filter}
'''


def flush(writer: pq.ParquetWriter, batch: list[dict]) -> None:
    if batch:
        writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA), row_group_size=50_000)
        batch.clear()


def export_one(client: bigquery.Client, out: Path, start: str, end: str,
               wallets: list[str] | None, execute: bool) -> dict:
    month = start[:7]
    sql = sql_for(start,end,wallets is not None)
    (out/f'{month}.sql').write_text(sql)
    params = [bigquery.ArrayQueryParameter('wallets','STRING',wallets)] if wallets is not None else []
    cfg = bigquery.QueryJobConfig(query_parameters=params,maximum_bytes_billed=CAP_BYTES,
                                   use_query_cache=False,dry_run=True)
    dry = client.query(sql,job_config=cfg,location='US')
    estimated=int(dry.total_bytes_processed)
    if estimated > CAP_BYTES:
        raise RuntimeError(f'{month}: dry run {estimated} exceeds cap {CAP_BYTES}')
    rec={'month':month,'start':start,'end_exclusive':end,'dry_run_bytes':estimated,
         'maximum_bytes_billed':CAP_BYTES,'status':'dry_run_only'}
    print(json.dumps(rec),flush=True)
    if not execute:
        return rec
    path=out/f'{month}.parquet'
    partial=out/f'{month}.parquet.partial'
    if path.exists():
        raise FileExistsError(f'{path} exists; refusing to overwrite')
    if partial.exists():
        partial.unlink()
    run_cfg=bigquery.QueryJobConfig(query_parameters=params,maximum_bytes_billed=CAP_BYTES,
                                    use_query_cache=True)
    job=client.query(sql,job_config=run_cfg,location='US')
    stats=Counter()
    batch=[]
    writer=None
    try:
        writer=pq.ParquetWriter(partial,SCHEMA,compression='zstd',use_dictionary=True)
        for row in job.result(page_size=10_000):
            obj=dict(row.items())
            batch.append(obj)
            stats['rows']+=1
            stats[f"family_{obj['event_family']}"]+=1
            if obj['event_family']=='external_tx':
                stats[f"receipt_status_{obj['receipt_status']}"]+=1
            if len(batch)>=50_000:
                flush(writer,batch)
                if stats['rows']%250_000==0:
                    print(json.dumps({'month':month,'rows_written':stats['rows']}),flush=True)
        flush(writer,batch)
        writer.close(); writer=None
        partial.rename(path)
    finally:
        if writer is not None: writer.close()
    rec.update({'status':'complete','job_id':job.job_id,'rows':stats['rows'],
                'stats':dict(stats),'actual_bytes_processed':int(job.total_bytes_processed or 0),
                'actual_bytes_billed':int(job.total_bytes_billed or 0),
                'cache_hit':bool(job.cache_hit),'output_bytes':path.stat().st_size,
                'sha256':sha256(path)})
    print(json.dumps(rec),flush=True)
    return rec


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=['pilot','full'],required=True)
    ap.add_argument('--execute',action='store_true')
    ap.add_argument('--months',nargs='*',default=None)
    args=ap.parse_args()
    out=ROOT/'artifacts'/f'offline_chain_events_v1_20260929_{args.mode}'
    out.mkdir(parents=True,exist_ok=True)
    wallets=None
    if args.mode=='pilot':
        with (ROOT/'artifacts/motif_hypothesis_eventlevel_20260927/frozen_wallets.csv').open() as f:
            wallets=sorted({r['target_address'].lower() for r in csv.DictReader(f)})
        assert len(wallets)==240
    selected=[(a,b) for a,b in MONTHS if args.months is None or a[:7] in args.months]
    if not selected: raise SystemExit('No selected months')
    client=bigquery.Client(project='ictdata-507912')
    if args.execute:
        preflight=[]
        for start,end in selected:
            params=[bigquery.ArrayQueryParameter('wallets','STRING',wallets)] if wallets is not None else []
            cfg=bigquery.QueryJobConfig(query_parameters=params,maximum_bytes_billed=CAP_BYTES,
                                        use_query_cache=False,dry_run=True)
            j=client.query(sql_for(start,end,wallets is not None),job_config=cfg,location='US')
            preflight.append((start[:7],int(j.total_bytes_processed)))
        total=sum(n for _,n in preflight)
        print(json.dumps({'preflight_months':preflight,'estimated_total_bytes':total,
                          'total_dry_run_cap_bytes':TOTAL_DRY_RUN_CAP_BYTES}),flush=True)
        if total>TOTAL_DRY_RUN_CAP_BYTES:
            raise RuntimeError('Total dry-run estimate exceeds authorized cap')
    manifest_path=out/'manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'version':'offline_chain_events_v1_20260929','mode':args.mode,
        'source':SOURCE,'receipt_source':RECEIPTS,
        'wallet_count':len(wallets) if wallets is not None else 'all_target_wallets',
        'script_sha256':sha256(Path(__file__)),'months':{},
        'created_utc':datetime.now(timezone.utc).isoformat(),
    }
    for start,end in selected:
        month=start[:7]
        if manifest['months'].get(month,{}).get('status')=='complete':
            print(json.dumps({'month':month,'status':'already_complete'}),flush=True)
            continue
        rec=export_one(client,out,start,end,wallets,args.execute)
        manifest['months'][month]=rec
        temp=manifest_path.with_suffix('.json.partial')
        temp.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        temp.replace(manifest_path)
    print(json.dumps({'output':str(out),'complete_months':sum(v['status']=='complete' for v in manifest['months'].values()),'selected_months':len(selected)}),flush=True)

if __name__=='__main__': main()
