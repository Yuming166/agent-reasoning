#!/usr/bin/env python3
"""Chief Scientist (merge + cross-method consensus, Section 17) at cutoff 2022-09-01.

Frozen protocol: research/audit/temporal_protocol.yaml v1.0 (Group 0).
All numbers are support-restricted:
  - B predictive influence : holdout09_predictions.csv      support = 18,519
  - C structural importance: wallet_importance_20220901.csv support =  7,929
  - D information gain     : wallet_ig_20220901.csv         support =  2,999
  - A behavior/volume base : feature_matrix_20220901.parquet support = 18,519
Labels (fwd30) are used ONLY for evaluation of frozen top-K lists (no leakage
into any selection score). Consensus != correctness (protocol Section 17).
CPU only; no LLM; no BigQuery.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RES = ROOT / "research"
OUT = RES / "chief_merge" / "consensus_analysis" / "results"
TOPKDIR = OUT / "topk_lists"
TOPKDIR.mkdir(parents=True, exist_ok=True)

KS = [10, 25, 50, 100, 250, 500, 1000]
CUTOFF = "2022-09-01"
PROTOCOL = "research/audit/temporal_protocol.yaml v1.0 (frozen 2026-09-11)"

# ----------------------------------------------------------------------------
# 1. Load frozen inputs (read-only)
# ----------------------------------------------------------------------------
fm = pd.read_parquet(RES / "groupA_behavior/results/data/feature_matrix_20220901.parquet")
labels = fm[["target_address", "fwd30_evt_cnt", "fwd30_cp_distinct",
             "fwd30_cp_out_distinct", "fwd30_new_cp"]].copy()

b_labels = pd.read_csv(RES / "groupB_predictive/results/data/labels_20220901_bq.csv")
# parity cross-check (Group B already verified vs Group A local parquet)
mchk = labels.merge(b_labels[["target_address", "fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_new_cp"]],
                    on="target_address", suffixes=("_fm", "_bq"))
parity = {c: int((mchk[f"{c}_fm"] != mchk[f"{c}_bq"]).sum()) for c in
          ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_new_cp"]}

b = pd.read_csv(RES / "groupB_predictive/results/holdout09_predictions.csv")
c = pd.read_csv(RES / "groupC_temporal_graph/results/data/wallet_importance_20220901.csv")
d = pd.read_csv(RES / "groupD_infogain/results/wallet_ig_20220901.csv")

# ----------------------------------------------------------------------------
# 2. Method score frames (all scores strictly as-of / frozen OOS outputs)
# ----------------------------------------------------------------------------
methods = {}
methods["B_act"] = b[["target_address", "pred_act_level_LightGBM"]].rename(
    columns={"pred_act_level_LightGBM": "score"})
methods["B_new"] = b[["target_address", "pred_new_level_LightGBM"]].rename(
    columns={"pred_new_level_LightGBM": "score"})
methods["C_struct"] = c[["target_address", "structure_pct"]].rename(
    columns={"structure_pct": "score"})
methods["C_novol"] = c[["target_address", "structure_novol_pct"]].rename(
    columns={"structure_novol_pct": "score"})
d_cp = d.loc[d.target.eq("y_cp_ge10") & d.model.eq("histgbm"),
            ["target_address", "ig_occ"]].rename(columns={"ig_occ": "score"})
d_act = d.loc[d.target.eq("y_active30") & d.model.eq("histgbm"),
             ["target_address", "ig_occ"]].rename(columns={"ig_occ": "score"})
methods["D_ig_cp"] = d_cp
methods["D_ig_act"] = d_act
methods["A_vol"] = fm[["target_address", "evt_cnt_90d"]].rename(
    columns={"evt_cnt_90d": "score"})

# A behavioral composite baseline (chief-merge reconstruction; Group A submitted no
# scalar importance ranking). Mean of percentile ranks over as-of behavioral
# features (activity + counterparty + trajectory). NO network (42.8% coverage),
# NO USD (91.3%/35.8% coverage), NO fwd30, NO static prior, NO importance_proxy_p3.
BEH_FEATS = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
    "evt_native_90d", "evt_token_90d", "active_days_90d", "tx_cnt_90d",
    "active_span_days_90d", "cp_distinct_90d", "cp_out_distinct_90d",
    "cp_in_distinct_90d", "cp_out_interact_90d", "cp_in_interact_90d",
    "token_distinct_90d", "cp_new_30d", "cp_new_rate_30d",
    "cp_reciprocity_90d", "token_event_rate_90d", "events_per_active_day_90d",
    "n_events_90d_traj", "active_days_90d_traj", "active_span_days_traj",
]
abeh = fm[["target_address"] + BEH_FEATS].copy()
for col in BEH_FEATS:
    abeh[col] = abeh[col].rank(pct=True)
abeh["score"] = abeh[BEH_FEATS].mean(axis=1)
methods["A_beh"] = abeh[["target_address", "score"]]

# ----------------------------------------------------------------------------
# 3. Helpers
# ----------------------------------------------------------------------------
def method_support(m):
    return set(methods[m]["target_address"])

_SORTED = {}
def topk_set(m, k):
    """K highest-scored wallets within the method's own support (global top-K)."""
    if m not in _SORTED:
        _SORTED[m] = methods[m].dropna(subset=["score"]).sort_values("score", ascending=False)
    df = _SORTED[m]
    return set(df.head(min(k, len(df)))["target_address"])

