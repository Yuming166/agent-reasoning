#!/usr/bin/env python3
"""Build a bounded, offline ENS event-query scope for confirmed seed links.

This is a planning artifact only: it performs no RPC, BigQuery, X/FxEmbed, or
network request, and it is not authorization to query. Unresolved forward ENS
nodes remain excluded from the eligible-node set; reverse nodes are independently
re-derived from wallet addresses and checked against the local revnode table.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.audit_confirmed_seed_textchanged_projection import resolve_account_confirm_evidence
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from audit_confirmed_seed_textchanged_projection import resolve_account_confirm_evidence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_namehash(project: Path):
    spec = importlib.util.spec_from_file_location("replay_ens_x_asof", project / "scripts/replay_ens_x_asof.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ENS namehash implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ens_namehash


def build_scope(project: Path) -> dict:
    base = project / "artifacts/ens_x_crosswalk"
    seed_path = base / "two_graph_seed_20260925/crosswalk_confirmed_unique.csv"
    evidence_path = base / "verification_sample_v2_filled.csv"
    revnodes_path = base / "candidate_revnodes.parquet"
    seed, evidence = read_csv(seed_path), read_csv(evidence_path)
    if not seed:
        raise ValueError("confirmed seed crosswalk is empty")
    namehash = load_namehash(project)

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("PyArrow is required to read the local reverse-node map") from exc
    rev_rows = pq.read_table(revnodes_path, columns=["address", "revnode"]).to_pylist()
    reverse_index: dict[str, set[str]] = defaultdict(set)
    for row in rev_rows:
        addr, node = (row.get("address") or "").lower(), (row.get("revnode") or "").lower()
        if addr and node:
            reverse_index[addr].add(node)

    seen_addresses, seen_ids = set(), set()
    links, forward_nodes, reverse_nodes = [], set(), set()
    unresolved_forward = []
    review_only_forward: dict[str, dict] = {}
    for row in seed:
        address, uid = (row.get("address") or "").strip().lower(), (row.get("x_user_id") or "").strip()
        if not address.startswith("0x") or len(address) != 42 or not uid:
            raise ValueError("seed row has malformed wallet address or stable X ID")
        if address in seen_addresses or uid in seen_ids:
            raise ValueError("seed crosswalk contains duplicate wallet or stable X ID")
        matched = resolve_account_confirm_evidence(row, evidence)
        reverse_name = address[2:] + ".addr.reverse"
        expected_reverse = namehash(reverse_name)
        local_reverse = reverse_index.get(address, set())
        if local_reverse != {expected_reverse}:
            raise ValueError(f"local reverse-node map mismatch/ambiguity for {address}: {sorted(local_reverse)}")
        reverse_nodes.add(expected_reverse)

        valid_forward = set()
        for source in matched:
            source_node = (source.get("node") or "").lower()
            try:
                expected_forward = namehash(source.get("reverse_name") or "")
            except (ValueError, RuntimeError):
                expected_forward = ""
            if source_node and expected_forward and source_node == expected_forward:
                valid_forward.add(source_node)
            else:
                reason = (
                    "namehash_input_unsupported_by_local_namehash" if not expected_forward else
                    "source_node_missing" if not source_node else
                    "source_node_not_equal_to_computed_namehash"
                )
                unresolved_forward.append({
                    "address": address, "x_user_id": uid, "pair_id": source.get("pair_id", ""),
                    "reverse_name": source.get("reverse_name", ""), "source_node": source_node,
                    "computed_namehash": expected_forward or None,
                    "reason": reason,
                })
                # Keep a separately labeled investigation node so the bounded
                # event extraction can test the ENS name's forward history. It
                # is NOT a validated crosswalk node and cannot promote a link.
                if expected_forward and source.get("reverse_name"):
                    review_only_forward.setdefault(expected_forward, {
                        "node": expected_forward,
                        "reverse_name": source.get("reverse_name", ""),
                        "candidate_wallets": [],
                        "source_pair_ids": [],
                        "status": "review_only_namehash_candidate_source_node_mismatch",
                        "mapping_adjudication_changed": False,
                    })
                    candidate = review_only_forward[expected_forward]
                    if address not in candidate["candidate_wallets"]:
                        candidate["candidate_wallets"].append(address)
                    if source.get("pair_id", "") not in candidate["source_pair_ids"]:
                        candidate["source_pair_ids"].append(source.get("pair_id", ""))
        if len(valid_forward) > 1:
            raise ValueError(f"multiple validated forward nodes for one seed wallet: {address}")
        forward_nodes.update(valid_forward)
        links.append({
            "address": address, "x_user_id": uid,
            "source_pair_ids": sorted(r["pair_id"] for r in matched),
            "forward_ens_nodes_namehash_validated": sorted(valid_forward),
            "reverse_node": expected_reverse,
            "forward_node_status": "namehash_validated" if valid_forward else "unresolved",
        })
        seen_addresses.add(address); seen_ids.add(uid)

    unresolved_wallets = {item["address"] for item in unresolved_forward}
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_confirmed_seed_ens_event_scope_only",
        "network_accessed": False,
        "query_performed": False,
        "collection_authorized": False,
        "scope": "12 currently account-confirmed seed wallet-X-ID links only; no unreviewed candidates",
        "inputs": {
            "seed_crosswalk": {"path": str(seed_path.relative_to(project)), "sha256": sha256_file(seed_path), "rows": len(seed)},
            "account_evidence": {"path": str(evidence_path.relative_to(project)), "sha256": sha256_file(evidence_path)},
            "local_reverse_node_map": {"path": str(revnodes_path.relative_to(project)), "sha256": sha256_file(revnodes_path), "rows": len(rev_rows)},
        },
        "links": links,
        "review_only_forward_node_candidates": [
            {**candidate,
             "candidate_wallets": sorted(candidate["candidate_wallets"]),
             "source_pair_ids": sorted(candidate["source_pair_ids"])}
            for _, candidate in sorted(review_only_forward.items())
        ],
        "query_node_sets": {
            "validated_forward_ens_nodes": sorted(forward_nodes),
            "review_only_forward_nodes_not_eligible_for_mapping": sorted(review_only_forward),
            "wallet_reverse_nodes": sorted(reverse_nodes),
            "all_eligible_nodes_union": sorted(forward_nodes | reverse_nodes),
            "bounded_investigation_query_nodes_union": sorted(forward_nodes | reverse_nodes | set(review_only_forward)),
        },
        "unresolved_forward_node_evidence": unresolved_forward,
        "unresolved_forward_wallet_count": len(unresolved_wallets),
        "required_event_families": [
            "ENS Registry resolver assignment changes (forward and reverse nodes)",
            "resolver AddrChanged (legacy ETH address state)",
            "resolver AddressChanged filtered to coinType=60 (multicoin ETH address state)",
            "resolver TextChanged for supported Twitter/X keys, decoded by emitter ABI/version",
            "resolver NameChanged (reverse name state)",
        ],
        "event_abi_review": {
            "status": "not_frozen",
            "local_evidence": [
                "notes/ens-x-crosswalk-pilot-20260924.md",
                "artifacts/ens_x_crosswalk/state_audit_20260925/text_projection_rebuild_20260925_v3.md",
                "scripts/audit_and_rebuild_ens_x_text_projection.py",
            ],
            "address_state_rule": "include both AddrChanged and AddressChanged; AddressChanged must be restricted to coinType=60 for this Ethereum-address crosswalk and decoded without lossy coercion",
            "text_state_rule": "support topic/ABI variants per resolver emitter and block interval; key-only events or unresolved legacy payload semantics cannot be treated as a known Twitter/X value or deletion",
            "emitter_rule": "bind every resolver log to the active ENS Registry resolver at that event order and retain resolver address plus ABI/code-version evidence",
            "freeze_requirements": [
                "event signature/topic0 and indexed/data layout per event family",
                "resolver emitter address and implementation/code hash over covered block interval",
                "decoder version and canary comparison against independent decoded logs",
                "explicit handling for missing TextChanged values and AddressChanged coinType filtering",
            ],
        },
        "required_chain_order_fields": ["block_number", "transaction_index", "log_index"],
        "query_gates": {
            "live_source_schema_and_partition_metadata_verified": False,
            "event_signatures_and_abi_versions_frozen": False,
            "history_start_boundary_justified": False,
            "dry_run_bytes_reviewed": False,
            "owner_approved_maximum_bytes_billed": False,
            "bounded_query_ready": False,
        },
        "readiness": {
            "reverse_node_scope_validated": len(reverse_nodes) == len(seed),
            "all_forward_nodes_resolved": len(unresolved_wallets) == 0,
            "event_time_asof_ready": False,
            "next_action": "Review the separate review-only namehash nodes against complete event history; preserve all 3 wallets as unresolved until forward/reverse/resolver/text and dated X evidence replay passes, then verify source schema/coverage/cost gates before any query; do not expand scope.",
        },
        "interpretation": "A reproducible bounded node-scope draft only. Review-only namehash nodes are included solely to investigate mismatched source-node claims; they are not validated links or promotion evidence. This report does not establish event-source completeness, historical resolver state, historical X identity, or as-of validity.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_scope(args.project.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "seed_links": len(report["links"]),
                      "validated_forward_nodes": len(report["query_node_sets"]["validated_forward_ens_nodes"]),
                      "reverse_nodes": len(report["query_node_sets"]["wallet_reverse_nodes"]),
                      "unresolved_forward_pair_evidence_rows": len(report["unresolved_forward_node_evidence"]),
                      "unresolved_forward_wallets": report["unresolved_forward_wallet_count"],
                      "query_performed": False, "event_time_asof_ready": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
