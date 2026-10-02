#!/usr/bin/env python3
"""Build an offline evidence packet for a frozen ENS-X manual-review sample.

This extracts fields from already archived profile responses. It does not call
X/ENS/FxEmbed, modify the frozen input, assign verdicts, or authorize collection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

FIELDS = [
    "address", "reverse_ens_name", "x_user_id", "handle_at_profile_audit",
    "profile_url_from_capture", "profile_snapshot_at_utc", "capture_http_status",
    "captured_x_user_id", "captured_handle", "captured_display_name",
    "captured_bio_text", "captured_website_url", "captured_website_display_url",
    "candidate_matched_terms_automatically", "candidate_evidence_types",
    "candidate_selection_stratum", "candidate_evidence_fields", "events_2026",
    "sampling_stratum", "design_weight", "raw_profile_relative_path",
    "raw_profile_sha256_expected", "raw_profile_sha256_verified", "stable_id_match",
    "review_state",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_packet(input_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sample = read_rows(input_path)
    if not sample:
        raise ValueError("frozen review sample is empty")
    seen: set[tuple[str, str]] = set()
    packet: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for row_no, row in enumerate(sample, 2):
        pair = (row.get("address", "").lower(), row.get("x_user_id", ""))
        if not all(pair) or pair in seen:
            issues.append({"row": str(row_no), "issue": "missing_or_duplicate_address_x_id"})
            continue
        seen.add(pair)
        raw_path = Path(row["profile_raw_file"])
        if not raw_path.is_absolute():
            raw_path = input_path.parent.parent.parent.parent / raw_path
            # Project-root-relative paths are also common; resolve from cwd if present.
            if not raw_path.exists():
                raw_path = Path.cwd() / row["profile_raw_file"]
        if not raw_path.exists():
            issues.append({"row": str(row_no), "issue": "raw_profile_missing"})
            continue
        digest = sha256_file(raw_path)
        if digest.lower() != row.get("profile_raw_sha256", "").lower():
            issues.append({"row": str(row_no), "issue": "raw_profile_sha256_mismatch"})
            continue
        try:
            wrapper = json.loads(raw_path.read_text(encoding="utf-8"))
            user = wrapper["data"]["user"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            issues.append({"row": str(row_no), "issue": "raw_profile_schema_invalid"})
            continue
        captured_id = str(user.get("id", ""))
        captured_handle = str(user.get("screen_name", ""))
        id_match = captured_id == str(row.get("x_user_id", ""))
        handle_match = captured_handle.casefold() == str(row.get("handle_at_profile_audit", "")).casefold()
        if wrapper.get("http_status") != 200 or not id_match or not handle_match:
            issues.append({"row": str(row_no), "issue": "http_or_profile_identity_mismatch"})
            continue
        website = user.get("website") or {}
        packet.append({
            "address": row.get("address", ""),
            "reverse_ens_name": row.get("reverse_ens_name", ""),
            "x_user_id": row.get("x_user_id", ""),
            "handle_at_profile_audit": row.get("handle_at_profile_audit", ""),
            "profile_url_from_capture": user.get("url", ""),
            "profile_snapshot_at_utc": wrapper.get("fetched_at_utc", ""),
            "capture_http_status": wrapper.get("http_status", ""),
            "captured_x_user_id": captured_id,
            "captured_handle": captured_handle,
            "captured_display_name": user.get("name", ""),
            "captured_bio_text": user.get("description", ""),
            "captured_website_url": website.get("url", "") if isinstance(website, dict) else "",
            "captured_website_display_url": website.get("display_url", "") if isinstance(website, dict) else "",
            "candidate_matched_terms_automatically": row.get("matched_terms", ""),
            "candidate_evidence_types": row.get("evidence_types", ""),
            "candidate_selection_stratum": row.get("selection_stratum", ""),
            "candidate_evidence_fields": row.get("evidence_fields", ""),
            "events_2026": row.get("events_2026", ""),
            "sampling_stratum": row.get("sampling_stratum", row.get("review_stratum", "")),
            "design_weight": row.get("design_weight", ""),
            "raw_profile_relative_path": row.get("profile_raw_file", ""),
            "raw_profile_sha256_expected": row.get("profile_raw_sha256", ""),
            "raw_profile_sha256_verified": digest,
            "stable_id_match": "true",
            "review_state": "pending_manual_verdict",
        })
    if issues:
        raise ValueError(json.dumps({"packet_rows": len(packet), "input_rows": len(sample), "issues": issues}, ensure_ascii=False))
    if len(packet) != len(sample):
        raise ValueError(f"packet/input row mismatch: {len(packet)} != {len(sample)}")
    info = {
        "mode": "offline_manual_review_evidence_packet",
        "input_rows": len(sample),
        "packet_rows": len(packet),
        "input_sha256": sha256_file(input_path),
        "all_raw_hashes_verified": True,
        "all_captured_stable_ids_match": True,
        "all_captured_handles_match_case_insensitive": True,
        "verdicts_assigned": False,
        "collection_authorized": False,
        "evidence_types": dict(Counter(r["candidate_evidence_types"] for r in packet)),
        "interpretation": "Captured profile text and automatic match terms are evidence for human review only, not wallet ownership confirmation or historical as-of validity.",
    }
    return packet, info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="frozen manual-review CSV")
    parser.add_argument("--out", type=Path, required=True, help="evidence packet CSV")
    parser.add_argument("--manifest", type=Path, required=True, help="packet audit JSON")
    args = parser.parse_args()
    packet, info = build_packet(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(packet)
    info["packet_path"] = str(args.out)
    info["packet_sha256"] = sha256_file(args.out)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
