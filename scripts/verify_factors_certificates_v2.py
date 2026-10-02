#!/usr/bin/env python3
"""EX-Graph v2 as-of factor and evidence-certificate verifier.

This script is deliberately label-free: it reads only the wallet history before each
cutoff and never opens future labels.  It can (1) enumerate executable certificates
for repeat_recency, activity_shift, and shared_contract/typed paths, and (2) verify
proposal JSONL produced by a teacher/LLM against the same as-of index.

Proposal JSONL accepts either {case_id, ...proposal fields} or
{case_id, "proposal": {...}}.  Evidence IDs may be canonical IDs emitted here or
legacy case-local IDs such as E1; legacy IDs are accepted only after a unique match
to the raw event by hash/time/family/index/target wallet.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

FACTORS = ("repeat_recency", "activity_shift", "typed_graph_path")

def dt(x: Any) -> pd.Timestamp:
    t = pd.Timestamp(x)
    if t.tzinfo is None: t = t.tz_localize("UTC")
    return t.tz_convert("UTC")

def norm(x: Any) -> str:
    return str(x or "").strip().lower()

def stable_json(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def event_id(e: dict[str, Any]) -> str:
    payload = {k: e.get(k) for k in (
        "target_address", "target_sequence_index", "transaction_hash",
        "event_family", "event_index", "counterparty_address",
        "direction", "token_contract_address", "block_timestamp")}
    return "ev:" + hashlib.sha256(stable_json(payload).encode()).hexdigest()[:24]

def event_sort_key(e: dict[str, Any]):
    return (dt(e["block_timestamp"]), int(e.get("target_sequence_index") or -1),
            str(e.get("transaction_hash") or ""), int(e.get("event_index") or -1))

def load_jsonl(path: Path):
    with path.open() as f:
        for line_no, line in enumerate(f, 1):
            if line.strip():
                try: yield json.loads(line)
                except Exception as exc: raise ValueError(f"invalid JSON at {path}:{line_no}: {exc}")

def raw_match(e: dict[str, Any], hint: dict[str, Any], wallet: str) -> bool:
    if norm(e.get("target_address")) != wallet: return False
    if hint.get("tx_hash") and norm(e.get("transaction_hash")) != norm(hint["tx_hash"]): return False
    if hint.get("transaction_hash") and norm(e.get("transaction_hash")) != norm(hint["transaction_hash"]): return False
    if hint.get("family") and e.get("event_family") != hint["family"]: return False
    if hint.get("event_index") is not None and e.get("event_index") != hint["event_index"]: return False
    if hint.get("time") and dt(e["block_timestamp"]) != dt(hint["time"]): return False
    if hint.get("sequence_index") is not None and e.get("target_sequence_index") != hint["sequence_index"]: return False
    return True

class AsOfIndex:
    def __init__(self, cases_path: Path, events_path: Path, max_cases: int | None = None):
        raw_cases = list(load_jsonl(cases_path))
        if max_cases: raw_cases = raw_cases[:max_cases]
        # Project away all future/label fields at load time.  The verifier only
        # retains the as-of case key and the historical evidence hints.
        self.cases = [{k: c.get(k) for k in ("case_id", "wallet", "cutoff", "split", "evidence")}
                      for c in raw_cases]
        self.events = []
        for e in load_jsonl(events_path):
            e = dict(e); e["_id"] = event_id(e); e["_time"] = dt(e["block_timestamp"])
            e["_target"] = norm(e.get("target_address")); e["_cp"] = norm(e.get("counterparty_address"))
            e["_contract"] = norm(e.get("token_contract_address"))
            self.events.append(e)
        self.by_target = defaultdict(list)
        for e in self.events: self.by_target[e["_target"]].append(e)
        for rows in self.by_target.values(): rows.sort(key=event_sort_key)
        self.aliases = {}
        self.alias_ambiguity = {}
        for c in self.cases:
            w = norm(c["wallet"])
            for h in c.get("evidence", []):
                matches = [e for e in self.by_target[w] if raw_match(e, h, w)]
                key = f"{c['case_id']}::{h.get('evidence_id')}"
                if len(matches) == 1: self.aliases[key] = matches[0]["_id"]
                else: self.alias_ambiguity[key] = len(matches)

    def history(self, wallet: str, cutoff: Any):
        cut = dt(cutoff); return [e for e in self.by_target[norm(wallet)] if e["_time"] < cut]

    def resolve_evidence(self, case: dict[str, Any], raw_id: str) -> str | None:
        rid = str(raw_id)
        all_ids = {e["_id"] for e in self.history(case["wallet"], case["cutoff"])}
        if rid in all_ids: return rid
        key = f"{case['case_id']}::{rid}"
        resolved = self.aliases.get(key)
        return resolved if resolved in all_ids else None

    def event_map(self, history): return {e["_id"]: e for e in history}

def ext_out(e):
    return e.get("direction") == "outgoing" and e.get("event_family") == "external_tx" and bool(e.get("counterparty_address"))

def certificate_repeat(history, cutoff):
    cut = dt(cutoff); start = cut - timedelta(days=30)
    rows = [e for e in history if start <= e["_time"] < cut and ext_out(e)]
    by = defaultdict(list)
    for e in rows: by[e["_cp"]].append(e)
    # deterministic tie break after count and latest time
    ranked = sorted(by.items(), key=lambda kv: (-len(kv[1]), -max(x["_time"].value for x in kv[1]), kv[0]))
    if not ranked or len(ranked[0][1]) < 2:
        return {"status":"insufficient", "factor":"repeat_recency", "rule":{"op":"recent_repeat","window_days":30,"min_count":2}, "certificate":None,
                "metrics":{"recent_external_outgoing":len(rows),"top_count":len(ranked[0][1]) if ranked else 0}}
    top = ranked[0][1]
    cert = {"factor":"repeat_recency", "window":{"start":start.isoformat(),"end":cut.isoformat()},
            "counterparty":ranked[0][0], "count":len(top), "denominator":len(rows),
            "event_ids":[e["_id"] for e in sorted(top,key=event_sort_key)],
            "latest_event_id":max(top,key=event_sort_key)["_id"]}
    return {"status":"verified", "factor":"repeat_recency", "rule":{"op":"recent_repeat","window_days":30,"min_count":2}, "certificate":cert,
            "metrics":{"recent_external_outgoing":len(rows),"top_count":len(top),"distinct_counterparties":len(by)}}

def certificate_shift(history, cutoff):
    cut = dt(cutoff); recent0, recent1 = cut-timedelta(days=30), cut; prior0 = cut-timedelta(days=60)
    recent = [e for e in history if recent0 <= e["_time"] < recent1 and ext_out(e)]
    prior = [e for e in history if prior0 <= e["_time"] < recent0 and ext_out(e)]
    delta = len(recent)-len(prior)
    if not recent and not prior:
        return {"status":"insufficient", "factor":"activity_shift", "rule":{"op":"activity_shift","window_days":30,"baseline_days":30,"min_abs_delta":1}, "certificate":None,
                "metrics":{"recent_count":0,"prior_count":0,"delta":0}}
    if delta == 0:
        return {"status":"insufficient", "factor":"activity_shift", "rule":{"op":"activity_shift","window_days":30,"baseline_days":30,"min_abs_delta":1}, "certificate":None,
                "metrics":{"recent_count":len(recent),"prior_count":len(prior),"delta":0,"direction":"flat"}}
    direction = "up" if delta > 0 else "down"
    cert = {"factor":"activity_shift", "recent_window":{"start":recent0.isoformat(),"end":recent1.isoformat()},
            "prior_window":{"start":prior0.isoformat(),"end":recent0.isoformat()}, "recent_count":len(recent), "prior_count":len(prior), "delta":delta,
            "recent_event_ids":[e["_id"] for e in recent], "prior_event_ids":[e["_id"] for e in prior]}
    return {"status":"verified", "factor":"activity_shift", "rule":{"op":"activity_shift","window_days":30,"baseline_days":30,"min_abs_delta":1,"direction":direction}, "certificate":cert,
            "metrics":{"recent_count":len(recent),"prior_count":len(prior),"delta":delta,"direction":direction}}

def certificate_typed(index: AsOfIndex, history, cutoff, wallet):
    cut = dt(cutoff); w = norm(wallet)
    # A typed path is wallet --(outgoing external/token event, contract c)--> peer,
    # with peer --(outgoing event, same contract c)--> another counterparty, all before cutoff.
    first = [e for e in history if e["_target"] == w and e["_contract"] and e["_cp"] and e["_time"] < cut and e.get("direction") == "outgoing"]
    for a in sorted(first, key=event_sort_key, reverse=True):
        peer = a["_cp"]; c = a["_contract"]
        peer_rows = [e for e in index.by_target.get(peer, []) if e["_time"] < cut and e["_contract"] == c and e.get("direction") == "outgoing" and e.get("counterparty_address")]
        if peer_rows:
            b = sorted(peer_rows, key=event_sort_key)[-1]
            cert = {"factor":"typed_graph_path", "path_type":"shared_contract",
                    "nodes":[w,peer,norm(b.get("counterparty_address"))], "typed_edge":{"contract":c,"first_family":a.get("event_family"),"second_family":b.get("event_family")},
                    "event_ids":[a["_id"],b["_id"]], "cutoff":cut.isoformat()}
            return {"status":"verified", "factor":"typed_graph_path", "rule":{"op":"shared_contract_path","contract":c,"peer":peer}, "certificate":cert,
                    "metrics":{"candidate_first_events":len(first)}}
    return {"status":"insufficient", "factor":"typed_graph_path", "rule":{"op":"shared_contract_path"}, "certificate":None,
            "metrics":{"candidate_first_events":len(first)}}

def verify_proposal(index, case, proposal):
    history = index.history(case["wallet"], case["cutoff"]); em = index.event_map(history)
    p = proposal.get("proposal", proposal) if isinstance(proposal, dict) else {}
    factor = p.get("factor") or (p.get("labels") or [None])[0]
    ids = p.get("evidence_event_ids", p.get("event_ids", []))
    if not isinstance(ids, list): return {"status":"invalid_schema","reason":"evidence_event_ids must be list"}
    resolved = []; invalid = []
    for x in ids:
        r = index.resolve_evidence(case, x)
        (resolved if r else invalid).append(r or str(x))
    if invalid: return {"status":"invalid_evidence_id","factor":factor,"invalid_ids":invalid,"resolved_ids":resolved}
    if factor == "repeat_recency": base = certificate_repeat(history, case["cutoff"])
    elif factor == "activity_shift": base = certificate_shift(history, case["cutoff"])
    elif factor in ("typed_graph_path","shared_contract"): base = certificate_typed(index, history, case["cutoff"], case["wallet"])
    else: return {"status":"unknown_factor","factor":factor}
    expected = set((base.get("certificate") or {}).get("event_ids", []))
    if base["status"] != "verified": return {"status":"rule_insufficient","factor":factor,"executor":base}
    if not set(resolved).issubset(expected): return {"status":"evidence_not_witness", "factor":factor,"resolved_ids":resolved,"expected_witness_ids":sorted(expected)}
    return {"status":"verified", "factor":factor,"resolved_ids":resolved,"executor":base}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--cases", default="artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl")
    ap.add_argument("--events", default="artifacts/motif_hypothesis_eventlevel_20260927/raw_events.jsonl")
    ap.add_argument("--proposals", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-cases", type=int, default=None)
    args=ap.parse_args(); root=Path(args.root)
    cases_path=root/args.cases; events_path=root/args.events
    out=Path(args.out) if args.out else root/"artifacts/factor_certificate_verifier_v2_20260930"
    out.mkdir(parents=True, exist_ok=False)
    index=AsOfIndex(cases_path, events_path, args.max_cases)
    rows=[]; cert_path=out/"factor_certificates.jsonl"
    with cert_path.open("w") as f:
        for c in index.cases:
            h=index.history(c["wallet"],c["cutoff"])
            factors=[certificate_repeat(h,c["cutoff"]), certificate_shift(h,c["cutoff"]), certificate_typed(index,h,c["cutoff"],c["wallet"])]
            item={"case_id":c["case_id"],"wallet":c["wallet"],"cutoff":c["cutoff"],"history_n":len(h),"factors":factors}
            f.write(json.dumps(item,ensure_ascii=False,default=str)+"\n")
            for x in factors: rows.append({"case_id":c["case_id"],"wallet":c["wallet"],"cutoff":c["cutoff"],"factor":x["factor"],"status":x["status"],"witness_n":len((x.get("certificate") or {}).get("event_ids",[])),"history_n":len(h)})
    pd.DataFrame(rows).to_csv(out/"factor_summary.csv",index=False)
    if args.proposals:
        ppath=root/args.proposals; vr=[]
        for p in load_jsonl(ppath):
            cid=p.get("case_id"); case=next((c for c in index.cases if c["case_id"]==cid),None)
            vr.append({"case_id":cid, **({"status":"unknown_case"} if case is None else verify_proposal(index,case,p))})
        with (out/"proposal_verification.jsonl").open("w") as f:
            for x in vr:f.write(json.dumps(x,ensure_ascii=False)+"\n")
        pd.DataFrame(vr).to_csv(out/"proposal_verification.csv",index=False)
    manifest={"version":"factor_certificate_verifier_v2_20260930","label_free":True,"future_labels_read":False,"cases":len(index.cases),"events":len(index.events),"evidence_alias_unique":len(index.aliases),"evidence_alias_ambiguous":len(index.alias_ambiguity),"cases_sha256":hashlib.sha256(cases_path.read_bytes()).hexdigest(),"events_sha256":hashlib.sha256(events_path.read_bytes()).hexdigest(),"outputs":sorted(p.name for p in out.iterdir())}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"out":str(out),"cases":len(index.cases),"events":len(index.events),"manifest":manifest},ensure_ascii=False))

if __name__=="__main__": main()