def rank_corr(m1, m2):
    a = methods[m1][["target_address", "score"]].rename(columns={"score": "s1"})
    b = methods[m2][["target_address", "score"]].rename(columns={"score": "s2"})
    j = a.merge(b, on="target_address").dropna()
    if len(j) < 3:
        return None
    sp = stats.spearmanr(j["s1"], j["s2"]).statistic
    kt = stats.kendalltau(j["s1"], j["s2"]).statistic
    return {"m1": m1, "m2": m2, "n_common": len(j),
            "spearman": float(sp), "kendall": float(kt)}

def jaccard_pair(m1, m2, k):
    s1, s2 = topk_set(m1, k), topk_set(m2, k)
    inter = len(s1 & s2)
    union = len(s1 | s2)
    n1, n2 = len(method_support(m1)), len(method_support(m2))
    shared = len(method_support(m1) & method_support(m2))
    # random expected overlap: shared * (K/N1) * (K/N2)
    exp_overlap = shared * (k / n1) * (k / n2) if (n1 and n2) else 0.0
    exp_jaccard = exp_overlap / (2 * k - exp_overlap) if exp_overlap > 0 else 0.0
    return {"m1": m1, "m2": m2, "K": k,
            "overlap": int(inter), "overlap_frac": float(inter / min(k, union)),
            "jaccard": float(inter / union) if union else 0.0,
            "random_expected_overlap": float(exp_overlap),
            "random_expected_jaccard": float(exp_jaccard)}

def future_stats(wallets):
    if not wallets:
        return {}
    lf = labels[labels.target_address.isin(wallets)]
    out = {"n": int(len(lf))}
    for col in ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_new_cp"]:
        out[f"mean_{col}"] = float(lf[col].mean())
        out[f"median_{col}"] = float(lf[col].median())
    return out

def future_utility(m, k):
    w = topk_set(m, k)
    st = future_stats(w)
    sup = method_support(m)
    sup_st = future_stats(sup)
    st["support"] = m
    st["K"] = k
    st["support_n"] = len(sup)
    st["support_mean_fwd30_evt"] = sup_st.get("mean_fwd30_evt_cnt")
    st["support_mean_fwd30_cp"] = sup_st.get("mean_fwd30_cp_distinct")
    st["support_mean_fwd30_newcp"] = sup_st.get("mean_fwd30_new_cp")
    if sup_st.get("mean_fwd30_evt_cnt"):
        st["lift_fwd30_evt_vs_support"] = float(
            st["mean_fwd30_evt_cnt"] / sup_st["mean_fwd30_evt_cnt"])
    return st

# ----------------------------------------------------------------------------
# 4. Rank correlation (pairwise on common wallets)
# ----------------------------------------------------------------------------
method_names = list(methods.keys())
corr_rows = []
for i, m1 in enumerate(method_names):
    for m2 in method_names[i + 1:]:
        r = rank_corr(m1, m2)
        if r:
            corr_rows.append(r)
corr_df = pd.DataFrame(corr_rows).sort_values(["m1", "m2"])
corr_df.to_csv(OUT / "rank_correlation.csv", index=False)
print("[ok] rank_correlation.csv", flush=True)

# ----------------------------------------------------------------------------
# 5. Pairwise top-K Jaccard / overlap
# ----------------------------------------------------------------------------
jac_rows = []
for m1 in method_names:
    for m2 in method_names:
        if m2 <= m1:
            continue
        for k in KS:
            jac_rows.append(jaccard_pair(m1, m2, k))
