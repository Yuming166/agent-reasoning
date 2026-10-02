"""Pull monthly as-of snapshots (wallet_asof_features_v1: May-Aug 2022) for
temporal-persistence analysis. Compact aggregated table; partition filtered."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import bq_client  # noqa: E402
import config  # noqa: E402


def main() -> None:
    sql = (config.SQL / "asof_features_monthly.sql").read_text()
    rows = bq_client.run_bounded_query(sql, max_bytes_billed=config.MAX_BYTES_BILLED)
    df = pd.DataFrame(rows)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")
    df = df.sort_values(["snapshot_date", "target_address"]).reset_index(drop=True)
    out = config.RESULTS / "data" / "asof_monthly_2022.parquet"
    df.to_parquet(out, index=False)
    counts = df.groupby("snapshot_date").size().to_dict()
    print("[ok] monthly asof:", counts)
    print("wrote", out)


if __name__ == "__main__":
    main()
