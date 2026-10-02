#!/usr/bin/env python3
"""Offline reconciliation of confirmed seed forward ENS nodes to addrchanged_latest.

This is a latest-extraction cross-check only. It is not historical as-of validation,
source completeness proof, or permission to promote unresolved mappings.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import pyarrow as pa
import pyarrow.dataset as ds

BASE = Path(__file__).resolve().parents[1]
DEFAULT_CROSSWALK = BASE / "artifacts/ens_x_crosswalk"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def build_report(audit: dict, parquet_path: Path, audit_path: Path | None = None) -> dict:
    links = audit["links"]
    forward_nodes = sorted({n.lower() for row in links for n in row.get("forward_ens_nodes_namehash_validated", [])})
    reverse_nodes = sorted({row["reverse_node"].lower() for row in links if row.get("reverse_node")})
    query_nodes = sorted(set(forward_nodes) | set(reverse_nodes))
    if query_nodes:
        table = ds.dataset(parquet_path, format="parquet").to_table(
            filter=ds.field("node").isin(pa.array(query_nodes, type=pa.string())),
            columns=["node", "address", "block_timestamp"],
        )
    else:
        table = pa.table({"node": pa.array([], type=pa.string()), "address": pa.array([], type=pa.string()), "block_timestamp": pa.array([], type=pa.timestamp("us", tz="UTC"))})
    records = [{
        "node": (r["node"] or "").lower(),
        "address": (r["address"] or "").lower(),
        "block_timestamp_utc": r["block_timestamp"].isoformat() if r["block_timestamp"] else None,
    } for r in table.to_pylist()]
    by_node: dict[str, list[dict]] = {}
    for row in records:
        by_node.setdefault(row["node"], []).append(row)
    per_link = []
    for link in links:
        address = link["address"].lower()
        f_nodes = [x.lower() for x in link.get("forward_ens_nodes_namehash_validated", [])]
        f_rows = [rec for node in f_nodes for rec in by_node.get(node, [])]
        r_node = (link.get("reverse_node") or "").lower()
        r_rows = by_node.get(r_node, [])
        per_link.append({
            "address": address,
            "x_user_id": link.get("x_user_id"),
            "source_pair_ids": link.get("source_pair_ids", []),
            "forward_node_status": link.get("forward_node_status"),
            "validated_forward_nodes": f_nodes,
            "forward_addrchanged_rows": f_rows,
            "forward_snapshot_has_expected_address": any(x["address"] == address for x in f_rows),
            "reverse_node": r_node,
            "reverse_addrchanged_rows": r_rows,
        })
    eligible = [x for x in per_link if x["validated_forward_nodes"]]
    matched = sum(x["forward_snapshot_has_expected_address"] for x in eligible)
    reverse_rows = sum(bool(x["reverse_addrchanged_rows"]) for x in per_link)
    source_hashes = {str(parquet_path): sha256(parquet_path)}
    if audit_path is not None:
        source_hashes[str(audit_path)] = sha256(audit_path)
    return {
        "audit": "offline_addrchanged_latest_forward_node_reconciliation",
        "interpretation": "Latest local AddrChanged extraction cross-check only; does not prove historical validity, event completeness, resolver history, or X identity at a past prediction time.",
        "input_sha256": source_hashes,
        "input_metadata": {
            "link_count": len(links), "links_with_namehash_validated_forward_nodes": len(eligible),
            "unique_validated_forward_nodes": len(forward_nodes), "unique_wallet_reverse_nodes": len(reverse_nodes),
            "queried_node_union": len(query_nodes), "addrchanged_rows_on_queried_nodes": len(records),
            "forward_nodes_with_expected_address": matched,
            "wallet_reverse_nodes_with_any_addrchanged_row": reverse_rows,
            "rows_timestamp_min_utc": min((r["block_timestamp_utc"] for r in records if r["block_timestamp_utc"]), default=None),
            "rows_timestamp_max_utc": max((r["block_timestamp_utc"] for r in records if r["block_timestamp_utc"]), default=None),
        },
        "links": per_link,
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_CROSSWALK)
    ap.add_argument("--audit", type=Path, default=None)
    ap.add_argument("--parquet", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    root = args.root
    audit_path = args.audit or root / "current_goal_audit/ens_seed_asof_scope_recheck_20260925.json"
    parquet_path = args.parquet or root / "addrchanged_latest.parquet"
    out_path = args.out or root / "current_goal_audit/addrchanged_forward_node_join_20260925.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    result = build_report(audit, parquet_path, audit_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out_path), **result["input_metadata"]}, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