jac_df = pd.DataFrame(jac_rows)
jac_df.to_csv(OUT / "pairwise_jaccard.csv", index=False)
print("[ok] pairwise_jaccard.csv", flush=True)

# ----------------------------------------------------------------------------
# 6. Consensus frequency (Section 17) — global top-K, counted on shared support
# ----------------------------------------------------------------------------
CONSENSUS_SETS = {
    "primary_B_C_D_A": ["B_act", "C_struct", "D_ig_cp", "A_vol"],
    "B_C_A": ["B_act", "C_struct", "A_vol"],
    "B_D_A": ["B_act", "D_ig_cp", "A_vol"],
    "C_D_A": ["C_struct", "D_ig_cp", "A_vol"],
    "all_variants": ["B_act", "B_new", "C_struct", "C_novol", "D_ig_cp", "D_ig_act", "A_vol", "A_beh"],
}
consensus_rows = []
consensus_json = {}
for setname, ms in CONSENSUS_SETS.items():
    shared = set.intersection(*[method_support(m) for m in ms])
    _labels_set = set(labels.target_address)
    shared = set(w for w in shared if w in _labels_set)
    # precompute each method's global top-K once per K
    tk = {(m, k): topk_set(m, k) for m in ms for k in KS}
    set_json = {"methods": ms, "shared_support_n": len(shared),
                "shared_support_note": f"{len(shared)} wallets (intersection of method supports)"}
    for k in KS:
        cnt = {}
        for w in shared:
            cnt[w] = sum(1 for m in ms if w in tk[(m, k)])
        freq = pd.Series(cnt)
        row = {"consensus_set": setname, "K": k, "shared_n": len(shared)}
        pp = k / len(shared)  # per-wallet inclusion prob under independent random top-K
        for j in range(1, len(ms) + 1):
            row[f"n_count_ge{j}"] = int((freq >= j).sum())
            # E[# wallets with >=j of m independent random K-subsets] = n * P(Binomial(m,p)>=j)
            exp = 0.0
            for i in range(j, len(ms) + 1):
                comb = math.comb(len(ms), i)
                exp += comb * (pp ** i) * ((1 - pp) ** (len(ms) - i))
            row[f"n_ge{j}_random_expected"] = float(len(shared) * exp)
        row["n_all_methods"] = int((freq >= len(ms)).sum())
        row["mean_consensus_count"] = float(freq.mean())
        row["mean_count_random_expected"] = float(len(ms) * (k / len(shared)))
        # future utility of the fully-consensus set (all methods agree)
        allw = [w for w in shared if cnt[w] >= len(ms)]
        fut = future_stats(allw)
        if fut:
            sup_st = future_stats(shared)
            row["consensus_n"] = fut["n"]
            row["consensus_mean_fwd30_evt"] = fut.get("mean_fwd30_evt_cnt")
            row["consensus_mean_fwd30_cp"] = fut.get("mean_fwd30_cp_distinct")
            row["consensus_mean_fwd30_newcp"] = fut.get("mean_fwd30_new_cp")
            if sup_st.get("mean_fwd30_evt_cnt"):
                row["lift_evt_vs_shared_support"] = float(
                    fut["mean_fwd30_evt_cnt"] / sup_st["mean_fwd30_evt_cnt"])
                row["lift_cp_vs_shared_support"] = float(
                    fut["mean_fwd30_cp_distinct"] / sup_st["mean_fwd30_cp_distinct"])
        consensus_rows.append(row)
        set_json[str(k)] = {kk: row.get(kk) for kk in row if kk not in ("consensus_set", "K", "shared_n")}
    consensus_json[setname] = set_json
consensus_df = pd.DataFrame(consensus_rows)
consensus_df.to_csv(OUT / "consensus_frequency.csv", index=False)
print("[ok] consensus_frequency.csv", flush=True)

# ----------------------------------------------------------------------------
# 7. Method-specific uniqueness (fraction of top-K in no other top-K)
# ----------------------------------------------------------------------------
uniq_rows = []
for setname, ms in CONSENSUS_SETS.items():
    for k in KS:
        for m in ms:
            mine = topk_set(m, k)
            others = set()
            for o in ms:
                if o != m:
                    others |= topk_set(o, k)
            uniq = mine - others
            uniq_rows.append({"consensus_set": setname, "method": m, "K": k,
                              "topk_n": len(mine), "unique_n": len(uniq),
                              "unique_frac": float(len(uniq) / len(mine)) if mine else 0.0})
