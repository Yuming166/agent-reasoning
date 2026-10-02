#!/usr/bin/env python3
"""Build a bounded, offline human-review priority list from existing provisional timelines.

This ranks pending candidates for *manual account-side evidence review only*. It does
not promote wallet/X links, authorize collection, or claim historical as-of validity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

WINDOW_START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-09-24T17:24:10+00:00")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def analyze(workbook, profile_leads, metrics, edges, confirmed_seed_rows,
            text_priority_n: int = 6):
    if text_priority_n < 0:
        raise ValueError("text_priority_n must be nonnegative")
    by_id = {r["x_user_id"].strip(): r for r in workbook}
    if len(workbook) != 231 or len(by_id) != 231:
        raise ValueError("expected 231 unique frozen-frame X IDs")
    arm_counts = Counter(r.get("review_arm", "") for r in workbook)
    if arm_counts != Counter({"stratified_probability_sample_60": 60,
                              "targeted_nonprobability_complement_171": 171}):
        raise ValueError(f"unexpected frozen review-arm counts: {dict(arm_counts)}")
    leads = {r["x_user_id"].strip(): r for r in profile_leads}
    if len(leads) != 231 or set(leads) != set(by_id):
        raise ValueError("profile evidence leads must exactly cover frozen candidate frame")
    met = {r["x_user_id"].strip(): r for r in metrics}
    if len(met) != len(metrics) or len(met) != 50 or not set(met) <= set(by_id):
        raise ValueError("timeline metrics contain duplicate IDs or IDs outside frozen frame")
    if any(r.get("crosswalk_status") != "candidate_unconfirmed_not_eligible_for_shortlist" for r in metrics):
        raise ValueError("timeline metrics must remain marked provisional/unconfirmed")
    seed_ids = {r["x_user_id"].strip() for r in confirmed_seed_rows}
    pilot_ids = set(met)

    # Count events only where a provisional-pilot source addresses an ID in the
    # frozen candidate frame. Source timeline data remains quarantined/provisional.
    pair_events = defaultdict(list)
    seed_edge_count = 0
    for e in edges:
        src, dst = e["source_x_user_id"].strip(), e["target_x_user_id"].strip()
        if src not in pilot_ids:
            raise ValueError(f"edge source outside the 50-account pilot: {src}")
        event_time = datetime.fromisoformat(e["created_at_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
        if not WINDOW_START <= event_time < WINDOW_END:
            raise ValueError(f"interaction edge outside the fixed study window: {e['created_at_utc']}")
        if dst in seed_ids:
            seed_edge_count += 1
        if dst in by_id and dst != src:
            pair_events[(src, dst)].append(e)

    node_pairs = defaultdict(set)
    node_events = Counter()
    for pair, observations in pair_events.items():
        for uid in pair:
            node_pairs[uid].add(pair)
            node_events[uid] += len(observations)

    pair_rows = []
    for (src, dst), obs in sorted(pair_events.items()):
        sm, dm = met.get(src, {}), met.get(dst, {})
        pair_rows.append({
            "source_x_user_id": src,
            "source_handle_at_audit": by_id[src]["handle_at_profile_audit"],
            "source_review_arm": by_id[src]["review_arm"],
            "source_review_state": by_id[src].get("manual_verdict", "pending"),
            "source_authored_posts_observed_lower_bound": sm.get("authored_posts_observed_in_window", ""),
            "target_x_user_id": dst,
            "target_handle_at_audit": by_id[dst]["handle_at_profile_audit"],
            "target_review_arm": by_id[dst]["review_arm"],
            "target_review_state": by_id[dst].get("manual_verdict", "pending"),
            "target_authored_posts_observed_lower_bound": dm.get("authored_posts_observed_in_window", ""),
            "observed_edge_event_count": len(obs),
            "event_types": ";".join(sorted({e["event_type"] for e in obs})),
            "months_utc": ";".join(sorted({e["created_at_utc"][:7] for e in obs})),
            "both_wallet_x_links_unconfirmed": "true",
        })

    pending_targeted = {uid for uid, row in by_id.items()
                        if row["review_arm"] == "targeted_nonprobability_complement_171"
                        and row.get("manual_verdict", "pending") == "pending"}
    bridge_ids = {uid for uid in pending_targeted if node_pairs[uid]}
    rows = []
    for uid in bridge_ids:
        row, lead, m = by_id[uid], leads[uid], met.get(uid, {})
        roles = sorted({"source" if p[0] == uid else "target" for p in node_pairs[uid]})
        rows.append({
            "priority_tier": "A_candidate_frame_interaction_bridge_review",
            "priority_rank": "",
            "address": row["address"], "x_user_id": uid,
            "handle_at_profile_audit": row["handle_at_profile_audit"],
            "review_arm": row["review_arm"], "manual_verdict": row.get("manual_verdict", "pending"),
            "profile_evidence_lead_type_not_adjudicated": lead.get("evidence_lead_type", ""),
            "candidate_events_2026": row.get("candidate_events_2026", ""),
            "authored_posts_observed_lower_bound": m.get("authored_posts_observed_in_window", ""),
            "nonempty_authored_posts_observed_lower_bound": m.get("nonempty_authored_posts_observed_in_window", ""),
            "unique_external_neighbors_observed_lower_bound": m.get("unique_external_interaction_neighbors_observed", ""),
            "candidate_frame_pair_count": len(node_pairs[uid]),
            "candidate_frame_edge_events": node_events[uid],
            "candidate_frame_edge_roles": ";".join(roles),
            "timeline_stop_reason": m.get("stop_reason", "not_in_pilot"),
            "review_only_not_collection_authorization": "true",
        })

    # Add high-text-volume provisional sources that have no observed edge to the
    # frozen candidate frame. This is only a review priority; the 60-row random
    # probability arm is never ranked into the targeted complement.
    text_candidates = []
    for uid in pilot_ids & pending_targeted:
        if uid in bridge_ids:
            continue
        m = met[uid]
        posts = int(m.get("nonempty_authored_posts_observed_in_window", "0") or 0)
        if posts <= 0:
            continue
        row, lead = by_id[uid], leads[uid]
        text_candidates.append((posts,
            int(m.get("unique_external_interaction_neighbors_observed", "0") or 0),
            int(row.get("candidate_events_2026", "0") or 0),
            uid, row, lead, m))
    text_candidates.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
    for posts, neighbors, _, uid, row, lead, m in text_candidates[:text_priority_n]:
        rows.append({
            "priority_tier": "B_text_coverage_review_no_observed_candidate_frame_edge",
            "priority_rank": "",
            "address": row["address"], "x_user_id": uid,
            "handle_at_profile_audit": row["handle_at_profile_audit"],
            "review_arm": row["review_arm"], "manual_verdict": row.get("manual_verdict", "pending"),
            "profile_evidence_lead_type_not_adjudicated": lead.get("evidence_lead_type", ""),
            "candidate_events_2026": row.get("candidate_events_2026", ""),
            "authored_posts_observed_lower_bound": m.get("authored_posts_observed_in_window", ""),
            "nonempty_authored_posts_observed_lower_bound": posts,
            "unique_external_neighbors_observed_lower_bound": neighbors,
            "candidate_frame_pair_count": 0,
            "candidate_frame_edge_events": 0,
            "candidate_frame_edge_roles": "",
            "timeline_stop_reason": m.get("stop_reason", ""),
            "review_only_not_collection_authorization": "true",
        })

    # Tier A is sorted by observed frame-pair connectivity; Tier B by text and
    # external-neighbor lower bounds. Neither score is a probability or a verdict.
    rows.sort(key=lambda r: (
        0 if r["priority_tier"].startswith("A_") else 1,
        -int(r["candidate_frame_pair_count"]),
        -int(r["candidate_frame_edge_events"]),
        -int(r["nonempty_authored_posts_observed_lower_bound"] or 0),
        -int(r["unique_external_neighbors_observed_lower_bound"] or 0),
        -int(r["candidate_events_2026"] or 0),
        r["x_user_id"],
    ))
    for i, r in enumerate(rows, 1):
        r["priority_rank"] = i
    stats = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_existing_provisional_timeline_manual_review_priority_only",
        "network_requests": 0, "paid_queries_usd": 0,
        "workbook_modified": False, "candidate_verdicts_assigned": 0,
        "mapping_promotions": 0, "timeline_collection_authorized": False,
        "candidate_frame_rows": len(workbook),
        "review_arm_counts": dict(arm_counts),
        "probability_arm_rows_excluded_from_targeted_ranking": arm_counts["stratified_probability_sample_60"],
        "provisional_timeline_accounts": len(pilot_ids),
        "targeted_pending_accounts_with_candidate_frame_edges": len(bridge_ids),
        "candidate_frame_directed_pairs": len(pair_rows),
        "candidate_frame_edge_events": sum(len(x) for x in pair_events.values()),
        "provisional_candidate_to_confirmed_seed_edge_events": seed_edge_count,
        "review_shortlist_rows": len(rows),
        "tier_a_bridge_review_rows": sum(r["priority_tier"].startswith("A_") for r in rows),
        "tier_b_text_review_rows": sum(r["priority_tier"].startswith("B_") for r in rows),
        "text_priority_requested": text_priority_n,
        "limitations": [
            "All 50 timeline links remain unconfirmed and quarantined; observed posts/edges are not wallet-linked data.",
            "Candidate-frame mentions/quotes are review leads only; both endpoint wallet-X links require independent account-side adjudication.",
            "No provisional timeline edge from this pilot targeted a currently confirmed seed X ID.",
            "Observed post/neighbor counts are lower bounds; page ceiling/cursor exhaustion does not prove history completeness.",
            "The 60-row stratified probability sample remains separate and must be adjudicated for weighted quality estimates.",
            "Profile exact-string leads are not adjudications. This priority list is not a collection allowlist.",
        ],
    }
    return pair_rows, rows, stats


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    if not fields:
        fields = ["source_x_user_id", "target_x_user_id"] if "pair" in path.name else ["priority_tier", "priority_rank", "address", "x_user_id"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, required=True)
    ap.add_argument("--profile-leads", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--edges", type=Path, required=True)
    ap.add_argument("--confirmed-seed", type=Path, required=True)
    ap.add_argument("--text-priority-n", type=int, default=6)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    pair_rows, priority, stats = analyze(read_csv(a.workbook), read_csv(a.profile_leads),
        read_csv(a.metrics), read_csv(a.edges), read_csv(a.confirmed_seed), a.text_priority_n)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    pair_path = a.out_dir / "provisional_candidate_frame_interactions.csv"
    priority_path = a.out_dir / "targeted_manual_review_priority.csv"
    write_csv(pair_path, pair_rows); write_csv(priority_path, priority)
    inputs = {str(p): sha256(p) for p in [a.workbook, a.profile_leads, a.metrics, a.edges, a.confirmed_seed]}
    stats["inputs_sha256"] = inputs
    stats["outputs_sha256"] = {pair_path.name: sha256(pair_path), priority_path.name: sha256(priority_path)}
    (a.out_dir / "manifest.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k not in {"limitations", "inputs_sha256", "outputs_sha256"}}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
