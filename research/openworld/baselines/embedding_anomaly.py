#!/usr/bin/env python3
"""Static graph-embedding anomaly baseline for OW-007.

The graph is constructed only from the pre-cutoff 30-day history. External labels are
not read. Future outcomes are joined only after scores are frozen.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import normalize
from sklearn.metrics import pairwise_distances

ROOT=Path(__file__).resolve().parents[3]
EDGE_PATH=ROOT/'research/community_temporal/results/data/edges_day_20220303_20220901.csv'
PANEL=ROOT/'research/openworld/results/future_consequence_panel.csv'
OUT=ROOT/'research/openworld/results'; OUT.mkdir(parents=True,exist_ok=True)
CUTOFFS=pd.to_datetime(['2022-05-01','2022-06-01','2022-07-01','2022-08-01'])

def graph_embedding_score(df,cutoff):
    h=df[(df.day_dt<cutoff)&(df.day_dt>=cutoff-pd.Timedelta(days=30))]
    nodes=np.sort(np.unique(np.r_[h.u.to_numpy(),h.v.to_numpy()]))
    idx={int(n):i for i,n in enumerate(nodes)}
    r=h.u.map(idx).to_numpy(); c=h.v.map(idx).to_numpy(); w=h.weight.to_numpy(dtype=float)
    a=coo_matrix((w,(r,c)),shape=(len(nodes),len(nodes))).tocsr()
    n_comp=min(16,max(2,len(nodes)-1))
    svd=TruncatedSVD(n_components=n_comp,random_state=20260918)
    z=svd.fit_transform(a)
    z=normalize(z)
    iso=IsolationForest(n_estimators=200,random_state=20260918,n_jobs=-1,contamination='auto')
    iso.fit(z)
    iforest=-iso.decision_function(z)
    # Reconstruction error from the fixed SVD embedding itself: a density/novelty proxy.
    # Use nearest-neighbor distance in normalized embedding space, no future labels.
    # For bounded memory, compute pairwise distances in chunks.
    nearest=np.full(len(nodes),np.inf)
    for start in range(0,len(nodes),1024):
        d=pairwise_distances(z[start:start+1024],z,metric='cosine',n_jobs=1)
        d[np.arange(len(d)),np.arange(start,min(start+len(d),len(nodes)))]=np.inf
        nearest[start:start+len(d)]=d.min(axis=1)
    out=pd.DataFrame({'node_id':nodes,'cutoff':cutoff.date().isoformat(),'embedding_iforest':iforest,'embedding_novelty':nearest})
    return out

def main():
    df=pd.read_csv(EDGE_PATH,dtype={'u':'int64','v':'int64','weight':'float64'}); df['day_dt']=pd.to_datetime(df.day)
    panel=pd.read_csv(PANEL)
    scores=[]
    for c in CUTOFFS: scores.append(graph_embedding_score(df,c))
    s=pd.concat(scores,ignore_index=True).merge(panel,on=['node_id','cutoff'],how='inner')
    rows=[]; rng=np.random.default_rng(20260918)
    score_names=['embedding_iforest','embedding_novelty']
    for cutoff,g in s.groupby('cutoff'):
        for name in score_names:
            rho=np.corrcoef(pd.Series(g[name]).rank(),pd.Series(g.future_volume).rank())[0,1]
            for k in [50,100,250,500]:
                top=g.sort_values([name,'node_id'],ascending=[False,True]).head(k)
                rnd=g.sample(k,random_state=int(rng.integers(1_000_000_000)))
                rows.append({'cutoff':cutoff,'score':name,'k':k,'spearman_future_volume':rho,'top_future_volume_mean':top.future_volume.mean(),'random_future_volume_mean':rnd.future_volume.mean(),'top_future_new_cp_mean':top.future_new_counterparties.mean(),'random_future_new_cp_mean':rnd.future_new_counterparties.mean()})
    m=pd.DataFrame(rows); s.to_csv(OUT/'embedding_anomaly_panel.csv',index=False); m.to_csv(OUT/'embedding_anomaly_metrics.csv',index=False)
    manifest={'experiment_id':'OW-007','edge_background':str(EDGE_PATH),'edge_background_sha256':hashlib.sha256(EDGE_PATH.read_bytes()).hexdigest(),'label_access':'none','model':'TruncatedSVD+IsolationForest','components':16,'cutoffs':[x.date().isoformat() for x in CUTOFFS],'lookback_days':30,'future_targets':'joined_after_score_freeze','rows':len(s)}
    (OUT/'embedding_anomaly_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(m[m.k==100].round(4).to_string(index=False)); print(json.dumps(manifest,indent=2))
if __name__=='__main__': main()