uniq_df = pd.DataFrame(uniq_rows)
uniq_df.to_csv(OUT / "uniqueness.csv", index=False)
print("[ok] uniqueness.csv", flush=True)

# ----------------------------------------------------------------------------
# 8. Future utility of each method's top-K (evaluation-only use of fwd30)
# ----------------------------------------------------------------------------
util_rows = []
for m in method_names:
    for k in KS:
        util_rows.append(future_utility(m, k))
util_df = pd.DataFrame(util_rows)
util_df.to_csv(OUT / "future_utility.csv", index=False)
print("[ok] future_utility.csv", flush=True)

# ----------------------------------------------------------------------------
# 9. Support sensitivity of a key correlation (B_act vs A_vol)
# ----------------------------------------------------------------------------
def rank_corr_on(wallet_subset, m1, m2):
    a = methods[m1][["target_address", "score"]].rename(columns={"score": "s1"})
    b = methods[m2][["target_address", "score"]].rename(columns={"score": "s2"})
    j = a.merge(b, on="target_address")
    j = j[j.target_address.isin(wallet_subset)].dropna()
    if len(j) < 3:
        return None
    return {"n": len(j), "spearman": float(stats.spearmanr(j.s1, j.s2).statistic)}

support_sens = {
    "full_18519": rank_corr_on(set(labels.target_address), "B_act", "A_vol"),
    "C_support_7929": rank_corr_on(method_support("C_struct"), "B_act", "A_vol"),
    "D_support_2999": rank_corr_on(method_support("D_ig_cp"), "B_act", "A_vol"),
    "C_and_D_1283": rank_corr_on(method_support("C_struct") & method_support("D_ig_cp"), "B_act", "A_vol"),
}

# ----------------------------------------------------------------------------
# 10. Write top-K lists and summary JSON
# ----------------------------------------------------------------------------
for m in method_names:
    df = methods[m].dropna(subset=["score"]).sort_values("score", ascending=False).copy()
    df["rank"] = np.arange(1, len(df) + 1)
    df = df.merge(labels, on="target_address", how="left")
    for k in [10, 25, 50, 100, 250, 500, 1000]:
        df.head(k).to_csv(TOPKDIR / f"{m}_top{k}.csv", index=False)

summary = {
    "cutoff": CUTOFF,
    "protocol_ref": PROTOCOL,
    "label_parity_vs_groupB_bq": parity,
    "method_supports": {m: int(len(method_support(m))) for m in method_names},
    "support_intersections": {
        "B_and_C": int(len(method_support("B_act") & method_support("C_struct"))),
        "B_and_D": int(len(method_support("B_act") & method_support("D_ig_cp"))),
        "C_and_D": int(len(method_support("C_struct") & method_support("D_ig_cp"))),
        "B_C_D": int(len(method_support("B_act") & method_support("C_struct") & method_support("D_ig_cp"))),
    },
    "rank_correlation_summary": {
        "B_act_vs_A_vol": rank_corr("B_act", "A_vol"),
        "B_act_vs_C_struct": rank_corr("B_act", "C_struct"),
        "B_act_vs_D_ig_cp": rank_corr("B_act", "D_ig_cp"),
        "C_struct_vs_D_ig_cp": rank_corr("C_struct", "D_ig_cp"),
        "C_struct_vs_A_vol": rank_corr("C_struct", "A_vol"),
        "D_ig_cp_vs_A_vol": rank_corr("D_ig_cp", "A_vol"),
        "D_ig_cp_vs_D_ig_act": rank_corr("D_ig_cp", "D_ig_act"),
        "B_act_vs_B_new": rank_corr("B_act", "B_new"),
        "C_struct_vs_C_novol": rank_corr("C_struct", "C_novol"),
        "A_vol_vs_A_beh": rank_corr("A_vol", "A_beh"),
        "B_act_vs_A_beh": rank_corr("B_act", "A_beh"),
        "B_new_vs_D_ig_cp": rank_corr("B_new", "D_ig_cp"),
    },
    "support_sensitivity_Bact_vs_Avol": support_sens,
    "consensus_sets": consensus_json,
}
with open(OUT / "consensus_summary.json", "w") as f:
    json.dump(summary, f, indent=1, ensure_ascii=False, default=float)

print("[ok] summary JSON written", flush=True)
print("wrote outputs to", OUT)
print("parity:", parity)
print("method supports:", {m: len(method_support(m)) for m in method_names})
print("B_C_D intersection:", len(method_support("B_act") & method_support("C_struct") & method_support("D_ig_cp")))
