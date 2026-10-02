#!/usr/bin/env python3
"""Leakage-corrected typed temporal retrieval pilot.

Candidate construction uses every wallet visible before each cutoff. Evaluation
cases are joined only after candidates are built; active-case membership is never
used to filter graph nodes, peers, or popular destinations.
"""
from __future__ import annotations
import csv, hashlib, json, math
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'artifacts/offline_chain_events_v1_20260929_full'
CASES=ROOT/'artifacts/fullpanel_candidate_coverage_v1_20260929/case_level.csv'
OUT=ROOT/'artifacts/hetero_temporal_retrieval_pilot_v3_20260929'
K=(5,50,500,2000)

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def main():
 if OUT.exists(): raise SystemExit(f'refusing to overwrite {OUT}')
 OUT.mkdir(parents=True)
 cases=pd.read_csv(CASES)
 active=cases[(cases.policy=='attempted') & (cases.active==True)].copy()
 cols=['target_address','counterparty_address','direction','event_family','block_timestamp','block_number','transaction_index','transaction_hash','token_contract_address','receipt_status']
 frames=[]
 for p in sorted(SRC.glob('2022-??.parquet')):
  x=pd.read_parquet(p,columns=cols)
  x.target_address=x.target_address.str.lower(); x.counterparty_address=x.counterparty_address.str.lower()
  x.block_timestamp=pd.to_datetime(x.block_timestamp,utc=True)
  x=x[x.counterparty_address.notna()].copy()
  frames.append(x)
 ev=pd.concat(frames,ignore_index=True)
 ev['family']=ev.event_family.fillna('unknown')
 ev['token']=ev.token_contract_address.fillna('').str.lower()
 # No filtering by active wallets occurs here.
 details=[]; summaries=[]
 for cutoff in sorted(active.cutoff.unique()):
  t=pd.Timestamp(cutoff,tz='UTC')
  h=ev[ev.block_timestamp<t].copy()
  ext=h[(h.direction=='outgoing')&(h.event_family=='external_tx')].copy()
  ext.sort_values(['block_timestamp','block_number','transaction_index','transaction_hash'],ascending=False,inplace=True)
  recent_by=defaultdict(list); freq=Counter(); global_users=defaultdict(set)
  for r in ext.itertuples():
   c=r.counterparty_address; w=r.target_address
   if c not in recent_by[w]: recent_by[w].append(c)
   freq[c]+=1; global_users[c].add(w)
  popular=sorted(freq,key=lambda c:(-freq[c],c))
  key_by_wallet=defaultdict(set); inv=defaultdict(set); latest={}
  for r in h.itertuples():
   k=(r.counterparty_address,r.family,r.token); w=r.target_address
   key_by_wallet[w].add(k); inv[k].add(w)
   pair=(w,k)
   if pair not in latest or r.block_timestamp>latest[pair]: latest[pair]=r.block_timestamp
  visible_wallets=set(key_by_wallet)|set(recent_by)
  def typed_graph(w):
   peer_score=Counter(); now=t
   for k in key_by_wallet.get(w,()):
    users=inv.get(k,())
    if len(users)<=1 or len(users)>200: continue
    hub_weight=math.log1p(len(visible_wallets)/len(users))
    age=max(0.0,(now-latest[(w,k)]).total_seconds()/86400.0)
    key_decay=math.exp(-age/90.0)
    for peer in users:
     if peer!=w: peer_score[peer]+=hub_weight*key_decay
   candidates=Counter()
   for peer,ps in peer_score.most_common(200):
    for rank,c in enumerate(recent_by.get(peer,[])[:100],1):
     if c!=w: candidates[c]+=ps/(rank**0.7)
   return sorted(candidates,key=lambda c:(-candidates[c],c)),len(peer_score)
  eval_rows=active[active.cutoff==cutoff]
  for row in eval_rows.itertuples(index=False):
   w=row.wallet.lower(); y=row.first_target.lower()
   graph,npeers=typed_graph(w); own=recent_by.get(w,[])
   mix=list(dict.fromkeys(own[:500]+graph[:1000]+popular[:500]+popular))[:2000]
   rec={'cutoff':cutoff,'wallet':w,'target':y,'n_typed_peers':npeers,'typed_graph_pool_size':len(graph),
        'old_for_wallet':bool(y in set(own)),'globally_seen':bool(y in global_users),
        'typed_mix_hit_2000':bool(y in set(mix))}
   for k in K:
    rec[f'typed_graph_hit_{k}']=bool(y in set(graph[:k]))
    rec[f'typed_mix_hit_{k}']=bool(y in set(mix[:k]))
   details.append(rec)
  d=[r for r in details if r['cutoff']==cutoff]
  summaries.append({'cutoff':cutoff,'active':len(d),'visible_wallets':len(visible_wallets),'global_pool_size':len(popular),
   **{f'typed_graph_hits_{k}':sum(r[f'typed_graph_hit_{k}'] for r in d) for k in K},
   **{f'typed_mix_hits_{k}':sum(r[f'typed_mix_hit_{k}'] for r in d) for k in K}})
  print(summaries[-1],flush=True)
 pd.DataFrame(details).to_csv(OUT/'case_level.csv',index=False)
 pd.DataFrame(summaries).to_csv(OUT/'summary.csv',index=False)
 manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'diagnostic_pilot_corrected','source_dir':str(SRC),'case_source':str(CASES),'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [CASES]},'event_rows_loaded':int(len(ev)),'cutoffs':sorted(active.cutoff.unique().tolist()),'route':'wallet -> typed (counterparty,event_family,token_contract) interaction key -> peer wallet -> peer recent outgoing external recipient','candidate_node_scope':'all wallets visible in the cutoff-truncated event panel; active evaluation cases are not used to filter graph construction','hub_cap':200,'peer_cap':200,'peer_recent_recipient_cap':100,'time_decay_days':90,'candidate_generation_uses_future_target':False,'independent_holdout':False,'prior_v1_status':'INVALID: active-label filtering selected only 159 active wallets and was not a fair comparative evaluation','note':'June/July/August explored diagnostic only; no final ranking claim.'}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (OUT/'REPORT.md').write_text('# Heterogeneous temporal retrieval pilot v2 (leakage-corrected)\n\nCandidate graphs and global popularity are built from all wallets visible strictly before each cutoff. Active-case membership is used only to select evaluation rows after candidate construction. v1 was invalid because it filtered graph construction by future-active wallets.\n\nThis remains a diagnostic candidate-coverage pilot on explored June/July/August cutoffs, not an independent test or final Top-5 ranker.\n')
 print(json.dumps({'output':str(OUT),'cases':len(details),'events':len(ev)},indent=2))
if __name__=='__main__': main()
