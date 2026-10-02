#!/usr/bin/env python3
"""Offline integrity audit for the frozen 60-row ENS-X review packet.

Verifies the frozen sample design, its one-to-one mapping into the 231-pair
candidate frame, and the captured profile bytes/identity referenced by the
review packet. It never assigns verdicts or authorizes collection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

IMMUTABLE_FIELDS = [
    "address", "x_user_id", "sampling_stratum", "stratum_population_N",
    "stratum_sample_n", "inclusion_probability", "design_weight", "sampling_seed",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def row_digest(row: dict[str, str]) -> str:
    payload = {key: row.get(key, "") for key in IMMUTABLE_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def pair_key(row: dict[str, str]) -> tuple[str, str]:
    return row.get("address", "").strip().lower(), row.get("x_user_id", "").strip()


def audit(sample_path: Path, frozen_manifest_path: Path, candidate_frame_path: Path,
          packet_path: Path, project_root: Path) -> dict[str, Any]:
    sample = read_csv(sample_path)
    frame = read_csv(candidate_frame_path)
    packet = read_csv(packet_path)
    frozen = json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if frozen.get("immutable_fields") != IMMUTABLE_FIELDS:
        errors.append("frozen_immutable_fields_mismatch")
    if frozen.get("row_count") != len(sample):
        errors.append("frozen_sample_row_count_mismatch")
    digests = [row_digest(row) for row in sample]
    if digests != frozen.get("ordered_row_digests"):
        errors.append("frozen_sample_membership_or_design_digest_mismatch")

    sample_keys = [pair_key(row) for row in sample]
    frame_keys = [pair_key(row) for row in frame]
    packet_keys = [pair_key(row) for row in packet]
    if len(set(sample_keys)) != len(sample_keys):
        errors.append("duplicate_pair_in_frozen_sample")
    if len(set(frame_keys)) != len(frame_keys):
        errors.append("duplicate_pair_in_231_candidate_frame")
    if len(set(packet_keys)) != len(packet_keys):
        errors.append("duplicate_pair_in_review_packet")
    frame_key_set = set(frame_keys)
    outside = [key for key in sample_keys if key not in frame_key_set]
    if outside:
        errors.append("frozen_sample_pair_missing_from_candidate_frame")
    if packet_keys != sample_keys:
        errors.append("review_packet_membership_or_order_mismatch")

    sample_hash = sha256_file(sample_path)
    frozen_source_hash_matches = sample_hash == frozen.get("source_sha256_at_freeze")
    packet_by_key = {pair_key(row): row for row in packet}
    identity_mismatches = []
    raw_hash_mismatches = []
    missing_captures = []
    for source_row in sample:
        key = pair_key(source_row)
        review_row = packet_by_key.get(key)
        if review_row is None:
            continue
        expected_raw_hash = source_row.get("profile_raw_sha256", "").strip().lower()
        packet_raw_hash = review_row.get("raw_profile_sha256_verified", "").strip().lower()
        if not expected_raw_hash or packet_raw_hash != expected_raw_hash:
            raw_hash_mismatches.append(key)
        relative = (review_row.get("raw_profile_relative_path") or source_row.get("profile_raw_file") or "").strip()
        raw_path = Path(relative)
        if not raw_path.is_absolute():
            raw_path = project_root / raw_path
        if not raw_path.is_file():
            missing_captures.append(key)
            continue
        actual_hash = sha256_file(raw_path)
        try:
            wrapper = json.loads(raw_path.read_text(encoding="utf-8"))
            user = wrapper["data"]["user"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            identity_mismatches.append(key)
            continue
        source_id = source_row.get("x_user_id", "").strip()
        source_handle = source_row.get("handle_at_profile_audit", "").strip().casefold()
        if (wrapper.get("http_status") != 200
                or actual_hash != expected_raw_hash or actual_hash != packet_raw_hash
                or str(user.get("id", "")) != source_id
                or str(user.get("screen_name", "")).casefold() != source_handle
                or str(review_row.get("captured_x_user_id", "")) != source_id
                or str(review_row.get("captured_handle", "")).casefold() != source_handle
                or str(review_row.get("stable_id_match", "")).casefold() != "true"):
            identity_mismatches.append(key)

    if raw_hash_mismatches:
        errors.append("packet_raw_hash_reference_mismatch")
    if missing_captures:
        errors.append("raw_profile_capture_missing")
    if identity_mismatches:
        errors.append("captured_profile_bytes_or_identity_mismatch")

    strata = Counter(row.get("sampling_stratum", "") for row in sample)
    report = {
        "mode": "offline_frozen_review_packet_integrity_audit",
        "sample_rows": len(sample),
        "candidate_frame_rows": len(frame),
        "packet_rows": len(packet),
        "sample_unique_pairs": len(set(sample_keys)),
        "candidate_frame_unique_pairs": len(set(frame_keys)),
        "packet_unique_pairs": len(set(packet_keys)),
        "sample_pairs_in_candidate_frame": len(sample_keys) - len(outside),
        "sample_strata_observed": dict(sorted(strata.items())),
        "frozen_ordered_design_digests_match": digests == frozen.get("ordered_row_digests"),
        "source_file_sha256": sample_hash,
        "source_file_sha256_matches_freeze": frozen_source_hash_matches,
        "packet_membership_and_order_match": packet_keys == sample_keys,
        "all_profile_capture_hashes_and_ids_match": not raw_hash_mismatches and not missing_captures and not identity_mismatches,
        "human_verdicts_assigned": any(row.get("review_state", "") != "pending_manual_verdict" for row in packet),
        "collection_authorized": False,
        "errors": errors,
        "interpretation": "Integrity only: captured profile identity and automatic candidate terms do not confirm wallet ownership or event-time historical validity.",
    }
    if errors:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--frozen-manifest", type=Path, required=True)
    parser.add_argument("--candidate-frame", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.sample, args.frozen_manifest, args.candidate_frame, args.packet,
                   args.project_root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "sample_rows", "candidate_frame_rows", "packet_rows", "sample_pairs_in_candidate_frame",
        "frozen_ordered_design_digests_match", "packet_membership_and_order_match",
        "all_profile_capture_hashes_and_ids_match", "source_file_sha256_matches_freeze",
        "collection_authorized")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
