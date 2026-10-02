#!/usr/bin/env python3
"""Build an auditable seed X graph and wallet crosswalk from archived evidence.

This script makes no network requests. It intentionally excludes reposts from
timestamped edges because FxEmbed timestamps the original source post.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = root / "artifacts/ens_x_crosswalk"
    batch = source / "fx_authorized_batch_20260924T172410Z"
    continuation = batch / "continuation_20260924_fixed_window"
    verification_path = source / "verification_sample_v2_filled.csv"
    tweet_path = continuation / "combined_tweets_in_window.jsonl"

    with verification_path.open(newline="", encoding="utf-8") as handle:
        verified = [row for row in csv.DictReader(handle)
                    if row["verification_status"] == "account_confirms" and row["x_user_id"]]
    crosswalk = []
    for row in verified:
        crosswalk.append({
            "address": row["address"].lower(),
            "x_user_id": row["x_user_id"],
            "handle_at_verification": row["handle"],
            "ens_node": row["node"],
            "ens_status_at_verification": row["status"],
            "ens_record_set_at": row["record_set_at"],
            "account_evidence_date": row["evidence_date"],
            "account_evidence_note": row["evidence_note"],
            "source_pair_id": row["pair_id"],
            "temporal_link_status": "snapshot_only_not_as_of_validated",
        })
    pair_fields = list(crosswalk[0])
    write_csv(out / "crosswalk_evidence_pairs.csv", crosswalk, pair_fields)
    unique = {}
    for row in crosswalk:
        key = (row["address"], row["x_user_id"])
        if key not in unique:
            unique[key] = {k: row[k] for k in (
                "address", "x_user_id", "handle_at_verification", "account_evidence_date",
                "temporal_link_status")}
            unique[key]["ens_evidence_statuses"] = set()
            unique[key]["source_pair_ids"] = []
        unique[key]["ens_evidence_statuses"].add(row["ens_status_at_verification"])
        unique[key]["source_pair_ids"].append(row["source_pair_id"])
    links = []
    for row in unique.values():
        row["ens_evidence_statuses"] = ";".join(sorted(row["ens_evidence_statuses"]))
        row["source_pair_ids"] = ";".join(row["source_pair_ids"])
        links.append(row)
    links.sort(key=lambda row: (row["address"], row["x_user_id"]))
    write_csv(out / "crosswalk_confirmed_unique.csv", links, list(links[0]))
    seed_ids = {row["x_user_id"] for row in links}

    with tweet_path.open(encoding="utf-8") as handle:
        tweets = [json.loads(line) for line in handle if line.strip()]
    post_authors = {t["tweet_id"]: t["source_author_id"] for t in tweets
                    if not t["is_repost"] and t.get("source_author_id")}
    raw_cache = {}
    raw_missing = 0
    status_missing = 0

    def raw_status(tweet: dict) -> dict | None:
        nonlocal raw_missing, status_missing
        relative = tweet.get("raw_response_file") or ""
        path = None
        for parent in (batch, continuation):
            candidate = parent / relative
            if candidate.is_file():
                path = candidate
                break
        if path is None:
            raw_missing += 1
            return None
        if path not in raw_cache:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw_cache[path] = {str(s.get("id")): s for s in data.get("results", [])}
            except (ValueError, OSError):
                raw_cache[path] = {}
        result = raw_cache[path].get(tweet["tweet_id"])
        if result is None:
            status_missing += 1
        return result

    node_handles = defaultdict(set)
    for row in links:
        node_handles[row["x_user_id"]].add(row["handle_at_verification"])
    edges = []
    edge_keys = set()
    authored = []
    reposts = []
    missing_reply_targets = 0
    self_reply_posts = 0
    for tweet in tweets:
        actor = str(tweet["queried_user_id"])
        if actor not in seed_ids:
            raise ValueError(f"Unconfirmed timeline owner: {actor}")
        if tweet.get("timeline_owner_id_verified") != actor:
            raise ValueError(f"Timeline owner mismatch for {tweet['tweet_id']}")
        status = raw_status(tweet)
        if tweet["is_repost"]:
            reposts.append({
                "x_user_id": actor,
                "source_author_id": tweet.get("source_author_id") or "",
                "source_post_id": tweet["tweet_id"],
                "source_post_created_at_utc": tweet["created_at_utc"],
                "repost_action_time_utc": "",
                "time_status": "unknown_original_post_time_only",
            })
            continue
        if tweet.get("source_author_id") != actor:
            raise ValueError(f"Authored post owner mismatch for {tweet['tweet_id']}")
        authored.append({
            "x_user_id": actor,
            "tweet_id": tweet["tweet_id"],
            "created_at_utc": tweet["created_at_utc"],
            "post_kind": tweet["post_kind"],
            "authored_text": tweet.get("authored_text") or "",
            "raw_response_file": tweet.get("raw_response_file") or "",
        })

        def add_edge(target: str | None, kind: str, target_post: str = "") -> None:
            if not target or target == actor:
                return
            key = (tweet["tweet_id"], kind, str(target))
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append({
                "source_x_user_id": actor,
                "target_x_user_id": str(target),
                "event_type": kind,
                "created_at_utc": tweet["created_at_utc"],
                "source_post_id": tweet["tweet_id"],
                "target_post_id": target_post,
                "time_semantics": "authored_post_creation_time",
                "target_is_confirmed_seed": str(target) in seed_ids,
            })

        quoted_author = tweet.get("quoted_author_id")
        if quoted_author:
            add_edge(quoted_author, "quote", tweet.get("quoted_tweet_id") or "")
            if tweet.get("quoted_author_handle"):
                node_handles[str(quoted_author)].add(tweet["quoted_author_handle"])
        reply_to = tweet.get("replying_to_tweet_id")
        if not reply_to and status is not None:
            reply_meta = status.get("replying_to") or {}
            if isinstance(reply_meta, dict):
                reply_to = reply_meta.get("status") or reply_meta.get("id")
        if tweet["is_reply"]:
            target = post_authors.get(str(reply_to)) if reply_to else None
            if target:
                if target == actor:
                    self_reply_posts += 1
                else:
                    add_edge(target, "reply", str(reply_to))
            else:
                missing_reply_targets += 1
        if status is not None:
            raw_text = status.get("raw_text") or {}
            if isinstance(raw_text, dict):
                for facet in raw_text.get("facets") or []:
                    if facet.get("type") == "mention" and facet.get("id"):
                        add_edge(str(facet["id"]), "mention")
                        if facet.get("original"):
                            node_handles[str(facet["id"])].add(facet["original"].lstrip("@"))

    edges.sort(key=lambda row: (row["created_at_utc"], row["source_post_id"], row["event_type"], row["target_x_user_id"]))
    edge_fields = ["source_x_user_id", "target_x_user_id", "event_type", "created_at_utc",
                   "source_post_id", "target_post_id", "time_semantics", "target_is_confirmed_seed"]
    write_csv(out / "x_interaction_edges_temporal.csv", edges, edge_fields)
    node_ids = seed_ids | {e["target_x_user_id"] for e in edges}
    nodes = [{"x_user_id": user_id,
              "role": "confirmed_seed" if user_id in seed_ids else "observed_external_target",
              "observed_handles": ";".join(sorted(node_handles[user_id]))}
             for user_id in sorted(node_ids)]
    write_csv(out / "x_interaction_nodes.csv", nodes, ["x_user_id", "role", "observed_handles"])
    with (out / "x_authored_posts.jsonl").open("w", encoding="utf-8") as handle:
        for row in authored:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_csv(out / "x_repost_observations_untimed.csv", reposts, [
        "x_user_id", "source_author_id", "source_post_id", "source_post_created_at_utc",
        "repost_action_time_utc", "time_status"])
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_verification_sha256": sha256(verification_path),
        "source_tweets_sha256": sha256(tweet_path),
        "account_confirmed_evidence_pairs": len(crosswalk),
        "unique_confirmed_wallet_x_links": len(links),
        "unique_seed_wallets": len({x["address"] for x in links}),
        "unique_seed_x_user_ids": len(seed_ids),
        "tweet_records": len(tweets),
        "post_kinds": dict(Counter(t["post_kind"] for t in tweets)),
        "authored_posts": len(authored),
        "repost_observations_without_action_time": len(reposts),
        "timestamped_social_edges": len(edges),
        "social_edges_by_type": dict(Counter(e["event_type"] for e in edges)),
        "social_nodes": len(nodes),
        "confirmed_seed_to_seed_edges": sum(e["target_is_confirmed_seed"] for e in edges),
        "unresolved_reply_target_posts": missing_reply_targets,
        "self_reply_posts_without_social_edge": self_reply_posts,
        "raw_response_files_missing": raw_missing,
        "raw_statuses_missing": status_missing,
        "known_limitations": [
            "Crosswalk is current account-side evidence, not a historical as-of link.",
            "Eight of twelve seed account timelines have truncated or uncertain coverage.",
            "Repost timestamps are source-post times; repost action times are unknown.",
            "Following relationships were not collected and are not historical edges.",
            "Interaction nodes outside the seed pool have no wallet crosswalk.",
            "This graph is a verified seed subset, not the complete desired two-graph dataset.",
        ],
    }
    report_path = out / "seed_quality_report.json"
    if report_path.is_file():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        if "chain_graph" in previous:
            report["chain_graph"] = previous["chain_graph"]
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
