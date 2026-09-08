#!/usr/bin/env python3
"""Exact hybrid new-counterparty model on frozen August events.

Candidates per event (u):
  1. u's 2-hop non-neighbor bridge pool, ranked by bridge_signal;
  2. then remaining global non-neighbors by historical popularity.
Ranks are computed without materializing full lists:
  hit in bridge pool  -> hybrid rank = bridge_rank
  not in bridge pool  -> hybrid rank = pool_size(u) + global_non_neighbor_rank
Reports new-event metrics and combined overall metrics (repeat: personal
recency over own prior neighbors)."""
import glob, json, bisect
import numpy as np, pandas as pd

NC="/tmp/nc"
def load(k):
    return pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{NC}/{k}_*.csv"))],ignore_index=True)
def m(r):
    r=np.asarray(r,float); r=np.where(r<=0,np.inf,r)
    return {"n":int(len(r)),"MRR":float((1/r).mean()),"R@1":float((r==1).mean()),
            "R@5":float((r<=5).mean()),"R@10":float((r<=10).mean())}

ev=load("events"); ed=load("edges"); pop=load("pop")
hits=pd.read_csv(f"{NC}/bridge_hits.csv"); poolsz=pd.read_csv(f"{NC}/poolsize.csv")
ev["month"]=pd.to_datetime(ev["month"]).dt.date.astype(str)
aug=ev[ev.month=="2022-08-01"].reset_index(drop=True)

pop=pop.sort_values("hist_cnt",ascending=False).reset_index(drop=True)
gpos={v:i for i,v in enumerate(pop.v)}
neigh={}
for u,v in zip(ed.u,ed.v): neigh.setdefault(u,set()).add(v)
pos_sets={u:np.sort([gpos[x] for x in s if x in gpos]) for u,s in neigh.items()}
pool=dict(zip(poolsz.u, poolsz.pool_size))
hmap={(r.u,int(r.target_sequence_index)):int(r.bridge_rank) for r in hits.itertuples()}

U=aug.u.to_numpy(); V=aug.v.to_numpy(); SI=aug.target_sequence_index.to_numpy()
isnew=(aug.cp_type=="new").to_numpy()
g_rank=np.array([gpos.get(v,len(pop))+1 for v in V])
gnew=np.empty(len(aug)); hyb=np.empty(len(aug))
for i in range(len(aug)):
    ps=pos_sets.get(U[i]); pos=gpos.get(V[i],-1)
    hi=bisect.bisect_left(ps,pos) if (ps is not None and pos>=0) else 0
    gnew[i]=g_rank[i]-hi
    br=hmap.get((U[i],int(SI[i])))
    if br is not None: hyb[i]=br
    else: hyb[i]=pool.get(U[i],0)+gnew[i]

# personal recency ranks for repeat-histknown events
ed["w"]=np.exp(-np.log(2)*ed["days_since_last"].clip(lower=0)/90.0)
ed["recency_score"]=ed.cnt*ed.w
rec={}
for u,g in ed.groupby("u",sort=False):
    gg=g.sort_values("recency_score",ascending=False)
    rec[u]={v:i+1 for i,v in enumerate(gg.v)}
pr=np.array([rec.get(U[i],{}).get(V[i],0) for i in range(len(aug))])
rep_hist=(~isnew)&(pr>0)

overall=[]
for i in range(len(aug)):
    overall.append(hyb[i] if isnew[i] else (pr[i] if pr[i]>0 else g_rank[i]))
overall=np.array(overall)

res={
 "new_global_nonneighbor": m(gnew[isnew]),
 "new_hybrid_bridge_then_global": m(hyb[isnew]),
 "repeat_personal_recency_histknown": m(pr[rep_hist]),
 "combined_all_events": m(overall),
 "bridge_pool_truth_coverage_of_new": float(len(hits)/isnew.sum()),
 "n_repeat_same_month_only": int(((~isnew)&(pr==0)).sum()),
}
print(json.dumps(res,indent=2))
json.dump(res, open("artifacts/nc_v1/candidate_model_comparison_v1.json","w"),indent=2)
