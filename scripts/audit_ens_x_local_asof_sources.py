#!/usr/bin/env python3
"""Read-only inventory of local ENS Parquet inputs for event-time replay.

This tool never accesses X/FxEmbed, ENS RPC, BigQuery, or the network. It records
local Parquet schemas, row counts, UTC timestamp bounds, and file hashes. It does
not infer source completeness from a timestamp range and never declares a
historical as-of join ready merely because files exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_FILES = (
    "addrchanged_latest.parquet",
    "reverse_evidence.parquet",
    "textchanged_raw.parquet",
    "textchanged_raw_v2.parquet",
    "textchanged_twitter.parquet",
    # These decoded derivatives were added after the first source inventory.
    # Keep them visible in every refresh, but do not treat decoder output as
    # canonical chain ordering or as independent extraction evidence.
    "textchanged_twitter_decoded_v2.parquet",
    "textchanged_twitter_decoded_v3.parquet",
    "candidate_revnodes.parquet",
)
CANONICAL_REPLAY_COLUMNS = frozenset({
    "block_number", "transaction_index", "log_index", "block_timestamp_utc",
    "event_type", "node", "address", "resolver", "key", "value", "emitter",
})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_parquet(path: Path, relative_path: str) -> dict[str, Any]:
    """Inspect metadata and timestamp column only; do not materialize payloads."""
    if not path.is_file():
        return {
            "path": relative_path,
            "exists": False,
            "size_bytes": None,
            "sha256": None,
            "row_count": None,
            "schema_columns": [],
            "timestamp_column": None,
            "timestamp_min_utc": None,
            "timestamp_max_utc": None,
            "missing_canonical_replay_columns": sorted(CANONICAL_REPLAY_COLUMNS),
        }

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment-specific diagnostic
        raise RuntimeError(
            "PyArrow is required; install requirements-ens-source-audit.txt"
        ) from exc

    parquet = pq.ParquetFile(path)
    columns = parquet.schema_arrow.names
    timestamp_column = next(
        (candidate for candidate in ("block_timestamp_utc", "block_timestamp")
         if candidate in columns),
        None,
    )
    min_ts = max_ts = None
    if timestamp_column:
        # Bounded batches avoid holding large source tables in memory.
        for batch in parquet.iter_batches(columns=[timestamp_column], batch_size=65536):
            values = batch.column(0).to_pylist()
            for value in values:
                if value is None:
                    continue
                if value.tzinfo is None:
                    raise ValueError(f"{relative_path}: naive timestamp in {timestamp_column}")
                value = value.astimezone(timezone.utc)
                min_ts = value if min_ts is None or value < min_ts else min_ts
                max_ts = value if max_ts is None or value > max_ts else max_ts

    return {
        "path": relative_path,
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_count": parquet.metadata.num_rows,
        "schema_columns": columns,
        "timestamp_column": timestamp_column,
        "timestamp_min_utc": min_ts.isoformat() if min_ts else None,
        "timestamp_max_utc": max_ts.isoformat() if max_ts else None,
        "missing_canonical_replay_columns": sorted(CANONICAL_REPLAY_COLUMNS - set(columns)),
    }


def build_report(project: Path, filenames: tuple[str, ...] = DEFAULT_FILES) -> dict[str, Any]:
    base = project / "artifacts/ens_x_crosswalk"
    records = [inspect_parquet(base / name, f"artifacts/ens_x_crosswalk/{name}")
               for name in filenames]
    union_columns = set().union(*(set(r["schema_columns"]) for r in records))
    missing_union = sorted(CANONICAL_REPLAY_COLUMNS - union_columns)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "local_read_only_parquet_inventory",
        "network_accessed": False,
        "project_root": str(project.resolve()),
        "canonical_replay_columns_required": sorted(CANONICAL_REPLAY_COLUMNS),
        "union_schema_missing_canonical_columns": missing_union,
        "schema_union_can_directly_satisfy_replay": not missing_union,
        "source_completeness_proven": False,
        "asof_replay_ready": False,
        "interpretation": (
            "Observed local schemas and date bounds do not prove extraction completeness, "
            "contract-event decoding, canonical block/transaction/log ordering, resolver "
            "history, or dated account-side X identity validity. A separate provenance and "
            "coverage audit is required before event-time replay. Decoded derivative files "
            "are inventoried for traceability but are not independent source-coverage proof."
        ),
        "files": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.project.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(args.out),
        "files_present": sum(item["exists"] for item in report["files"]),
        "union_schema_can_directly_satisfy_replay": report["schema_union_can_directly_satisfy_replay"],
        "asof_replay_ready": report["asof_replay_ready"],
    }))


if __name__ == "__main__":
    main()
