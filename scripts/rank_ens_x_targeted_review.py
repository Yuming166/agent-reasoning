#!/usr/bin/env python3
"""Rank a bounded, offline follow-up manual-review queue for ENS↔X candidates.

Uses archived profile metadata and already-collected, timestamped interaction edges.
It performs no network/cloud access and grants no timeline-collection authorization.
Scores are transparent ordering fields, not probabilities. Lifetime profile tweet
counts are only a coarse text-volume proxy, never evidence of 2026 text coverage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_profile_tweet_count(repo: Path, row: dict[str, str]) -> tuple[int | None, str]:
    rel = row.get("profile_raw_file", "").strip()
    if not rel:
        return None, "missing_profile_path"
    path = (repo / rel).resolve()
    try:
        path.relative_to(repo.resolve())
    except ValueError:
        return None, "profile_path_outside_repo"
    if not path.is_file():
        return None, "profile_file_missing"
    expected = row.get("profile_raw_sha256", "").strip()
    if expected and sha256(path) != expected:
        return None, "profile_sha256_mismatch"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("data", {}).get("user", {}).get("tweets")
        if isinstance(raw, int) and raw >= 0:
            return raw, "lifetime_profile_counter"
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return None, "tweet_counter_unavailable"


def build_queue(candidates, sampled_pairs, confirmed, edges, repo, limit):
    sampled = {(r.get("address", "").lower(), r.get("x_user_id", "")) for r in sampled_pairs}
    confirmed_ids = {r["x_user_id"].strip() for r in confirmed if r.get("x_user_id", "").strip()}
    # Only edges authored by an already account-confirmed seed are evidence of a
    # currently observed bridge. Candidate identity remains unconfirmed.
    inbound = defaultdict(list)
    for edge in edges:
        source = edge.get("source_x_user_id", "").strip()
        target = edge.get("target_x_user_id", "").strip()
        if source in confirmed_ids and target:
            inbound[target].append(edge)

    remaining = []
    excluded_sample = 0
    for row in candidates:
        uid = row.get("x_user_id", "").strip()
        pair = (row.get("address", "").lower(), uid)
        if pair in sampled:
            excluded_sample += 1
            continue
        tweet_count, tweet_source = get_profile_tweet_count(repo, row)
        links = inbound.get(uid, [])
        source_ids = sorted({e["source_x_user_id"] for e in links})
        months = sorted({e.get("created_at_utc", "")[:7] for e in links if e.get("created_at_utc")})
        evidence_types = set(filter(None, row.get("evidence_types", "").split(";")))
        evidence_rank = 2 if "full_wallet_address" in evidence_types else 1
        remaining.append({
            "address": row.get("address", ""),
            "x_user_id": uid,
            "handle_at_profile_audit": row.get("handle_at_profile_audit", ""),
            "reverse_ens_name": row.get("reverse_ens_name", ""),
            "review_stratum": row.get("review_stratum", ""),
            "candidate_review_status": row.get("manual_verdict", "pending"),
            "profile_evidence_types": row.get("evidence_types", ""),
            "chain_events_2026": int(row.get("events_2026", "0") or 0),
            "confirmed_seed_inbound_edge_count": len(links),
            "distinct_confirmed_seed_sources": len(source_ids),
            "confirmed_seed_edge_months": ";".join(months),
            "profile_lifetime_tweet_count_proxy": "" if tweet_count is None else tweet_count,
            "tweet_proxy_source": tweet_source,
            "already_confirmed_x_user_id": str(uid in confirmed_ids).lower(),
            "priority_basis": "confirmed_seed_bridge_then_lifetime_tweet_proxy_then_chain_activity_then_full_address_evidence",
            "timeline_collection_authorized": "false",
        })
    # Accounts already in the confirmed seed add no new text author; retain them
    # in the audit tail for possible multi-wallet adjudication, not in top-N.
    fresh = [r for r in remaining if r["already_confirmed_x_user_id"] == "false"]
    fresh.sort(key=lambda r: (
        -int(r["distinct_confirmed_seed_sources"]),
        -int(r["confirmed_seed_inbound_edge_count"]),
        -(int(r["profile_lifetime_tweet_count_proxy"]) if str(r["profile_lifetime_tweet_count_proxy"]).isdigit() else -1),
        -int(r["chain_events_2026"]),
        -int("full_wallet_address" in r["profile_evidence_types"].split(";")),
        r["x_user_id"], r["address"].lower(),
    ))
    for i, row in enumerate(fresh, 1):
        row["targeted_review_rank"] = i
        row["queue_partition"] = "new_account_candidate"
    dup_rank_start = len(fresh) + 1
    dupes = [r for r in remaining if r["already_confirmed_x_user_id"] == "true"]
    dupes.sort(key=lambda r: (-int(r["chain_events_2026"]), r["x_user_id"], r["address"].lower()))
    for i, row in enumerate(dupes, dup_rank_start):
        row["targeted_review_rank"] = i
        row["queue_partition"] = "existing_confirmed_x_id_multi_wallet_check_not_new_text"
    ordered = fresh + dupes
    top = fresh[:limit]
    stats = {
        "candidate_rows": len(candidates), "representative_sample_rows_excluded": excluded_sample,
        "remaining_rows": len(remaining), "remaining_new_x_ids": len(fresh),
        "remaining_already_confirmed_x_ids": len(dupes), "recommended_top_n": min(limit, len(top)),
        "recommended_top_n_with_seed_bridge": sum(int(r["distinct_confirmed_seed_sources"]) > 0 for r in top),
        "recommended_top_n_with_tweet_counter": sum(str(r["profile_lifetime_tweet_count_proxy"]).isdigit() for r in top),
        "recommended_top_n_with_full_wallet_address_profile_hit": sum("full_wallet_address" in r["profile_evidence_types"].split(";") for r in top),
        "limitations": [
            "This is a targeted manual-review queue, not a confirmed crosswalk or a collection authorization.",
            "Only timestamped edges authored by the 12 currently confirmed seed IDs are counted; candidate IDs remain unconfirmed.",
            "Lifetime profile tweet counters are not counts of posts in the study window and do not establish text coverage.",
            "Current wallet links are snapshots and are not historical as-of validated.",
            "The separate 60-row stratified probability sample must remain intact and be reviewed for design-based quality estimates.",
        ],
    }
    return ordered, top, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--sample", type=Path, required=True)
    ap.add_argument("--confirmed", type=Path, required=True)
    ap.add_argument("--edges", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if args.limit < 1:
        ap.error("--limit must be positive")
    rows, top, stats = build_queue(read_csv(args.candidates), read_csv(args.sample),
                                   read_csv(args.confirmed), read_csv(args.edges),
                                   args.repo, args.limit)
    fields = ["targeted_review_rank", "queue_partition", "address", "x_user_id",
              "handle_at_profile_audit", "reverse_ens_name", "review_stratum",
              "candidate_review_status", "profile_evidence_types", "chain_events_2026",
              "confirmed_seed_inbound_edge_count", "distinct_confirmed_seed_sources",
              "confirmed_seed_edge_months", "profile_lifetime_tweet_count_proxy",
              "tweet_proxy_source", "already_confirmed_x_user_id", "priority_basis",
              "timeline_collection_authorized"]
    write_csv(args.out, rows, fields)
    stats["top_n_x_user_ids"] = [r["x_user_id"] for r in top]
    stats["queue_csv_sha256"] = sha256(args.out)
    stats["source_sha256"] = {str(p): sha256(p) for p in
                               [args.candidates, args.sample, args.confirmed, args.edges]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "top_n_x_user_ids"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
