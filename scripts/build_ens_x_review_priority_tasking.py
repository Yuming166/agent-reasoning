#!/usr/bin/env python3
"""Map an offline targeted-review priority list to coordinator-only review tokens.

The output is tasking metadata only. Never distribute it to reviewers: priority tiers
can reveal enrichment/interaction signals and are not part of the blinded evidence packet.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

EXPECTED_ARM = "targeted_nonprobability_complement_171"
EXPECTED_VERDICT = "pending"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_tasking(priority_rows: list[dict[str, str]], key_rows: list[dict[str, str]]):
    if not priority_rows:
        raise ValueError("priority list is empty")
    key_by_pair = {}
    tokens = set()
    for row in key_rows:
        pair = (row.get("address", "").strip().lower(), row.get("x_user_id", "").strip())
        token = row.get("review_token", "").strip()
        if not all(pair) or not token or pair in key_by_pair or token in tokens:
            raise ValueError("coordinator key has missing/duplicate identity or token")
        key_by_pair[pair] = row
        tokens.add(token)

    seen = set()
    ranked = []
    try:
        ordered = sorted(priority_rows, key=lambda r: int(r["priority_rank"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("priority ranks must be integers") from exc
    ranks = [int(r["priority_rank"]) for r in ordered]
    if ranks != list(range(1, len(ordered) + 1)):
        raise ValueError("priority ranks must be unique and contiguous from 1")

    for row in ordered:
        pair = (row.get("address", "").strip().lower(), row.get("x_user_id", "").strip())
        if not all(pair) or pair in seen:
            raise ValueError("priority list has missing or duplicate wallet/X identity")
        seen.add(pair)
        if row.get("review_arm") != EXPECTED_ARM:
            raise ValueError("only targeted-complement rows may enter this tasking overlay")
        if row.get("manual_verdict") != EXPECTED_VERDICT:
            raise ValueError("only pending rows may enter this tasking overlay")
        if row.get("review_only_not_collection_authorization") != "true":
            raise ValueError("priority row is missing its review-only safety marker")
        key_row = key_by_pair.get(pair)
        if key_row is None or key_row.get("review_arm") != EXPECTED_ARM:
            raise ValueError("priority identity does not exactly match a targeted coordinator-key row")
        tier = row.get("priority_tier", "").strip()
        if not tier:
            raise ValueError("priority tier is missing")
        ranked.append({
            "review_token": key_row["review_token"].strip(),
            "priority_rank": str(int(row["priority_rank"])),
            "tasking_tier": tier,
        })
    return ranked


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["review_token", "priority_rank", "tasking_tier"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--priority", type=Path, required=True)
    ap.add_argument("--coordinator-key", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    tasking = build_tasking(read_csv(a.priority), read_csv(a.coordinator_key))
    write_csv(a.out, tasking)
    print(json.dumps({
        "rows": len(tasking),
        "output": str(a.out),
        "output_sha256": sha256(a.out),
        "priority_sha256": sha256(a.priority),
        "coordinator_key_sha256": sha256(a.coordinator_key),
        "network_requests": 0,
        "collection_authorized": False,
        "reviewer_distribution_allowed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
