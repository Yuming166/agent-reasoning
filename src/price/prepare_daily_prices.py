#!/usr/bin/env python3
"""Prepare offline macro/token price files for the EX-Graph macro layer.

No network access. Reads local CSV inputs under data/raw/prices/, validates
the 2022 study window (default 2022-03-01 through 2022-09-01 inclusive), then
writes normalized Parquet files and a provenance manifest.

Expected inputs:
  prices.csv       date,symbol,price_usd
  token_map.csv    token_contract_address,symbol,decimals,source_note
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_PRICES_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "prices")
OUT_DIR = os.path.join(PROJECT_ROOT, "artifacts", "prices_v1")
WINDOW_START = "2022-03-01"
WINDOW_END = "2022-09-01"  # inclusive market day


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def coverage_report(df: pd.DataFrame, date_col: str = "date") -> dict:
    dates = pd.to_datetime(df[date_col], utc=True).dt.strftime("%Y-%m-%d")
    start = pd.Timestamp(WINDOW_START, tz="UTC")
    end = pd.Timestamp(WINDOW_END, tz="UTC")
    full_days = pd.date_range(start, end, freq="D", tz="UTC").strftime("%Y-%m-%d")
    present = set(dates)
    missing = [d for d in full_days if d not in present]
    out_of_window_before = int((pd.to_datetime(dates, utc=True) < start).sum())
    out_of_window_after = int((pd.to_datetime(dates, utc=True) > end).sum())
    return {
        "unique_days": int(dates.nunique()),
        "missing_days_in_window": len(missing),
        "missing_dates": missing[:50],
        "out_of_window_before": out_of_window_before,
        "out_of_window_after": out_of_window_after,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
    }


def main() -> None:
    global WINDOW_START, WINDOW_END
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prices", default=os.path.join(RAW_PRICES_DIR, "prices.csv"))
    ap.add_argument("--token-map", default=os.path.join(RAW_PRICES_DIR, "token_map.csv"))
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--window-start", default=WINDOW_START)
    ap.add_argument("--window-end", default=WINDOW_END)
    args = ap.parse_args()

    if not os.path.exists(args.prices):
        raise SystemExit(
            f"missing local price file: {args.prices}. "
            "Place an offline `prices.csv` there; this tool must not fetch via API."
        )

    prices = pd.read_csv(args.prices, dtype={"symbol": str})
    required = {"date", "symbol", "price_usd"}
    if not required.issubset(prices.columns):
        raise SystemExit(f"prices.csv must contain columns: {sorted(required)}")

    prices["date"] = pd.to_datetime(prices["date"], utc=True, errors="coerce")
    if prices["date"].isna().any():
        raise SystemExit("prices.csv contains invalid dates")
    prices["symbol"] = prices["symbol"].str.upper().str.strip()
    prices = prices.drop_duplicates(["date", "symbol"], keep="last").sort_values(["symbol", "date"])

    WINDOW_START, WINDOW_END = args.window_start, args.window_end

    report = {"symbols": {}}
    for sym, grp in prices.groupby("symbol", sort=True):
        report["symbols"][str(sym)] = {
            **coverage_report(grp),
            "n_rows": int(len(grp)),
            "min_date": grp["date"].min().strftime("%Y-%m-%d"),
            "max_date": grp["date"].max().strftime("%Y-%m-%d"),
        }

    os.makedirs(args.out_dir, exist_ok=True)
    prices_out = args.out_dir + "/price_usd_daily_v1.csv"
    prices.to_csv(prices_out, index=False)

    token_out = args.out_dir + "/token_price_map_v1.csv"
    token_report = {"token_map_path": None, "n_tokens": 0}
    if os.path.exists(args.token_map):
        token_map = pd.read_csv(args.token_map, dtype={"token_contract_address": str, "symbol": str})
        required_tok = {"token_contract_address", "symbol", "decimals", "source_note"}
        missing_tok = required_tok - set(token_map.columns)
        if missing_tok:
            raise SystemExit(f"token_map.csv missing columns: {sorted(missing_tok)}")
        token_map["symbol"] = token_map["symbol"].str.upper().str.strip()
        token_map["token_contract_address"] = token_map["token_contract_address"].str.strip().str.lower()
        token_map = token_map.drop_duplicates("token_contract_address", keep="last")
        mappings = set(prices["symbol"]) - set(token_map["symbol"])
        token_report = {
            "token_map_path": os.path.basename(args.token_map),
            "n_tokens": int(len(token_map)),
            "priced_symbols_without_mapping": sorted(mappings),
            "token_map_rows": len(token_map),
        }
        token_map.to_csv(token_out, index=False)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_prices_path": os.path.basename(args.prices),
        "source_prices_sha256": sha256_file(args.prices),
        "source_prices_bytes": os.path.getsize(args.prices),
        "window": {"start": WINDOW_START, "end": WINDOW_END},
        "outputs": [],
        "coverage": report,
        "token": token_report,
    }

    def add_out(path: str, desc: str) -> None:
        manifest["outputs"].append({
            "path": os.path.relpath(path, PROJECT_ROOT),
            "sha256": sha256_file(path),
            "bytes": os.path.getsize(path),
            "description": desc,
        })

    add_out(prices_out, "normalized daily USD prices")
    if os.path.exists(token_out):
        add_out(token_out, "token address/symbol/decimals map")

    manifest_path = os.path.join(args.out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
