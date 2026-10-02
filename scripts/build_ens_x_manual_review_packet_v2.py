#!/usr/bin/env python3
"""Join the frozen v2 probability-review workbook to its archived profile context.

Offline only. The archived profile is a navigation/review lead, never identity
proof. This packet is read-only context; human verdicts belong only in the
v2 authoritative workbook.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from typing import Any

PROBABILITY_ARM = "stratified_probability_sample_60"
TARGETED_ARM = "targeted_nonprobability_complement_171"

OUTPUT_FIELDS = [
    "review_order", "address", "x_user_id", "handle_at_profile_audit",
    "reverse_ens_name", "x_profile_url_from_stable_id", "sampling_stratum",
    "stratum_population_N", "stratum_sample_n", "inclusion_probability",
    "design_weight", "sampling_seed", "candidate_events_2026",
    "candidate_matched_terms_automatically", "candidate_evidence_types",
    "candidate_evidence_fields", "profile_capture_url",
    "profile_snapshot_at_utc", "capture_http_status", "captured_x_user_id",
    "captured_handle", "captured_display_name", "captured_bio_text",
    "captured_website_url", "captured_website_display_url",
    "raw_profile_relative_path", "raw_profile_sha256_expected",
    "raw_profile_sha256_verified", "capture_stable_id_match",
    "captured_profile_is_identity_verdict", "authoritative_entry_file",
    "authoritative_workbook_row_order", "authoritative_manual_verdict",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def pair_key(row: dict[str, str]) -> tuple[str, str]:
    address = row.get("address", "").strip().lower()
    user_id = row.get("x_user_id", "").strip()
    if not address or not user_id:
        raise ValueError("review row missing address or stable x_user_id")
    return address, user_id


def join_review_rows(
    workbook_rows: list[dict[str, str]], packet_rows: list[dict[str, str]],
    authoritative_workbook_path: str,
) -> list[dict[str, str]]:
    """One-to-one join by wallet + stable X ID and verify all packet identities."""
    review = [r for r in workbook_rows if r.get("review_arm") == PROBABILITY_ARM]
    if len(review) != 60:
        raise ValueError(f"expected 60 probability-arm rows, got {len(review)}")
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in packet_rows:
        key = pair_key(row)
        if key in by_key:
            raise ValueError(f"duplicate archived packet key: {key}")
        by_key[key] = row
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in review:
        key = pair_key(row)
        if key in seen:
            raise ValueError(f"duplicate probability workbook key: {key}")
        seen.add(key)
        capture = by_key.get(key)
        if capture is None:
            raise ValueError(f"no archived profile packet row for {key}")
        if capture.get("captured_x_user_id", "").strip() != key[1]:
            raise ValueError(f"captured stable X ID mismatch for {key}")
        if capture.get("captured_handle", "").strip().casefold() != row.get("handle_at_profile_audit", "").strip().casefold():
            raise ValueError(f"captured handle mismatch for {key}")
        if capture.get("stable_id_match", "").strip().lower() != "true":
            raise ValueError(f"archived capture did not verify stable ID for {key}")
        if capture.get("raw_profile_sha256_expected", "") != capture.get("raw_profile_sha256_verified", ""):
            raise ValueError(f"archived profile hash mismatch for {key}")
        if capture.get("sampling_stratum", "") != row.get("sampling_stratum", ""):
            raise ValueError(f"sampling stratum mismatch for {key}")
        if capture.get("design_weight", "") != row.get("design_weight", ""):
            raise ValueError(f"design weight mismatch for {key}")
        out.append({
            "review_order": row["review_order"],
            "address": row["address"],
            "x_user_id": row["x_user_id"],
            "handle_at_profile_audit": row["handle_at_profile_audit"],
            "reverse_ens_name": row.get("reverse_ens_name", ""),
            "x_profile_url_from_stable_id": row.get("x_profile_url_from_stable_id", ""),
            "sampling_stratum": row["sampling_stratum"],
            "stratum_population_N": row["stratum_population_N"],
            "stratum_sample_n": row["stratum_sample_n"],
            "inclusion_probability": row["inclusion_probability"],
            "design_weight": row["design_weight"],
            "sampling_seed": row["sampling_seed"],
            "candidate_events_2026": row.get("candidate_events_2026", ""),
            "candidate_matched_terms_automatically": capture.get("candidate_matched_terms_automatically", ""),
            "candidate_evidence_types": capture.get("candidate_evidence_types", ""),
            "candidate_evidence_fields": capture.get("candidate_evidence_fields", ""),
            "profile_capture_url": capture.get("profile_url_from_capture", ""),
            "profile_snapshot_at_utc": capture.get("profile_snapshot_at_utc", ""),
            "capture_http_status": capture.get("capture_http_status", ""),
            "captured_x_user_id": capture.get("captured_x_user_id", ""),
            "captured_handle": capture.get("captured_handle", ""),
            "captured_display_name": capture.get("captured_display_name", ""),
            "captured_bio_text": capture.get("captured_bio_text", ""),
            "captured_website_url": capture.get("captured_website_url", ""),
            "captured_website_display_url": capture.get("captured_website_display_url", ""),
            "raw_profile_relative_path": capture.get("raw_profile_relative_path", ""),
            "raw_profile_sha256_expected": capture.get("raw_profile_sha256_expected", ""),
            "raw_profile_sha256_verified": capture.get("raw_profile_sha256_verified", ""),
            "capture_stable_id_match": capture.get("stable_id_match", ""),
            "captured_profile_is_identity_verdict": "false",
            "authoritative_entry_file": authoritative_workbook_path,
            "authoritative_workbook_row_order": row["review_order"],
            "authoritative_manual_verdict": row.get("manual_verdict", "pending"),
        })
    extra = set(by_key) - seen
    if extra:
        raise ValueError(f"archived packet has {len(extra)} keys outside frozen probability sample")
    return out


def build(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, Any]]:
    actual_wm_hash = sha256(args.workbook_manifest)
    if actual_wm_hash != args.expected_workbook_manifest_sha256:
        raise ValueError("authoritative workbook manifest hash mismatch")
    actual_pm_hash = sha256(args.packet_manifest)
    if actual_pm_hash != args.expected_packet_manifest_sha256:
        raise ValueError("archived packet manifest hash mismatch")
    workbook_hash, packet_hash = sha256(args.workbook), sha256(args.packet)
    wm, pm = read_json(args.workbook_manifest), read_json(args.packet_manifest)
    if wm.get("mode") != "offline_full_frame_manual_review_packet_v2":
        raise ValueError("unexpected authoritative workbook manifest mode")
    if wm.get("output_csv_sha256") != workbook_hash:
        raise ValueError("workbook CSV hash does not match its pinned manifest")
    if pm.get("mode") != "offline_manual_review_evidence_packet" or pm.get("packet_sha256") != packet_hash:
        raise ValueError("archived profile packet does not match its manifest")
    for field in ("all_raw_hashes_verified", "all_captured_stable_ids_match", "all_captured_handles_match_case_insensitive"):
        if pm.get(field) is not True:
            raise ValueError(f"archived packet integrity flag is not true: {field}")
    if pm.get("verdicts_assigned") is not False or pm.get("collection_authorized") is not False:
        raise ValueError("archived packet must be non-adjudicative and non-authorizing")
    workbook_rows, packet_rows = read_csv(args.workbook), read_csv(args.packet)
    arm_counts = Counter(r.get("review_arm", "") for r in workbook_rows)
    if len(workbook_rows) != 231 or arm_counts != Counter({PROBABILITY_ARM: 60, TARGETED_ARM: 171}):
        raise ValueError(f"unexpected workbook frame/arms: rows={len(workbook_rows)} arms={dict(arm_counts)}")
    for row in workbook_rows:
        if row.get("manual_verdict") != "pending":
            raise ValueError("workbook contains non-pending verdict; packet generation is pre-review only")
    if len(packet_rows) != 60 or pm.get("packet_rows") != 60:
        raise ValueError("archived profile packet must contain exactly 60 rows")
    rows = join_review_rows(workbook_rows, packet_rows, str(args.workbook))
    manifest = {
        "mode": "offline_v2_probability_manual_review_context_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator_sha256": sha256(Path(__file__).resolve()),
        "probability_rows": len(rows),
        "targeted_rows_excluded": 171,
        "verdicts_assigned": False,
        "all_authoritative_workbook_verdicts_pending": True,
        "network_requests": 0,
        "paid_queries_usd": 0,
        "collection_authorized": False,
        "archived_profile_fields_are_identity_proof": False,
        "authoritative_entry_file": str(args.workbook),
        "review_rule": "Reviewers must inspect evidence attributable to the stable X user ID and record verdict/evidence only in the authoritative v2 workbook. Cached profile text, automatic matches, account existence, and ENS-side records alone are not account-side confirmation.",
        "source_sha256": {
            "authoritative_workbook": workbook_hash,
            "authoritative_workbook_manifest": actual_wm_hash,
            "archived_profile_packet": packet_hash,
            "archived_profile_packet_manifest": actual_pm_hash,
        },
    }
    return rows, manifest


def write_no_clobber(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, required=True)
    ap.add_argument("--workbook-manifest", type=Path, required=True)
    ap.add_argument("--expected-workbook-manifest-sha256", required=True)
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--packet-manifest", type=Path, required=True)
    ap.add_argument("--expected-packet-manifest-sha256", required=True)
    ap.add_argument("--out-csv", type=Path, required=True)
    ap.add_argument("--out-manifest", type=Path, required=True)
    args = ap.parse_args()
    if args.out_csv.exists() or args.out_manifest.exists():
        raise SystemExit("refusing to overwrite an existing output")
    rows, manifest = build(args)
    csv_text = __import__("io").StringIO(newline="")
    writer = csv.DictWriter(csv_text, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = csv_text.getvalue().encode("utf-8")
    manifest["output_csv_sha256"] = hashlib.sha256(csv_bytes).hexdigest()
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # Write manifest first; if CSV creation fails, remove only our newly-created manifest.
    write_no_clobber(args.out_manifest, manifest_bytes)
    try:
        write_no_clobber(args.out_csv, csv_bytes)
    except Exception:
        args.out_manifest.unlink(missing_ok=True)
        raise
    print(json.dumps({"packet_rows": len(rows), "verdicts_assigned": False,
                      "collection_authorized": False, "output_csv_sha256": manifest["output_csv_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
