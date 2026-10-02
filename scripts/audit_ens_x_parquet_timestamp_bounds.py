#!/usr/bin/env python3
"""Offline, bounded audit of timestamps in local ENS/X Parquet snapshots.

This checks only timestamp values in the files present at audit time. It does
not establish extraction completeness, chain canonicality, or historical state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq

TIMESTAMP_COLUMNS = ("block_timestamp", "block_timestamp_utc", "timestamp")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    return parsed.astimezone(timezone.utc)


def summarize_timestamps(values: Iterable[datetime | None], cutoff: datetime) -> dict[str, Any]:
    count = 0
    minimum = maximum = first_future = last_future = None
    future_count = 0
    for value in values:
        if value is None:
            continue
        stamp = value.astimezone(timezone.utc)
        count += 1
        minimum = stamp if minimum is None or stamp < minimum else minimum
        maximum = stamp if maximum is None or stamp > maximum else maximum
        if stamp > cutoff:
            future_count += 1
            first_future = stamp if first_future is None or stamp < first_future else first_future
            last_future = stamp if last_future is None or stamp > last_future else last_future
    return {
        "timestamp_rows_non_null": count,
        "min_utc": minimum.isoformat() if minimum else None,
        "max_utc": maximum.isoformat() if maximum else None,
        "rows_after_cutoff": future_count,
        "first_after_cutoff_utc": first_future.isoformat() if first_future else None,
        "last_after_cutoff_utc": last_future.isoformat() if last_future else None,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_file(path: Path, cutoff: datetime) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    column = next((name for name in TIMESTAMP_COLUMNS if name in parquet.schema_arrow.names), None)
    result: dict[str, Any] = {
        "path": str(path),
        "sha256": sha256(path),
        "rows": parquet.metadata.num_rows,
        "timestamp_column": column,
        "schema": str(parquet.schema_arrow),
    }
    if column is None:
        result["timestamp_audit"] = None
        result["interpretation"] = "no recognized event timestamp column; not checked"
        return result
    def timestamp_values():
        for batch in parquet.iter_batches(columns=[column], batch_size=131072):
            yield from batch.column(0).to_pylist()

    result["timestamp_audit"] = summarize_timestamps(timestamp_values(), cutoff)
    result["interpretation"] = "snapshot value bounds only; does not prove source completeness or as-of validity"
    return result


def build(directory: Path, cutoff: datetime) -> dict[str, Any]:
    paths = sorted(directory.glob("*.parquet"))
    return {
        "audit": "offline_ens_x_parquet_timestamp_bounds_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "network_requests": 0,
        "ens_rpc_requests": 0,
        "bigquery_queries": 0,
        "collection_performed": False,
        "files": [audit_file(path, cutoff) for path in paths],
        "interpretation": (
            "A zero future-row count means only that the inspected local snapshot contains no timestamp value "
            "after the stated cutoff. It is not evidence that the underlying source is complete or that "
            "historical ENS/X links are valid as-of any event."
        ),
    }


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=project / "artifacts/ens_x_crosswalk")
    parser.add_argument("--cutoff", required=True, help="ISO-8601 timestamp with timezone")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.directory.resolve(), parse_utc(args.cutoff))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checked = [x for x in report["files"] if x["timestamp_audit"] is not None]
    print(json.dumps({
        "output": str(args.out),
        "files_total": len(report["files"]),
        "files_with_timestamps": len(checked),
        "rows_after_cutoff": sum(x["timestamp_audit"]["rows_after_cutoff"] for x in checked),
    }, indent=2))


if __name__ == "__main__":
    main()
