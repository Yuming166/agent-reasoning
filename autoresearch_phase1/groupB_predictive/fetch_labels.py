#!/usr/bin/env python3
"""Group B — fetch future labels at cutoff 2022-09-01 from BigQuery (bounded).

Labels window: [2022-09-01, 2022-10-01). Only the compact aggregated
wallet_asof_features_20220901 table is read (partition-filtered), never raw
event tables. Verifies parity against Group A's local parquet labels.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
HERE = ROOT / "research" / "groupB_predictive"
sys.path.insert(0, str(HERE / "src"))
import bq_client  # noqa: E402

SQL_FILE = HERE / "sql" / "pull_labels_20220901.sql"
OUT = HERE / "results" / "data" / "labels_20220901_bq.csv"


def main() -> None:
    sql = SQL_FILE.read_text()
    rows = bq_client.run_bounded_query(sql, max_bytes_billed=512 * 1024**2)
    df = pd.DataFrame(rows)
    df["snapshot_date"] = "2022-09-01"
    df.to_csv(OUT, index=False)
    print(f"wrote {len(df)} rows -> {OUT}")

    # Parity check against Group A local parquet labels.
    fm = pd.read_parquet(ROOT / "research/groupA_behavior/results/data/feature_matrix_20220901.parquet")
    local = fm[["target_address", "fwd30_evt_cnt", "fwd30_cp_distinct",
                "fwd30_cp_out_distinct", "fwd30_new_cp"]].copy()
    m = local.merge(df, on="target_address", suffixes=("_local", "_bq"))
    for col in ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_cp_out_distinct", "fwd30_new_cp"]:
        diff = (m[f"{col}_local"] != m[f"{col}_bq"]).sum()
        print(f"parity {col}: local_vs_bq_diff={diff} / {len(m)}")


if __name__ == "__main__":
    main()
