#!/usr/bin/env python3
"""Fail-closed event-time replay for ENS wallet↔X record state.

This offline tool accepts only a canonical event stream accompanied by a
completeness/ordering manifest and a hash-bound independent coverage-audit
record. It replays resolver, forward-address, Twitter
text-record, and ENS reverse-name state strictly before prediction cutoffs, then
requires dated account-side evidence linking a stable X ID to the same address
or ENS node. It does not infer completeness from observed date ranges and does
not access X, ENS RPC, BigQuery, or the network.

Canonical event CSV columns:
  block_number,transaction_index,log_index,block_timestamp_utc,event_type,
  node,address,resolver,key,value,emitter,coin_type
Event types: resolver_changed, addr_changed, address_changed, text_changed,
reverse_name_changed. `address_changed` is the normalized multicoin resolver
family; `coin_type` must be 60 and `address` must be a decoded 20-byte address
or empty for a clear. This replay tool does not decode raw ABI bytes or establish
the deployed ABI/version for an emitter.
`reverse_name_changed` represents a resolver `NameChanged(node,name)` log:
`node` is the address-specific reverse node and `value` is the name string.
Its emitter must equal the resolver active for that reverse node at that log.
The reverse node is derived from the address using ENS namehash on
`<lowercase-40-hex-address>.addr.reverse`; the reverse name is independently
namehashed and must equal the crosswalk's forward ENS node. Legacy
`reverse_changed(address -> node)` rows are rejected by schema/event-type checks.

The event manifest also carries `source_provenance` (provider, dataset, table,
extraction job ID, query/schema/scope SHA-256 values) and a relative path plus
SHA-256 for an `ens_asof_independent_coverage_audit_v1` JSON record. That audit
record binds the event CSV, scope and coverage interval; enumerates all five
event families; declares passing scope/order/decode/resolver checks; and
includes a non-empty zero-mismatch comparison against an independent source.
These checks make the audit trail tamper-evident and machine-checkable, but do
not prove that the declared method was actually performed: reviewers must
inspect its retained evidence before accepting source completeness.

Namehash validation is deliberately limited to lowercaseable ASCII LDH labels;
non-ASCII or otherwise non-normalized ENS names fail closed. Install the pinned
dependencies in requirements-ens-asof.txt. This restriction avoids silently
claiming ENSIP-15 normalization for names the tool does not normalize.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_EVENT_COLUMNS = {
    "block_number", "transaction_index", "log_index", "block_timestamp_utc",
    "event_type", "node", "address", "resolver", "key", "value", "emitter", "coin_type",
}
REQUIRED_LINK_COLUMNS = {
    "address", "ens_node", "handle", "x_user_id",
    "account_evidence_valid_from_utc", "account_evidence_valid_to_utc",
    "account_evidence_uri", "account_evidence_type",
}
REQUIRED_EVENT_TYPES = {
    "resolver_changed", "addr_changed", "address_changed", "text_changed",
    "reverse_name_changed",
}
TWITTER_KEYS = {"com.twitter", "twitter", "twitter.com", "com.x", "x"}
ZERO = "0x0000000000000000000000000000000000000000"


def parse_utc(raw: str, label: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise ValueError(f"{label}: invalid ISO-8601 timestamp") from e
    if dt.tzinfo is None:
        raise ValueError(f"{label}: timezone required")
    return dt.astimezone(timezone.utc)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path, required_columns: set[str] | None = None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"empty CSV: {path}")
        if required_columns and not required_columns.issubset(reader.fieldnames):
            raise ValueError(
                f"CSV missing columns: {sorted(required_columns - set(reader.fieldnames))}"
            )
        return list(reader)


def _hex_address(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""
    if not re.fullmatch(r"0x[0-9a-f]{40}", v):
        raise ValueError(f"invalid 20-byte address: {value!r}")
    return v


def _node(value: str) -> str:
    v = (value or "").strip().lower()
    if not re.fullmatch(r"0x[0-9a-f]{64}", v):
        raise ValueError(f"invalid 32-byte ENS node: {value!r}")
    return v


def _keccak(data: bytes) -> bytes:
    try:
        from eth_utils import keccak
    except ImportError as e:
        raise RuntimeError("ENS reverse replay requires pinned eth-utils; install requirements-ens-asof.txt") from e
    return keccak(data)


def normalize_ens_name(name: str) -> str:
    """Normalize a name with the pinned ENSIP-15 reference implementation."""
    try:
        from scripts.ensip15 import ensip15_normalize
    except ModuleNotFoundError:  # direct `python scripts/replay_ens_x_asof.py` execution
        from ensip15 import ensip15_normalize
    return ensip15_normalize(name)


def ens_namehash(name: str) -> str:
    """Return ENS namehash after ENSIP-15 normalization."""
    normalized = normalize_ens_name(name)
    node = bytes(32)
    for label in reversed(normalized.split(".")):
        node = _keccak(node + _keccak(label.encode("utf-8")))
    return "0x" + node.hex()


def reverse_node_for_address(address: str) -> str:
    """Derive the ENSIP-3 Ethereum reverse node for a 20-byte address."""
    normalized = _hex_address(address)
    if not normalized:
        raise ValueError("cannot derive reverse node from an empty address")
    return ens_namehash(normalized[2:] + ".addr.reverse")


def _norm_handle(value: str) -> str:
    v = (value or "").strip()
    for prefix in ("https://twitter.com/", "http://twitter.com/", "https://x.com/", "http://x.com/"):
        if v.lower().startswith(prefix):
            v = v[len(prefix):].split("/", 1)[0].split("?", 1)[0]
            break
    return v.lstrip("@").strip().casefold()


def validate_manifest(manifest: dict, cutoffs: list[datetime]) -> None:
    if manifest.get("complete") is not True:
        raise ValueError("event manifest does not assert complete extraction")
    if manifest.get("total_ordering_complete") is not True:
        raise ValueError("event manifest does not assert complete block/tx/log ordering")
    if manifest.get("decoding_validated") is not True:
        raise ValueError("event manifest does not assert validated event decoding")
    covered = set(manifest.get("event_types_complete", []))
    if not REQUIRED_EVENT_TYPES.issubset(covered):
        raise ValueError(f"event manifest missing complete event types: {sorted(REQUIRED_EVENT_TYPES - covered)}")
    if not manifest.get("source_sha256"):
        raise ValueError("event manifest missing source_sha256")
    provenance = manifest.get("source_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("event manifest missing source_provenance")
    for field in ("provider", "dataset", "table", "extraction_job_id"):
        if not isinstance(provenance.get(field), str) or not provenance[field].strip():
            raise ValueError(f"event manifest source_provenance missing {field}")
    for field in ("query_sha256", "source_schema_sha256", "scope_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get(field, ""))):
            raise ValueError(f"event manifest source_provenance has invalid {field}")
    audit = provenance.get("independent_coverage_audit")
    if not isinstance(audit, dict):
        raise ValueError("event manifest missing independent_coverage_audit")
    if not isinstance(audit.get("path"), str) or not audit["path"].strip():
        raise ValueError("event manifest independent_coverage_audit missing path")
    if not re.fullmatch(r"[0-9a-f]{64}", str(audit.get("sha256", ""))):
        raise ValueError("event manifest independent_coverage_audit has invalid sha256")
    start = parse_utc(manifest.get("coverage_start_utc", ""), "coverage_start_utc")
    end = parse_utc(manifest.get("coverage_end_utc", ""), "coverage_end_utc")
    if end <= start:
        raise ValueError("event manifest coverage interval is empty")
    if not cutoffs:
        raise ValueError("no prediction cutoffs supplied")
    if any(c <= start or c > end for c in cutoffs):
        raise ValueError("all cutoffs must be strictly after coverage_start and no later than coverage_end")


def validate_independent_coverage_audit(manifest: dict, manifest_path: Path,
                                        event_path: Path) -> dict:
    """Verify a separately stored coverage-audit record is hash-bound to inputs.

    This verifies provenance linkage and the audit record's declared checks; it
    cannot independently prove that an upstream provider returned all events.
    The audit record therefore must retain its own inspectable method/evidence.
    """
    provenance = manifest["source_provenance"]
    ref = provenance["independent_coverage_audit"]
    rel = Path(ref["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("independent coverage audit path must be relative and stay within manifest directory")
    audit_root = manifest_path.parent.resolve()
    audit_path = (audit_root / rel).resolve()
    if not audit_path.is_relative_to(audit_root):
        raise ValueError("independent coverage audit path resolves outside manifest directory")
    if not audit_path.is_file():
        raise ValueError("independent coverage audit file is missing")
    actual_sha = sha256(audit_path)
    if actual_sha != ref["sha256"]:
        raise ValueError("independent coverage audit sha256 mismatch")
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("independent coverage audit is not valid JSON") from exc
    if audit.get("schema") != "ens_asof_independent_coverage_audit_v1":
        raise ValueError("unsupported independent coverage audit schema")
    if audit.get("result") != "pass":
        raise ValueError("independent coverage audit did not pass")
    if audit.get("event_csv_sha256") != sha256(event_path):
        raise ValueError("coverage audit is not bound to this event CSV")
    if audit.get("scope_sha256") != provenance["scope_sha256"]:
        raise ValueError("coverage audit scope hash does not match source provenance")
    if (audit.get("coverage_start_utc") != manifest.get("coverage_start_utc")
            or audit.get("coverage_end_utc") != manifest.get("coverage_end_utc")):
        raise ValueError("coverage audit interval does not match event manifest")
    checked_families = set(audit.get("event_types_verified", []))
    if not REQUIRED_EVENT_TYPES.issubset(checked_families):
        raise ValueError("coverage audit does not verify every required ENS event family")
    checks = audit.get("checks")
    required_checks = {
        "scope_complete", "canonical_order", "decoding", "resolver_emitter_consistency",
        "independent_source_sample",
    }
    if not isinstance(checks, dict) or any(checks.get(name) is not True for name in required_checks):
        raise ValueError("coverage audit is missing a required passing check")
    comparison = audit.get("independent_source_comparison")
    if not isinstance(comparison, dict):
        raise ValueError("coverage audit missing independent_source_comparison")
    try:
        sample_n = int(comparison.get("sample_n", 0))
        mismatch_n = int(comparison.get("mismatch_n", -1))
    except (TypeError, ValueError) as exc:
        raise ValueError("coverage audit has invalid independent sample counts") from exc
    if sample_n <= 0 or mismatch_n != 0 or not comparison.get("method"):
        raise ValueError("independent source comparison must have a method, nonzero sample, and zero mismatches")
    return {"path": str(audit_path), "sha256": actual_sha, "schema": audit["schema"]}


def normalize_events(rows: list[dict[str, str]], manifest: dict) -> list[dict]:
    if rows and not REQUIRED_EVENT_COLUMNS.issubset(rows[0]):
        raise ValueError(f"event CSV missing columns: {sorted(REQUIRED_EVENT_COLUMNS - set(rows[0]))}")
    if manifest.get("event_count") != len(rows):
        raise ValueError("event_count does not match canonical event CSV")
    events = []
    prior_key = None
    prior_timestamp = None
    for i, r in enumerate(rows, 2):
        try:
            key = (int(r["block_number"]), int(r["transaction_index"]), int(r["log_index"]))
        except (ValueError, TypeError) as e:
            raise ValueError(f"row {i}: invalid block/transaction/log ordering") from e
        if min(key) < 0:
            raise ValueError(f"row {i}: negative chain ordering field")
        if prior_key is not None and key <= prior_key:
            raise ValueError(f"row {i}: events are not strictly ordered by block/tx/log index")
        prior_key = key
        typ = r["event_type"].strip().casefold()
        if typ not in REQUIRED_EVENT_TYPES:
            raise ValueError(f"row {i}: unsupported event_type {typ!r}")
        ts = parse_utc(r["block_timestamp_utc"], f"row {i} block_timestamp_utc")
        if prior_timestamp is not None and ts < prior_timestamp:
            raise ValueError(f"row {i}: block timestamps decrease in canonical chain order")
        prior_timestamp = ts
        subject = _node(r["node"])
        value = r.get("value", "").strip()
        if typ == "addr_changed":
            address = _hex_address(r.get("address", ""))
            if not address:
                raise ValueError(f"row {i}: AddrChanged missing address")
        coin_type = ""
        if typ == "address_changed":
            try:
                coin_type = str(int(r.get("coin_type", "")))
            except (ValueError, TypeError) as e:
                raise ValueError(f"row {i}: AddressChanged missing/invalid coin_type") from e
            if coin_type != "60":
                raise ValueError(f"row {i}: AddressChanged coin_type must be 60 for Ethereum")
            raw_address = (r.get("address", "") or "").strip()
            if raw_address:
                _hex_address(raw_address)
        if typ == "reverse_name_changed" and value:
            # Validate/normalize through ENSIP-15 before accepting a name event.
            normalize_ens_name(value)
        event = {"order": key, "timestamp": ts, "type": typ, "subject": subject,
                 "address": _hex_address(r.get("address", "")) if r.get("address", "").strip() else "",
                 "resolver": _hex_address(r.get("resolver", "")) if r.get("resolver", "").strip() else "",
                 "key": (r.get("key", "") or "").strip().casefold(),
                 "value": value,
                 "coin_type": coin_type,
                 "emitter": _hex_address(r.get("emitter", "")) if r.get("emitter", "").strip() else ""}
        events.append(event)
    # Do not require every family to have at least one observed row. A
    # candidate-scoped, complete extraction can legitimately contain zero
    # TextChanged (or other family) events in its coverage interval. Coverage
    # is established by validate_manifest()'s event_types_complete assertion,
    # not by treating an observed event as proof that a family was queried.
    return events


def _apply_event(e: dict, state: dict) -> None:
    typ, subject = e["type"], e["subject"]
    if typ == "resolver_changed":
        resolver = e["resolver"] or e["address"]
        state["resolver"][subject] = "" if resolver == ZERO else resolver
    elif typ in {"addr_changed", "address_changed"}:
        active = state["resolver"].get(subject, "")
        if not active or e["emitter"] != active:
            family = "AddrChanged" if typ == "addr_changed" else "AddressChanged"
            raise ValueError(f"{family} emitter is not active resolver at {e['order']}")
        address = e["address"]
        state["address"][subject] = "" if address == ZERO else address
    elif typ == "reverse_name_changed":
        active = state["resolver"].get(subject, "")
        if not active or e["emitter"] != active:
            raise ValueError(f"NameChanged emitter is not active resolver at {e['order']}")
        state["reverse_name"][subject] = e["value"]
    elif typ == "text_changed":
        if e["key"] in TWITTER_KEYS:
            active = state["resolver"].get(subject, "")
            if not active or e["emitter"] != active:
                raise ValueError(f"TextChanged emitter is not active resolver at {e['order']}")
            value = e["value"]
            state["text"][(subject, e["key"])] = "" if not value else value


def _text_for_node(state: dict, node: str) -> set[str]:
    return {_norm_handle(v) for (n, _k), v in state["text"].items() if n == node and _norm_handle(v)}


def replay(events: list[dict], links: list[dict[str, str]], cutoffs: list[datetime]) -> list[dict]:
    if links and not REQUIRED_LINK_COLUMNS.issubset(links[0]):
        raise ValueError(f"crosswalk evidence missing columns: {sorted(REQUIRED_LINK_COLUMNS - set(links[0]))}")
    output = []
    for cutoff in sorted(cutoffs):
        state = {"resolver": {}, "address": {}, "text": {}, "reverse_name": {}}
        for event in events:
            if event["timestamp"] >= cutoff:  # strict pre-cutoff state; same-time excluded
                break
            _apply_event(event, state)
        for link in links:
            address = _hex_address(link.get("address", ""))
            node = _node(link.get("ens_node", ""))
            uid = link.get("x_user_id", "").strip()
            handle = _norm_handle(link.get("handle", ""))
            reasons = []
            if not (uid.isdigit() and int(uid) > 0): reasons.append("invalid_stable_x_user_id")
            if not link.get("account_evidence_uri", "").strip() or not link.get("account_evidence_type", "").strip():
                reasons.append("missing_account_side_evidence")
            try:
                evidence_from = parse_utc(link.get("account_evidence_valid_from_utc", ""), "account_evidence_valid_from_utc")
                valid_to_raw = link.get("account_evidence_valid_to_utc", "").strip()
                evidence_to = parse_utc(valid_to_raw, "account_evidence_valid_to_utc") if valid_to_raw else None
                if evidence_from >= cutoff or (evidence_to is not None and cutoff >= evidence_to):
                    reasons.append("account_evidence_not_valid_before_cutoff")
            except ValueError:
                reasons.append("invalid_account_evidence_interval")
            if not node: reasons.append("missing_ens_node")
            if state["address"].get(node) != address: reasons.append("forward_address_mismatch")
            reverse_node = ""
            try:
                reverse_node = reverse_node_for_address(address)
                reverse_name = state["reverse_name"].get(reverse_node, "")
                if not reverse_name or ens_namehash(reverse_name) != node:
                    reasons.append("reverse_record_mismatch")
            except (ValueError, RuntimeError):
                reverse_name = ""
                reasons.append("reverse_record_unverifiable")
            if handle not in _text_for_node(state, node): reasons.append("twitter_text_record_mismatch")
            if not state["resolver"].get(node): reasons.append("resolver_not_set")
            if reverse_node and not state["resolver"].get(reverse_node): reasons.append("reverse_resolver_not_set")
            output.append({
                "address": address, "ens_node": node, "handle": link.get("handle", ""),
                "x_user_id": uid, "prediction_cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
                "reverse_node": reverse_node,
                "reverse_name_at_cutoff": state["reverse_name"].get(reverse_node, "") if reverse_node else "",
                "historical_asof_status": "valid" if not reasons else "not_validated",
                "failure_reasons": ";".join(reasons),
                "account_evidence_uri": link.get("account_evidence_uri", ""),
                "event_state_rule": "strictly_before_cutoff",
            })
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, required=True, help="canonical ENS event CSV")
    ap.add_argument("--event-manifest", type=Path, required=True, help="completeness/ordering manifest JSON")
    ap.add_argument("--crosswalk-evidence", type=Path, required=True, help="account-side evidence intervals CSV")
    ap.add_argument("--cutoffs", type=Path, required=True, help="CSV with prediction_cutoff_utc column")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--manifest-out", type=Path, required=True)
    args = ap.parse_args()
    manifest = json.loads(args.event_manifest.read_text(encoding="utf-8"))
    cutoff_rows = read_csv(args.cutoffs)
    if not cutoff_rows or "prediction_cutoff_utc" not in cutoff_rows[0]:
        raise ValueError("cutoffs CSV must contain prediction_cutoff_utc")
    cutoffs = [parse_utc(r["prediction_cutoff_utc"], "prediction_cutoff_utc") for r in cutoff_rows]
    validate_manifest(manifest, cutoffs)
    if manifest.get("source_sha256") != sha256(args.events):
        raise ValueError("event manifest source_sha256 does not match event CSV")
    coverage_audit = validate_independent_coverage_audit(manifest, args.event_manifest, args.events)
    event_rows = read_csv(args.events, required_columns=REQUIRED_EVENT_COLUMNS)
    events = normalize_events(event_rows, manifest)
    rows = replay(events, read_csv(args.crosswalk_evidence), cutoffs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["address", "x_user_id", "prediction_cutoff_utc", "historical_asof_status", "failure_reasons"]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    report = {
        "mode": "event_time_replay_strict_pre_cutoff",
        "event_sha256": sha256(args.events), "event_manifest_sha256": sha256(args.event_manifest),
        "crosswalk_evidence_sha256": sha256(args.crosswalk_evidence),
        "cutoffs_sha256": sha256(args.cutoffs), "output_sha256": sha256(args.out),
        "events": len(events), "crosswalk_rows": len(read_csv(args.crosswalk_evidence)),
        "cutoffs": len(cutoffs),
        "valid_rows": sum(r["historical_asof_status"] == "valid" for r in rows),
        "not_validated_rows": sum(r["historical_asof_status"] != "valid" for r in rows),
        "independent_coverage_audit": coverage_audit,
        "interpretation": "Validity is emitted only when the source manifest, hash-bound independent coverage-audit record, and replay checks pass. The verifier checks audit provenance/schema and declared comparisons; reviewers must inspect the retained audit method/evidence before treating source completeness as established.",
    }
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
