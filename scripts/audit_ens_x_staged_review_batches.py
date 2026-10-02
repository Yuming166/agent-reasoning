#!/usr/bin/env python3
"""Fail-closed offline verification for restricted targeted-review batches."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
from collections import Counter
from pathlib import Path

try:
    from scripts.stage_ens_x_review_batches import REVIEW_FIELDS
except ModuleNotFoundError:  # direct script execution from the project root
    from stage_ens_x_review_batches import REVIEW_FIELDS

EXPECTED = {
    "schema": "ens-x-targeted-review-batch-staging-v1",
    "mode": "offline_restricted_staging_not_distributed",
    "source_rows": 171,
    "priority_batch_rows": 12,
    "remaining_batch_rows": 159,
}
BATCHES = {
    "targeted_priority_batch_12.csv": 12,
    "targeted_remaining_batch_159.csv": 159,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {path.name}")
        return reader.fieldnames, list(reader)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def audit(root: Path) -> dict:
    if root.is_symlink():
        raise ValueError("staging root must not be a symlink")
    root = root.resolve(strict=True)
    reviewer = root / "reviewer_handoff"
    coordinator = root / "coordinator_only"
    manifest_path = coordinator / "manifest.json"
    if root.is_symlink() or reviewer.is_symlink() or coordinator.is_symlink():
        raise ValueError("staging paths must not be symlinks")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, value in EXPECTED.items():
        if manifest.get(key) != value:
            raise ValueError(f"manifest {key} mismatch")
    if manifest.get("probability_packet_included_or_modified") is not False:
        raise ValueError("probability packet must not be included or modified")
    for key, expected in (("verdicts_assigned", 0), ("mappings_promoted", 0),
                          ("network_requests", 0), ("paid_queries_usd", 0)):
        if manifest.get(key) != expected:
            raise ValueError(f"manifest {key} must equal {expected}")
    if manifest.get("collection_authorized") is not False:
        raise ValueError("staging must not authorize collection")
    restrictions = manifest.get("distribution_restrictions", {})
    if restrictions.get("reviewer_batch_fields") != REVIEW_FIELDS:
        raise ValueError("manifest reviewer field allowlist mismatch")
    if restrictions.get("priority_reasons_in_reviewer_files") is not False:
        raise ValueError("priority reasons must not be exposed")

    expected_modes = {root: 0o700, reviewer: 0o700, coordinator: 0o700}
    for path, expected in expected_modes.items():
        if _mode(path) != expected:
            raise ValueError(f"unsafe directory mode for {path.name}: {_mode(path):o}")
    if _mode(manifest_path) != 0o600:
        raise ValueError("manifest must have mode 0600")

    rows_by_batch = {}
    hashes = {}
    identities = set()
    tokens = set()
    sequences = set()
    output_hashes = manifest.get("outputs_sha256", {})
    if set(output_hashes) != set(BATCHES) | {"README.txt", "REVIEW_INSTRUCTIONS.md"}:
        raise ValueError("manifest output hash allowlist mismatch")
    for name, expected_n in BATCHES.items():
        path = reviewer / name
        if path.is_symlink() or not path.is_file() or _mode(path) != 0o600:
            raise ValueError(f"review batch must be a regular 0600 file: {name}")
        digest = sha256(path)
        if digest != output_hashes[name]:
            raise ValueError(f"batch hash mismatch: {name}")
        hashes[name] = digest
        fields, rows = read_rows(path)
        if fields != REVIEW_FIELDS or len(rows) != expected_n:
            raise ValueError(f"batch schema/count mismatch: {name}")
        if any(any(term in field.lower() for term in ("priority", "tier", "reason", "score")) for field in fields):
            raise ValueError("coordinator priority metadata leaked into reviewer batch")
        for row in rows:
            token = row["review_token"].strip()
            seq = int(row["review_sequence"])
            identity = (row["address"].strip().lower(), row["x_user_id"].strip())
            if not token or token in tokens or seq in sequences or identity in identities:
                raise ValueError("duplicate token, sequence, or wallet/X identity across batches")
            if row["manual_verdict"] != "pending":
                raise ValueError("staged row has a non-pending verdict")
            tokens.add(token)
            sequences.add(seq)
            identities.add(identity)
        rows_by_batch[name] = rows

    # Non-CSV reviewer files are also hash-bound and restricted.
    for name in ("README.txt", "REVIEW_INSTRUCTIONS.md"):
        path = reviewer / name
        if path.is_symlink() or not path.is_file() or _mode(path) != 0o600:
            raise ValueError(f"reviewer handoff file must be regular mode 0600: {name}")
        digest = sha256(path)
        if digest != output_hashes[name]:
            raise ValueError(f"reviewer file hash mismatch: {name}")
        hashes[name] = digest
    priority = rows_by_batch["targeted_priority_batch_12.csv"]
    remaining = rows_by_batch["targeted_remaining_batch_159.csv"]
    if [int(r["review_sequence"]) for r in priority] != sorted(int(r["review_sequence"]) for r in priority):
        raise ValueError("priority batch sequence order changed")
    if [int(r["review_sequence"]) for r in remaining] != sorted(int(r["review_sequence"]) for r in remaining):
        raise ValueError("remaining batch sequence order changed")
    if sequences != set(range(1, 172)) or tokens != {r["review_token"] for rs in rows_by_batch.values() for r in rs}:
        raise ValueError("partition does not cover the frozen 1..171 sequence")

    tier_counts = manifest.get("priority_tasking_tier_counts", {})
    if tier_counts != {
        "A_candidate_frame_interaction_bridge_review": 6,
        "B_text_coverage_review_no_observed_candidate_frame_edge": 6,
    }:
        raise ValueError("manifest priority tier counts mismatch")
    return {
        "schema": "ens-x-staged-review-batch-audit-v1",
        "status": "pass",
        "mode": "offline_read_only",
        "reviewer_rows": {name: len(rows) for name, rows in rows_by_batch.items()},
        "unique_tokens": len(tokens),
        "sequence_coverage": [1, 171],
        "verdicts": dict(Counter(r["manual_verdict"] for rs in rows_by_batch.values() for r in rs)),
        "priority_tier_counts_from_manifest": tier_counts,
        "probability_packet_included_or_modified": False,
        "mappings_promoted": 0,
        "collection_authorized": False,
        "network_requests": 0,
        "paid_queries_usd": 0,
        "sha256_verified_files": hashes,
        "permissions": {"root": "0700", "reviewer_handoff": "0700", "coordinator_only": "0700", "files": "0600"},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staging-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, help="optional coordinator-only JSON receipt; must not exist")
    args = ap.parse_args()
    report = audit(args.staging_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = args.output
        if out.exists():
            raise FileExistsError("audit output must be new; refusing overwrite")
        if out.parent.resolve() != (args.staging_root.resolve() / "coordinator_only").resolve():
            raise ValueError("audit output must be written directly under coordinator_only")
        out.write_text(rendered, encoding="utf-8")
        os.chmod(out, 0o600)
    print(rendered, end="")


if __name__ == "__main__":
    main()
