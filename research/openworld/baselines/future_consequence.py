#!/usr/bin/env python3
"""Label-free temporal consequence sanity check on the local daily EX-Graph graph.

Scores use only history before each cutoff. Future outcomes are evaluation targets,
not features. This is a node-level baseline and does not claim group-level discovery.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT=Path(__file__).resolve().parents[3]
EDGE_PATH=ROOT/'research/community_temporal/results/data/edges_day_20220303_20220901.csv'
OUT=ROOT/'research/openworld/results'
OUT.mkdir(parents=True,exist_ok=True)
CUTOFFS=pd.to_datetime(['2022-05-01','2022-06-01','2022-07-01','2022-08-01'])
LOOKBACK=30; HORIZON=30


def entropy(values):
    c=pd.Series(values).value_counts().to_numpy(dtype=float)
    if len(c)==0:return 0.0
    p=c/c.sum()
    return float(-(p*np.log2(p)).sum())

def _incidence(x: pd.DataFrame) -> pd.DataFrame:
    a=x[['u','v','day_dt','weight']].rename(columns={'u':'node_id','v':'cp'})
    b=x[['v','u','day_dt','weight']].rename(columns={'v':'node_id','u':'cp'})
    return pd.concat([a,b],ignore_index=True)

def build_features(df, cutoff):
    hist=df[(df.day_dt < cutoff)&(df.day_dt >= cutoff-pd.Timedelta(days=LOOKBACK))].copy()
    fut=df[(df.day_dt >= cutoff)&(df.day_dt < cutoff+pd.Timedelta(days=HORIZON))].copy()
    if hist.empty:return pd.DataFrame()
    hi=_incidence(hist); fi=_incidence(fut) if not fut.empty else pd.DataFrame(columns=hi.columns)
    node_ids=np.sort(hi.node_id.unique())
    g=hi.groupby('node_id',sort=False)
    feat=pd.DataFrame(index=node_ids)
    feat.index.name='node_id'
    feat['volume']=g.weight.sum()
    feat['active_days']=g.day_dt.nunique()
    feat['unique_counterparties']=g.cp.nunique()
    cp_counts=hi.groupby(['node_id','cp'],sort=False).weight.sum()
    cp_entropy=cp_counts.groupby(level=0).apply(lambda s: entropy(s.to_numpy()))
    feat['counterparty_entropy']=cp_entropy
    daily=hi.groupby(['node_id','day_dt'],sort=False).weight.sum()
    feat['burstiness']=daily.groupby(level=0).max()/daily.groupby(level=0).mean().clip(lower=1.0)
    last7=hi[hi.day_dt >= cutoff-pd.Timedelta(days=7)]
    prev=hi[hi.day_dt < cutoff-pd.Timedelta(days=7)]
    last_cp=last7.groupby('node_id').cp.agg(lambda s:set(s.astype(int)))
    prev_cp=prev.groupby('node_id').cp.agg(lambda s:set(s.astype(int)))
    feat['novelty']=[len(last_cp.get(n,set())-prev_cp.get(n,set()))/max(1,len(last_cp.get(n,set()))) for n in node_ids]
    last7w=last7.groupby('node_id').weight.sum()
    prevw=prev.groupby('node_id').weight.sum()
    feat['temporal_surprise']=((last7w.reindex(node_ids,fill_value=0)+1)/(prevw.reindex(node_ids,fill_value=0)/23+1)).to_numpy()
    # Reciprocal directed edge support.
    pair_set=set(map(tuple,hist[['u','v']].drop_duplicates().astype(int).to_numpy()))
    recip_pairs=[(u,v) for u,v in pair_set if (v,u) in pair_set and u<v]
    recip_count=Counter()
    for u,v in recip_pairs: recip_count[u]+=1; recip_count[v]+=1
    feat['reciprocity']=[float(recip_count.get(int(n),0)) for n in node_ids]
    feat=feat.reset_index()
    feat['cutoff']=cutoff.date().isoformat()
    # Future consequences (evaluation only).
    future_ids=np.sort(fi.node_id.unique()) if not fi.empty else np.array([],dtype=int)
    f_volume=fi.groupby('node_id').weight.sum() if not fi.empty else pd.Series(dtype=float)
    f_days=fi.groupby('node_id').day_dt.nunique() if not fi.empty else pd.Series(dtype=float)
    f_cp=fi.groupby('node_id').cp.agg(lambda s:set(s.astype(int))) if not fi.empty else pd.Series(dtype=object)
    f_daily=fi.groupby(['node_id','day_dt']).weight.sum() if not fi.empty else pd.Series(dtype=float)
    f_burst=(f_daily.groupby(level=0).max()/f_daily.groupby(level=0).mean().clip(lower=1.0)) if not fi.empty else pd.Series(dtype=float)
    h_cp=hi.groupby('node_id').cp.agg(lambda s:set(s.astype(int)))
    feat['future_volume']=feat.node_id.map(f_volume).fillna(0.0)
    feat['future_active_days']=feat.node_id.map(f_days).fillna(0).astype(int)
    feat['future_counterparties']=feat.node_id.map(f_cp.apply(len) if not fi.empty else pd.Series(dtype=float)).fillna(0).astype(int)
    feat['future_new_counterparties']=[len(f_cp.get(int(n),set())-h_cp.get(int(n),set())) for n in feat.node_id]
    feat['future_burstiness']=feat.node_id.map(f_burst).fillna(0.0)
    return feat

def evaluate(panel):
    rows=[]
    scores=['volume','active_days','unique_counterparties','counterparty_entropy','burstiness','reciprocity','novelty','temporal_surprise']
    for cutoff,g in panel.groupby('cutoff'):
        g=g.copy(); n=len(g)
        for score in scores:
            for k in [50,100,250,500]:
                top=g.sort_values([score,'node_id'],ascending=[False,True]).head(min(k,n))
                # Uniform random expectation estimated analytically and by fixed seed sample.
                rng=np.random.default_rng(20260918+int(pd.Timestamp(cutoff).month)*100+len(score))
                sample=g.sample(min(k,n),random_state=int(rng.integers(1_000_000)))
                for unit,x in [('top',top),('random',sample)]:
                    rows.append({'cutoff':cutoff,'score':score,'k':k,'selection':unit,'n_nodes':n,
                        'future_volume_mean':x.future_volume.mean(),'future_new_counterparties_mean':x.future_new_counterparties.mean(),
                        'future_active_days_mean':x.future_active_days.mean(),'history_volume_mean':x.volume.mean()})
            rho,p=spearmanr(g[score],g['future_volume']) if g[score].nunique()>1 else (np.nan,np.nan)
            rows.append({'cutoff':cutoff,'score':score,'k':None,'selection':'spearman_future_volume','n_nodes':n,
                         'spearman':rho,'p_value':p})
    return pd.DataFrame(rows)

def main():
    df=pd.read_csv(EDGE_PATH, dtype={'u':'int64','v':'int64','weight':'float64'})
    df['day_dt']=pd.to_datetime(df.day)
    panels=[]
    for c in CUTOFFS:
        p=build_features(df,c); panels.append(p)
    panel=pd.concat(panels,ignore_index=True)
    metrics=evaluate(panel)
    panel.to_csv(OUT/'future_consequence_panel.csv',index=False)
    metrics.to_csv(OUT/'future_consequence_metrics.csv',index=False)
    manifest={'experiment_id':'OW-006','edge_background':str(EDGE_PATH),'edge_background_sha256':hashlib.sha256(EDGE_PATH.read_bytes()).hexdigest(),
              'label_access':'none','cutoffs':[x.date().isoformat() for x in CUTOFFS], 'lookback_days':LOOKBACK,'horizon_days':HORIZON,
              'features':['volume','active_days','unique_counterparties','counterparty_entropy','burstiness','reciprocity','novelty','temporal_surprise'],
              'future_targets':['future_volume','future_active_days','future_new_counterparties'], 'rows':len(panel)}
    (OUT/'future_consequence_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    x=metrics[(metrics.selection=='top')&(metrics.k==100)]
    print(x[['cutoff','score','future_volume_mean','future_new_counterparties_mean','future_active_days_mean']].to_string(index=False))
    print('\nSpearman future volume')
    print(metrics[metrics.selection=='spearman_future_volume'][['cutoff','score','spearman','p_value']].to_string(index=False))
    print(json.dumps(manifest,indent=2))
if __name__=='__main__': main()
