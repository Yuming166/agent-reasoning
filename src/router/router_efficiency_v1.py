#!/usr/bin/env python3
"""P4 efficiency analysis: cumulative headroom utility vs agent budget.

The learned router predicts future headroom; allocation follows predicted
score. We compare the frozen-August cumulative-utility curves and compute
normalized area above the random allocation line (selection AUC) and
marginal utility per selected wallet at each budget.
"""
import json
import numpy as np
import pandas as pd

df = pd.read_csv("/tmp/router/000000000000.csv")
df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date.astype(str)
tr = df[df.snapshot_date == "2022-06-01"]
te = df[df.snapshot_date == "2022-08-01"].reset_index(drop=True)

FEATS = ["evt_cnt_90d","evt_out_90d","evt_in_90d","evt_self_90d","evt_native_90d",
 "evt_token_90d","active_days_90d","tx_cnt_90d","active_span_days_90d","cp_distinct_90d",
 "cp_out_distinct_90d","cp_in_distinct_90d","cp_out_interact_90d","cp_in_interact_90d",
 "cp_entropy_90d","cp_new_30d","cp_new_rate_30d","events_per_active_day_90d",
 "cp_reciprocity_90d","self_tx_rate_90d","token_event_rate_90d","token_hhi_90d",
 "cp_both_dir_90d","token_distinct_90d","icf_score_p1","p1_bridges_events",
 "trigger_score_p2","trigger_strong_pairs"]

from sklearn.ensemble import HistGradientBoostingRegressor
m = HistGradientBoostingRegressor(max_iter=100, learning_rate=0.05,
    max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=1.0, random_state=7)
m.fit(tr[FEATS].fillna(0), np.log1p(tr["y_headroom_sum"].clip(lower=0)))
te["router_score"] = m.predict(te[FEATS].fillna(0))

y = te["y_headroom_sum"].clip(lower=0).to_numpy(float)
n = len(y); budgets = np.linspace(0.01, 0.5, 50)

def cum_curve(score):
    order = np.argsort(-np.asarray(score), kind="mergesort")
    cum = np.cumsum(y[order]) / y.sum()
    out = {}
    for b in (0.01, 0.05, 0.10, 0.20, 0.50):
        k = max(1, int(round(b * n)))
        out[b] = float(cum[k-1])
    # selection AUC over full 1..50% curve vs random line
    ks = np.maximum(1, np.round(budgets * n)).astype(int)
    curve = cum[ks-1]
    auc = float(np.trapezoid(curve - budgets, budgets))  # area above random
    return out, auc, cum

scores = {
  "learned_router": te["router_score"],
  "raw_volume": te["evt_cnt_90d"],
  "P1_occlusion": te["icf_score_p1"],
  "P2_trigger": te["trigger_score_p2"],
  "P3_newcp_asof": te["cp_new_30d"],
  "oracle": y,
}
res = {}
for name, sc in scores.items():
    pts, auc, _ = cum_curve(sc)
    res[name] = {"points": pts, "area_above_random": auc}

# Gini-like concentration of true utility (oracle max auc)
oracle_auc = res["oracle"]["area_above_random"]
for name in res:
    res[name]["normalized_vs_oracle"] = res[name]["area_above_random"] / oracle_auc

# marginal utility: average headroom captured per selected wallet at each budget
order = np.argsort(-te["router_score"].to_numpy(), kind="mergesort")
cum = np.cumsum(y[order])
marg = {}
prev_k, prev_v = 0, 0.0
for b in (0.01, 0.05, 0.10, 0.20):
    k = max(1, int(round(b*n)))
    marg[f"{int(b*100)}pct"] = {
      "wallets": k,
      "avg_headroom_per_wallet": float((cum[k-1]-prev_v)/(k-prev_k)),
      "cum_utility_share": float(cum[k-1]/y.sum())}
    prev_k, prev_v = k, cum[k-1]
res["_marginal"] = marg

print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'points'} for k,v in res.items() if k!='_marginal'}, indent=1))
print("points @ budgets:")
for name in scores:
    print(f"  {name:16s}", {f"{int(b*100)}%": round(v,3) for b,v in res[name]['points'].items()})
with open("artifacts/router_v1/router_efficiency_v1.json","w") as f:
    json.dump(res, f, indent=2)
