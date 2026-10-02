#!/usr/bin/env python3
"""Volume/edge-count matched control for OW-004 synthetic motifs."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from run_benchmark import (  # noqa: E402
    EDGE_PATH, OUT_DIR, MOTIFS, STAGES, SEEDS, N_GROUPS,
    motif_edges, graph_scores, top_nodes, ego_candidates, group_recovery,
)

def random_pairs(nodes, n, rng):
    out=[]; seen=set()
    while len(out)<n:
        u,v=rng.choice(nodes,2,replace=False)
        pair=(int(u),int(v))
        if pair not in seen:
            seen.add(pair); out.append(pair)
    return out

def inject(df, seed, stage, mode, rng):
    day=sorted(df.day.unique())[seed % df.day.nunique()]
    bg=df[df.day==day][['u','v','weight']].copy()
    if len(bg)>2500: bg=bg.sample(2500,random_state=seed)
    edges=[(int(r.u),int(r.v),int(r.weight)) for r in bg.itertuples(index=False)]
    bg_nodes=np.unique(np.r_[bg.u.to_numpy(),bg.v.to_numpy()]).astype(int)
    groups={}; next_id=1_000_000+seed*100_000
    for gi in range(N_GROUPS):
        kind=MOTIFS[gi%len(MOTIFS)]
        n=4 if kind not in {'fan_in','fan_out','split_merge'} else 6
        nodes=list(range(next_id,next_id+n)); next_id+=100
        groups[f'g{gi:02d}_{kind}']=set(nodes)
        canonical=motif_edges(kind,nodes)
        if mode=='motif':
            pairs=canonical
        else:
            pairs=random_pairs(nodes,len(canonical),rng)
        weights=[int(rng.integers(1,4)) for _ in pairs]
        for (u,v),w in zip(pairs,weights): edges.append((u,v,w))
        if stage in {'S2_noise','S3_camouflage','S4_high_camouflage'}:
            n_noise={'S2_noise':2,'S3_camouflage':4,'S4_high_camouflage':8}[stage]
            for _ in range(n_noise):
                u,v=rng.choice(nodes,2,replace=False); edges.append((int(u),int(v),int(rng.integers(1,3))))
        if stage in {'S3_camouflage','S4_high_camouflage'}:
            n_external={'S3_camouflage':2,'S4_high_camouflage':6}[stage]
            for _ in range(n_external):
                edges.append((int(rng.choice(nodes)),int(rng.choice(bg_nodes)),int(rng.integers(1,3))))
        if stage=='S4_high_camouflage':
            # remove one injected edge and add weight-noise edges, preserving the control symmetry
            drop_idx=int(rng.integers(0,len(pairs)))
            target=pairs[drop_idx]
            removed=False; kept=[]
            for e in edges:
                if not removed and e[0]==target[0] and e[1]==target[1]: removed=True
                else: kept.append(e)
            edges=kept
            for _ in range(3):
                u,v=rng.choice(nodes,2,replace=False); edges.append((int(u),int(v),int(rng.integers(1,8))))
    return edges,groups,str(day)

def main():
    df=pd.read_csv(EDGE_PATH); rows=[]
    for seed in SEEDS:
      for stage in STAGES:
       for mode in ('motif','matched_random'):
        rng=np.random.default_rng(seed*1000+STAGES.index(stage)*10+(0 if mode=='motif' else 1))
        edges,groups,day=inject(df,seed,stage,mode,rng)
        g,scores=graph_scores(edges); injected=set().union(*groups.values())
        for name,score in scores.items():
          for k in (100,200):
            rows.append({'seed':seed,'stage':stage,'mode':mode,'score':name,'unit':'node','k':k,'recall':len(top_nodes(score,k)&injected)/len(injected)})
          cand=ego_candidates(g,score)
          for k in (25,50):
            hit,iou=group_recovery(cand,groups,k)
            rows.append({'seed':seed,'stage':stage,'mode':mode,'score':name,'unit':'group_ego','k':k,'group_hit_rate':hit,'mean_best_iou':iou})
    out=pd.DataFrame(rows); path=OUT_DIR/'synthetic_motif_matched_control_results.csv'; out.to_csv(path,index=False)
    summary=[]
    for unit,k in [('node',100),('group_ego',25)]:
      x=out[(out.unit==unit)&(out.k==k)]
      for stage in STAGES:
       for score in sorted(out.score.unique()):
        a=x[(x.stage==stage)&(x.score==score)].pivot(index='seed',columns='mode',values='recall' if unit=='node' else 'group_hit_rate')
        if {'motif','matched_random'} <= set(a.columns):
         summary.append({'stage':stage,'score':score,'unit':unit,'k':k,'motif_minus_matched_random':float((a['motif']-a['matched_random']).mean()),'motif_mean':float(a['motif'].mean()),'matched_random_mean':float(a['matched_random'].mean())})
    sp=OUT_DIR/'synthetic_motif_matched_control_summary.json'; sp.write_text(json.dumps({'experiment_id':'OW-005','rows':len(out),'summary':summary},indent=2)+'\n')
    print(pd.DataFrame(summary).round(4).to_string(index=False))
    print('wrote',path,sp)
if __name__=='__main__': main()
