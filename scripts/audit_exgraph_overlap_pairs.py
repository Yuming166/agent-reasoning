#!/usr/bin/env python3
"""Offline audit of exgraph_overlap_pairs.csv against frozen seed/candidate frames.

No network, BigQuery, X endpoint, or source mutation is performed. The overlap file
is treated only as transaction/ENS-record context, never as account-side identity proof.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/ens_x_crosswalk"
INPUT = BASE / "exgraph_overlap_pairs.csv"
CANDIDATES = BASE / "expansion_decision_20260925/candidate_review_full_231.csv"
SEED = BASE / "two_graph_seed_20260925/crosswalk_confirmed_unique.csv"
OUT = BASE / "state_audit_20260925"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def norm(value: str | None) -> str:
    return (value or "").strip().lower().removeprefix("@")


def main() -> None:
    overlaps = read_csv(INPUT)
    candidates = read_csv(CANDIDATES)
    seed = read_csv(SEED)
    required = {"address", "handle", "record_set_at", "transaction_hash", "year"}
    if not overlaps or not required.issubset(overlaps[0]):
        raise SystemExit(f"Unexpected overlap schema; expected {sorted(required)}")
    if len(candidates) != 231:
        raise SystemExit(f"Frozen candidate frame changed: expected 231 rows, got {len(candidates)}")

    pair_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in overlaps:
        pair_rows[(norm(row["address"]), norm(row["handle"]))].append(row)
    candidate_pairs = {
        (norm(r["address"]), norm(r["handle_at_profile_audit"])) for r in candidates
    }
    seed_pairs = {
        (norm(r["address"]), norm(r["handle_at_verification"])) for r in seed
    }
    exact_candidate_matches = [
        r for r in candidates
        if (norm(r["address"]), norm(r["handle_at_profile_audit"])) in pair_rows
    ]
    overlap_addresses = {norm(r["address"]) for r in overlaps}
    candidate_addresses = {norm(r["address"]) for r in candidates}
    seed_addresses = {norm(r["address"]) for r in seed}

    # Validate timestamps, address/hash shapes and year consistency without inferring identity.
    timestamp_errors, year_mismatches, invalid_addresses, invalid_hashes = [], [], [], []
    parsed_times = []
    for i, row in enumerate(overlaps, start=2):
        try:
            dt = datetime.fromisoformat(row["record_set_at"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("timezone missing")
            parsed_times.append(dt.astimezone(timezone.utc))
            if str(dt.year) != row["year"].strip():
                year_mismatches.append(i)
        except Exception as exc:  # audited and surfaced rather than silently discarded
            timestamp_errors.append({"line": i, "error": str(exc)})
        if len(norm(row["address"]).removeprefix("0x")) != 40:
            invalid_addresses.append(i)
        if len(norm(row["transaction_hash"]).removeprefix("0x")) != 64:
            invalid_hashes.append(i)

    year_counts = dict(sorted(Counter(r["year"].strip() for r in overlaps).items()))
    repeated_pairs = [
        {"address": key[0], "handle": key[1], "rows": len(rows),
         "years": sorted({r["year"].strip() for r in rows})}
        for key, rows in sorted(pair_rows.items()) if len(rows) > 1
    ]
    candidate_crosscheck = []
    for r in exact_candidate_matches:
        key = (norm(r["address"]), norm(r["handle_at_profile_audit"]))
        matching = pair_rows[key]
        candidate_crosscheck.append({
            "address": r["address"],
            "handle": r["handle_at_profile_audit"],
            "x_user_id": r["x_user_id"],
            "candidate_manual_verdict": r.get("manual_verdict", ""),
            "candidate_review_status": r.get("review_status", ""),
            "overlap_rows": len(matching),
            "overlap_years": sorted({x["year"].strip() for x in matching}),
            "transaction_hashes": sorted({x["transaction_hash"].strip() for x in matching}),
            "interpretation": "manual review context only; not account-side confirmation",
        })

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_local_csv_audit_no_network_no_bigquery_no_collection",
        "inputs": {
            str(p.relative_to(ROOT)): {"sha256": sha256(p), "bytes": p.stat().st_size}
            for p in (INPUT, CANDIDATES, SEED)
        },
        "overlap_file": {
            "rows": len(overlaps),
            "unique_addresses": len(overlap_addresses),
            "unique_handles_casefolded": len({norm(r["handle"]) for r in overlaps}),
            "unique_address_handle_pairs_casefolded": len(pair_rows),
            "unique_transaction_hashes": len({r["transaction_hash"].strip().lower() for r in overlaps}),
            "unique_record_timestamps": len({r["record_set_at"].strip() for r in overlaps}),
            "rows_by_year": year_counts,
            "duplicate_pair_keys": len(repeated_pairs),
            "extra_rows_on_repeated_pairs": sum(x["rows"] - 1 for x in repeated_pairs),
            "repeated_pairs": repeated_pairs,
            "timestamp_min_utc": min(parsed_times).isoformat() if parsed_times else None,
            "timestamp_max_utc": max(parsed_times).isoformat() if parsed_times else None,
            "timestamp_parse_errors": timestamp_errors,
            "year_timestamp_mismatches_csv_line_numbers": year_mismatches,
            "invalid_address_shape_csv_line_numbers": invalid_addresses,
            "invalid_hash_shape_csv_line_numbers": invalid_hashes,
        },
        "crosschecks": {
            "candidate_frame_rows": len(candidates),
            "candidate_addresses_overlapping_file": len(candidate_addresses & overlap_addresses),
            "exact_candidate_address_handle_pairs_overlapping_file": len(exact_candidate_matches),
            "candidate_pair_details": candidate_crosscheck,
            "seed_addresses_overlapping_file": len(seed_addresses & overlap_addresses),
            "seed_exact_address_handle_pairs_overlapping_file": len(seed_pairs & pair_rows.keys()),
        },
        "limits": [
            "This file has address, ENS handle, record timestamp, transaction hash and year only; it has no stable X user ID or account-side evidence.",
            "Matching an ENS/address pair to a candidate row does not establish control of the X account.",
            "Rows are retained as review context only and do not alter or supplement the frozen 60-row probability sample.",
            "The CSV alone does not establish complete event-time resolver/reverse-record state or a valid historical wallet-to-X link.",
        ],
    }
    json_path = OUT / "exgraph_overlap_pairs_audit_20260925.json"
    md_path = OUT / "exgraph_overlap_pairs_audit_20260925.md"
    cross_path = OUT / "exgraph_overlap_candidate_context_20260925.csv"
    OUT.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with cross_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["address", "handle", "x_user_id", "candidate_manual_verdict", "candidate_review_status", "overlap_rows", "overlap_years", "transaction_hashes", "interpretation"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in candidate_crosscheck:
            row = dict(row)
            row["overlap_years"] = ";".join(row["overlap_years"])
            row["transaction_hashes"] = ";".join(row["transaction_hashes"])
            writer.writerow(row)

    o = report["overlap_file"]
    c = report["crosschecks"]
    md = f"""# Offline audit: `exgraph_overlap_pairs.csv` (2026-09-25)\n\n- Mode: offline only; no network, BigQuery, or collection.\n- Source SHA-256: `{report['inputs'][str(INPUT.relative_to(ROOT))]['sha256']}`\n- Rows: {o['rows']}; unique addresses: {o['unique_addresses']}; case-folded handles: {o['unique_handles_casefolded']}; case-folded address-handle pairs: {o['unique_address_handle_pairs_casefolded']}; unique transaction hashes: {o['unique_transaction_hashes']}.\n- Rows by year: {', '.join(f'{y}: {n}' for y, n in o['rows_by_year'].items())}.\n- Repeated address-handle keys: {o['duplicate_pair_keys']} (extra rows: {o['extra_rows_on_repeated_pairs']}); timestamp range: {o['timestamp_min_utc']} to {o['timestamp_max_utc']}.\n- Shape/time checks: timestamp parse errors {len(o['timestamp_parse_errors'])}; year/timestamp mismatches {len(o['year_timestamp_mismatches_csv_line_numbers'])}; malformed address/hash rows {len(o['invalid_address_shape_csv_line_numbers'])}/{len(o['invalid_hash_shape_csv_line_numbers'])}.\n\n## Cross-checks\n\n- Candidate frame: {c['candidate_frame_rows']} rows; {c['candidate_addresses_overlapping_file']} candidate addresses overlap the file, with {c['exact_candidate_address_handle_pairs_overlapping_file']} exact normalized address-handle matches.\n- Confirmed seed: address overlap {c['seed_addresses_overlapping_file']}; exact address-handle overlap {c['seed_exact_address_handle_pairs_overlapping_file']}.\n- Exact candidate matches are exported to `{cross_path.name}` as review context only. They remain unconfirmed and do not change the frozen 60-row sample or the expansion shortlist.\n\n## Interpretation boundary\n\nThe CSV contains no stable X user ID or account-side evidence. ENS record/transaction co-occurrence is not proof that the wallet controls the named X account, nor does this CSV reconstruct complete resolver/reverse-record state at an event time. Do not promote any row to `account_confirms` or call it a historically valid crosswalk.\n\nFull machine-readable details: `{json_path.name}`.\n"""
    md_path.write_text(md, encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "candidate_context": str(cross_path), "summary": {k: o[k] for k in ("rows", "unique_addresses", "unique_handles_casefolded", "unique_address_handle_pairs_casefolded", "rows_by_year", "duplicate_pair_keys", "timestamp_parse_errors", "year_timestamp_mismatches_csv_line_numbers")}, "crosschecks": c}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
