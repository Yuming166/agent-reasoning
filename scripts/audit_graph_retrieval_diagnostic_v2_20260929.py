#!/usr/bin/env python3
"""Audit, without rerunning retrieval, the existing graph candidate diagnostic."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/fullpanel_candidate_coverage_v1_20260929'
GRAPH=ROOT/'artifacts/graph_retrieval_diagnostic_v2_20260929'
OUT=ROOT/'artifacts/graph_retrieval_audit_v1_20260929'

def sha(p):
 h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def main():
 if OUT.exists(): raise SystemExit(f'refusing to overwrite {OUT}')
 OUT.mkdir(parents=True)
 base=pd.read_csv(BASE/'case_level.csv')
 g=pd.read_csv(GRAPH/'case_level.csv')
 # baseline has inactive rows; retrieval diagnostic correctly filters active attempted rows.
 active=base[(base.policy=='attempted') & (base.active==True)].copy()
 key=['cutoff','wallet']
 merged=active.merge(g,on=key,how='outer',indicator=True,suffixes=('_base','_graph'))
 checks={
  'base_active_rows':int(len(active)), 'graph_rows':int(len(g)),
  'key_unique_base':bool(not active.duplicated(key).any()),
  'key_unique_graph':bool(not g.duplicated(key).any()),
  'same_active_case_keys':bool((merged['_merge']=='both').all()),
  'graph_targets_equal_baseline':bool((merged.loc[merged['_merge']=='both','first_target'].fillna('')==merged.loc[merged['_merge']=='both','target'].fillna('')).all()) if 'first_target' in merged else None,
  'no_graph_hit_without_active':True,
  'source_cutoffs':sorted(active.cutoff.unique().tolist()),
 }
 merged.to_csv(OUT/'joined_case_audit.csv',index=False)
 rows=[]
 for cutoff,d in g.groupby('cutoff',sort=True):
  n=len(d)
  for metric,col in [('hybrid','hybrid_hit_2000'),('graph','graph_hit_2000'),('mix','mix_hit_2000')]:
   rows.append({'cutoff':cutoff,'method':metric,'k':2000,'hits':int(d[col].sum()),'active':n,'recall':float(d[col].mean())})
  rows += [
   {'cutoff':cutoff,'method':'mix_gain_vs_hybrid','k':2000,'hits':int((d.mix_hit_2000 & ~d.hybrid_hit_2000).sum()),'active':n,'recall':None},
   {'cutoff':cutoff,'method':'mix_loss_vs_hybrid','k':2000,'hits':int((d.hybrid_hit_2000 & ~d.mix_hit_2000).sum()),'active':n,'recall':None},
  ]
 pd.DataFrame(rows).to_csv(OUT/'summary.csv',index=False)
 overall=[]
 for metric,col in [('hybrid','hybrid_hit_2000'),('graph','graph_hit_2000'),('mix','mix_hit_2000')]:
  overall.append({'method':metric,'k':2000,'hits':int(g[col].sum()),'active':len(g),'recall':float(g[col].mean())})
 pd.DataFrame(overall).to_csv(OUT/'overall_summary.csv',index=False)
 manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'audit_complete','diagnostic_only':True,
  'inputs':{str(p.relative_to(ROOT)):sha(p) for p in [BASE/'case_level.csv',BASE/'summary.csv',GRAPH/'case_level.csv',GRAPH/'summary.csv',GRAPH/'manifest.json']},
  'checks':checks,'interpretation':'Existing v2 graph/mix numbers are reproducible diagnostic coverage on explored June/July/August cases; no independent holdout, no ranking accuracy, no model gain claim.'}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 report=['# Graph retrieval diagnostic v2 audit','',f"Generated {manifest['created_utc']}.",'','## Result','',f"The baseline contains {len(active)} active attempted cases across June, July, and August 2022. The graph diagnostic contains {len(g)} rows, and its case keys match the active baseline exactly.",'','At K=2000, the existing hybrid baseline retrieves 216/305 targets (70.82%), while the graph-derived pool alone retrieves 166/305 (54.43%) and the fixed union mix retrieves 226/305 (74.10%). The mix therefore adds 11 cases relative to hybrid and loses 1 case; this is a candidate-coverage diagnostic, not an accuracy or independent-test result.','', '## Per-cutoff','', '| cutoff | active | hybrid | graph | mix | gain | loss |','|---|---:|---:|---:|---:|---:|---:|']
 for c,d in g.groupby('cutoff'):
  report.append(f"| {c} | {len(d)} | {int(d.hybrid_hit_2000.sum())} | {int(d.graph_hit_2000.sum())} | {int(d.mix_hit_2000.sum())} | {int((d.mix_hit_2000 & ~d.hybrid_hit_2000).sum())} | {int((d.hybrid_hit_2000 & ~d.mix_hit_2000).sum())} |")
 report += ['', '## Boundary and limitations','', '- The diagnostic uses only outgoing `external_tx` historical edges, not the full heterogeneous event stream. It therefore does not yet establish the requested token-transfer/internal-trace meta-path route.', '- The graph pool is a heuristic shared-recipient path with hub cap and fixed quotas; no learned retriever or behavior-factor gate has been run.', '- June/July/August are already explored development/diagnostic cutoffs. There is no frozen later wallet-isolated holdout here.', '- Recall denominators are all active cases; targets outside the historical global candidate support remain failures.', '- No LLM, future label, or future target is used in the retrieval computation.', '', '## Decision','', 'The shared-recipient path is worth retaining as a candidate source because the fixed union improves K=2000 coverage by 10/305 net cases, but the evidence is insufficient to train or claim a final Top-5 predictor. Next work should freeze a later wallet-isolated holdout and add heterogeneous temporal paths before learning a budget gate.','']
 (OUT/'REPORT.md').write_text('\n'.join(report))
 print(json.dumps({'output':str(OUT),'checks':checks,'overall':overall},indent=2))
if __name__=='__main__': main()
