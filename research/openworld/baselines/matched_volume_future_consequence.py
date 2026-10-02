#!/usr/bin/env python3
"""Volume-decile matched future-consequence audit for OW-006."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
PANEL=ROOT/'research/openworld/results/future_consequence_panel.csv'
OUT=ROOT/'research/openworld/results'
SCORES=['active_days','unique_counterparties','counterparty_entropy','burstiness','novelty','temporal_surprise','reciprocity']
TARGETS=['future_volume','future_new_counterparties','future_active_days']

def metric(x):
    return {f'{t}_mean':float(x[t].mean()) for t in TARGETS}

def main():
    p=pd.read_csv(PANEL); rows=[]; rng=np.random.default_rng(20260918)
    for cutoff,g in p.groupby('cutoff'):
        g=g.copy(); g['volume_bin']=pd.qcut(g.volume.rank(method='first'),10,labels=False,duplicates='drop')
        k=100; quota=k//10
        vol=g.sort_values(['volume','node_id'],ascending=[False,True]).head(k)
        rows.append({'cutoff':cutoff,'score':'volume','selection':'top_volume','draw':0,**metric(vol)})
        bins=[gb.reset_index(drop=True) for _,gb in g.groupby('volume_bin')]
        for score in SCORES:
            selected=[]
            for gb in bins:
                selected.append(gb.sort_values([score,'node_id'],ascending=[False,True]).head(quota))
            rows.append({'cutoff':cutoff,'score':score,'selection':'volume_decile_top','draw':0,**metric(pd.concat(selected))})
            arrays={t:[gb[t].to_numpy(dtype=float) for gb in bins] for t in TARGETS}
            for draw in range(1000):
                vals={t:[] for t in TARGETS}
                for j,gb in enumerate(bins):
                    n=min(quota,len(gb))
                    ix=rng.choice(len(gb),size=n,replace=False)
                    for t in TARGETS: vals[t].extend(arrays[t][j][ix].tolist())
                rows.append({'cutoff':cutoff,'score':score,'selection':'volume_decile_random','draw':draw,**{f'{t}_mean':float(np.mean(v)) for t,v in vals.items()}})
    out=pd.DataFrame(rows); out.to_csv(OUT/'matched_volume_future_consequence.csv',index=False)
    summary=[]
    for (cutoff,score),x in out[out.score.isin(SCORES)].groupby(['cutoff','score']):
        top=x[x.selection=='volume_decile_top'].iloc[0]; rand=x[x.selection=='volume_decile_random']
        for target in [f'{t}_mean' for t in TARGETS]:
            summary.append({'cutoff':cutoff,'score':score,'target':target,'top_value':float(top[target]),'random_mean':float(rand[target].mean()),'random_ci_lo':float(rand[target].quantile(.025)),'random_ci_hi':float(rand[target].quantile(.975)),'top_minus_random':float(top[target]-rand[target].mean())})
    summary_df=pd.DataFrame(summary); summary_df.to_csv(OUT/'matched_volume_future_consequence_summary.csv',index=False)
    print(summary_df.query("target == 'future_new_counterparties_mean'").round(3).to_string(index=False))
if __name__=='__main__': main()
