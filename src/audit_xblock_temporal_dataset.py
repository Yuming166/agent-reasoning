#!/usr/bin/env python3
"""Audit the XBlock/Kaggle Ethereum Partial Transaction Dataset.

The archive contains EthereumG1/G2/G3 address-index maps and temporal edge-list
files. This audit intentionally uses only the text files, so it does not need
pandas to unpickle the optional pre-sorted DataFrames.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import zipfile
from pathlib import Path
from typing import Dict, Iterable


def norm_address(value: str) -> str:
    value = value.strip().lower()
    return value[2:] if value.startswith("0x") else value


def parse_target_addresses(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return {norm_address(row["ethereum_address"]) for row in reader}


def parse_index(lines: Iterable[str]) -> Dict[int, str]:
    result: Dict[int, str] = {}
    for line in lines:
        parts = re.split(r"[\s,]+", line.strip())
        if len(parts) < 2 or parts[0].lower() in {"addr", "address"}:
            continue
        if not re.fullmatch(r"\d+", parts[-1]):
            continue
        result[int(parts[-1])] = norm_address(parts[0])
    return result


def iso_utc(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()


def audit(zip_path: Path, mapping_path: Path) -> dict:
    targets = parse_target_addresses(mapping_path)
    output = {
        "archive": str(zip_path),
        "target_address_count": len(targets),
        "graphs": {},
        "dataset_level": {
            "license_observed_in_kaggle_metadata": "Unknown",
            "source_description": "XBlock/Kaggle Ethereum Partial Transaction Dataset",
        },
    }
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for graph in ("EthereumG1", "EthereumG2", "EthereumG3"):
            prefix = f"Ethereum Partial Transaction Dataset/{graph}/"
            addr_name = next(n for n in names if n.startswith(prefix) and n.endswith("addr2Idx.txt"))
            edge_name = next(n for n in names if n.startswith(prefix) and n.endswith("TransEdgelist.txt"))
            with zf.open(addr_name) as raw:
                mapping = parse_index((line.decode("utf-8", "replace") for line in raw))
            mapped_targets = sorted({addr for addr in mapping.values() if addr in targets})
            rows = 0
            bad_rows = 0
            endpoints = set()
            pairs = set()
            timestamps = []
            values = []
            rows_touching_target = 0
            outgoing_target_rows = 0
            incoming_target_rows = 0
            with zf.open(edge_name) as raw:
                for raw_line in raw:
                    fields = raw_line.decode("utf-8", "replace").strip().split(",")
                    if len(fields) != 4:
                        bad_rows += 1
                        continue
                    try:
                        from_id, to_id = int(fields[0]), int(fields[1])
                        value = float(fields[2])
                        timestamp = int(float(fields[3]))
                    except ValueError:
                        bad_rows += 1
                        continue
                    rows += 1
                    endpoints.update((from_id, to_id))
                    pairs.add((from_id, to_id))
                    timestamps.append(timestamp)
                    values.append(value)
                    from_addr = mapping.get(from_id, "")
                    to_addr = mapping.get(to_id, "")
                    from_target = from_addr in targets
                    to_target = to_addr in targets
                    if from_target or to_target:
                        rows_touching_target += 1
                    if from_target:
                        outgoing_target_rows += 1
                    if to_target:
                        incoming_target_rows += 1
            output["graphs"][graph] = {
                "address_map_rows": len(mapping),
                "edge_list_file": edge_name,
                "address_map_file": addr_name,
                "edge_rows": rows,
                "bad_rows": bad_rows,
                "endpoint_node_count": len(endpoints),
                "unique_directed_pairs": len(pairs),
                "timestamp_min": min(timestamps),
                "timestamp_max": max(timestamps),
                "timestamp_min_utc": iso_utc(min(timestamps)),
                "timestamp_max_utc": iso_utc(max(timestamps)),
                "value_min": min(values),
                "value_max": max(values),
                "mapped_target_address_count": len(mapped_targets),
                "mapped_target_addresses": mapped_targets,
                "edge_rows_touching_target": rows_touching_target,
                "outgoing_target_rows": outgoing_target_rows,
                "incoming_target_rows": incoming_target_rows,
            }
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.zip, args.mapping)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
