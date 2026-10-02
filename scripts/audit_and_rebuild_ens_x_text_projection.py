#!/usr/bin/env python3
"""Audit and rebuild a decoded ENS text-record projection from local Parquet only.

No network, X/FxEmbed, ENS RPC, or BigQuery access occurs. This output is an
analysis projection, not a complete or canonically ordered ENS event stream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEXT_TOPICS = {
    "0xd8c9334b1a9c2f9da342a0a2b32629c1a229b6445dad78947f674b44444a7550": "text_changed_legacy",
    "0x448bc014f1536726cf8d54ff3d6481ed3cbc683c2591ca204274009afa09b1a1": "text_changed_indexed_key",
}
TWITTER_KEYS = frozenset({"twitter", "com.twitter", "x", "com.x"})
REQUIRED_ASOF_FIELDS = frozenset({
    "block_number", "transaction_index", "log_index", "block_timestamp_utc",
    "event_type", "node", "address", "resolver", "key", "value", "emitter",
})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _word(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 32 > len(data):
        raise ValueError("ABI word is out of bounds")
    return int.from_bytes(data[offset:offset + 32], "big")


def decode_abi_string(data_hex: str) -> str:
    """Decode one non-indexed dynamic string from an event data payload."""
    raw = _hex_payload(data_hex)
    if len(raw) < 64 or len(raw) % 32:
        raise ValueError("single-string ABI payload has invalid length")
    offset = _word(raw, 0)
    if offset < 32 or offset % 32:
        raise ValueError("single-string ABI offset is invalid")
    length = _word(raw, offset)
    start, end = offset + 32, offset + 32 + length
    if end > len(raw):
        raise ValueError("single-string ABI content is truncated")
    _validate_padding(raw, end)
    return raw[start:end].decode("utf-8", errors="strict")


def decode_abi_string_pair(data_hex: str) -> tuple[str, str]:
    """Decode two non-indexed strings from an event data payload.

    The returned tuple is only a payload-level interpretation. Event family and
    emitter must be retained because historical TextChanged ABI layouts vary.
    """
    raw = _hex_payload(data_hex)
    if len(raw) < 128 or len(raw) % 32:
        raise ValueError("two-string ABI payload has invalid length")
    offsets = (_word(raw, 0), _word(raw, 32))
    if any(o < 64 or o % 32 for o in offsets) or offsets[0] == offsets[1]:
        raise ValueError("two-string ABI offsets are invalid")
    decoded: list[tuple[int, int, str]] = []
    for offset in offsets:
        length = _word(raw, offset)
        start, end = offset + 32, offset + 32 + length
        if end > len(raw):
            raise ValueError("two-string ABI content is truncated")
        _validate_padding(raw, end)
        decoded.append((offset, end, raw[start:end].decode("utf-8", errors="strict")))
    # Dynamic tails must not overlap. Ordering need not be key then value by offset.
    intervals = sorted((offset, end) for offset, end, _ in decoded)
    if intervals[0][1] > intervals[1][0]:
        raise ValueError("two-string ABI tails overlap")
    return decoded[0][2], decoded[1][2]


def decode_textchanged_payload(topic0: str, data_hex: str) -> tuple[str, str | None, str]:
    """Decode a known TextChanged payload without inventing a missing value.

    The four-argument family has two data strings. The legacy three-argument
    family is observed locally with either one or two data strings; preserve
    that shape and do not infer a value for one-string payloads.
    """
    family = TEXT_TOPICS.get(str(topic0).lower())
    if family == "text_changed_indexed_key":
        key, value = decode_abi_string_pair(data_hex)
        return key, value, "two_strings_key_value_by_family"
    if family == "text_changed_legacy":
        try:
            key, value = decode_abi_string_pair(data_hex)
            return key, value, "two_strings_legacy_semantics_uncertain"
        except ValueError as pair_error:
            try:
                key = decode_abi_string(data_hex)
                return key, None, "one_string_key_only_value_unavailable"
            except (ValueError, UnicodeError):
                raise pair_error
    raise ValueError("unrecognized TextChanged topic")


def _validate_padding(raw: bytes, end: int) -> None:
    padded_end = ((end + 31) // 32) * 32
    if padded_end > len(raw):
        raise ValueError("ABI string padding is truncated")
    if any(raw[end:padded_end]):
        raise ValueError("ABI string padding is nonzero")


def _hex_payload(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("ABI data is not text")
    text = value[2:] if value.startswith("0x") else value
    if len(text) % 2:
        raise ValueError("ABI hex payload has odd length")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError("ABI payload is not hex") from exc


def _normalize_node(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s.startswith("0x") and len(s) == 66:
        try:
            bytes.fromhex(s[2:])
            return s
        except ValueError:
            pass
    return ""


def _ascii_namehash(name: str) -> str:
    """Conservative ASCII ENS namehash; return empty for unsupported names."""
    name = name.strip().rstrip(".").lower()
    if not name or any(ord(c) > 127 for c in name):
        return ""
    try:
        from eth_utils import keccak
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("eth-utils is required for ENS candidate scoping") from exc
    node = bytes(32)
    try:
        for label in reversed(name.split(".")):
            if not label or any(not (c.isalnum() or c == "-") for c in label):
                return ""
            label_hash = keccak(text=label)
            node = keccak(node + label_hash)
    except (UnicodeError, ValueError):
        return ""
    return "0x" + node.hex()


def load_candidates(project: Path) -> dict[str, dict[str, Any]]:
    import csv
    path = project / "artifacts/ens_x_crosswalk/expansion_decision_20260925/candidate_review_full_231.csv"
    if not path.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            address = row.get("address", "").strip().lower()
            node = _ascii_namehash(row.get("reverse_ens_name", ""))
            if address:
                out[address] = {
                    "address": address,
                    "x_user_id": row.get("x_user_id", "").strip(),
                    "reverse_ens_name": row.get("reverse_ens_name", "").strip(),
                    "forward_node": node,
                    "manual_verdict": row.get("manual_verdict", "pending").strip(),
                }
    return out


def _parquet_file(path: Path):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("PyArrow is required; use the project .venv-cuda environment") from exc
    return pq.ParquetFile(path)


def build_report(project: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    base = project / "artifacts/ens_x_crosswalk"
    reverse_path = base / "reverse_evidence.parquet"
    text_path = base / "textchanged_raw_v2.parquet"
    projection_path = base / "textchanged_twitter.parquet"
    candidate_path = project / "artifacts/ens_x_crosswalk/expansion_decision_20260925/candidate_review_full_231.csv"
    candidates = load_candidates(project)
    forward_node_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cand in candidates.values():
        if cand["forward_node"]:
            forward_node_candidates[cand["forward_node"]].append(cand)
    candidate_forward_nodes = set(forward_node_candidates)
    reverse_nodes = set()
    revnode_path = base / "candidate_revnodes.parquet"
    if revnode_path.exists() and candidates:
        pf = _parquet_file(revnode_path)
        for batch in pf.iter_batches(columns=["address", "revnode"], batch_size=65536):
            for row in batch.to_pylist():
                if str(row.get("address", "")).lower() in candidates:
                    n = _normalize_node(row.get("revnode"))
                    if n:
                        reverse_nodes.add(n)

    text_pf = _parquet_file(text_path)
    text_cols = set(text_pf.schema_arrow.names)
    text_missing = sorted({"block_number", "transaction_index", "log_index", "topic1", "topic2"} - text_cols)
    topic_counts: Counter[str] = Counter()
    emitter_counts: Counter[str] = Counter()
    decode_errors: Counter[str] = Counter()
    decode_errors_by_emitter: Counter[str] = Counter()
    payload_shape_counts: Counter[str] = Counter()
    payload_shape_by_emitter: Counter[str] = Counter()
    key_counts: Counter[str] = Counter()
    candidate_text_nodes: set[str] = set()
    candidate_text_key_counts: Counter[str] = Counter()
    first_by_candidate: dict[str, str] = {}
    last_by_candidate: dict[str, str] = {}
    candidate_event_counts: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    projection_key_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    source_identity_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    source_first = source_last = None
    decoded_known = 0
    text_rows = 0

    needed = [c for c in ("block_timestamp", "node", "topic0", "resolver", "data", "transaction_hash") if c in text_cols]
    for batch in text_pf.iter_batches(columns=needed, batch_size=32768):
        for row in batch.to_pylist():
            text_rows += 1
            ts = row.get("block_timestamp")
            ts_s = ts.astimezone(timezone.utc).isoformat() if ts else ""
            source_first = min(source_first, ts_s) if source_first and ts_s else (ts_s or source_first)
            source_last = max(source_last, ts_s) if source_last and ts_s else (ts_s or source_last)
            topic = str(row.get("topic0", "")).lower()
            topic_counts[topic] += 1
            emitter = str(row.get("resolver", "")).lower()
            emitter_counts[emitter] += 1
            node = _normalize_node(row.get("node"))
            kind = TEXT_TOPICS.get(topic)
            if not kind:
                continue
            try:
                key, value, decode_status = decode_textchanged_payload(topic, row.get("data") or "")
            except (ValueError, UnicodeError) as exc:
                decode_errors[kind + ": " + str(exc)] += 1
                decode_errors_by_emitter[kind + "|" + emitter + "|" + str(exc)] += 1
                continue
            decoded_known += 1
            payload_shape_counts[kind + "|" + decode_status] += 1
            payload_shape_by_emitter[kind + "|" + emitter + "|" + decode_status] += 1
            key_fold = key.casefold()
            key_counts[f"{kind}|{key_fold}"] += 1
            tx = str(row.get("transaction_hash", "")).lower()
            identity = (tx, node, topic)
            decoded_event = {
                "block_timestamp": ts,
                "node": node,
                "topic0": topic,
                "resolver": str(row.get("resolver", "")).lower(),
                "transaction_hash": tx,
                "key": key,
                "value": value,
                "decode_status": decode_status,
                "event_family": kind,
                "source_file": "textchanged_raw_v2.parquet",
                "source_row_index": text_rows - 1,
            }
            source_identity_rows[identity].append(decoded_event)
            if key_fold in TWITTER_KEYS and value is not None:
                rec = decoded_event
                records.append(rec)
                projection_key_rows[identity].append(rec)
            if node in candidate_forward_nodes and key_fold in TWITTER_KEYS and value is not None:
                candidate_text_nodes.add(node)
                candidate_text_key_counts[key_fold] += 1
                for cand in forward_node_candidates[node]:
                    addr = cand["address"]
                    candidate_event_counts[addr] += 1
                    if ts_s:
                        first_by_candidate[addr] = min(first_by_candidate.get(addr, ts_s), ts_s)
                        last_by_candidate[addr] = max(last_by_candidate.get(addr, ts_s), ts_s)

    # Reconcile old projection rows against all ABI-decoded raw events. Since
    # log_index is absent, duplicate (tx,node,topic0) identities stay ambiguous.
    old_pf = _parquet_file(projection_path)
    old_cols = set(old_pf.schema_arrow.names)
    old_decoded_counts: Counter[str] = Counter()
    reconcile = Counter()
    old_only_legacy_keys: Counter[str] = Counter()
    for batch in old_pf.iter_batches(columns=[c for c in ("node", "topic0", "transaction_hash", "key", "value") if c in old_cols], batch_size=32768):
        for row in batch.to_pylist():
            identity = (str(row.get("transaction_hash", "")).lower(), _normalize_node(row.get("node")), str(row.get("topic0", "")).lower())
            old_decoded_counts[str(row.get("key", "")).casefold()] += 1
            if not all(identity):
                reconcile["old_row_missing_identity"] += 1
                continue
            raw_matches = source_identity_rows.get(identity, [])
            if not raw_matches:
                reconcile["no_decoded_raw_identity_match"] += 1
                continue
            if len(raw_matches) != 1:
                reconcile["ambiguous_raw_identity_missing_log_index"] += 1
                continue
            raw = raw_matches[0]
            if raw["key"] != row.get("key"):
                reconcile["matched_identity_key_disagreement"] += 1
                old_only_legacy_keys[str(row.get("key", "")).casefold()] += 1
            elif raw["value"] is None:
                reconcile["matched_key_only_value_unavailable"] += 1
            elif raw["value"] != row.get("value"):
                reconcile["matched_identity_value_disagreement"] += 1
                old_only_legacy_keys[str(row.get("key", "")).casefold()] += 1
            else:
                reconcile["matched_key_value"] += 1

    reverse_pf = _parquet_file(reverse_path)
    reverse_topics: Counter[str] = Counter()
    reverse_emitters: Counter[str] = Counter()
    reverse_decode_errors: Counter[str] = Counter()
    reverse_name_events = 0
    reverse_candidate_rows = 0
    candidate_reverse_nodes_observed: set[str] = set()
    reverse_candidate_exact = 0
    candidate_reverse_exact_nodes: set[str] = set()
    reverse_ts_min = reverse_ts_max = None
    reverse_cols = set(reverse_pf.schema_arrow.names)
    for batch in reverse_pf.iter_batches(columns=[c for c in ("block_timestamp", "transaction_hash", "emitter", "log_index", "topic0", "topic1", "data") if c in reverse_cols], batch_size=32768):
        for row in batch.to_pylist():
            topic = str(row.get("topic0", "")).lower()
            reverse_topics[topic] += 1
            emitter = str(row.get("emitter", "")).lower()
            reverse_emitters[emitter] += 1
            ts = row.get("block_timestamp")
            if ts:
                reverse_ts_min = min(reverse_ts_min, ts) if reverse_ts_min else ts
                reverse_ts_max = max(reverse_ts_max, ts) if reverse_ts_max else ts
            if topic != "0xb7d29e911041e8d9b843369e890bcb72c9388692ba48b65ac54e7214c4c348f7":
                continue
            try:
                name = decode_abi_string(row.get("data") or "")
            except (ValueError, UnicodeError) as exc:
                reverse_decode_errors[str(exc)] += 1
                continue
            reverse_name_events += 1
            node = _normalize_node(row.get("topic1"))
            if node in reverse_nodes:
                reverse_candidate_rows += 1
                candidate_reverse_nodes_observed.add(node)

    # Build reverse-node to candidate name map and exact match counts with one additional bounded pass.
    reverse_node_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if revnode_path.exists():
        pf = _parquet_file(revnode_path)
        for batch in pf.iter_batches(columns=["address", "revnode"], batch_size=65536):
            for r in batch.to_pylist():
                address = str(r.get("address", "")).lower()
                if address in candidates:
                    node = _normalize_node(r.get("revnode"))
                    if node:
                        reverse_node_candidates[node].append(candidates[address])
    # Exact candidate reverse-name comparisons.
    for batch in reverse_pf.iter_batches(columns=[c for c in ("topic0", "topic1", "data") if c in reverse_cols], batch_size=32768):
        for row in batch.to_pylist():
            if str(row.get("topic0", "")).lower() != "0xb7d29e911041e8d9b843369e890bcb72c9388692ba48b65ac54e7214c4c348f7":
                continue
            node = _normalize_node(row.get("topic1"))
            if node not in reverse_node_candidates:
                continue
            try:
                name = decode_abi_string(row.get("data") or "").strip().rstrip(".").casefold()
            except (ValueError, UnicodeError):
                continue
            if any(name == c["reverse_ens_name"].strip().rstrip(".").casefold() for c in reverse_node_candidates[node]):
                reverse_candidate_exact += 1
                candidate_reverse_exact_nodes.add(node)

    # Build corrected projection table in deterministic source iteration order.
    projection_rows = records
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "local_read_only_source_audit_and_decoded_projection",
        "network_accessed": False,
        "bigquery_accessed": False,
        "fxembed_accessed": False,
        "project_root": str(project.resolve()),
        "inputs": {
            "text_source": {"path": str(text_path.relative_to(project)), "sha256": sha256_file(text_path), "row_count": text_pf.metadata.num_rows},
            "old_filtered_projection": {"path": str(projection_path.relative_to(project)), "sha256": sha256_file(projection_path), "row_count": old_pf.metadata.num_rows},
            "reverse_source": {"path": str(reverse_path.relative_to(project)), "sha256": sha256_file(reverse_path), "row_count": reverse_pf.metadata.num_rows},
            "candidate_frame": {"path": str(candidate_path.relative_to(project)), "sha256": sha256_file(candidate_path) if candidate_path.exists() else None, "unique_addresses": len(candidates)},
        },
        "text_source": {
            "rows_scanned": text_rows,
            "observed_min_utc": source_first,
            "observed_max_utc": source_last,
            "topic_counts": dict(sorted(topic_counts.items())),
            "resolver_or_emitter_counts": dict(sorted(emitter_counts.items())),
            "known_topic_abi_decode_successes": decoded_known,
            "known_topic_abi_decode_errors": dict(sorted(decode_errors.items())),
            "known_topic_abi_decode_errors_by_emitter": dict(sorted(decode_errors_by_emitter.items())),
            "payload_shape_and_semantics_counts": dict(sorted(payload_shape_counts.items())),
            "payload_shape_and_semantics_counts_by_emitter": dict(sorted(payload_shape_by_emitter.items())),
            "distinct_decoded_key_count": len(key_counts),
            "top_50_decoded_key_counts": dict(key_counts.most_common(50)),
            "old_projection_key_counts": dict(sorted(old_decoded_counts.items())),
            "old_projection_reconciliation": dict(sorted(reconcile.items())),
            "old_projection_mismatch_key_counts": dict(sorted(old_only_legacy_keys.items())),
            "decoded_value_bearing_target_key_rows": len(projection_rows),
            "projection_rule": "target keys only; only rows with decoded second string are included; legacy two-string rows retain an explicit uncertain-semantics status",
            "corrected_target_key_rows": len(projection_rows),
            "corrected_projection_rows_without_canonical_order": len(projection_rows),
            "candidate_forward_namehash_supported": sum(bool(c["forward_node"]) for c in candidates.values()),
            "candidate_forward_nodes_with_matching_text_events": len(candidate_text_nodes),
            "candidate_text_record_counts_by_key": dict(sorted(candidate_text_key_counts.items())),
            "candidate_text_event_counts_by_address": dict(sorted(candidate_event_counts.items())),
            "candidate_text_event_date_bounds": {
                "minimum_by_candidate": min(first_by_candidate.values()) if first_by_candidate else None,
                "maximum_by_candidate": max(last_by_candidate.values()) if last_by_candidate else None,
            },
            "missing_ordering_and_indexed_fields": text_missing,
        },
        "reverse_source": {
            "rows_scanned": reverse_pf.metadata.num_rows,
            "observed_min_utc": reverse_ts_min.astimezone(timezone.utc).isoformat() if reverse_ts_min else None,
            "observed_max_utc": reverse_ts_max.astimezone(timezone.utc).isoformat() if reverse_ts_max else None,
            "topic_counts": dict(sorted(reverse_topics.items())),
            "emitter_counts": dict(sorted(reverse_emitters.items())),
            "namechanged_rows_decoded": reverse_name_events,
            "namechanged_decode_errors": dict(sorted(reverse_decode_errors.items())),
            "candidate_reverse_nodes_with_observed_namechanged": len(candidate_reverse_nodes_observed),
            "candidate_reverse_name_exact_nodes": len(candidate_reverse_exact_nodes),
            "candidate_namechanged_rows_on_candidate_reverse_nodes": reverse_candidate_rows,
            "candidate_reverse_name_exact_event_matches": reverse_candidate_exact,
            "missing_ordering_fields": sorted({"block_number", "transaction_index"} - reverse_cols),
        },
        "unknown_topic_policy": "unrecognized topics remain counted but are not decoded or assigned event semantics",
        "asof_replay_ready": False,
        "asof_blockers": [
            "text and reverse sources lack block_number and transaction_index; text source also lacks log_index and the indexed topic fields",
            "no complete historical ResolverChanged and AddrChanged event streams were found in these inputs",
            "source extraction completeness is not established by local row counts or timestamp bounds",
            "candidate account-side X identity evidence is current snapshot/manual review, not a dated historical validity interval",
        ],
        "interpretation": "Payload decoding is family-aware. The legacy TextChanged signature occurs with one-string and two-string payload shapes across emitters; one-string rows provide no value, while two-string legacy semantics remain explicitly uncertain. The modern indexed-key family uses a two-string payload. Missing topic1/topic2 prevents indexed-key validation. None of this establishes complete coverage or canonical replay order; candidate-scoped counts are observations only, not historical-link validation.",
    }
    return report, projection_rows


def write_projection(rows: list[dict[str, Any]], out: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    fields = [
        ("block_timestamp", pa.timestamp("us", tz="UTC")), ("node", pa.string()),
        ("topic0", pa.string()), ("resolver", pa.string()), ("transaction_hash", pa.string()),
        ("key", pa.string()), ("value", pa.string()), ("decode_status", pa.string()),
        ("event_family", pa.string()), ("source_file", pa.string()),
        ("source_row_index", pa.int64()),
    ]
    schema = pa.schema(fields, metadata={
        b"description": b"Decoded ENS TextChanged target-key rows with payload values; not a complete/canonically ordered event stream.",
        b"source": b"textchanged_raw_v2.parquet",
        b"decoder": b"topic-family-aware ABI decode; value-bearing target-key rows only; UTF-8 strict",
    })
    table = pa.Table.from_pylist(rows, schema=schema)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out, compression="zstd")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True, help="audit JSON output")
    parser.add_argument("--corrected-projection", type=Path, help="optional new Parquet path; never overwrites source projection")
    args = parser.parse_args()
    project = args.project.resolve()
    report, records = build_report(project)
    if args.corrected_projection:
        destination = args.corrected_projection.resolve()
        protected = {
            (project / "artifacts/ens_x_crosswalk/textchanged_twitter.parquet").resolve(),
            (project / "artifacts/ens_x_crosswalk/textchanged_raw.parquet").resolve(),
            (project / "artifacts/ens_x_crosswalk/textchanged_raw_v2.parquet").resolve(),
        }
        if destination in protected:
            raise SystemExit("refusing to overwrite an input Parquet file")
        write_projection(records, destination)
        report["corrected_projection"] = {
            "path": str(destination), "row_count": len(records), "sha256": sha256_file(destination),
            "warning": "filtered decoded projection only; not canonical or complete for as-of replay",
        }
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(out),
        "text_rows_scanned": report["text_source"]["rows_scanned"],
        "corrected_target_key_rows": report["text_source"]["corrected_target_key_rows"],
        "old_projection_reconciliation": report["text_source"]["old_projection_reconciliation"],
        "candidate_nodes_with_text_events": report["text_source"]["candidate_forward_nodes_with_matching_text_events"],
        "asof_replay_ready": report["asof_replay_ready"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
