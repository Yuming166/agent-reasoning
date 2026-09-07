#!/usr/bin/env python3
from __future__ import annotations
import json, pickle, statistics, time
from collections import Counter
from pathlib import Path
import argparse

p=argparse.ArgumentParser(); p.add_argument('--graph',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
t=time.time()
with a.graph.open('rb') as f: g=pickle.load(f)
weights=[]; hist=Counter(); high=[]; sum_w=0
for u,v,d in g.edges(data=True):
    w=d.get('weight')
    weights.append(w); hist[w]+=1; sum_w += w
    if len(high)<20 or w>high[0][0]:
        high.append((w,u,v)); high=sorted(high)[-20:]
result={
 'graph_type':f'{type(g).__module__}.{type(g).__name__}',
 'graph_metadata':{str(k):repr(v) for k,v in getattr(g,'graph',{}).items()},
 'nodes':g.number_of_nodes(),'edges':g.number_of_edges(),
 'weight_sum':sum_w,'weight_min':min(weights),'weight_max':max(weights),
 'weight_mean':statistics.fmean(weights),'weight_median':statistics.median(weights),
 'edges_weight_gt_1':sum(n for w,n in hist.items() if w>1),
 'edges_weight_eq_1':hist.get(1,0),
 'weight_histogram':{str(k):hist[k] for k in sorted(hist)},
 'top_weight_edges':[{'weight':w,'source':u,'target':v} for w,u,v in sorted(high,reverse=True)],
 'load_and_scan_seconds':time.time()-t,
}
a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False)); print('wrote',a.output)
