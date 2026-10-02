#!/usr/bin/env python3
"""Convert an offline 1-minute OHLC CSV into UTC daily price files.

No network / no API. Intended for a local file already copied to this server.

Supported time columns (case-insensitive aliases):
  timestamp, unix, open_time, datetime, date_time, date, time
Supported close columns (case-insensitive aliases):
  close, price, last, close_price, usd_close

The daily close is the LAST observed close on each UTC day. This is a
convenient macro-layer default; if you later need intraday as-of alignment,
keep the original 1-minute file and join on exact timestamps instead of daily
resampling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "prices")

TIME_ALIASES = ["timestamp", "unix", "open_time", "datetime", "date_time", "date", "time"]
CLOSE_ALIASES = ["close", "price", "last", "close_price", "usd_close"]
OHLC_ALIASES = {"open": ["open", "open_price"], "high": ["high", "high_price"],
                "low": ["low", "low_price"], "volume": ["volume", "vol", "volume_usd"]}


def first_col(cols: list[str], aliases: list[str]) -> str | None:
    lower = {c: c.lower() for c in cols}
    for a in aliases:
        for c in cols:
            if lower[c] == a:
                return c
    return None


def parse_time(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip()
    numeric = pd.to_numeric(x, errors="coerce")
    # Unambiguous unix time: mostly numeric values that look too large for year strings.
    if numeric.notna().all() and (numeric >= 1e8).all():
        units = "ms" if (numeric >= 1e12).iloc[0] else "s"
        return pd.to_datetime(numeric, unit=units, utc=True)
    # Otherwise parse ISO-like strings. Handle both naive and offset.
    dt = pd.to_datetime(x, utc=True, errors="coerce")
    # If it appears the source was naive UTC, pandas will not help; assume UTC.
    return dt


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--daily-freq", default="1D")
    ap.add_argument("--sep", default=None,
                    help="CSV delimiter; autodetect by default")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit(f"file not found: {args.src}")

    raw = pd.read_csv(args.src) if args.sep is None else pd.read_csv(args.src, sep=args.sep)
    raw.columns = [str(c).strip() for c in raw.columns]

    tcol = first_col(list(raw.columns), TIME_ALIASES)
    ccol = first_col(list(raw.columns), CLOSE_ALIASES)
    if tcol is None or ccol is None:
        raise SystemExit(
            f"could not identify time/close columns. Detected columns: {list(raw.columns)}"
        )

    ts = parse_time(raw[tcol])
    close = pd.to_numeric(raw[ccol], errors="coerce")
    df = pd.DataFrame({"ts": ts, "close": close})
    df = df.dropna(subset=["ts", "close"]).sort_values("ts")
    df = df.drop_duplicates("ts", keep="last")

    # Optional OHLCV columns.
    for std, aliases in OHLC_ALIASES.items():
        col = first_col(list(raw.columns), aliases)
        if col:
            df[std] = pd.to_numeric(raw[col], errors="coerce")

    df["date"] = df["ts"].dt.tz_localize(None).dt.strftime("%Y-%m-%d")
    daily = (
        df.groupby("date", sort=True)
        .agg(
            open=("open", "first") if "open" in df.columns else ("close", "first"),
            high=("high", "max") if "high" in df.columns else ("close", "max"),
            low=("low", "min") if "low" in df.columns else ("close", "min"),
            close=("close", "last"),
            volume=("volume", "sum") if "volume" in df.columns else ("close", "count"),
        )
        .reset_index()
    )
    daily = daily.rename(columns={"date": "date"})
    if "volume" not in df.columns:
        daily = daily.drop(columns=["volume"])

    os.makedirs(args.out_dir, exist_ok=True)
    symbol = args.symbol.upper()
    prepare_prices_path = os.path.join(args.out_dir, "prices.csv")
    daily_ohlc_path = os.path.join(args.out_dir, f"{symbol.lower()}_{args.daily_freq.lower()}_ohlc.csv")

    # One symbol per run by default; append-friendly for multiple symbols.
    mapper = daily[["date", "close"]].copy()
    mapper.insert(1, "symbol", symbol)
    mapper.columns = ["date", "symbol", "price_usd"]
    if os.path.exists(prepare_prices_path):
        old = pd.read_csv(prepare_prices_path, dtype={"symbol": str})
        mapper = pd.concat([old, mapper], ignore_index=True)
    mapper = mapper.drop_duplicates(["date", "symbol"], keep="last").sort_values(["symbol", "date"])
    mapper.to_csv(prepare_prices_path, index=False)
    daily.to_csv(daily_ohlc_path, index=False)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": os.path.basename(args.src),
        "source_sha256": sha256_file(args.src),
        "source_bytes": os.path.getsize(args.src),
        "time_column": tcol,
        "close_column": ccol,
        "symbol": symbol,
        "n_minute_rows": int(len(df)),
        "n_daily_rows": int(len(daily)),
        "date_min": daily["date"].min(),
        "date_max": daily["date"].max(),
        "outputs": {
            "prepare_prices": os.path.relpath(prepare_prices_path, PROJECT_ROOT),
            "daily_ohlc": os.path.relpath(daily_ohlc_path, PROJECT_ROOT),
        },
    }
    manifest_path = os.path.join(args.out_dir, f"convert_{symbol.lower()}_1min_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
