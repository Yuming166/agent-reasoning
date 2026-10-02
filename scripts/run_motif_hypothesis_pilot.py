#!/usr/bin/env python3
"""Bounded, leakage-aware motif -> hypothesis -> future-window verifier pilot.
Uses only archived panel event rows; no network or paid query.
"""
from __future__ import annotations
import argparse, json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

FEATURES = ["evt_cnt_90d","active_days_90d","cp_entropy_90d","cp_new_rate_30d","pop_weight"]

def load_events(root: Path) -> pd.DataFrame:
    ps = sorted((root / "artifacts/llm_panel_v1/events").glob("*.csv.gz"))
    ds = [pd.read_csv(p) for p in ps]
    d = pd.concat(ds, ignore_index=True)
    d["snapshot_date"] = pd.to_datetime(d["snapshot_date"], utc=True)
    d["block_timestamp"] = pd.to_datetime(d["block_timestamp"], utc=True)
    d["future_days"] = (d.block_timestamp - d.snapshot_date).dt.total_seconds()/86400
    # Future-window validity: the archived rows are actual subsequent events; retain only <= 7d.
    d = d[(d.future_days >= 0) & (d.future_days <= 7)].copy()
    d["outcome_new"] = (d.cp_type == "new").astype(int)
    d["event_id"] = d.apply(lambda r: f"{r.target_address}:{int(r.target_sequence_index)}:{r.block_timestamp.isoformat()}", axis=1)
    for c in FEATURES:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=FEATURES+["outcome_new"])

