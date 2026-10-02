#!/usr/bin/env python3
"""Freeze the immutable design fields of an ENS-X manual-review frame.

Offline only. Requires the caller to provide the independently recorded source
CSV SHA-256 so this tool cannot silently bless an altered or post-review file.
Run once before adjudication; do not regenerate the manifest after review starts.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

IMMUTABLE_FIELDS = [
    "address", "x_user_id", "sampling_stratum", "stratum_population_N",
    "stratum_sample_n", "inclusion_probability", "design_weight", "sampling_seed",
]

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def row_digest(row: dict[str, str]) -> str:
    payload = {k: row.get(k, "") for k in IMMUTABLE_FIELDS}
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--expected-source-sha256", required=True)
    args = ap.parse_args()
    raw = args.input.read_bytes()
    actual = sha256_bytes(raw)
    if actual.lower() != args.expected_source_sha256.lower():
        raise SystemExit(f"source SHA-256 mismatch: expected {args.expected_source_sha256}, got {actual}; refusing to freeze")
    with args.input.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(IMMUTABLE_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"missing immutable columns: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise SystemExit("refusing to freeze an empty frame")
    allocations: dict[str, dict[str, int]] = {}
    for r in rows:
        h = r["sampling_stratum"]
        item = {"N_h": int(r["stratum_population_N"]), "n_h": int(r["stratum_sample_n"])}
        if h in allocations and allocations[h] != item:
            raise SystemExit(f"inconsistent allocation within stratum {h}")
        allocations[h] = item
    observed = Counter(r["sampling_stratum"] for r in rows)
    for h, item in allocations.items():
        if observed[h] != item["n_h"]:
            raise SystemExit(f"stratum {h} has {observed[h]} rows but declares n_h={item['n_h']}")
    manifest = {
        "mode": "frozen_ens_x_review_frame_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(args.input),
        "source_sha256_at_freeze": actual,
        "row_count": len(rows),
        "immutable_fields": IMMUTABLE_FIELDS,
        "ordered_row_digests": [row_digest(r) for r in rows],
        "strata": allocations,
        "interpretation": "Locks sample membership, order, and design fields while allowing manual adjudication columns to change. Do not regenerate after review begins.",
    }
    out = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")
    print(json.dumps({"out": str(args.out), "row_count": len(rows), "source_sha256": actual,
                      "manifest_sha256": sha256_bytes(out.encode()), "strata_count": len(allocations)}))
if __name__ == "__main__": main()
