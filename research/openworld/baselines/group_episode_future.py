#!/usr/bin/env python3
"""Temporal group/episode baseline with a participant-budget comparison.

Episodes are connected components of high-weight edges in a pre-cutoff 7-day
window. This is a deliberately shallow Tier-0 probe, not the final ontology.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,networkx as nx
ROOT=Path(__file__).resolve().parents[3]
EDGE=ROOT/'research/community_temporal/results/data/edges_day_20220303_20220901.csv'
OUT=ROOT/'research/openworld/results'; OUT.mkdir(parents=True,exist_ok=True)
CUTOFFS=pd.to_datetime(['2022-05-01','2022-06-01','2022-07-01','2022-08-01'])
LOOKBACK=7; HORIZON=30; PARTICIPANT_BUDGET=100

def incidence(x):
 a=x[['u','v','weight']].rename(columns={'u':'node','v':'cp'})
 b=x[['v','u','weight']].rename(columns={'v':'node','u':'cp'})
 return pd.concat([a,b],ignore_index=True)

def future_node_targets(df,cutoff):
 h=df[(df.day_dt<cutoff)&(df.day_dt>=cutoff-pd.Timedelta(days=LOOKBACK))]
 f=df[(df.day_dt>=cutoff)&(df.day_dt<cutoff+pd.Timedelta(days=HORIZON))]
 hi=incidence(h); fi=incidence(f)
 hcp=hi.groupby('node').cp.agg(lambda s:set(s.astype(int)))
 fcp=fi.groupby('node').cp.agg(lambda s:set(s.astype(int)))
 fv=fi.groupby('node').weight.sum(); fa=fi.groupby('node').day_dt.nunique() if 'day_dt' in fi else pd.Series()
 nodes=np.unique(np.r_[hi.node.to_numpy(),hi.cp.to_numpy()])
 return {int(n):{'future_volume':float(fv.get(n,0)),'future_new_cp':len(fcp.get(n,set())-hcp.get(n,set())),'future_active_days':int(fa.get(n,0))} for n in nodes}

def build_groups(df,cutoff):
 h=df[(df.day_dt<cutoff)&(df.day_dt>=cutoff-pd.Timedelta(days=LOOKBACK))].copy()
 if h.empty:return []
 threshold=max(1.0,float(h.weight.quantile(.5)))
 q=h[h.weight>=threshold]
 g=nx.Graph(); g.add_edges_from(q[['u','v']].itertuples(index=False,name=None))
 rows=[]
 for cid,nodes in enumerate(nx.connected_components(g)):
  nodes=set(map(int,nodes)); n=len(nodes)
  if n<3 or n>50: continue
  sub=q[q.u.isin(nodes)&q.v.isin(nodes)]
  if len(sub)<2:continue
  possible=n*(n-1)/2
  w=float(sub.weight.sum()); density=float(len(sub)/max(1,possible));
  day_sum=sub.groupby('day_dt').weight.sum()
  burst=float(day_sum.max()/max(1,day_sum.mean()))
  # directed reciprocal support; if the source export duplicates directions this remains a measurable baseline.
  pairs=set(map(tuple,sub[['u','v']].astype(int).to_numpy())); recip=sum(1 for u,v in pairs if u<v and (v,u) in pairs)
  rows.append({'episode_id':f'{cutoff.date()}_{cid}','cutoff':cutoff.date().isoformat(),'nodes':nodes,'size':n,'volume':w,'density':density,'burst':burst,'reciprocity':float(recip),'edge_count':len(sub),'threshold':threshold})
 return rows

def select_groups(groups,score,budget=100):
 ordered=sorted(groups,key=lambda x:(-x[score],x['episode_id'])); chosen=[]; used=set()
 for g in ordered:
  new=g['nodes']-used
  if not new:continue
  if len(used)+len(new)>budget:
   new=set(list(sorted(new))[:budget-len(used)])
  if not new:break
  chosen.append((g,new)); used.update(new)
  if len(used)>=budget:break
 return chosen,used

def eval_selection(sel,targets):
 ns=set().union(*(x[1] for x in sel)) if sel else set()
 if not ns:return {'n_nodes':0,'future_volume':0,'future_new_cp':0,'future_active_days':0}
 vals=[targets[n] for n in ns if n in targets]
 return {'n_nodes':len(vals),'future_volume':float(np.mean([x['future_volume'] for x in vals])),'future_new_cp':float(np.mean([x['future_new_cp'] for x in vals])),'future_active_days':float(np.mean([x['future_active_days'] for x in vals]))}

def main():
 df=pd.read_csv(EDGE,dtype={'u':'int64','v':'int64','weight':'float64'});df['day_dt']=pd.to_datetime(df.day)
 rows=[]; rng=np.random.default_rng(20260918)
 for c in CUTOFFS:
  groups=build_groups(df,c); targets=future_node_targets(df,c)
  for score in ['volume','density','burst','reciprocity']:
   sel,used=select_groups(groups,score,PARTICIPANT_BUDGET); m=eval_selection(sel,targets)
   rows.append({'cutoff':c.date().isoformat(),'selection':score,'draw':0,'episode_count':len(groups),**m})
   # random episode baseline, same greedy participant budget.
   for draw in range(200):
    perm=list(groups); rng.shuffle(perm); rand=sorted(perm,key=lambda x:rng.random()); chosen=[];u=set()
    for gg in rand:
     new=gg['nodes']-u
     if not new:continue
     if len(u)+len(new)>PARTICIPANT_BUDGET:new=set(list(sorted(new))[:PARTICIPANT_BUDGET-len(u)])
     if not new:break
     chosen.append((gg,new));u.update(new)
     if len(u)>=PARTICIPANT_BUDGET:break
    rows.append({'cutoff':c.date().isoformat(),'selection':score,'draw':draw+1,'episode_count':len(groups),**eval_selection(chosen,targets)})
 out=pd.DataFrame(rows);out.to_csv(OUT/'group_episode_future_metrics.csv',index=False)
 summ=[]
 for (c,s),x in out.groupby(['cutoff','selection']):
  top=x[x.draw==0].iloc[0];rand=x[x.draw>0]
  for t in ['future_volume','future_new_cp','future_active_days']:
   summ.append({'cutoff':c,'selection':s,'target':t,'top':float(top[t]),'random_mean':float(rand[t].mean()),'random_ci_lo':float(rand[t].quantile(.025)),'random_ci_hi':float(rand[t].quantile(.975)),'delta':float(top[t]-rand[t].mean()),'episode_count':int(top.episode_count),'n_nodes':int(top.n_nodes)})
 sd=pd.DataFrame(summ);sd.to_csv(OUT/'group_episode_future_summary.csv',index=False)
 manifest={'experiment_id':'OW-008','edge_background':str(EDGE),'edge_background_sha256':hashlib.sha256(EDGE.read_bytes()).hexdigest(),'label_access':'none','lookback_days':LOOKBACK,'horizon_days':HORIZON,'participant_budget':PARTICIPANT_BUDGET,'episode_rule':'connected_components_of_weight>=50th_percentile_excluding_components_over_50_nodes','cutoffs':[x.date().isoformat() for x in CUTOFFS]}
 (OUT/'group_episode_future_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(sd.query("target=='future_new_cp'").round(3).to_string(index=False));print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
