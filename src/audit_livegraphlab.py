#!/usr/bin/env python3
"""Stream-audit Live Graph Lab's metadata CSV against EX-Graph target addresses.

The input is the Zenodo/Google Drive ZIP containing the raw NFT transaction
metadata. The CSV is streamed from the ZIP; no uncompressed full copy is made.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def canon(s: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def parse_time(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        x = float(value)
        # Live Graph Lab timestamps are Unix seconds; protect against ms values.
        if x > 10**12:
            x /= 1000
        return datetime.fromtimestamp(x, tz=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def first_col(header: list[str], names: Iterable[str]) -> int | None:
    normalized = {canon(x): i for i, x in enumerate(header)}
    for name in names:
        if canon(name) in normalized:
            return normalized[canon(name)]
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--zip", type=Path, required=True)
    p.add_argument("--mapping", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--start", default="2021-08-01T00:00:00+00:00")
    p.add_argument("--end", default="2022-08-01T00:00:00+00:00")
    args = p.parse_args()

    with args.mapping.open(newline="") as f:
        mapping = list(csv.DictReader(f))
    target = {r["ethereum_address"].strip().lower() for r in mapping if r.get("ethereum_address")}
    target_node_by_address = {r["ethereum_address"].strip().lower(): r.get("node_id") for r in mapping}
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    with zipfile.ZipFile(args.zip) as zf:
        members = [x for x in zf.namelist() if not x.endswith("/")]
        csv_members = [x for x in members if x.lower().endswith((".csv", ".txt"))]
        if not csv_members:
            raise RuntimeError(f"No CSV/TXT member found; members={members[:20]}")
        # The Zenodo file normally contains one metadata CSV. If there are
        # several, inspect the largest text member first.
        member = max(csv_members, key=lambda x: zf.getinfo(x).file_size)
        member_size_uncompressed = zf.getinfo(member).file_size
        total = 0
        window_rows = 0
        target_rows = 0
        target_window_rows = 0
        seen_target: set[str] = set()
        seen_target_window: set[str] = set()
        event_hashes: Counter[str] = Counter()
        monthly: Counter[str] = Counter()
        header = None
        columns = {}
        with zf.open(member) as raw:
            text = (line.decode("utf-8", errors="replace") for line in raw)
            reader = csv.reader(text)
            header = next(reader)
            columns = {
                "from": first_col(header, ["from address", "from", "sender"]),
                "to": first_col(header, ["to address", "to", "receiver"]),
                "timestamp": first_col(header, ["timestamp", "time", "block timestamp"]),
                "transaction_hash": first_col(header, ["transaction hash", "tx hash", "hash"]),
            }
            if columns["from"] is None or columns["to"] is None or columns["timestamp"] is None:
                raise RuntimeError(f"Could not identify required columns: {header}")
            for row in reader:
                if not row:
                    continue
                total += 1
                src = row[columns["from"]].strip().lower() if columns["from"] < len(row) else ""
                dst = row[columns["to"]].strip().lower() if columns["to"] < len(row) else ""
                hit = {x for x in (src, dst) if x in target}
                if hit:
                    target_rows += 1
                    seen_target.update(hit)
                dt = parse_time(row[columns["timestamp"]]) if columns["timestamp"] < len(row) else None
                if dt is None:
                    continue
                if start <= dt < end:
                    window_rows += 1
                    if hit:
                        target_window_rows += 1
                        seen_target_window.update(hit)
                        monthly[dt.strftime("%Y-%m")] += 1
                        if columns["transaction_hash"] is not None and columns["transaction_hash"] < len(row):
                            h = row[columns["transaction_hash"]].strip()
                            if h:
                                event_hashes[h] += 1

    result = {
        "zip": str(args.zip),
        "member": member,
        "member_size_uncompressed": member_size_uncompressed,
        "mapping_rows": len(mapping),
        "unique_target_addresses": len(target),
        "window_start": start.isoformat(),
        "window_end_exclusive": end.isoformat(),
        "header": header,
        "identified_columns": columns,
        "total_rows": total,
        "all_period_target_rows": target_rows,
        "target_addresses_seen_all_period": len(seen_target),
        "window_rows": window_rows,
        "target_window_rows": target_window_rows,
        "target_addresses_seen_in_window": len(seen_target_window),
        "window_month_counts": dict(sorted(monthly.items())),
        "transaction_hashes_with_multiple_rows_in_target_window": sum(1 for n in event_hashes.values() if n > 1),
        "max_rows_per_transaction_hash_in_target_window": max(event_hashes.values(), default=0),
        "note": "Rows are NFT transfer/event records; a transaction hash may occur multiple times for multi-token transfers.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
