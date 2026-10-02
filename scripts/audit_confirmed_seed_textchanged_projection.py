#!/usr/bin/env python3
"""Offline, partial TextChanged audit for the account-confirmed seed crosswalk.

This deliberately does not perform an ENS historical as-of replay: the source is
TextChanged-only, lacks canonical chain order, and is not a completeness proof.
No network, ENS RPC, X/FxEmbed, or BigQuery access is performed.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter, defaultdict
from datetime import timezone
from pathlib import Path
import importlib.util

KEYS = {"twitter", "com.twitter", "x", "com.x"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))



def resolve_account_confirm_evidence(seed_row: dict[str, str], evidence_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return the exact account-confirming source rows for one seed link.

    Fail closed if a declared source pair is absent, duplicated, belongs to a
    different address/X ID, or is not explicitly marked account_confirms.
    """
    uid = (seed_row.get("x_user_id") or "").strip()
    address = (seed_row.get("address") or "").strip().lower()
    pair_ids = [item.strip() for item in (seed_row.get("source_pair_ids") or "").split(";") if item.strip()]
    if not uid or not address or not pair_ids or len(pair_ids) != len(set(pair_ids)):
        raise ValueError("seed row has missing identity/source pair or duplicate source pair IDs")
    resolved = []
    for pair_id in pair_ids:
        matches = [r for r in evidence_rows if (r.get("pair_id") or "").strip() == pair_id]
        if len(matches) != 1:
            raise ValueError(f"source pair {pair_id} resolves to {len(matches)} evidence rows; expected exactly one")
        evidence = matches[0]
        if (evidence.get("address") or "").strip().lower() != address:
            raise ValueError(f"source pair {pair_id} address does not match seed row")
        if (evidence.get("x_user_id") or "").strip() != uid:
            raise ValueError(f"source pair {pair_id} stable X ID does not match seed row")
        if (evidence.get("verification_status") or "").strip() != "account_confirms":
            raise ValueError(f"source pair {pair_id} is not explicitly account_confirms")
        resolved.append(evidence)
    return resolved


