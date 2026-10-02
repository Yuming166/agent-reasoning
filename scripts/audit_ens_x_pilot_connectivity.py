#!/usr/bin/env python3
"""Offline audit of observed X graph/text coverage for the 12-seed + 50-account pilot.

This analyzes stable X IDs and cached observations only. The 50 pilot wallet/X
pairs are provisional; none are promoted or attributed to wallet ownership.
No network access or paid queries are performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

WINDOW_START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-09-24T17:24:10+00:00")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def in_window(value: str) -> bool:
    dt = parse_utc(value)
    return dt is not None and WINDOW_START <= dt < WINDOW_END


def _components(nodes: set[str], undirected_pairs: set[tuple[str, str]]) -> list[int]:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in undirected_pairs:
        if a in adj and b in adj and a != b:
            adj[a].add(b)
            adj[b].add(a)
    unseen = set(nodes)
    sizes: list[int] = []
    while unseen:
        root = unseen.pop()
        queue = deque([root])
        n = 0
        while queue:
            cur = queue.popleft()
            n += 1
            for nxt in adj[cur] & unseen:
                unseen.remove(nxt)
                queue.append(nxt)
        sizes.append(n)
    return sorted(sizes, reverse=True)


def analyze(seed_crosswalk: list[dict[str, str]], seed_posts: list[dict], seed_edges: list[dict[str, str]],
            candidate_crosswalk: list[dict[str, str]], candidate_posts: list[dict],
            candidate_edges: list[dict[str, str]], coverage: list[dict],
            input_hashes: dict[str, str] | None = None) -> dict:
    seed_ids = {str(r["x_user_id"]) for r in seed_crosswalk}
    candidate_ids = {str(r["x_user_id"]) for r in candidate_crosswalk}
    if len(seed_ids) != len(seed_crosswalk) or len(candidate_ids) != len(candidate_crosswalk):
        raise ValueError("duplicate stable X IDs in a crosswalk input")
    if not all(x.isdigit() for x in seed_ids | candidate_ids):
        raise ValueError("non-numeric or missing stable X ID")

    ids = seed_ids | candidate_ids
    if seed_ids & candidate_ids:
        raise ValueError("seed and provisional candidate X-ID sets overlap")

    posts_by_tier = {
        "confirmed_seed_accounts_only": [r for r in seed_posts if in_window(str(r.get("created_at_utc", "")))],
        "provisional_candidate_accounts_only": [r for r in candidate_posts if in_window(str(r.get("created_at_utc", "")))],
    }
    post_counts: dict[str, dict] = {}
    monthly_posts: Counter[tuple[str, str, str]] = Counter()
    for tier, rows in posts_by_tier.items():
        kinds = Counter()
        authors = set()
        for r in rows:
            kind = str(r.get("post_kind", "unknown")).lower()
            # Reposts have no verified actor action timestamp; never treat their
            # source-post time as an authored post by the reposting account.
            if kind in {"repost", "retweet"}:
                continue
            kinds[kind] += 1
            uid = str(r.get("x_user_id", ""))
            if uid:
                authors.add(uid)
            dt = parse_utc(str(r.get("created_at_utc", "")))
            if dt:
                monthly_posts[(tier, dt.strftime("%Y-%m"), kind)] += 1
        post_counts[tier] = {"authored_posts_observed": sum(kinds.values()),
                             "accounts_with_authored_posts": len(authors),
                             "post_kind_counts": dict(sorted(kinds.items()))}

    edge_inputs = [("confirmed_seed_timeline", seed_edges),
                   ("provisional_candidate_timeline", candidate_edges)]
    edges: list[dict] = []
    seen = set()
    monthly_edge_counts: Counter[tuple[str, str]] = Counter()
    monthly_pairs: dict[tuple[str, str], set[tuple[str, str, str]]] = defaultdict(set)
    for tier, rows in edge_inputs:
        for r in rows:
            created = str(r.get("created_at_utc", ""))
            if not in_window(created):
                continue
            source, target = str(r.get("source_x_user_id", "")), str(r.get("target_x_user_id", ""))
            kind = str(r.get("event_type", ""))
            if not source.isdigit() or not target.isdigit() or kind not in {"mention", "quote", "reply"}:
                continue
            post_id = str(r.get("source_post_id", ""))
            # Preserve one event per authored post, target, and interaction type.
            key = (source, target, kind, post_id, created)
            if key in seen:
                continue
            seen.add(key)
            edge = {"source": source, "target": target, "kind": kind,
                    "month": parse_utc(created).strftime("%Y-%m"), "tier": tier}
            edges.append(edge)
            monthly_edge_counts[(tier, edge["month"])] += 1
            if source in ids and target in ids:
                monthly_pairs[(tier, edge["month"])].add((source, target, kind))

    induced = [e for e in edges if e["source"] in ids and e["target"] in ids]
    candidate_induced = [e for e in induced if e["source"] in candidate_ids or e["target"] in candidate_ids]
    tier_edge_counts = Counter(e["tier"] for e in edges)
    type_counts = Counter(e["kind"] for e in edges)
    induced_by_relation = Counter()
    directed_pairs: set[tuple[str, str]] = set()
    undirected_pairs: set[tuple[str, str]] = set()
    nodes_with_edge: set[str] = set()
    monthly_induced_pair_sets: dict[str, set[tuple[str, str]]] = defaultdict(set)
    induced_pair_months: dict[tuple[str, str], set[str]] = defaultdict(set)
    for e in induced:
        s, t = e["source"], e["target"]
        if s in seed_ids and t in seed_ids:
            rel = "seed_to_seed"
        elif s in candidate_ids and t in candidate_ids:
            rel = "candidate_to_candidate_provisional_ids"
        else:
            rel = "candidate_seed_cross_group_provisional_wallet_link"
        induced_by_relation[rel] += 1
        directed_pairs.add((s, t))
        undirected_pairs.add(tuple(sorted((s, t))))
        nodes_with_edge.update((s, t))
        monthly_induced_pair_sets[e["month"]].add((s, t))
        induced_pair_months[(s, t)].add(e["month"])

    coverage_reasons = Counter(str(r.get("stop_reason", "unknown")) for r in coverage)
    covered_ids = {str(r.get("x_user_id", "")) for r in coverage}
    monthly = {}
    months = sorted({m for _, m, _ in monthly_posts} | {m for _, m in monthly_edge_counts})
    for month in months:
        monthly[month] = {
            "authored_posts_by_tier_and_kind": {
                tier: dict(sorted((kind, n) for (t, m, kind), n in monthly_posts.items() if t == tier and m == month))
                for tier in post_counts
            },
            "observed_timeline_edges_by_tier": {
                tier: monthly_edge_counts[(tier, month)] for tier, _ in edge_inputs
            },
            "sample_induced_edges": sum(1 for e in induced if e["month"] == month),
            "sample_induced_distinct_directed_pairs": len(monthly_induced_pair_sets[month]),
        }

    return {
        "schema": "ens_x_pilot_connectivity_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_window_utc": {"start_inclusive": WINDOW_START.isoformat(), "end_exclusive": WINDOW_END.isoformat()},
        "scope": {
            "confirmed_seed_accounts": len(seed_ids),
            "provisional_candidate_accounts": len(candidate_ids),
            "provisional_wallet_x_links_promoted": 0,
            "network_requests": 0,
            "paid_queries": 0,
            "inputs_sha256": input_hashes or {},
        },
        "observed_authored_text": post_counts,
        "timeline_coverage": {
            "candidate_accounts_with_coverage_row": len(covered_ids & candidate_ids),
            "candidate_account_count": len(candidate_ids),
            "stop_reasons": dict(sorted(coverage_reasons.items())),
            "complete_history_claims_allowed": False,
        },
        "observed_timestamped_edges": {
            "counts_by_source_tier": dict(sorted(tier_edge_counts.items())),
            "counts_by_type": dict(sorted(type_counts.items())),
            "all_observed_edge_count": len(edges),
            "sample_induced_edge_count": len(induced),
            "sample_induced_distinct_directed_pairs": len(directed_pairs),
            "sample_nodes_with_at_least_one_induced_edge": len(nodes_with_edge),
            "sample_node_count": len(ids),
            "sample_induced_undirected_component_sizes_including_isolates": _components(ids, undirected_pairs),
            "sample_induced_edges_by_relation": dict(sorted(induced_by_relation.items())),
            "provisional_candidate_involved_induced_edges": len(candidate_induced),
            "months_with_sample_induced_edges": sorted(month for month, pairs in monthly_induced_pair_sets.items() if pairs),
            "induced_directed_pairs_repeated_across_months": sum(
                len(months) > 1 for months in induced_pair_months.values()),
        },
        "monthly_observations": monthly,
        "limitations": [
            "The 50 candidate wallet/X links remain provisional; candidate-linked counts describe observed X IDs and do not establish wallet ownership.",
            "Edges are observed mentions/quotes/replies from cached authored-post timestamps, not a complete X social graph.",
            "Repost/source-post timestamps are not repost action times and are excluded from posts and temporal edges.",
            "A page-ceiling or cursor-exhausted stop is not proof of full timeline history; missing edges are not evidence of no interaction.",
            "Current sampled graph connectivity is not historical edge availability or a leakage-safe feature without event-time identity/coverage reconstruction.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    src = args.project.resolve() / "artifacts/ens_x_crosswalk"
    seed = src / "two_graph_seed_20260925"
    pilot = src / "timeline_expansion_pilot_20260925"
    files = {
        "seed_crosswalk": seed / "crosswalk_confirmed_unique.csv",
        "seed_posts": seed / "x_authored_posts.jsonl",
        "seed_edges": seed / "x_interaction_edges_temporal.csv",
        "candidate_crosswalk": pilot / "provisional_wallet_x_crosswalk.csv",
        "candidate_posts": pilot / "provisional_x_authored_posts.jsonl",
        "candidate_edges": pilot / "provisional_x_interaction_edges_temporal.csv",
        "candidate_coverage": pilot / "coverage.jsonl",
    }
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("missing required frozen pilot inputs: " + ", ".join(missing))
    hashes = {name: sha256(path) for name, path in files.items()}
    report = analyze(read_csv(files["seed_crosswalk"]), read_jsonl(files["seed_posts"]),
                     read_csv(files["seed_edges"]), read_csv(files["candidate_crosswalk"]),
                     read_jsonl(files["candidate_posts"]), read_csv(files["candidate_edges"]),
                     read_jsonl(files["candidate_coverage"]), hashes)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    edge = report["observed_timestamped_edges"]
    lines = [
        "# ENS/X pilot connectivity audit (offline)", "",
        f"Generated UTC: `{report['generated_at_utc']}`", "",
        "## Scope and gate", "",
        "- 12 confirmed seed X IDs + 50 provisional candidate X IDs; candidate wallet/X links promoted: **0**.",
        "- Network requests: **0**; paid queries: **0**.",
        "- Candidate timeline stops: " + json.dumps(report["timeline_coverage"]["stop_reasons"], ensure_ascii=False) + ".",
        "- Timeline stop status does not establish complete history.", "",
        "## Observed coverage", "",
    ]
    for tier, data in report["observed_authored_text"].items():
        lines.append(f"- `{tier}`: {data['authored_posts_observed']} authored posts across {data['accounts_with_authored_posts']} accounts; types `{data['post_kind_counts']}`.")
    lines += ["", "## Sample-induced observed X graph", "",
              f"- {edge['sample_induced_edge_count']} observed events on {edge['sample_induced_distinct_directed_pairs']} directed account-pairs.",
              f"- {edge['sample_nodes_with_at_least_one_induced_edge']}/{edge['sample_node_count']} sample X IDs incident to an edge.",
              f"- Relation counts: `{edge['sample_induced_edges_by_relation']}`.",
              f"- Undirected component sizes including isolates: `{edge['sample_induced_undirected_component_sizes_including_isolates']}`.",
              f"- Induced directed pairs observed in multiple months: {edge['induced_directed_pairs_repeated_across_months']}.",
              "", "## Interpretation limits", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    lines += ["", "Monthly counts are in the JSON artifact. File hashes bind this report to the exact cached inputs.", ""]
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"out_json": str(args.out_json), "out_md": str(args.out_md),
                      "sample_induced_edges": edge["sample_induced_edge_count"],
                      "sample_induced_pairs": edge["sample_induced_distinct_directed_pairs"],
                      "candidate_links_promoted": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
