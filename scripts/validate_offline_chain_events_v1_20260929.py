#!/usr/bin/env python3
"""Check downloaded EX-Graph monthly Parquet against the export manifest."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
import pyarrow.parquet as pq

ROOT=Path('/storage/gaoym/ex-graph-microtransaction-analysis')
EXPECTED_FULL_ROWS=11_836_196

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['pilot','full'],required=True)
    args=ap.parse_args()
    out=ROOT/'artifacts'/f'offline_chain_events_v1_20260929_{args.mode}'
    manifest=json.loads((out/'manifest.json').read_text())
    stats=Counter(); months=[]; issues=[]
    for month,rec in sorted(manifest['months'].items()):
        if rec.get('status')!='complete':
            issues.append(f'{month}: incomplete in manifest'); continue
        path=out/f'{month}.parquet'
        if not path.exists(): issues.append(f'{month}: missing Parquet'); continue
        actual_sha=sha256(path)
        if actual_sha!=rec['sha256']: issues.append(f'{month}: SHA-256 mismatch')
        pf=pq.ParquetFile(path)
        if pf.metadata.num_rows!=rec['rows']: issues.append(f'{month}: row count mismatch')
        mstats=Counter()
        cols=['target_address','counterparty_address','direction','event_family',
              'block_timestamp','block_number','transaction_index','from_address','to_address',
              'receipt_status']
        for batch in pf.iter_batches(batch_size=100_000,columns=cols):
            d=batch.to_pydict()
            for i in range(len(d['event_family'])):
                fam=d['event_family'][i]; direction=d['direction'][i]
                ts=d['block_timestamp'][i]
                mstats['rows']+=1; mstats[f'family_{fam}']+=1
                if ts is None or ts.strftime('%Y-%m')!=month: mstats['bad_month']+=1
                if d['block_number'][i] is None or d['transaction_index'][i] is None:
                    mstats['missing_canonical_order']+=1
                if fam=='external_tx':
                    status=d['receipt_status'][i]
                    mstats[f'receipt_status_{status}']+=1
                    target=d['target_address'][i]; frm=d['from_address'][i]
                    to=d['to_address'][i]; cp=d['counterparty_address'][i]
                    if direction=='outgoing' and (target!=frm or cp!=to):
                        mstats['bad_outgoing_roles']+=1
                    if direction=='incoming' and (target!=to or cp!=frm):
                        mstats['bad_incoming_roles']+=1
                    if direction=='self' and target!=frm:
                        mstats['bad_self_roles']+=1
        for k,v in mstats.items(): stats[k]+=v
        months.append({'month':month,'rows':mstats['rows'],'bytes':path.stat().st_size,
                       'sha256':actual_sha,'stats':dict(mstats)})
        if mstats['rows']!=rec['rows']: issues.append(f'{month}: iterated count mismatch')
        for k in ['bad_month','missing_canonical_order','bad_outgoing_roles','bad_incoming_roles','bad_self_roles']:
            if mstats[k]: issues.append(f'{month}: {k}={mstats[k]}')
        if mstats['receipt_status_None']:
            issues.append(f'{month}: missing external receipt statuses={mstats["receipt_status_None"]}')
    if args.mode=='full' and stats['rows']!=EXPECTED_FULL_ROWS:
        issues.append(f'full total row count {stats["rows"]} != {EXPECTED_FULL_ROWS}')
    report={'mode':args.mode,'checked_utc':datetime.now(timezone.utc).isoformat(),
            'status':'PASS' if not issues else 'FAIL','months':months,
            'total':dict(stats),'issues':issues}
    (out/'validation.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'months':len(months),'rows':stats['rows'],
                      'failed_external_rows':stats['receipt_status_0'],'issues':issues}),flush=True)
    if issues: raise SystemExit(1)

if __name__=='__main__': main()