def build_report(project: Path) -> dict:
    base = project / "artifacts/ens_x_crosswalk"
    seed_path = base / "two_graph_seed_20260925/crosswalk_confirmed_unique.csv"
    evidence_path = base / "verification_sample_v2_filled.csv"
    projection_path = base / "textchanged_twitter_decoded_v3.parquet"
    seed, evidence = read_csv(seed_path), read_csv(evidence_path)
    evidence_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evidence:
        if row.get("x_user_id"):
            evidence_by_id[row["x_user_id"]].append(row)
    replay_spec = importlib.util.spec_from_file_location("replay_ens_x_asof", project / "scripts/replay_ens_x_asof.py")
    replay_mod = importlib.util.module_from_spec(replay_spec)
    replay_spec.loader.exec_module(replay_mod)
    seen_ids, seen_addresses, seen_nodes = set(), set(), set()
    links, node_audit = [], []
    for row in seed:
        uid, address = row.get("x_user_id", "").strip(), row.get("address", "").lower()
        if not uid or uid in seen_ids or address in seen_addresses:
            raise ValueError("seed crosswalk has missing/duplicate stable X ID or address")
        pair_ids = {item.strip() for item in row.get("source_pair_ids", "").split(";") if item.strip()}
        matches = resolve_account_confirm_evidence(row, evidence)
        valid_nodes = []
        invalid_node_pairs = []
        for match in matches:
            node = (match.get("node") or "").lower()
            try:
                expected = replay_mod.ens_namehash(match.get("reverse_name", ""))
            except (ValueError, RuntimeError):
                expected = ""
            if node and node == expected:
                valid_nodes.append((node, match))
            else:
                invalid_node_pairs.append(match.get("pair_id", ""))
        # Never choose a node merely because it shares the same stable X ID.
        selected = valid_nodes[0] if len(valid_nodes) == 1 else None
        node_audit.append({"address": address, "x_user_id": uid,
                           "source_pair_ids": sorted(pair_ids),
                           "account_confirms_pair_ids": sorted(r.get("pair_id", "") for r in matches),
                           "account_confirms_evidence_rows": len(matches),
                           "namehash_valid_pair_ids": sorted(r.get("pair_id", "") for _, r in valid_nodes),
                           "node_hash_mismatch_or_unsupported_pair_ids": sorted(invalid_node_pairs),
                           "ens_node_status": "uniquely_namehash_validated" if selected else ("ambiguous_valid_nodes" if valid_nodes else "no_namehash_validated_node")})
        if selected:
            node = selected[0]
            if node in seen_nodes:
                raise ValueError("validated ENS node is duplicated across seed pairs")
            seen_nodes.add(node)
            links.append({"x_user_id": uid, "address": address, "ens_node": node})
        seen_ids.add(uid); seen_addresses.add(address)

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("PyArrow is required for the local projection audit") from exc
    parquet = pq.ParquetFile(projection_path)
    columns = parquet.schema_arrow.names
    required = {"node", "block_timestamp", "topic0", "transaction_hash", "key", "value", "decode_status", "event_family", "resolver"}
    if not required.issubset(columns):
        raise ValueError(f"projection missing columns: {sorted(required - set(columns))}")
    counts = Counter(); per_node = defaultdict(Counter); times = []
    identities = Counter()
    node_set = {x["ens_node"] for x in links}
    for batch in parquet.iter_batches(batch_size=8192):
        for row in batch.to_pylist():
            node = (row.get("node") or "").lower()
            key = (row.get("key") or "").lower()
            if node not in node_set or key not in KEYS:
                continue
            counts["rows"] += 1
            per_node[node]["rows"] += 1
            per_node[node][f"key:{key}"] += 1
            per_node[node][f"event_family:{row.get('event_family') or 'unknown'}"] += 1
            if row.get("resolver"):
                counts["rows_with_resolver_field"] += 1
            if "uncertain" in (row.get("decode_status") or ""):
                counts["rows_with_uncertain_decode_status"] += 1
            ts = row.get("block_timestamp")
            if ts is not None:
                if ts.tzinfo is None:
                    raise ValueError("projection has naive block_timestamp")
                times.append(ts.astimezone(timezone.utc))
            # This is only a duplicate-warning key; without log_index it is not a canonical event ID.
            identities[(node, row.get("transaction_hash"), row.get("topic0"), key, row.get("value"))] += 1
    nodes_with_rows = sum(bool(per_node[n]["rows"]) for n in node_set)
    return {
        "generated_at_utc": __import__("datetime").datetime.now(timezone.utc).isoformat(),
        "mode": "offline_confirmed_seed_textchanged_projection_audit",
        "network_accessed": False,
        "inputs": {
            "confirmed_crosswalk": {"path": str(seed_path.relative_to(project)), "sha256": sha256_file(seed_path), "rows": len(seed), "unique_x_ids": len(seen_ids), "unique_addresses": len(seen_addresses), "unique_ens_nodes_namehash_validated": len(seen_nodes),
                                 "seed_wallet_x_links_with_exact_account_confirms": len(node_audit),
                                 "account_confirms_evidence_rows": sum(len(x["account_confirms_pair_ids"]) for x in node_audit),
                                 "ens_node_unresolved_pairs": len(seed) - len(links)},
            "account_evidence": {"path": str(evidence_path.relative_to(project)), "sha256": sha256_file(evidence_path)},
            "projection": {"path": str(projection_path.relative_to(project)), "sha256": sha256_file(projection_path), "total_rows": parquet.metadata.num_rows, "schema": columns},
        },
        "filtered_textchanged": {
            "target_keys": sorted(KEYS), "rows": counts["rows"], "ens_nodes_with_observed_rows": nodes_with_rows,
            "utc_min": min(times).isoformat() if times else None, "utc_max": max(times).isoformat() if times else None,
            "rows_with_resolver_field": counts["rows_with_resolver_field"],
            "rows_with_uncertain_decode_status": counts["rows_with_uncertain_decode_status"],
            "duplicate_groups_on_noncanonical_node_tx_topic_key_value_key": sum(v > 1 for v in identities.values()),
        },
        "ens_node_resolution_audit": node_audit,
        "per_ens_node": {n: dict(per_node[n]) for n in sorted(node_set)},
        "readiness": {"text_record_partial_observations_available": bool(counts["rows"]), "full_event_time_asof_ready": False,
                      "missing_or_unproven": ["TextChanged-only projection; resolver assignment, AddrChanged, and reverse NameChanged histories absent", "no block_number/transaction_index/log_index canonical order", "topic1/topic2 indexed-field consistency unavailable", "source-family completeness and ABI coverage not proven", "historical X account identity validity intervals absent"]},
        "interpretation": "Observed decoded Twitter/X TextChanged rows for currently account-confirmed seed ENS nodes only. Counts are partial projection observations, not complete historical state or valid event-time wallet-X links.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    report = build_report(args.project.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "seed_pairs": report["inputs"]["confirmed_crosswalk"]["rows"], **report["filtered_textchanged"], "full_event_time_asof_ready": False}, ensure_ascii=False))

if __name__ == "__main__":
    main()