def metric(y, p):
    pr, rc, f1, _ = precision_recall_fscore_support(y,p,average="binary",zero_division=0)
    return {"n":int(len(y)),"accuracy":float(accuracy_score(y,p)),"precision_new":float(pr),"recall_new":float(rc),"f1_new":float(f1),"coverage":1.0}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--n",type=int,default=400); ap.add_argument("--seed",type=int,default=20260927); args=ap.parse_args()
    root=Path(args.root); out=root/"artifacts/motif_hypothesis_pilot_20260927"; out.mkdir(parents=True,exist_ok=True)
    d=load_events(root)
    # Stratified, bounded sample by activity and cp_type, then temporal holdout by month.
    rng=np.random.default_rng(args.seed)
    d["stratum2"] = d["activity"].astype(str)+"__"+d["cp_type"].astype(str)
    parts=[]
    per=max(1,args.n//max(1,d.stratum2.nunique()))
    for _,g in d.groupby("stratum2",sort=True):
        parts.append(g.sample(n=min(per,len(g)),random_state=int(rng.integers(1<<31))))
    s=pd.concat(parts).drop_duplicates("event_id").sort_values(["block_timestamp","event_id"])
    if len(s)<args.n:
        rem=d[~d.event_id.isin(s.event_id)].sample(n=min(args.n-len(s),len(d)-len(s)),random_state=args.seed)
        s=pd.concat([s,rem]).drop_duplicates("event_id")
    s=s.sort_values(["block_timestamp","event_id"]).head(args.n).copy()
    s["split"] = np.where(s.snapshot_date.dt.month==8,"holdout_aug", "development")
    # Thresholds are fit on development only: no future leakage.
    dev=s[s.split=="development"]
    med=dev[FEATURES].median(numeric_only=True)
    # Natural-language hypothesis + DSL, generated deterministically from observed pre-cutoff fields.
    s["h_exploration_rule"] = ((s.cp_new_rate_30d >= med.cp_new_rate_30d) & (s.cp_entropy_90d >= med.cp_entropy_90d)).astype(int)
    s["h_persistence_rule"] = ((s.cp_new_rate_30d < med.cp_new_rate_30d) & (s.cp_entropy_90d < med.cp_entropy_90d)).astype(int)
    s["h_frequency_rule"] = (s.cp_new_rate_30d >= med.cp_new_rate_30d).astype(int)
    # fallback middle region: direct frequency rule is complete coverage; persistence/exploration are selective.
    s["direct_template_pred"] = s.h_frequency_rule
    # Numerical baseline: trained only on development and evaluated on Aug holdout.
    lr=LogisticRegression(max_iter=1000,random_state=args.seed)
    lr.fit(dev[FEATURES],dev.outcome_new)
    s["numeric_pred"] = lr.predict(s[FEATURES])
    # A constrained verifier: hypothesis cites event id and pre-cutoff fields; validity is automatic outcome check.
    s["evidence_cutoff"] = s.snapshot_date.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    s["hypothesis_text"] = np.where(s.h_frequency_rule==1,
        "Given the pre-cutoff 30-day new-counterparty rate is at/above the development median, the next 7-day event is hypothesized to be a new counterparty.",
        "Given the pre-cutoff 30-day new-counterparty rate is below the development median, the next 7-day event is hypothesized to be a repeat counterparty.")
    s["hypothesis_dsl"] = np.where(s.h_frequency_rule==1,
        "IF cp_new_rate_30d >= DEV_MEDIAN THEN outcome=new ELSE outcome=repeat",
        "IF cp_new_rate_30d < DEV_MEDIAN THEN outcome=repeat ELSE outcome=new")
    s["evidence_event_id"] = s.event_id
    s["evidence_fields"] = "evt_cnt_90d,active_days_90d,cp_entropy_90d,cp_new_rate_30d,pop_weight"
    s["verified"] = (s.direct_template_pred == s.outcome_new).astype(int)
    s.to_csv(out/"sample_verification_rows.csv",index=False)
    results={"pilot":"motif_hypothesis_future7d_v1","generated_utc":pd.Timestamp.utcnow().isoformat(),"network_requests":0,"paid_queries":0,"source":"archived artifacts/llm_panel_v1/events/*.csv.gz","sample_n":int(len(s)),"development_n":int((s.split=="development").sum()),"holdout_n":int((s.split=="holdout_aug").sum()),"future_window_days":7,"cutoff_rule":"snapshot_date; rows after cutoff not used in features","thresholds":{k:float(v) for k,v in med.items()},"outcome_counts":s.outcome_new.value_counts().rename(index={0:"repeat",1:"new"}).to_dict(),"methods":{},"limitations":["Archived panel rows provide sequence index but not transaction_hash/event_family in the local input; event citations are stable composite IDs, not transaction hashes.","Only the next observed event is available for this bounded verifier; it is not a complete 7-day event stream.","No LLM call was made because the configured local endpoint was unreachable during the smoke test; this is a deterministic hypothesis/DSL pilot, not an LLM effectiveness result."]}
    for name,col in [("exploration_rule","h_exploration_rule"),("persistence_rule","h_persistence_rule"),("direct_template","direct_template_pred"),("numeric_baseline","numeric_pred")]:
        results["methods"][name]={"all":metric(s.outcome_new,s[col]),"holdout_aug":metric(s.loc[s.split=="holdout_aug","outcome_new"],s.loc[s.split=="holdout_aug",col]) if (s.split=="holdout_aug").any() else None}
    results["selective_rules"]={"exploration_coverage":float(s.h_exploration_rule.mean()),"persistence_coverage":float(s.h_persistence_rule.mean()),"exploration_accuracy_when_fired":float(s.loc[s.h_exploration_rule==1,"h_exploration_rule"].eq(s.loc[s.h_exploration_rule==1,"outcome_new"]).mean()) if s.h_exploration_rule.sum() else None,"persistence_accuracy_when_fired":float((1-s.loc[s.h_persistence_rule==1,"outcome_new"]).mean()) if s.h_persistence_rule.sum() else None}
    results["sample_sha256"]=hashlib.sha256((out/"sample_verification_rows.csv").read_bytes()).hexdigest()
    (out/"pilot_report.json").write_text(json.dumps(results,indent=2,ensure_ascii=False)+"\n")
    readme=f'''# Motif hypothesis pilot (2026-09-27)\n\nThis is a bounded offline pilot. It uses archived next-event panel rows only; no network or paid query.\n\n## Hypotheses\n- Exploration: high pre-cutoff new-counterparty rate plus high entropy predicts a new counterparty in the next 7 days.\n- Persistence: low new-counterparty rate plus low entropy predicts a repeat counterparty.\n- Frequency template: new-counterparty rate alone gives a complete-coverage direct hypothesis.\n\nEach row carries a composite stable event ID, a cutoff, cited pre-cutoff fields, natural-language hypothesis and DSL, then an automatic future-window verification.\n\n## Important boundary\nThe local panel lacks transaction_hash and event_family, and includes only the next observed event, so this does not claim complete future-event coverage. The configured Qwen endpoint smoke test was unreachable, so no LLM effectiveness claim is made.\n'''
    (out/"README.md").write_text(readme)
    print(json.dumps(results,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
