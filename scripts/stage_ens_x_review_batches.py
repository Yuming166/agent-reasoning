#!/usr/bin/env python3
"""Stage token-selected targeted review rows without exposing coordinator cues.

This is an offline, fail-closed packet splitter. Outputs must remain in a restricted
folder until a coordinator intentionally distributes only reviewer_handoff/.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

REVIEW_FIELDS = [
    "review_token", "review_sequence", "address", "x_user_id",
    "handle_at_profile_audit", "x_profile_url", "manual_verdict",
    "x_profile_evidence_url", "evidence_quote_or_capture_id",
    "evidence_verified_x_user_id", "evidence_seen_at_utc", "reviewer",
    "reviewed_at_utc", "review_notes",
]
EXPECTED_BATCH_TIERS = Counter({
    "A_candidate_frame_interaction_bridge_review": 6,
    "B_text_coverage_review_no_observed_candidate_frame_edge": 6,
})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"missing or duplicate CSV headers: {path}")
        return list(reader)


def validate_and_split(review_rows, tasking_rows):
    if len(review_rows) != 171:
        raise ValueError("targeted reviewer handoff must contain exactly 171 rows")
    if not review_rows or list(review_rows[0]) != REVIEW_FIELDS:
        raise ValueError("reviewer packet schema differs from the frozen approved schema")
    if any(list(r) != REVIEW_FIELDS for r in review_rows):
        raise ValueError("inconsistent reviewer packet schema")
    by_token = {}
    sequences = set()
    identities = set()
    for row in review_rows:
        token = row["review_token"].strip()
        try:
            seq = int(row["review_sequence"])
        except (ValueError, TypeError) as exc:
            raise ValueError("review_sequence must be an integer") from exc
        identity = (row["address"].strip().lower(), row["x_user_id"].strip())
        if not token or token in by_token or seq in sequences or identity in identities:
            raise ValueError("duplicate/missing token, sequence, or identity in reviewer packet")
        if row["manual_verdict"] != "pending":
            raise ValueError("frozen targeted packet contains a non-pending row")
        by_token[token] = row
        sequences.add(seq)
        identities.add(identity)
    if sequences != set(range(1, 172)):
        raise ValueError("targeted review_sequence must remain the frozen 1..171 sequence")

    tier_counts = Counter()
    selected_tokens = set()
    selected_rows = []
    ranks = []
    for task in tasking_rows:
        token = task.get("review_token", "").strip()
        tier = task.get("tasking_tier", "").strip()
        try:
            rank = int(task.get("priority_rank", ""))
        except (ValueError, TypeError) as exc:
            raise ValueError("priority rank must be an integer") from exc
        if not token or token in selected_tokens or token not in by_token:
            raise ValueError("tasking token missing, duplicated, or outside reviewer handoff")
        if not tier:
            raise ValueError("tasking tier missing")
        selected_tokens.add(token)
        tier_counts[tier] += 1
        ranks.append(rank)
        selected_rows.append(by_token[token])
    if len(selected_tokens) != 12 or tier_counts != EXPECTED_BATCH_TIERS:
        raise ValueError("priority batch must contain exactly six A and six B tasking rows")
    if sorted(ranks) != list(range(1, 13)):
        raise ValueError("priority ranks must be unique and contiguous 1..12")

    selected_rows.sort(key=lambda r: int(r["review_sequence"]))
    selected = {r["review_token"] for r in selected_rows}
    remaining = [r for r in review_rows if r["review_token"] not in selected]
    if len(remaining) != 159 or selected & {r["review_token"] for r in remaining}:
        raise ValueError("partition does not reconcile to 12 + 159 unique review rows")
    return selected_rows, remaining, tier_counts


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o600)


def stage(packet_path: Path, tasking_path: Path, instructions_path: Path, output_root: Path) -> dict:
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError("output root must be new or empty")
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_root, 0o700)
    reviewer_dir = output_root / "reviewer_handoff"
    coordinator_dir = output_root / "coordinator_only"
    reviewer_dir.mkdir(mode=0o700)
    coordinator_dir.mkdir(mode=0o700)
    os.chmod(reviewer_dir, 0o700); os.chmod(coordinator_dir, 0o700)

    rows = read_csv(packet_path)
    tasking = read_csv(tasking_path)
    first, second, tiers = validate_and_split(rows, tasking)
    p1 = reviewer_dir / "targeted_priority_batch_12.csv"
    p2 = reviewer_dir / "targeted_remaining_batch_159.csv"
    write_csv(p1, first); write_csv(p2, second)
    readme = reviewer_dir / "README.txt"
    readme.write_text(
        "Restricted reviewer handoff. Review only public account-side evidence under "
        "the supplied REVIEW_INSTRUCTIONS.md. Preserve review_token and review_sequence; "
        "do not infer ownership from account existence, profile similarity, ENS-only "
        "evidence, or reposted content. These rows are for account-side evidence review "
        "only; they do not authorize timeline collection or establish historical as-of validity.\n"
        "Batch 1 contains 12 rows; batch 2 contains the other 159 targeted rows. "
        "The original stratified probability sample is not included or modified.\n",
        encoding="utf-8")
    os.chmod(readme, 0o600)
    instructions_out = reviewer_dir / "REVIEW_INSTRUCTIONS.md"
    instructions_out.write_bytes(instructions_path.read_bytes())
    os.chmod(instructions_out, 0o600)

    manifest = {
        "schema": "ens-x-targeted-review-batch-staging-v1",
        "mode": "offline_restricted_staging_not_distributed",
        "source_targeted_packet_sha256": sha256(packet_path),
        "coordinator_tasking_sha256": sha256(tasking_path),
        "review_instructions_source_sha256": sha256(instructions_path),
        "source_rows": len(rows),
        "priority_batch_rows": len(first),
        "remaining_batch_rows": len(second),
        "priority_tasking_tier_counts": dict(tiers),
        "probability_packet_included_or_modified": False,
        "review_sequence_preserved": True,
        "verdicts_assigned": 0,
        "mappings_promoted": 0,
        "collection_authorized": False,
        "network_requests": 0,
        "paid_queries_usd": 0,
        "distribution_restrictions": {
            "output_root": "coordinator-controlled restricted directory",
            "reviewer_handoff": "only distribute to authorized reviewers; do not send coordinator_only",
            "coordinator_only": "contains no row identities but retains tasking audit metadata; coordinator only",
            "public_or_repository_distribution": "prohibited",
            "reviewer_batch_fields": REVIEW_FIELDS,
            "priority_reasons_in_reviewer_files": False,
        },
        "outputs_sha256": {
            p1.name: sha256(p1), p2.name: sha256(p2), readme.name: sha256(readme),
            instructions_out.name: sha256(instructions_out),
        },
    }
    manifest_path = coordinator_dir / "manifest.json"
    with manifest_path.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(manifest_path, 0o600)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targeted-packet", type=Path, required=True)
    ap.add_argument("--tasking", type=Path, required=True)
    ap.add_argument("--instructions", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, required=True)
    a = ap.parse_args()
    result = stage(a.targeted_packet, a.tasking, a.instructions, a.output_root)
    print(json.dumps({k: v for k, v in result.items() if k != "distribution_restrictions"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
