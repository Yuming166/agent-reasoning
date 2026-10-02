#!/usr/bin/env python3
"""Offline v1 label, temporal, and candidate-support audit for pure-chain task.
No network access, model training, or mutation of source artifacts.
"""
from __future__ import annotations
import csv, hashlib, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927/raw_events.jsonl'
CASES=ROOT/'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl'
OUT=ROOT/'artifacts/pure_chain_next_recipient_v1_20260929_run02'
CUTS=['2022-06-01','2022-07-01','2022-08-01']
KS=[5,50,500,2000]

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dumpcsv(path,rows,fields=None):
 if fields is None: fields=list(rows[0]) if rows else []
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def addr(v):
 if v is None:return None
 s=str(v).strip().lower()
 return s if s and s not in {'none','nan',''} else None
def main():
 if OUT.exists(): raise SystemExit(f'refusing to overwrite {OUT}')
 OUT.mkdir(parents=True)
 events=[]
 with SRC.open() as f:
  for i,line in enumerate(f):
   if not line.strip():continue
   x=json.loads(line); x['_row_id']=i
   x['_ts']=pd.Timestamp(x['block_timestamp'])
   x['_wallet']=addr(x.get('target_address'));x['_to']=addr(x.get('counterparty_address'))
   x['_family']=str(x.get('event_family'))
   x['_out']=str(x.get('direction'))=='outgoing'
   x['_qual']=x['_family']=='external_tx' and x['_out'] and x['_to'] is not None
   try:x['_zero']=x.get('value_lossless') is not None and float(x['value_lossless'])==0
   except (ValueError,TypeError):x['_zero']=None
   events.append(x)
 cases=[]
 with CASES.open() as f:
  for l in f:
   if l.strip():cases.append(json.loads(l))
 wallets=sorted({addr(x.get('target_address')) for x in events if x.get('_wallet')})
 by_wallet=defaultdict(list);all_qual=[]
 for x in events:
  if x['_wallet']:by_wallet[x['_wallet']].append(x)
  if x['_qual']:all_qual.append(x)
 for w in by_wallet:by_wallet[w].sort(key=lambda x:(x['_ts'],int(x.get('target_sequence_index') or 0),str(x.get('transaction_hash') or '')))
 instances=[]; labels=[]; candidate_rows=[]; eval_rows=[]
 cutoff_aud=[]
 for cutstr in CUTS:
  cut=pd.Timestamp(cutstr,tz='UTC');end=cut+pd.Timedelta(days=7)
  panel=[x for x in all_qual if cut>x['_ts'] or x['_ts']<end] # only used to build each strict historical library below
  hist_global=[x for x in all_qual if x['_ts']<cut]
  gcount=Counter(x['_to'] for x in hist_global)
  global_rank=sorted(gcount,key=lambda a:(-gcount[a],a))
  library=set(gcount)
  case_cut=[c for c in cases if c.get('cutoff')==cutstr]
  for c in case_cut:
   w=addr(c.get('wallet')); evs=by_wallet.get(w,[])
   hist=[x for x in evs if x['_ts']<cut]
   fut=[x for x in evs if cut<=x['_ts']<end and x['_qual']]
   # This ordering is only a disclosed proxy: canonical block/tx indices were
   # dropped from raw_events; timestamp + target sequence index is not a proof
   # of chain order when timestamps collide.
   fut.sort(key=lambda x:(x['_ts'],int(x.get('target_sequence_index') or 0),str(x.get('transaction_hash') or '')))
   hist_targets=[x for x in hist if x['_qual']]
   wallet_seen={x['_to'] for x in hist_targets}
   old_global=set(gcount)
   active=bool(fut);first=fut[0] if fut else None
   target=first['_to'] if first else None
   old_wallet=bool(target in wallet_seen) if target else None
   globally_seen=bool(target in old_global) if target else None
   zero=first['_zero'] if first else None
   # Within-wallet recency and frequency candidate order.
   recent=[]
   for x in reversed(hist_targets):
    if x['_to'] not in recent:recent.append(x['_to'])
   wc=Counter(x['_to'] for x in hist_targets)
   freq=sorted(wc,key=lambda a:(-wc[a],a))
   # Candidate availability uses the full cutoff-visible historical destination library.
   rank=None
   if target is not None and target in global_rank:rank=global_rank.index(target)+1
   rec={
    'case_id':c['case_id'],'wallet':w,'cutoff':cutstr,'split_existing':c.get('split'),
    'history_event_rows':sum(x['_ts']<cut for x in evs),'history_qualifying_outgoing_external':len(hist_targets),
    'future_window_end_exclusive_utc':end.isoformat(),'future_qualifying_outgoing_external_count':len(fut),
    'active_label':int(active),'next_target_address':target,'next_target_old_for_wallet':old_wallet,
    'next_target_globally_seen_pre_cutoff':globally_seen,'next_target_zero_value':zero,
    'next_target_value_lossless':first.get('value_lossless') if first else None,
    'next_target_order_timestamp_utc':first['_ts'].isoformat() if first else None,
    'next_target_tx_hash':first.get('transaction_hash') if first else None,
    'next_target_sequence_index_proxy':first.get('target_sequence_index') if first else None,
    'global_library_size_pre_cutoff':len(library),'global_popularity_rank':rank,
    'wallet_history_candidate_count':len(wc),'missing_destination_future_external_rows':sum(1 for x in evs if cut<=x['_ts']<end and x['_family']=='external_tx' and x['_out'] and x['_to'] is None),
    'zero_value_future_qualifying_count':sum(1 for x in fut if x['_zero'] is True),
    'nonzero_value_future_qualifying_count':sum(1 for x in fut if x['_zero'] is False),
   }
   # Compare the old prototype labels only as a diagnostic.
   rec['prototype_label_any_new_cp_7d']=c.get('label_any_new_cp_7d')
   rec['prototype_label_disagrees']=int(rec['active_label'] != c.get('label_any_new_cp_7d'))
   labels.append(rec)
   # Candidate sets; all constructed exclusively from strict pre-cutoff rows.
   candsets={
    'wallet_recent':recent,
    'wallet_frequency':freq,
    'global_popular':global_rank,
    'historical_library_global_frequency':global_rank,
   }
   for name,ordered in candsets.items():
    for k in KS:
     cand=ordered[:k]
     eval_rows.append({'case_id':c['case_id'],'wallet':w,'cutoff':cutstr,'strategy':name,'k':k,'active':int(active),'target_address':target,'target_in_pool':int(target in set(ordered)) if active and target else 0,'hit_at_k':int(active and target in set(cand)),'candidate_count':len(cand),'pool_size':len(set(ordered))})
   for rankpos,a in enumerate(global_rank,1):
    if rankpos<=2000: candidate_rows.append({'cutoff':cutstr,'rank':rankpos,'candidate_address':a,'pre_cutoff_global_tx_count':gcount[a]})
   instances.append(rec)
 # summaries retain all active cases as denominator, including out-of-pool targets
 edf=pd.DataFrame(eval_rows); summaries=[]
 for (cut,strat,k),g in edf.groupby(['cutoff','strategy','k'],sort=True):
  active=g[g.active==1]; summaries.append({'cutoff':cut,'strategy':strat,'k':int(k),'all_instances':len(g),'active_denominator':len(active),'active_targets_in_candidate_pool':int(active.target_in_pool.sum()),'candidate_pool_coverage':float(active.target_in_pool.mean()) if len(active) else None,'hits':int(active.hit_at_k.sum()),'recall_at_k_all_active':float(active.hit_at_k.mean()) if len(active) else None})
 # stratify outcomes for the available candidate protocols by old/new, global visibility, zero/value category.
 strat=[]
 for (cut,stratname,k,oldflag,globalflag,zeroflag),g in edf.merge(pd.DataFrame(labels)[['case_id','next_target_old_for_wallet','next_target_globally_seen_pre_cutoff','next_target_zero_value']],on='case_id',how='left').groupby(['cutoff','strategy','k','next_target_old_for_wallet','next_target_globally_seen_pre_cutoff','next_target_zero_value'],dropna=False,sort=True):
  a=g[g.active==1]
  strat.append({'cutoff':cut,'strategy':stratname,'k':int(k),'old_for_wallet':oldflag,'globally_seen':globalflag,'zero_value':zeroflag,'active_denominator':len(a),'hits':int(a.hit_at_k.sum()),'recall_at_k':float(a.hit_at_k.mean()) if len(a) else None})
 dumpcsv(OUT/'wallet_cutoff_labels.csv',labels)
 dumpcsv(OUT/'candidate_recall_by_cutoff.csv',summaries)
 dumpcsv(OUT/'candidate_recall_stratified.csv',strat)
 dumpcsv(OUT/'historical_candidate_library_top2000.csv',candidate_rows)
 # Data-quality diagnostics by cutoff and aggregate.
 for cutstr in CUTS:
  cut=pd.Timestamp(cutstr,tz='UTC');end=cut+pd.Timedelta(days=7)
  ext=[x for x in events if x['_family']=='external_tx' and cut<=x['_ts']<end]
  extout=[x for x in ext if x['_out']]
  cutoff_aud.append({'cutoff':cutstr,'window_end_exclusive':end.isoformat(),'external_rows_in_window':len(ext),'outgoing_external_rows':len(extout),'qualifying_nonnull_destination_rows':sum(x['_to'] is not None for x in extout),'missing_destination_outgoing_rows':sum(x['_to'] is None for x in extout),'zero_value_outgoing_rows':sum(x['_zero'] is True for x in extout),'nonzero_value_outgoing_rows':sum(x['_zero'] is False for x in extout),'events_before_cutoff_included_in_future':sum(x['_ts']<cut for x in ext),'events_at_cutoff':sum(x['_ts']==cut for x in ext),'events_at_window_end_excluded':sum(x['_ts']==end for x in ext)})
 dumpcsv(OUT/'cutoff_boundary_audit.csv',cutoff_aud)
 # duplicates audit by family/hash/target; expected multiplicity across event families is allowed.
 dup=Counter((x['_wallet'],x.get('transaction_hash'),x['_family']) for x in events)
 dups=[{'wallet':k[0],'transaction_hash':k[1],'event_family':k[2],'rows':v} for k,v in dup.items() if v>1]
 dumpcsv(OUT/'duplicate_event_keys.csv',dups,['wallet','transaction_hash','event_family','rows'])
 # metadata and unresolved requirements
 alltimes=[x['_ts'] for x in events]
 manifest={'version':'pure_chain_next_recipient_v1_20260929','generated_utc':datetime.now(timezone.utc).isoformat(),'status':'offline_audit_complete_with_source_field_gaps','network_calls':0,'model_training':False,'new_test_touched':False,'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [SRC,CASES]},'source_event_rows':len(events),'source_wallets':len(wallets),'source_time_min_utc':min(alltimes).isoformat(),'source_time_max_utc':max(alltimes).isoformat(),'source_fields':sorted(set().union(*(x.keys() for x in events))-{k for k in []}),'missing_required_fields':['block_number','transaction_index','from_address','to_address','transaction_receipt_status','transaction_error','contract_code_metadata'],'ordering_used_for_offline_proxy':['block_timestamp','target_sequence_index','transaction_hash'],'canonical_ordering_available':False,'failure_status_available':False,'contract_call_classification_available':False,'cutoffs':CUTS,'cutoff_rows':len(labels),'active_instances_by_cutoff':{c:sum(r['cutoff']==c and r['active_label']==1 for r in labels) for c in CUTS},'all_active_retained_in_recall_denominator':True,'duplicate_wallet_hash_family_keys':len(dups),'missing_destination_handling':'counted and excluded from active label','zero_value_handling':'included; reported as zero-value, not inferred contract call','interpretation':'Exploratory offline audit only; August is not blind; no predictive-gain claim.'}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
 # Summary report
 active=pd.DataFrame(labels).groupby('cutoff').agg(instances=('case_id','size'),active=('active_label','sum'),label_disagreements=('prototype_label_disagrees','sum'),zero_value_active=('next_target_zero_value',lambda s:0)).reset_index()
 text=['# Pure-chain next-recipient offline audit v1','',f"Generated {manifest['generated_utc']}. No network calls or model training.",'','## Recomputed labels and candidate coverage','', 'All active instances remain in each Recall@K denominator, even when the target is outside a historical candidate pool. See `candidate_recall_by_cutoff.csv` and `candidate_recall_stratified.csv`.','', '## Cutoff rows','']
 for r in cutoff_aud:text.append(f"- {r['cutoff']}: {sum(x['cutoff']==r['cutoff'] for x in labels)} instances; {manifest['active_instances_by_cutoff'][r['cutoff']]} active; {r['missing_destination_outgoing_rows']} outgoing external rows missing destination; {r['zero_value_outgoing_rows']} zero-value outgoing rows.")
 text+=['','## Important source gaps','', '- Canonical `(block_number, transaction_index)` ordering is unavailable in this event export; next target is only a timestamp/sequence-index proxy.', '- Receipt success/failure status is unavailable, so failed transactions cannot be excluded or separately analyzed.', '- Zero-value rows are not proven contract calls; contract-code metadata is unavailable.', '- The event panel is left-censored at 2022-03-01; historical visibility means visible in this panel only.', '- Existing June/July/August cutoffs are exploratory; August is not a blind test.', '- This is an offline data/candidate audit only. It does not establish model performance or prediction gain.', '', '## Promotion gate','', 'Before model experiments, materialize source rows with block number, transaction index, raw endpoints, and receipt status; verify the SQL source window and failure semantics; then freeze an untouched later test period. The precise query plan is recorded in `required_data_query_dry_run.md`; no query was run.','']
 (OUT/'REPORT.md').write_text('\n'.join(text))
 (OUT/'required_data_query_dry_run.md').write_text('''# Required source-data query plan (dry-run only; not executed)\n\nPurpose: rebuild the already authorized March 1–September 1, 2022 target-touching event panel with fields lost by the current compact JSONL. Do not run until an explicit cost-reviewed authorization.\n\n1. Read only existing materialized source tables for external transactions, token transfers, and internal traces; do not create tables or export full raw payloads.\n2. Select target wallet, normalized from/to endpoints, event family, UTC block timestamp, block number, transaction index, transaction hash, event index/trace address, value, receipt/error status, token contract, and the target-role direction.\n3. Apply partition filters to `[2022-03-01, 2022-09-01)` and target-address filtering; dry-run to record estimated bytes before any execution.\n4. Validate success/failure semantics against source schema; determine whether failed native transactions are present and whether zero-value rows have destination/code evidence.\n5. Export only a bounded wallet-cutoff label/candidate aggregate, not the full event table, if cost permits.\n6. Audit equal timestamps/order ties, cutoff inclusion, duplicate transaction/family rows, null destinations, and complete seven-day label windows.\n\nNo SQL job, BigQuery query, or network request was issued during v1.\n''')
 print(json.dumps({'output':str(OUT),'instances':len(labels),'active':sum(r['active_label'] for r in labels),'duplicates':len(dups),'status':manifest['status']},indent=2))
if __name__=='__main__':main()
