#!/usr/bin/env python3
"""Offline audit of reverse NameChanged evidence for unresolved confirmed seeds.

Reads only frozen local ENS scope and Parquet extracts. It does not use network,
ENS RPC, X/FxEmbed, or BigQuery, and never changes crosswalk adjudication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SCOPE_REL = Path("artifacts/ens_x_crosswalk/current_goal_audit/confirmed_seed_asof_scope_recheck_20260925T2019Z.json")
REVERSE_REL = Path("artifacts/ens_x_crosswalk/reverse_evidence.parquet")
ADDR_REL = Path("artifacts/ens_x_crosswalk/addrchanged_latest.parquet")
TEXT_REL = Path("artifacts/ens_x_crosswalk/textchanged_twitter_decoded_v3.parquet")
NAME_CHANGED_TOPIC = "0xb7d29e911041e8d9b843369e890bcb72c9388692ba48b65ac54e7214c4c348f7"

sys.path.insert(0, str(ROOT / "scripts"))
from audit_and_rebuild_ens_x_text_projection import decode_abi_string  # noqa: E402
from replay_ens_x_asof import ens_namehash, reverse_node_for_address  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_name(value: str) -> str:
    return value.strip().rstrip(".").casefold()


def build(project: Path) -> dict[str, Any]:
    scope_path, reverse_path, addr_path = (project / p for p in (SCOPE_REL, REVERSE_REL, ADDR_REL))
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in scope.get("unresolved_forward_node_evidence", []):
        by_address[entry["address"].lower()].append(entry)

    expected_nodes = {address: reverse_node_for_address(address) for address in by_address}
    events: dict[str, list[dict[str, Any]]] = {a: [] for a in by_address}
    reverse_node_to_address = {n: a for a, n in expected_nodes.items()}
    pf = pq.ParquetFile(reverse_path)
    needed = ["block_timestamp", "transaction_hash", "emitter", "log_index", "topic0", "topic1", "data"]
    for batch in pf.iter_batches(columns=needed, batch_size=32768):
        for row in batch.to_pylist():
            if str(row.get("topic0") or "").lower() != NAME_CHANGED_TOPIC:
                continue
            node = str(row.get("topic1") or "").lower()
            address = reverse_node_to_address.get(node)
            if address is None:
                continue
            try:
                name = decode_abi_string(row.get("data") or "")
                decode_status = "decoded"
            except (ValueError, UnicodeError) as exc:
                name = None
                decode_status = f"error:{type(exc).__name__}:{exc}"
            try:
                event_namehash = ens_namehash(name) if name is not None and name.isascii() else None
            except (ValueError, UnicodeError):
                event_namehash = None
            claims = by_address[address]
            matching_pairs = [x["pair_id"] for x in claims if name is not None and norm_name(name) == norm_name(x["reverse_name"])]
            source_nodes_for_name = sorted({
                x["source_node"].lower() for x in claims
                if name is not None and norm_name(name) == norm_name(x["reverse_name"])
            })
            events[address].append({
                "block_timestamp_utc": row["block_timestamp"].astimezone(timezone.utc).isoformat() if row.get("block_timestamp") else None,
                "transaction_hash": row.get("transaction_hash"),
                "log_index": row.get("log_index"),
                "emitter": str(row.get("emitter") or "").lower(),
                "reverse_node": node,
                "decoded_name": name,
                "decode_status": decode_status,
                "decoded_namehash_ascii_only": event_namehash,
                "matches_claimed_reverse_name_pair_ids": matching_pairs,
                "claimed_source_nodes_for_matching_name": source_nodes_for_name,
                "namehash_matches_any_claimed_source_node": bool(event_namehash and event_namehash in source_nodes_for_name),
            })

    # Snapshot cross-check only: compare both the supplied source node and the
    # namehash derived from each claimed reverse name. This does not recover
    # historical state because addrchanged_latest is a one-row-per-node snapshot.
    source_pairs: set[tuple[str, str]] = set()
    claimed_nodes: dict[tuple[str, str], dict[str, Any]] = {}
    nodes_to_inspect: set[str] = set()
    for address, entries in by_address.items():
        for x in entries:
            source_node = x["source_node"].lower()
            source_pairs.add((source_node, address))
            nodes_to_inspect.add(source_node)
            try:
                derived = ens_namehash(x["reverse_name"])
                status = "ascii_namehash_derived"
            except (ValueError, UnicodeError) as exc:
                derived = None
                status = f"unsupported_by_ascii_only_namehash:{type(exc).__name__}"
            claimed_nodes[(address, x["pair_id"])] = {
                "claimed_reverse_name": x["reverse_name"],
                "namehash_node": derived,
                "namehash_status": status,
            }
            if derived:
                nodes_to_inspect.add(derived)
    addr_rows: dict[tuple[str, str], list[str]] = defaultdict(list)
    latest_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    addr_pf = pq.ParquetFile(addr_path)
    for batch in addr_pf.iter_batches(columns=["node", "address", "block_timestamp"], batch_size=65536):
        for row in batch.to_pylist():
            node = str(row.get("node") or "").lower()
            address = str(row.get("address") or "").lower()
            ts = row.get("block_timestamp")
            stamp = ts.astimezone(timezone.utc).isoformat() if ts else None
            if (node, address) in source_pairs:
                addr_rows[(node, address)].append(stamp or "")
            if node in nodes_to_inspect:
                latest_by_node[node].append({"address": address, "block_timestamp_utc": stamp})

    text_path = project / TEXT_REL
    text_pf = pq.ParquetFile(text_path)
    text_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    text_cols = [c for c in ("node", "block_timestamp", "key", "value", "decode_status", "transaction_hash") if c in text_pf.schema_arrow.names]
    for batch in text_pf.iter_batches(columns=text_cols, batch_size=32768):
        for row in batch.to_pylist():
            node = str(row.get("node") or "").lower()
            if node not in nodes_to_inspect:
                continue
            stamp = row.get("block_timestamp")
            text_by_node[node].append({
                "block_timestamp_utc": stamp.astimezone(timezone.utc).isoformat() if stamp else None,
                "key": row.get("key"), "value": row.get("value"),
                "decode_status": row.get("decode_status"),
                "transaction_hash": row.get("transaction_hash"),
            })

    result_links = []
    for address, claims in sorted(by_address.items()):
        ev = sorted(events[address], key=lambda x: (x["block_timestamp_utc"] or "", x["log_index"] if x["log_index"] is not None else -1))
        matching = [e for e in ev if e["matches_claimed_reverse_name_pair_ids"]]
        source_checks = []
        for claim in claims:
            key = (claim["source_node"].lower(), address)
            derived = claimed_nodes[(address, claim["pair_id"])]
            claimed_node = derived["namehash_node"]
            source_checks.append({
                "pair_id": claim["pair_id"],
                "claimed_reverse_name": claim["reverse_name"],
                "scope_source_node": claim["source_node"].lower(),
                "scope_computed_namehash": claim.get("computed_namehash"),
                "claimed_namehash_node": claimed_node,
                "claimed_namehash_status": derived["namehash_status"],
                "source_node_snapshot_rows_for_seed_address": len(addr_rows.get(key, [])),
                "source_node_snapshot_timestamps_utc": sorted(addr_rows.get(key, [])),
                "claimed_namehash_latest_snapshot_rows": latest_by_node.get(claimed_node, []) if claimed_node else [],
                "claimed_namehash_twitter_text_events": sorted(text_by_node.get(claimed_node, []), key=lambda r: r["block_timestamp_utc"] or "") if claimed_node else [],
                "snapshot_only_not_history": True,
            })
        result_links.append({
            "address": address,
            "pair_ids": [x["pair_id"] for x in claims],
            "stable_x_user_ids": sorted({x["x_user_id"] for x in claims}),
            "reverse_node_derived_ensip3": expected_nodes[address],
            "claimed_reverse_names": sorted({x["reverse_name"] for x in claims}),
            "observed_namechanged_event_count": len(ev),
            "exact_claimed_reverse_name_event_count": len(matching),
            "events": ev,
            "forward_source_node_snapshot_checks": source_checks,
        })

    return {
        "audit": "offline_unresolved_seed_reverse_namechanged_evidence_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_requests": 0,
        "ens_rpc_requests": 0,
        "bigquery_queries": 0,
        "collection_performed": False,
        "mapping_adjudications_changed": 0,
        "interpretation": (
            "Decoded local reverse NameChanged observations are evidence about what names were written to the derived reverse nodes. "
            "They do not prove source completeness, resolver assignment at each log, canonical block/transaction/log ordering, "
            "forward address validity at the same time, or X account identity. Do not promote mappings from this audit alone."
        ),
        "inputs": {
            "scope": {"path": str(SCOPE_REL), "sha256": sha256(scope_path)},
            "reverse_evidence": {"path": str(REVERSE_REL), "sha256": sha256(reverse_path), "rows": pf.metadata.num_rows,
                                 "schema": str(pf.schema_arrow)},
            "addrchanged_latest": {"path": str(ADDR_REL), "sha256": sha256(addr_path), "rows": addr_pf.metadata.num_rows,
                                    "schema": str(addr_pf.schema_arrow)},
            "decoded_twitter_text_events": {"path": str(TEXT_REL), "sha256": sha256(text_path), "rows": text_pf.metadata.num_rows,
                                             "schema": str(text_pf.schema_arrow)},
        },
        "namechanged_topic0": NAME_CHANGED_TOPIC,
        "links": result_links,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/ens_x_crosswalk/current_goal_audit/unresolved_seed_reverse_namechanged_20260926.json")
    args = parser.parse_args()
    report = build(args.project.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.out),
        "addresses": len(report["links"]),
        "observed_events": sum(x["observed_namechanged_event_count"] for x in report["links"]),
        "links_with_exact_claimed_reverse_name_event": sum(bool(x["exact_claimed_reverse_name_event_count"]) for x in report["links"]),
        "snapshot_source_node_address_matches": sum(c["source_node_snapshot_rows_for_seed_address"] > 0 for x in report["links"] for c in x["forward_source_node_snapshot_checks"]),
        "claimed_namehash_snapshot_matches": sum(any(r["address"] == x["address"] for r in c["claimed_namehash_latest_snapshot_rows"]) for x in report["links"] for c in x["forward_source_node_snapshot_checks"]),
    }, indent=2))


if __name__ == "__main__":
    main()
