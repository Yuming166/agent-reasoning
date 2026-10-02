#!/usr/bin/env python3
"""Offline reconciliation of seven explicitly scoped seed-source ENS text nodes.

This produces projection observations only. It never promotes a wallet-X link
or reconstructs historical ENS state; timestamps lack canonical chain order.
No network, RPC, FxEmbed, or BigQuery access is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

EXPECTED_PAIR_IDS = ("P003", "P008", "P081", "P031", "P048", "P035", "P091")
NO_ASOF = "projection_observation_only_not_asof_valid"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def norm(value: object) -> str:
    return str(value or "").strip().lower()


def timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("naive timestamp in projection")
    return result.astimezone(timezone.utc)



def classify_reverse_namehash(node: str, reverse_name: str, namehash_fn) -> tuple[str | None, str]:
    """Classify the reverse-name comparison without upgrading unsupported names."""
    try:
        result = namehash_fn(reverse_name)
    except (ValueError, RuntimeError):
        return None, "unsupported_non_ascii_or_noncanonical"
    if norm(node) == norm(result):
        raise ValueError("pair reverse namehash matches the candidate node; not in mismatch scope")
    return result, "computed_node_mismatch"


def expected_handle(value: str) -> str:
    return value.strip().removeprefix("@").casefold()


def reconcile_pair_rows(
    evidence: dict[str, str], text_rows: Iterable[dict], address_rows: Iterable[dict],
    reverse_namehash: str | None = None,
) -> dict:
    pair_id = (evidence.get("pair_id") or "").strip()
    if pair_id not in EXPECTED_PAIR_IDS:
        raise ValueError(f"pair outside frozen candidate-node scope: {pair_id}")
    if evidence.get("verification_status") != "account_confirms":
        raise ValueError(f"{pair_id}: source row is not account_confirms")
    node, tx = norm(evidence.get("node")), norm(evidence.get("transaction_hash"))
    address, handle = norm(evidence.get("address")), expected_handle(evidence.get("handle", ""))
    if not all((node, tx, address, handle, evidence.get("x_user_id"))):
        raise ValueError(f"{pair_id}: missing node/tx/address/handle/stable X ID")

    matches = [r for r in text_rows if norm(r.get("node")) == node
               and norm(r.get("transaction_hash")) == tx
               and norm(r.get("key")) == "com.twitter"
               and expected_handle(str(r.get("value") or "")) == handle]
    if len(matches) != 1:
        raise ValueError(f"{pair_id}: expected one exact TextChanged row, found {len(matches)}")
    text = matches[0]
    text_ts = timestamp(text.get("block_timestamp"))
    if text_ts is None:
        raise ValueError(f"{pair_id}: matched TextChanged row has no timestamp")

    addr = [r for r in address_rows if norm(r.get("node")) == node
            and norm(r.get("address")) == address]
    addr_times = [timestamp(r.get("block_timestamp")) for r in addr]
    addr_times = [t for t in addr_times if t is not None]
    latest = max(addr_times) if addr_times else None
    delta = (text_ts - latest).total_seconds() if latest else None
    return {
        "pair_id": pair_id,
        "address": address,
        "x_user_id": str(evidence["x_user_id"]).strip(),
        "ens_node": node,
        "reverse_name": evidence.get("reverse_name", ""),
        "reverse_namehash": reverse_namehash,
        "source_node_differs_from_reverse_namehash": (node != reverse_namehash) if reverse_namehash else None,
        "handle": evidence.get("handle", ""),
        "account_evidence_status": "account_confirms",
        "textchanged_match": {
            "count": 1,
            "transaction_hash": tx,
            "key": text.get("key"),
            "value": text.get("value"),
            "timestamp_utc": text_ts.isoformat(),
            "resolver": text.get("resolver"),
            "event_family": text.get("event_family"),
            "decode_status": text.get("decode_status"),
        },
        "same_node_address_observation": {
            "row_count": len(addr),
            "first_timestamp_utc": min(addr_times).isoformat() if addr_times else None,
            "last_timestamp_utc": latest.isoformat() if latest else None,
            "text_minus_latest_addrchanged_seconds_timestamp_only": delta,
            "timestamp_precision_warning": "source timestamps only; no block/transaction/log ordering",
        },
        "link_status": NO_ASOF,
    }


def build_report(project: Path) -> dict:
    base = project / "artifacts/ens_x_crosswalk"
    evidence_path = base / "verification_sample_v2_filled.csv"
    text_path = base / "textchanged_twitter_decoded_v3.parquet"
    addr_path = base / "addrchanged_latest.parquet"
    evidence_rows = read_csv(evidence_path)
    by_pair = {}
    for row in evidence_rows:
        pair_id = row.get("pair_id")
        if pair_id in EXPECTED_PAIR_IDS:
            if pair_id in by_pair:
                raise ValueError(f"duplicate frozen candidate pair in source: {pair_id}")
            by_pair[pair_id] = row
    if set(by_pair) != set(EXPECTED_PAIR_IDS):
        raise ValueError("frozen candidate pair scope is incomplete in source")
    selected = [by_pair[pair_id] for pair_id in EXPECTED_PAIR_IDS]
    if any(r.get("verification_status") != "account_confirms" for r in selected):
        raise ValueError("candidate pair evidence status changed; refusing reconciliation")

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("PyArrow is required") from exc
    text_wanted = {(norm(r["node"]), norm(r["transaction_hash"])) for r in selected}
    text_rows = []
    for batch in pq.ParquetFile(text_path).iter_batches(batch_size=8192):
        for row in batch.to_pylist():
            key = (norm(row.get("node")), norm(row.get("transaction_hash")))
            if key in text_wanted:
                text_rows.append(row)
    addr_wanted = {norm(r["node"]) for r in selected}
    addr_rows = []
    for batch in pq.ParquetFile(addr_path).iter_batches(batch_size=65536):
        for row in batch.to_pylist():
            if norm(row.get("node")) in addr_wanted:
                addr_rows.append(row)

    replay_spec = importlib.util.spec_from_file_location("replay_ens_x_asof_scope_audit", project / "scripts/replay_ens_x_asof.py")
    replay_mod = importlib.util.module_from_spec(replay_spec)
    replay_spec.loader.exec_module(replay_mod)
    reconciliations = []
    for row in selected:
        try:
            reverse_hash, reverse_status = classify_reverse_namehash(
                row.get("node", ""), row.get("reverse_name", ""), replay_mod.ens_namehash
            )
        except ValueError as exc:
            raise ValueError(f"{row['pair_id']}: {exc}") from exc
        result = reconcile_pair_rows(row, text_rows, addr_rows, reverse_hash)
        result["reverse_namehash_status"] = reverse_status
        reconciliations.append(result)
    if any(row["link_status"] != NO_ASOF for row in reconciliations):
        raise AssertionError("status promotion invariant violated")
    generated = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at_utc": generated,
        "mode": "offline_frozen_seed_pair_projection_reconciliation_no_network_no_bigquery",
        "scope_pair_ids": list(EXPECTED_PAIR_IDS),
        "scope_expansion_allowed": False,
        "input_sha256": {p.name: sha256_file(p) for p in (evidence_path, text_path, addr_path)},
        "counts": {
            "scoped_pairs": len(reconciliations),
            "exact_textchanged_matches": sum(r["textchanged_match"]["count"] == 1 for r in reconciliations),
            "pairs_with_same_node_address_observation": sum(r["same_node_address_observation"]["row_count"] > 0 for r in reconciliations),
            "asof_valid_links": 0,
        },
        "reconciliations": reconciliations,
        "limitations": [
            "Exact projection observations for a frozen seven-pair scope only; not an ENS ownership proof.",
            "Six supported ASCII reverse names have computed node-hash mismatches; P035 has a non-ASCII reverse name unsupported by the configured namehash validator and is not classified as a verified mismatch.",
            "AddrChanged projection completeness and resolver history are unverified.",
            "Timestamps do not include canonical block/transaction/log ordering; timestamp precedence is not event order.",
            "Historical X identity validity intervals are unavailable.",
            "No node outside the explicit source-pair list is searched or added to scope.",
            "Therefore no row is asof_valid and this is not an event-time wallet-X crosswalk.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.project.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
