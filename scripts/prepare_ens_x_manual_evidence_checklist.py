#!/usr/bin/env python3
"""Prepare a blank, frozen-frame checklist for human ENS↔X account-side review.

Offline only. Reads no cached/raw profile payloads and assigns no verdicts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from summarize_ens_x_manual_review import frozen_frame_errors, load_rows  # noqa: E402

REQUIRED_BLANK_REVIEW_FIELDS = (
    "x_profile_evidence_url",
    "evidence_quote_or_capture_id",
    "evidence_seen_at_utc",
    "reviewer",
    "reviewed_at_utc",
    "review_notes",
)
OUTPUT_FIELDS = (
    "address", "x_user_id", "handle_at_profile_audit", "reverse_ens_name",
    "x_profile_url_from_stable_id",
    "sampling_stratum", "stratum_population_N", "stratum_sample_n",
    "inclusion_probability", "design_weight", "sampling_seed",
    "manual_verdict", "review_state", "missing_required_fields",
    *REQUIRED_BLANK_REVIEW_FIELDS,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(sample_path: Path, manifest_path: Path, expected_manifest_sha256: str) -> tuple[list[dict[str, str]], dict]:
    sample_bytes = sample_path.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = sha256_bytes(manifest_bytes)
    if manifest_sha.lower() != expected_manifest_sha256.lower():
        raise ValueError("frozen manifest SHA-256 does not match the out-of-band expected digest")
    manifest = json.loads(manifest_bytes)
    source_sha = manifest.get("source_sha256_at_freeze")
    if source_sha != sha256_bytes(sample_bytes):
        raise ValueError("current review CSV SHA-256 differs from the frozen source CSV")
    rows = load_rows(sample_path)
    errors = frozen_frame_errors(rows, manifest)
    if errors:
        raise ValueError("frozen sample integrity check failed: " + "; ".join(errors[:10]))
    if len(rows) != 60:
        raise ValueError(f"expected frozen 60-row sample, found {len(rows)}")
    for line, row in enumerate(rows, start=2):
        verdict = row.get("manual_verdict", "").strip()
        if verdict != "pending":
            raise ValueError(f"line {line} is not pending ({verdict!r}); refusing to regenerate checklist")
        present = [field for field in REQUIRED_BLANK_REVIEW_FIELDS if row.get(field, "").strip()]
        if present:
            raise ValueError(f"line {line} already has review evidence fields; refusing to rewrite workflow state")
    checklist = []
    for row in rows:
        item = {field: row.get(field, "") for field in OUTPUT_FIELDS}
        # Convenience only: this stable-ID route helps a reviewer find the
        # account. Opening the profile or confirming that it exists is not
        # account-side evidence and must never determine the verdict.
        item["x_profile_url_from_stable_id"] = f"https://x.com/i/user/{row['x_user_id'].strip()}"
        item["manual_verdict"] = "pending"
        item["review_state"] = "not_started_account_side_evidence_required"
        item["missing_required_fields"] = ";".join(REQUIRED_BLANK_REVIEW_FIELDS)
        for field in REQUIRED_BLANK_REVIEW_FIELDS:
            item[field] = ""
        checklist.append(item)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_blank_human_review_checklist",
        "network_requests_made": 0,
        "raw_or_cached_profile_payloads_read": False,
        "verdicts_assigned": 0,
        "all_rows_remain_pending": True,
        "row_count": len(checklist),
        "sample_path": str(sample_path),
        "sample_sha256": sha256_bytes(sample_bytes),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "required_fields_to_complete_per_row": list(REQUIRED_BLANK_REVIEW_FIELDS),
        "review_rule": "Only direct account-side evidence connecting the stable X user ID to the full address/ENS can support account_confirms; account existence, ENS-side records, profile text matches, or cached profile snapshots alone do not.",
        "profile_url_note": "x_profile_url_from_stable_id is a navigation aid constructed from the frozen numeric ID only; it is not evidence and has not been fetched or verified by this script.",
        "instructions": "Review the live account or a newly captured, attributable account-side source. Record URL, exact short excerpt or durable capture ID, evidence-seen UTC timestamp, reviewer, review timestamp, and rationale. Never alter immutable sampling fields. This checklist itself contains no evidence and is not a crosswalk or collection authorization.",
    }
    return checklist, metadata


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--expected-manifest-sha256", required=True)
    ap.add_argument("--out-csv", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    args = ap.parse_args()
    rows, metadata = prepare(args.sample, args.manifest, args.expected_manifest_sha256)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    metadata["checklist_path"] = str(args.out_csv)
    metadata["checklist_sha256"] = sha256_bytes(args.out_csv.read_bytes())
    args.out_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": metadata["row_count"], "verdicts_assigned": 0,
                      "all_rows_remain_pending": True, "checklist_sha256": metadata["checklist_sha256"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
