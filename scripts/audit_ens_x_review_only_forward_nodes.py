#!/usr/bin/env python3
"""Offline diagnostics for ENSIP-15 forward nodes retained only for review.

This script joins *review-only* candidate nodes from a frozen confirmed-seed
scope to local AddrChanged snapshot and decoded TextChanged extracts, and
cross-references observed reverse NameChanged records. It performs no network,
RPC, BigQuery, X/FxEmbed request, mapping promotion, or completeness inference.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("artifacts/ens_x_crosswalk")
DEFAULT_SCOPE = BASE / "current_goal_audit/confirmed_seed_asof_query_scope_ensip15_reviewnodes_20260926.json"
DEFAULT_REVERSE = BASE / "current_goal_audit/unresolved_seed_reverse_namechanged_20260926.json"
ADDR = BASE / "addrchanged_latest.parquet"
TEXT = BASE / "textchanged_twitter_decoded_v3.parquet"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iso(v):
    return v.isoformat() if v is not None else None


def audit(project: Path, scope_path: Path, reverse_path: Path) -> dict:
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    reverse = json.loads(reverse_path.read_text(encoding="utf-8"))
    if scope.get("mode") != "offline_confirmed_seed_ens_event_scope_only":
        raise ValueError("unexpected scope mode")
    if scope.get("query_performed") or scope.get("collection_authorized"):
        raise ValueError("scope must remain planning-only")
    candidates = scope.get("review_only_forward_node_candidates", [])
    if any(x.get("status") != "review_only_namehash_candidate_source_node_mismatch" for x in candidates):
        raise ValueError("unexpected review-only candidate status")
    addr_path, text_path = project / ADDR, project / TEXT
    # The address snapshot is multi-million-row.  This diagnostic only needs
    # the frozen review-only nodes; predicate pushdown keeps the offline audit
    # bounded and avoids materializing the full snapshot in memory.
    review_nodes = sorted({c["node"].lower() for c in candidates})
    addr_table = pq.read_table(
        addr_path,
        columns=["node", "address", "block_timestamp"],
        filters=[("node", "in", review_nodes)],
    )
    addr_rows = addr_table.to_pylist()
    addr_idx = {(r["node"] or "").lower(): r for r in addr_rows}
    text_rows = pq.read_table(text_path, columns=["node", "block_timestamp", "key", "value", "transaction_hash"]).to_pylist()
    text_idx: dict[str, list[dict]] = {}
    for r in text_rows:
        text_idx.setdefault((r["node"] or "").lower(), []).append(r)
    reverse_by_address = {x["address"].lower(): x for x in reverse.get("links", [])}
    out = []
    for c in candidates:
        node = c["node"].lower()
        snapshot = addr_idx.get(node)
        x_events = [r for r in text_idx.get(node, []) if (r.get("key") or "").casefold() in {"com.twitter", "twitter", "com.x", "x"}]
        out.append({
            **c,
            "latest_addrchanged_snapshot": ({"address": (snapshot["address"] or "").lower(), "block_timestamp_utc": iso(snapshot["block_timestamp"])} if snapshot else None),
            "twitter_text_observations": [{"block_timestamp_utc": iso(r["block_timestamp"]), "key": r["key"], "value": r["value"], "transaction_hash": r["transaction_hash"]} for r in sorted(x_events, key=lambda z: z["block_timestamp"])],
            "reverse_namechanged_observations_by_wallet": [
                {"address": a, "claimed_reverse_names": reverse_by_address[a].get("claimed_reverse_names", []),
                 "exact_claimed_reverse_name_event_count": reverse_by_address[a].get("exact_claimed_reverse_name_event_count", 0),
                 "events": reverse_by_address[a].get("events", [])}
                for a in c["candidate_wallets"] if a in reverse_by_address
            ],
            "mapping_adjudication_changed": False,
            "historical_asof_validated": False,
        })
    return {
        "mode": "offline_review_only_forward_node_snapshot_diagnostic_v1",
        "network_requests": 0, "ens_rpc_requests": 0, "bigquery_queries": 0,
        "x_or_fxembed_requests": 0, "mapping_adjudications_changed": 0,
        "inputs": {str(p.relative_to(project)): {"sha256": sha256(p), "bytes": p.stat().st_size} for p in [scope_path, reverse_path, addr_path, text_path]},
        "candidate_node_count": len(out),
        "scope_candidate_wallets_remain_unresolved": True,
        "addrchanged_rows_seen": len(addr_rows), "twitter_text_rows_seen": len(text_rows),
        "candidates": out,
        "interpretation": "Joins to addrchanged_latest and decoded TextChanged are local snapshot/partial observations only. Reverse NameChanged observations are not a complete ordered resolver history. No wallet-X mapping is promoted; event-time as-of validity remains unverified.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, default=ROOT)
    ap.add_argument("--scope", type=Path, default=None)
    ap.add_argument("--reverse-audit", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    project = args.project.resolve()
    scope = (args.scope or project / DEFAULT_SCOPE).resolve()
    reverse = (args.reverse_audit or project / DEFAULT_REVERSE).resolve()
    result = audit(project, scope, reverse)
    out = args.out if args.out.is_absolute() else project / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "candidate_node_count": result["candidate_node_count"], "network_requests": 0, "bigquery_queries": 0, "mapping_adjudications_changed": 0}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
