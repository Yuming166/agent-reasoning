"""Build compact behavioral profile texts for the sampled wallets.

Inputs (all local, all as-of, no future labels):
  * feature_matrix_20220901.parquet   (90-day lookback aggregates, cutoff 09-01)
  * trajectory_stats_20220901.csv     (event-timing statistics)
  * asof_monthly_2022.parquet         (May-Aug monthly snapshots for the trend)

The prompt text NEVER contains fwd30_* columns or importance_proxy_p3.
Output: results/profiles_20220901.jsonl  (address, node_id, profile_text)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import re
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

MONTHS = ["2022-05-01", "2022-06-01", "2022-07-01", "2022-08-01"]
EXCLUDE = {"fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_cp_out_distinct",
           "fwd30_new_cp", "importance_proxy_p3"}


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def profile_text(row: pd.Series, traj: pd.Series, monthly: pd.DataFrame) -> str:
    net_missing = bool(row.get("in_mm_subgraph") in (None, False)) or \
        pd.isna(row.get("asof_mm_in_degree"))
    lines = [
        "ETHEREUM WALLET BEHAVIOR PROFILE (as-of snapshot 2022-09-01)",
        "Information window: 90-day lookback [2022-06-03, 2022-09-01) plus monthly as-of snapshots.",
        "",
        f"node_id={row['target_exgraph_node_id']}",
        "",
        "ACTIVITY (90d):",
        f"- events={row['evt_cnt_90d']:.0f} (out={row['evt_out_90d']:.0f}, in={row['evt_in_90d']:.0f}, self={row['evt_self_90d']:.0f})",
        f"- native_events={row['evt_native_90d']:.0f}, token_events={row['evt_token_90d']:.0f}, token_event_rate={row['token_event_rate_90d']:.3f}",
        f"- active_days={row['active_days_90d']:.0f}, active_span_days={row['active_span_days_90d']:.0f}, events_per_active_day={row['events_per_active_day_90d']:.2f}, tx_count={row['tx_cnt_90d']:.0f}",
        "",
        "COUNTERPARTIES (90d):",
        f"- distinct_cp={row['cp_distinct_90d']:.0f} (out={row['cp_out_distinct_90d']:.0f}, in={row['cp_in_distinct_90d']:.0f})",
        f"- cp_entropy_bits={row['cp_entropy_90d']:.2f}, new_cp_rate_30d={row['cp_new_rate_30d']:.3f}, cp_both_dir={row['cp_both_dir_90d']:.0f}, reciprocity={row['cp_reciprocity_90d']:.3f}",
        f"- self_tx_rate={row['self_tx_rate_90d']:.3f}",
        "",
        "TOKEN BEHAVIOR (90d):",
        f"- distinct_tokens={row['token_distinct_90d']:.0f}, token_hhi={row['token_hhi_90d']:.4f} (1=fully concentrated)",
        "",
        "TRAJECTORY / TIMING (90d):",
        f"- first_event_offset_days={row['first_event_offset_days']:.0f}, last_event_recency_days={row['last_event_recency_days']:.0f}",
        f"- gaps_days: mean={traj['mean_gap_days']:.3f}, median={traj['median_gap_days']:.4f}, max={traj['max_gap_days']:.2f}, std={traj['std_gap_days']:.2f}; gaps_gt7d={traj['n_gaps_gt7d']:.0f}",
    ]
    if "burstiness" in row and not pd.isna(row.get("burstiness")):
        lines.append(f"- burstiness={row['burstiness']:.3f} (positive=bursty, negative=regular)")
    lines += [
        "",
        "NETWORK CONTEXT (as-of, matched-matched subgraph):",
    ]
    if net_missing:
        lines.append("- wallet not present in the as-of matched-matched subgraph; no network-degree features")
    else:
        lines.append(
            f"- in_deg={row['asof_mm_in_degree']:.0f}, out_deg={row['asof_mm_out_degree']:.0f}, undir_deg={row['asof_mm_undir_degree']:.0f}")
        lines.append(
            f"- w_in={row['asof_mm_w_in_degree']:.1f}, w_out={row['asof_mm_w_out_degree']:.1f}, pagerank={row['asof_mm_pagerank']:.6f}, kcore={row['asof_mm_kcore']:.0f}, clustering={row['asof_mm_clustering']:.3f}, hub_neighbors={row['asof_mm_hub_neighbors']:.0f}")
    usd_missing = pd.isna(row.get("native_usd"))
    lines += ["", "CAPITAL (as-of USD value moved in 90d):"]
    if usd_missing:
        lines.append("- native_usd: n/a (no USD-priced native outflow); token_usd_priced=" + fmt(row.get("token_usd_priced")))
    else:
        lines.append(f"- native_usd={row['native_usd']:.2f}, token_usd_priced=" + fmt(row.get("token_usd_priced")) + f", token_rows_priced={fmt(row.get('token_rows_priced'), 0)}")
    # monthly trend (May..Aug), as-of snapshots only
    lines += ["", "MONTHLY TREND (90d-rolling aggregates at each monthly snapshot; no future data):"]
    if monthly is None or len(monthly) == 0:
        lines.append("- no monthly snapshots available")
    else:
        for m in MONTHS:
            if m in monthly.index:
                r = monthly.loc[m]
                lines.append(
                    f"- {m}: events={r['evt_cnt_90d']:.0f}, active_days={r['active_days_90d']:.0f}, "
                    f"distinct_cp={r['cp_distinct_90d']:.0f}, token_hhi={r['token_hhi_90d']:.4f}, "
                    f"new_cp_rate={r['cp_new_rate_30d']:.3f}, token_event_rate={r['token_event_rate_90d']:.3f}")
            else:
                lines.append(f"- {m}: n/a")
    return "\n".join(lines)


def main() -> None:
    df = pd.read_parquet(config.FEATURE_MATRIX)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")
    traj = pd.read_csv(config.TRAJ_STATS).set_index("target_address")
    monthly_all = pd.read_parquet(config.MONTHLY)
    monthly_all = monthly_all.loc[:, ~monthly_all.columns.isin(EXCLUDE)]
    sample = pd.read_csv(config.SAMPLE_CSV)
    monthly_index = {}
    for addr in sample["target_address"]:
        sub = monthly_all[monthly_all["target_address"] == addr].set_index("snapshot_date")
        monthly_index[addr] = sub

    rows = []
    for _, r in sample.iterrows():
        addr = r["target_address"]
        fm = df[df["target_address"] == addr].iloc[0]
        t = traj.loc[addr] if addr in traj.index else pd.Series({c: np.nan for c in [
            "mean_gap_days", "median_gap_days", "max_gap_days", "std_gap_days",
            "n_gaps_gt7d", "n_gaps"]})
        rows.append({
            "target_address": addr,
            "target_exgraph_node_id": int(fm["target_exgraph_node_id"]),
            "activity_tier": r["activity_tier"],
            "traj_cluster": int(r["traj_cluster"]),
            "net_cov": r["net_cov"],
            "profile_text": profile_text(fm, t, monthly_index.get(addr)),
        })
    with open(config.PROFILES_JSONL, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n = len(rows)
    avg_len = np.mean([len(x["profile_text"].split()) for x in rows])
    print(f"[ok] wrote {config.PROFILES_JSONL}  n={n}  avg_profile_words={avg_len:.0f}")
    # quick leakage self-check: no fwd column name in any prompt text
    bad = [x["target_address"] for x in rows if re.search(r"fwd30|importance_proxy|fwd_evt|fwd_cp", x["profile_text"])]
    print("leakage_scan_found (fwd/importance tokens):", bad)


if __name__ == "__main__":
    main()
