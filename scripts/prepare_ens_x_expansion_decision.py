#!/usr/bin/env python3
"""Prepare a deterministic, offline-only ENS↔X candidate review and expansion bundle.

This script does not make network requests, change labels, or treat profile matches
as confirmed identity links. It uses already archived artifacts only.
"""
from __future__ import annotations


import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

SEED = 20260925
VERDICTS = ("account_confirms", "ens_only", "conflict", "unverifiable")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def activity_band(n: int) -> str:
    return "1_50" if n <= 50 else ("51_500" if n <= 500 else "501_plus")


def year_band(value: str) -> str:
    try:
        y = int(value[:4])
    except (ValueError, TypeError):
        return "unknown"
    return "le_2023" if y <= 2023 else ("2024" if y == 2024 else "2025_2026")


def evidence_family(types: str) -> str:
    vals = set(types.split(";"))
    a = "full_wallet_address" in vals
    b = "exact_reverse_ens_name" in vals
    return "wallet_and_ens" if a and b else ("wallet_address" if a else "ens_name")


def allocate_stratified_sample(groups: dict[str, list[dict]], n_total: int, seed: int):
    """Proportional allocation with >=2 per non-census stratum when feasible."""
    nonempty = {k: v for k, v in groups.items() if v}
    n_total = min(n_total, sum(map(len, nonempty.values())))
    minimum = {k: min(2, len(v)) for k, v in nonempty.items()}
    if n_total < sum(minimum.values()):
        raise ValueError(f"Sample size must be at least {sum(minimum.values())} for two-per-stratum allocation")
    alloc = dict(minimum)
    capacity = {k: len(v) - alloc[k] for k, v in nonempty.items()}
    remaining = n_total - sum(alloc.values())
    while remaining:
        eligible = [k for k in nonempty if capacity[k] > 0]
        if not eligible:
            break
        mass = sum(len(nonempty[k]) for k in eligible)
        quotas = {k: remaining * len(nonempty[k]) / mass for k in eligible}
        floors = {k: min(capacity[k], math.floor(quotas[k])) for k in eligible}
        used = sum(floors.values())
        for k, v in floors.items():
            alloc[k] += v
            capacity[k] -= v
        remaining -= used
        if not remaining:
            break
        ranked = sorted((k for k in eligible if capacity[k] > 0),
                        key=lambda k: (-(quotas[k] - math.floor(quotas[k])), k))
        if not ranked:
            break
        for k in ranked:
            if not remaining:
                break
            alloc[k] += 1
            capacity[k] -= 1
            remaining -= 1
    if remaining:
        raise RuntimeError(f"Stratified allocation left {remaining} unallocated rows")
    rng = random.Random(seed)
    sample = []
    for key, values in sorted(nonempty.items()):
        n_h = min(alloc[key], len(values))
        picks = rng.sample(values, n_h)
        for row in picks:
            x = dict(row)
            x.update({"sampling_stratum": key, "stratum_population_N": len(values),
                      "stratum_sample_n": n_h, "inclusion_probability": n_h / len(values),
                      "design_weight": len(values) / n_h, "sampling_seed": seed})
            sample.append(x)
    return sample, alloc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--sample-size", type=int, default=60)
    ap.add_argument("--next-profile-budget", type=int, default=100)
    args = ap.parse_args()
    root = args.root.resolve()
    base = root / "artifacts/ens_x_crosswalk"
    prof = base / "profile_expansion_20260925"
    pilot = base / "timeline_expansion_pilot_20260925"
    seed = base / "two_graph_seed_20260925"
    out = base / "expansion_decision_20260925"
    out.mkdir(parents=True, exist_ok=True)

    pair_rows = read_csv(base / "pairs_stratified_frame.csv")
    valid_rows = read_csv(base / "bidirectional_validation.csv")
    validation = defaultdict(set)
    for r in valid_rows:
        if r["status"] == "bidirectional_ok":
            validation[(r["address"].lower(), r["handle"].lower())].add(r["reverse_name"] or "")

    # Complete active, currently bidirectional address↔handle candidate frame.
    active = {}
    for r in pair_rows:
        key = (r["address"].lower(), r["handle"].lower())
        ev = int(float(r["events_2026"] or 0))
        if key not in validation or ev <= 0:
            continue
        k = (key[0], key[1], r["record_set_at"])
        old = active.get(k)
        reverse_names = sorted(x for x in validation[key] if x)
        item = {"address": key[0], "handle": r["handle"], "record_set_at": r["record_set_at"],
                "record_tx_hash": r.get("transaction_hash", ""), "resolver": r.get("resolver", ""),
                "addr_set_at": r.get("addr_set_at", ""), "events_2026": ev,
                "selection_stratum": "not_in_frozen_2000",
                "reverse_ens_name": reverse_names[0] if len(reverse_names) == 1 else "",
                "reverse_ens_name_candidates_json": json.dumps(reverse_names, separators=(",", ":")),
                "reverse_name_count": len(reverse_names)}
        if old is None or ev > old["events_2026"]:
            active[k] = item

    audits = [json.loads(line) for line in (prof / "profile_audit_results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    audit_by_handle = {r["handle_requested"].lower(): r for r in audits}
    for row in active.values():
        a = audit_by_handle.get(row["handle"].lower())
        row["profile_audit_classification"] = a["classification"] if a else "not_profile_audited"
        row["x_user_id"] = str(a.get("x_user_id") or "") if a else ""
        row["profile_http_status"] = str(a.get("http_status") or "") if a else ""
        row["profile_audit_at_utc"] = a.get("fetched_at_utc", "") if a else ""
        row["profile_raw_file"] = a.get("raw_file", "") if a else ""
        row["profile_raw_sha256"] = a.get("raw_sha256", "") if a else ""
        row["profile_evidence_type"] = ""
        row["profile_evidence_field"] = ""
        row["manual_verdict"] = "pending"
        row["historical_asof_status"] = "not_reconstructed"

    # Account-level event totals and active months from archived local data.
    monthly_path = base / "final_validated_address_month_events_2026.parquet"
    monthly_rows = pq.read_table(monthly_path, columns=["address", "month", "total"]).to_pylist()
    activity = defaultdict(lambda: {"events": 0, "months": 0, "month_events": {}})
    for r in monthly_rows:
        a = str(r["address"]).lower()
        n = int(r["total"] or 0)
        activity[a]["events"] += n
        activity[a]["months"] += int(n > 0)
        activity[a]["month_events"][str(r["month"])] = n
    for row in active.values():
        m = activity.get(row["address"], {"events": row["events_2026"], "months": 0, "month_events": {}})
        row["events_2026_validated_monthly_source"] = m["events"]
        row["active_months_2026"] = m["months"]

    # Existing timeline pilot coverage and graph indicators are discovery signals only.
    coverage = {r["x_user_id"]: r for r in read_csv(pilot / "coverage.jsonl")} if False else {}
    coverage = {}
    for line in (pilot / "coverage.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line); coverage[str(r["x_user_id"])] = r
    posts = Counter()
    for line in (pilot / "provisional_x_authored_posts.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            posts[str(json.loads(line)["x_user_id"])] += 1
    edges = read_csv(pilot / "provisional_x_interaction_edges_temporal.csv")
    inbound = Counter(str(e["target_x_user_id"]) for e in edges)
    outbound = Counter(str(e["source_x_user_id"]) for e in edges)
    target_ids_by_source = defaultdict(set)
    for e in edges:
        target_ids_by_source[str(e["source_x_user_id"])].add(str(e["target_x_user_id"]))
    for row in active.values():
        uid = row["x_user_id"]
        c = coverage.get(uid, {})
        row["pilot_authored_posts"] = posts[uid]
        row["pilot_inbound_interaction_edges"] = inbound[uid]
        row["pilot_outbound_interaction_edges"] = outbound[uid]
        row["pilot_pages"] = c.get("pages", "")
        row["pilot_stop_reason"] = c.get("stop_reason", "")
        row["pilot_direct_link_edges_observed"] = int(inbound[uid] + outbound[uid] > 0)
        row["expansion_priority_reason"] = (
            "pilot_graph_observed_target_or_source" if inbound[uid] + outbound[uid] else
            ("authored_text_observed" if posts[uid] else "chain_activity_only_unprofiled_or_unobserved"))

    all_active = list(active.values())
    # A pair-level audit queue keeps ENS pair evidence and profile evidence separate.
    fields = ["address", "handle", "x_user_id", "reverse_ens_name", "reverse_ens_name_candidates_json",
              "reverse_name_count", "record_set_at", "addr_set_at", "record_tx_hash", "resolver",
              "events_2026", "events_2026_validated_monthly_source",
              "active_months_2026", "selection_stratum", "profile_audit_classification",
              "profile_http_status", "profile_audit_at_utc", "profile_raw_file", "profile_raw_sha256",
              "profile_evidence_type", "profile_evidence_field", "pilot_authored_posts",
              "pilot_inbound_interaction_edges", "pilot_outbound_interaction_edges", "pilot_pages",
              "pilot_stop_reason", "pilot_direct_link_edges_observed", "expansion_priority_reason",
              "manual_verdict", "historical_asof_status"]
    # First write the complete extant active pair universe (not just 231 exact matches).
    all_active.sort(key=lambda r: (-int(r["events_2026"]), r["address"], r["handle"].lower()))
    write_csv(out / "active_bidirectional_pair_review_universe.csv", all_active, fields)

    exact = read_csv(prof / "account_side_exact_match_candidates.csv")
    exact_by_pair = {(r["address"].lower(), str(r["x_user_id"])): r for r in exact}
    for row in all_active:
        e = exact_by_pair.get((row["address"].lower(), str(row.get("x_user_id", ""))))
        row["profile_evidence_type"] = e.get("evidence_types", "") if e else ""
        row["profile_evidence_field"] = e.get("evidence_fields", "") if e else ""
        row["profile_candidate_pair_match"] = bool(e)
    write_csv(out / "active_bidirectional_pair_review_universe.csv", all_active, fields + ["profile_candidate_pair_match"])
    # Preserve all prior evidence and append fields needed for auditable independent review.
    review_fields = list(exact[0].keys()) + ["review_stratum", "manual_verdict", "reviewer",
        "reviewed_at_utc", "x_profile_evidence_url", "evidence_quote_or_capture_id",
        "evidence_seen_at_utc", "review_notes", "historical_asof_status"]
    full_review = []
    for r in exact:
        rr = dict(r)
        types = r["evidence_types"]
        fam = evidence_family(types)
        ev = int(float(r["events_2026"] or 0))
        rr["review_stratum"] = "|".join([r["selection_stratum"], year_band(r["ens_record_set_at"]), fam, activity_band(ev)])
        rr.update({"manual_verdict": "pending", "reviewer": "", "reviewed_at_utc": "",
                   "x_profile_evidence_url": "", "evidence_quote_or_capture_id": "",
                   "evidence_seen_at_utc": "", "review_notes": "",
                   "historical_asof_status": "not_reconstructed"})
        full_review.append(rr)
    write_csv(out / "candidate_review_full_231.csv", full_review, review_fields)
    groups = defaultdict(list)
    for r in full_review:
        groups[r["review_stratum"]].append(r)
    sample, allocation = allocate_stratified_sample(groups, args.sample_size, SEED)
    sample_fields = review_fields + ["sampling_stratum", "stratum_population_N", "stratum_sample_n",
                                     "inclusion_probability", "design_weight", "sampling_seed"]
    write_csv(out / f"candidate_review_stratified_sample_{len(sample)}.csv", sample, sample_fields)

    # Rank candidate links already found, keeping identity confirmation pending.
    profile = {r["address"].lower(): r for r in exact}
    candidate_ranked = []
    for r in full_review:
        uid = r["x_user_id"]
        c = coverage.get(uid, {})
        rr = dict(r)
        rr["pilot_authored_posts"] = posts[uid]
        rr["pilot_inbound_interaction_edges"] = inbound[uid]
        rr["pilot_outbound_interaction_edges"] = outbound[uid]
        rr["pilot_pages"] = c.get("pages", "")
        rr["pilot_stop_reason"] = c.get("stop_reason", "")
        rr["priority_reason"] = "existing_pilot_graph_overlap" if inbound[uid] + outbound[uid] else (
            "existing_pilot_authored_text" if posts[uid] else "higher_chain_activity" )
        candidate_ranked.append(rr)
    candidate_ranked.sort(key=lambda r: (
        -(int(r["pilot_inbound_interaction_edges"]) + int(r["pilot_outbound_interaction_edges"])),
        -int(r["pilot_authored_posts"]), -int(float(r["events_2026"] or 0)),
        r["address"]))
    rank_fields = review_fields + ["pilot_authored_posts", "pilot_inbound_interaction_edges",
        "pilot_outbound_interaction_edges", "pilot_pages", "pilot_stop_reason", "priority_reason"]
    for i, r in enumerate(candidate_ranked, 1): r["priority_rank"] = i
    rank_fields.append("priority_rank")
    write_csv(out / "candidate_review_priority_231.csv", candidate_ranked, rank_fields)

    # Select new, not-yet-profile-audited handles from the full active/bidirectional pool.
    # Prefer handles already observed on the pilot graph, then wallet activity. No API yet.
    known_handles = set(audit_by_handle)
    handle_groups = defaultdict(list)
    for r in all_active:
        h = r["handle"].lower()
        if h not in known_handles:
            handle_groups[h].append(r)
    node_rows = read_csv(pilot / "provisional_x_interaction_nodes.csv")
    graph_handles = set()
    graph_ids_by_handle = defaultdict(set)
    for r in node_rows:
        uid = str(r["x_user_id"])
        for h in (x.strip().lstrip("@").lower() for x in (r.get("observed_handles") or "").split(";") if x.strip()):
            graph_handles.add(h)
            graph_ids_by_handle[h].add(uid)
    pilot_in = Counter(str(e["target_x_user_id"]) for e in edges)
    pilot_out = Counter(str(e["source_x_user_id"]) for e in edges)
    next_handles = []
    for h, rows in handle_groups.items():
        rows.sort(key=lambda r: -int(r["events_2026"]))
        observed_ids = graph_ids_by_handle.get(h, set())
        observed_edge_count = sum(pilot_in[uid] + pilot_out[uid] for uid in observed_ids)
        next_handles.append({"handle": rows[0]["handle"], "active_pair_count": len(rows),
             "active_wallet_count": len({x["address"] for x in rows}),
             "max_events_2026": max(int(x["events_2026"]) for x in rows),
             "total_events_2026_across_pairs_not_deduplicated": sum(int(x["events_2026"]) for x in rows),
             "pilot_observed_handle": h in graph_handles,
             "pilot_observed_x_user_ids_json": json.dumps(sorted(observed_ids), separators=(",", ":")),
             "pilot_interaction_edge_count_for_observed_x_ids": observed_edge_count,
             "selection_scope": "profile_audit_queue_only_not_timeline_authorization",
             "all_address_pairs_json": json.dumps([{k: x.get(k, "") for k in ("address", "record_set_at", "events_2026", "resolver")} for x in rows], separators=(",", ":")),
             "selection_status": "not_yet_profile_audited", "confirmation_status": "not_established"})
    next_handles.sort(key=lambda r: (-int(r["pilot_interaction_edge_count_for_observed_x_ids"]),
                                     -int(r["max_events_2026"]), r["handle"].lower()))
    queue = next_handles[:max(0, args.next_profile_budget)]
    for i, r in enumerate(queue, 1):
        r["priority_rank"] = i
        r["priority_reason"] = ("pilot_external_node_with_observed_edges; not a confirmed wallet-X link"
                                if int(r["pilot_interaction_edge_count_for_observed_x_ids"]) else
                                "high_2026_chain_activity; no pilot graph overlap")
    next_fields = ["priority_rank", "handle", "active_pair_count", "active_wallet_count", "max_events_2026",
        "total_events_2026_across_pairs_not_deduplicated", "pilot_observed_handle",
        "pilot_observed_x_user_ids_json", "pilot_interaction_edge_count_for_observed_x_ids",
        "selection_scope", "priority_reason",
        "all_address_pairs_json", "selection_status", "confirmation_status"]
    write_csv(out / f"next_profile_audit_queue_{len(queue)}.csv", queue, next_fields)

    # Count identity/source coverage and enforce disjoint seed and auto-candidate cohorts.
    seed_rows = read_csv(seed / "crosswalk_confirmed_unique.csv")
    seed_pairs = {(r["address"].lower(), str(r.get("x_user_id", ""))) for r in seed_rows}
    candidate_pairs = {(r["address"].lower(), str(r["x_user_id"])) for r in exact}
    overlap = seed_pairs & candidate_pairs
    classification = Counter(r["classification"] for r in audits)
    selection = Counter(r["selection_stratum"] for r in audits)
    evidence_types = Counter(x for r in exact for x in r["evidence_types"].split(";") if x)
    evidence_fields = Counter(x for r in exact for x in r["evidence_fields"].split(";") if x)
    verdict_counts = Counter(r["manual_verdict"] for r in read_csv(prof / "manual_review_50.csv"))
    pilot_summary = json.loads((pilot / "summary.json").read_text(encoding="utf-8"))
    seed_posts = sum(1 for line in (seed / "x_authored_posts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_artifact_audit_no_network_no_paid_queries",
        "generator_sha256": sha256(Path(__file__).resolve()),
        "source_sha256": {str(p.relative_to(root)): sha256(p) for p in [
            prof / "profile_audit_results.jsonl", prof / "account_side_exact_match_candidates.csv",
            prof / "manual_review_50.csv", base / "bidirectional_validation.csv",
            base / "pairs_stratified_frame.csv", monthly_path,
            pilot / "summary.json", pilot / "coverage.jsonl", pilot / "provisional_x_authored_posts.jsonl",
            pilot / "provisional_x_interaction_edges_temporal.csv", seed / "crosswalk_confirmed_unique.csv"]},
        "candidate_pool": {"profiled_handles": len(audits), "profile_classification": dict(classification),
            "profile_selection_stratum_handles": dict(selection), "auto_match_candidate_pairs": len(exact),
            "auto_match_addresses": len({r["address"].lower() for r in exact}),
            "auto_match_stable_x_user_ids": len({r["x_user_id"] for r in exact}),
            "seed_pairs": len(seed_pairs), "seed_candidate_pair_overlap": len(overlap),
            "auto_candidate_unique_pair_count": len(candidate_pairs),
            "auto_candidate_pairs_unique_address_user_id": len(candidate_pairs) == len(exact),
            "ens_bidirectional_2026_active_record_level_rows": len(all_active),
            "ens_bidirectional_2026_active_unique_address_handle_pairs": len({(r["address"], r["handle"].lower()) for r in all_active}),
            "ens_bidirectional_2026_active_unique_addresses": len({r["address"] for r in all_active}),
            "ens_bidirectional_2026_active_unique_handles": len({r["handle"].lower() for r in all_active}),
            "next_profile_queue_handles": len(queue), "remaining_unprofiled_active_handles": len(handle_groups)},
        "auto_match_evidence_types": dict(evidence_types), "auto_match_evidence_fields": dict(evidence_fields),
        "manual_review": {"legacy_50_rows": 50, "legacy_50_filled_verdicts": sum(n for v, n in verdict_counts.items() if v.strip()),
            "new_stratified_sample_size": len(sample), "strata_count": len(groups),
            "allocation": {k: {"N_h": len(groups[k]), "n_h": allocation.get(k, 0),
                                "pi_h": allocation.get(k, 0) / len(groups[k])} for k in sorted(groups)},
            "estimand_note": "Use stratum weights N_h/n_h only after independent manual verdicts are completed; do not use empty legacy labels."},
        "timeline_pilot": pilot_summary,
        "next_profile_selection": {"budget": args.next_profile_budget, "selected": len(queue),
            "rank_rule": "observed pilot external-node edge count, then max 2026 wallet events; profile audit only, no identity or timeline authorization",
            "api_requests_made_by_this_script": 0},
        "research_gates": {
            "mapping_gate": "Only manual_verdict=account_confirms with stable X user ID, dated evidence URL/capture, and no unresolved conflict enters confirmed crosswalk; profile text auto-matches stay candidates.",
            "profile_expansion_gate": f"One bounded FxEmbed profile batch of at most {len(queue)} new handles; preserve response/hash/status. Stop on 20 consecutive non-200s; no automatic timeline acquisition.",
            "bigquery_gate": "No BigQuery job was run. Reconstruct historical address+reverse+twitter records from event-level ENS logs only after metadata check, dry-run, and explicit maximumBytesBilled; local current/latest artifacts do not prove as-of validity.",
            "timeline_scale_gate": "Before larger timeline collection: require manually confirmed stable IDs; target >=30 confirmed accounts with usable authored-in-window text, report account/page coverage and truncation; require >=20 nodes with timestamped interaction and >=10 directly observed confirmed-to-confirmed edges before claiming a connected mapped social graph. Common external targets are covariates, not direct propagation.",
            "historical_gate": "Every prediction feature must use wallet mapping and ENS records effective strictly before cutoff; unresolved link intervals are excluded or explicitly unknown."},
        "limitations": [
            "No human identity verdict was inferred or filled by this script.",
            "A current FxEmbed profile exact string hit is a candidate, not independent proof of personhood/control.",
            "Historical as-of ENS links are not reconstructable from local latest AddrChanged and monthly aggregates alone.",
            "The 50-account timeline pilot is provisional; 41/50 hit page ceiling and repost action time is unavailable.",
            "The stratified sample is for manual quality review; it is not complete review of all 231 links.",
            "The active universe is record-level: multiple record timestamps may belong to the same address-handle pair.",
            "The follow-up handle queue is for bounded profile-audit prioritization only, not permission to collect timelines."],
    }
    (out / "expansion_decision_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "auto_candidates": len(exact), "active_pairs": len(all_active),
                      "review_sample": len(sample), "next_profile_queue": len(queue),
                      "report": str(out / 'expansion_decision_report.json')}, ensure_ascii=False))


if __name__ == "__main__":
    main()
