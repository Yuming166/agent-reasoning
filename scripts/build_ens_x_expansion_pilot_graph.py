#!/usr/bin/env python3
"""Build an auditable X interaction graph from a frozen confirmed-account run."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_run_inputs(out: Path) -> tuple[list[dict], list[dict]]:
    """Load a completed frozen run and fail closed on manifest/coverage drift."""
    manifest_path = out / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing frozen run manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "ens-x-confirmed-timeline-pilot-v1":
        raise ValueError("unsupported run manifest schema")
    queue = manifest.get("accounts")
    if not isinstance(queue, list) or not queue:
        raise ValueError("manifest must contain a non-empty accounts list")
    ids = []
    for account in queue:
        if not isinstance(account, dict) or account.get("verification_status") != "account_confirms":
            raise ValueError("manifest contains a non-confirmed account")
        uid = str(account.get("x_user_id", ""))
        if not uid.isdigit():
            raise ValueError("manifest account has an invalid stable X ID")
        ids.append(uid)
    if len(ids) != len(set(ids)):
        raise ValueError("manifest contains duplicate X IDs")

    coverage_path = out / "coverage.jsonl"
    coverage = [json.loads(line) for line in coverage_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    coverage_ids = [str(row.get("x_user_id", "")) for row in coverage]
    if len(coverage_ids) != len(set(coverage_ids)):
        raise ValueError("coverage ledger contains duplicate accounts")
    if set(coverage_ids) != set(ids):
        raise RuntimeError(f"Timeline pilot incomplete or out-of-scope: {len(set(coverage_ids) & set(ids))} of {len(ids)} accounts")
    return queue, coverage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    queue, coverage = load_run_inputs(out)
    with (out / "normalized_observed_statuses.jsonl").open(encoding="utf-8") as handle:
        statuses = [json.loads(line) for line in handle if line.strip()]
    seed_ids = {str(q["x_user_id"]) for q in queue}
    links = [{**q, "link_quality": "account_side_confirmed",
              "historical_link_quality": "event_time_as_of_not_validated"} for q in queue]
    write_csv(out / "provisional_wallet_x_crosswalk.csv", links, list(links[0]))

    post_authors = {r["tweet_id"]: r["source_author_id"] for r in statuses
                    if not r["is_repost"] and r.get("source_author_id")}
    node_handles = defaultdict(set)
    for q in queue:
        node_handles[q["x_user_id"]].add(q["handle_at_profile_audit"])
    edges = []
    edge_keys = set()
    authored = []
    reposts = []
    self_replies = 0
    unresolved_replies = 0
    missing_raw = 0
    raw_cache = {}
    for record in statuses:
        actor = record["queried_user_id"]
        if actor not in seed_ids or record["timeline_owner_id_verified"] != actor:
            raise RuntimeError("Unexpected or mismatched timeline owner")
        if record["is_repost"]:
            reposts.append({"x_user_id": actor, "source_author_id": record.get("source_author_id") or "",
                            "source_post_id": record["tweet_id"],
                            "source_post_created_at_utc": record["created_at_utc"],
                            "repost_action_time_utc": "", "time_status": "unknown_original_post_time_only"})
            continue
        if record.get("source_author_id") != actor:
            raise RuntimeError(f"Authored status ID mismatch: {record['tweet_id']}")
        authored.append({"x_user_id": actor, "tweet_id": record["tweet_id"],
                         "created_at_utc": record["created_at_utc"],
                         "post_kind": record["post_kind"],
                         "authored_text": record.get("authored_text") or ""})

        def add(target: str | None, kind: str, target_post: str = "") -> None:
            if not target or target == actor:
                return
            target = str(target)
            key = (actor, record["tweet_id"], target, kind)
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append({"source_x_user_id": actor, "target_x_user_id": target,
                          "event_type": kind, "created_at_utc": record["created_at_utc"],
                          "source_post_id": record["tweet_id"], "target_post_id": target_post,
                          "target_is_provisional_seed": target in seed_ids,
                          "time_semantics": "authored_post_creation_time"})

        if record.get("quoted_author_id"):
            target = str(record["quoted_author_id"])
            add(target, "quote", record.get("quoted_tweet_id") or "")
            if record.get("quoted_author_handle"):
                node_handles[target].add(record["quoted_author_handle"])
        raw_path = out / (record.get("raw_response_file") or "")
        raw_status = None
        if raw_path.is_file():
            if raw_path not in raw_cache:
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                raw_cache[raw_path] = {str(s.get("id")): s for s in payload.get("results", [])}
            raw_status = raw_cache[raw_path].get(record["tweet_id"])
        if raw_status is None:
            missing_raw += 1
        reply_to = record.get("replying_to_tweet_id")
        if not reply_to and raw_status is not None:
            reply = raw_status.get("replying_to") or {}
            if isinstance(reply, dict):
                reply_to = reply.get("status") or reply.get("id")
        if record["is_reply"]:
            target = post_authors.get(str(reply_to)) if reply_to else None
            if target == actor:
                self_replies += 1
            elif target:
                add(target, "reply", str(reply_to))
            else:
                unresolved_replies += 1
        if raw_status is not None:
            raw_text = raw_status.get("raw_text") or {}
            if isinstance(raw_text, dict):
                for facet in raw_text.get("facets") or []:
                    if facet.get("type") == "mention" and facet.get("id"):
                        target = str(facet["id"])
                        add(target, "mention")
                        if facet.get("original"):
                            node_handles[target].add(facet["original"].lstrip("@"))

    edges.sort(key=lambda r: (r["created_at_utc"], r["source_post_id"], r["event_type"]))
    write_csv(out / "provisional_x_interaction_edges_temporal.csv", edges,
              ["source_x_user_id", "target_x_user_id", "event_type", "created_at_utc",
               "source_post_id", "target_post_id", "target_is_provisional_seed", "time_semantics"])
    node_ids = seed_ids | {e["target_x_user_id"] for e in edges}
    nodes = [{"x_user_id": uid, "role": "provisional_seed" if uid in seed_ids else "observed_external_target",
              "observed_handles": ";".join(sorted(node_handles[uid]))} for uid in sorted(node_ids)]
    write_csv(out / "provisional_x_interaction_nodes.csv", nodes,
              ["x_user_id", "role", "observed_handles"])
    with (out / "provisional_x_authored_posts.jsonl").open("w", encoding="utf-8") as handle:
        for row in authored:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_csv(out / "provisional_x_repost_observations_untimed.csv", reposts,
              ["x_user_id", "source_author_id", "source_post_id", "source_post_created_at_utc",
               "repost_action_time_utc", "time_status"])
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    summary["graph"] = {
        "account_side_confirmed_crosswalk_pairs": len(links),
        "nodes": len(nodes), "timestamped_edges": len(edges),
        "edges_by_type": dict(Counter(e["event_type"] for e in edges)),
        "provisional_seed_to_seed_edges": sum(e["target_is_provisional_seed"] for e in edges),
        "authored_posts": len(authored), "repost_observations_untimed": len(reposts),
        "self_reply_posts": self_replies, "unresolved_reply_posts": unresolved_replies,
        "missing_raw_statuses": missing_raw,
        "authored_months": dict(sorted(Counter(r["created_at_utc"][:7] for r in authored).items())),
        "coverage_stop_reasons": dict(Counter(r["stop_reason"] for r in coverage)),
        "limitation": "All manifest links were individually marked account_confirms, but this does not establish event-time ENS/X validity. Cursor exhaustion is only an operational stop, not proof that the mirror has complete historical coverage. Page ceilings and missing repost action times further prevent completeness claims.",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["graph"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
