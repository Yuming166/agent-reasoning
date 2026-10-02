#!/usr/bin/env python3
"""Stage C: leakage-safe event gate and budgeted deliberation proxy."""
import argparse, glob, json, os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATS = ["g_rank", "g_cnt", "personal_cnt", "days_since", "bridge_paths", "bridge_signal"]
EVENT_BASE = ["candidate_n", "neg_n", "bridge_candidate_n", "bridge_share",
              "bridge_signal_sum", "bridge_signal_mean", "bridge_signal_max",
              "bridge_paths_sum", "best_neg_g_rank", "median_neg_g_rank"]
STRUCT = ["out_degree", "in_degree", "degree", "w_out_degree", "w_in_degree", "pagerank"]
GATE_FEATS = EVENT_BASE + ["log_" + c for c in EVENT_BASE[:8]]
KEYS = ["snapshot_date", "u", "target_sequence_index"]
# One feature retrieval + 64 generated ranking tokens + answer formatting.  The
# cheap global list uses a cached table and needs only answer formatting.
DELIB_TOKEN_UNITS = 96
CHEAP_TOKEN_UNITS = 32
BUDGETS = (0.01, 0.05, 0.10, 0.20, 0.50, 1.00)


def load_samples(workdir):
    paths = sorted(glob.glob(os.path.join(workdir, "*.csv.gz")))
    if not paths:
        raise FileNotFoundError(f"no *.csv.gz under {workdir}")
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    for c in FEATS:
        df[c] = df[c].replace([np.inf, -np.inf], np.nan).fillna(0)
    return df


def load_struct(path):
    if not path or not os.path.exists(path):
        return pd.DataFrame(columns=["ethereum_address"] + STRUCT)
    s = pd.read_csv(path, usecols=["ethereum_address"] + STRUCT)
    return s.rename(columns={"ethereum_address": "u"})


def add_event_context(df):
    """Event context from sampled negatives only: no positive-label leakage."""
    neg = df[df.label == 0]
    b = neg[neg.bridge_paths > 0]
    g = neg.groupby(KEYS).agg(
        neg_n=("c", "size"),
        best_neg_g_rank=("g_rank", "min"),
        median_neg_g_rank=("g_rank", "median"),
    ).reset_index()
    ba = b.groupby(KEYS).agg(
        bridge_candidate_n=("c", "size"),
        bridge_signal_sum=("bridge_signal", "sum"),
        bridge_signal_mean=("bridge_signal", "mean"),
        bridge_signal_max=("bridge_signal", "max"),
        bridge_paths_sum=("bridge_paths", "sum"),
    ).reset_index()
    cn = df.groupby(KEYS).agg(candidate_n=("c", "size")).reset_index()
    ev = cn.merge(g, on=KEYS, how="left").merge(ba, on=KEYS, how="left")
    for c in ["bridge_candidate_n", "bridge_signal_sum", "bridge_signal_mean",
              "bridge_signal_max", "bridge_paths_sum"]:
        ev[c] = ev[c].fillna(0.0)
    ev["bridge_share"] = ev.bridge_candidate_n / ev.neg_n.clip(lower=1)
    return ev


def candidate_ranker(train, tune=None):
    data = train if tune is None else pd.concat([train, tune], ignore_index=True)
    # Frozen August model after July tuning; June-only model supplies
    # out-of-sample July labels for gate training without gate target leakage.
    m = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
        min_samples_leaf=50, l2_regularization=1.0, random_state=7)
    m.fit(data[FEATS], data.label)
    return m


def ranks(df, score):
    x = df[KEYS + ["label", score]].copy()
    x = x.sort_values(KEYS + [score], ascending=[True, True, True, False])
    x["rank"] = x.groupby(KEYS).cumcount() + 1
    return x[x.label == 1][KEYS + ["rank"]]


def gate_table(df, model, event_context, struct, snapshot, score_col):
    x = df[df.snapshot_date == snapshot].copy()
    x[score_col] = model.predict_proba(x[FEATS])[:, 1]
    learned = ranks(x, score_col).rename(columns={"rank": "learned_rank"})
    globalr = ranks(x.assign(global_score=-x.g_rank.astype(float)), "global_score")
    globalr = globalr.rename(columns={"rank": "global_rank"})
    ev = event_context[event_context.snapshot_date == snapshot].merge(
        learned, on=KEYS, how="inner").merge(globalr, on=KEYS, how="inner")
    # The published static EX-Graph features are not an as-of monthly view;
    # deliberately exclude them from the leakage-safe temporal gate.
    _ = struct
    ev["gate_target"] = (ev.learned_rank < ev.global_rank).astype(int)
    for c in EVENT_BASE[:8]:
        ev["log_" + c] = np.log1p(ev[c].astype(float))
    return ev

def fit_gate(train_events):
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced",
                           C=0.5, solver="liblinear", random_state=11))
    model.fit(train_events[GATE_FEATS], train_events.gate_target)
    return model


def metrics_from_ranks(events, rank_col):
    rr = 1.0 / events[rank_col].astype(float)
    return {
        "n_events": int(len(events)),
        "MRR": float(rr.mean()),
        "R@1": float((events[rank_col] == 1).mean()),
        "R@5": float((events[rank_col] <= 5).mean()),
        "R@10": float((events[rank_col] <= 10).mean()),
        "median_rank": float(events[rank_col].median()),
    }


def policy_curve(events, gate_p):
    n = len(events)
    cheap_u = (1.0 / events.global_rank.astype(float)).to_numpy()
    delib_u = (1.0 / events.learned_rank.astype(float)).to_numpy()
    gain = np.maximum(0.0, delib_u - cheap_u)
    order = np.argsort(-gate_p, kind="mergesort")
    oracle_order = np.argsort(-gain, kind="mergesort")
    rows = []
    for b in BUDGETS:
        k = max(1, int(round(b * n)))
        selected = np.zeros(n, dtype=bool)
        selected[order[:k]] = True
        mrr = np.where(selected, delib_u, cheap_u).mean()
        osel = np.zeros(n, dtype=bool)
        osel[oracle_order[:k]] = True
        omrr = np.where(osel, delib_u, cheap_u).mean()
        rows.append({
            "budget_fraction": b,
            "selected_events": int(k),
            "learned_gate_MRR": float(mrr),
            "learned_gate_gain": float(mrr - cheap_u.mean()),
            "oracle_gate_MRR": float(omrr),
            "oracle_gate_gain": float(omrr - cheap_u.mean()),
            "random_expected_MRR": float(cheap_u.mean() + b * (delib_u.mean() - cheap_u.mean())),
            "delta_MRR_per_1000_token_units": float(
                (mrr - cheap_u.mean()) * 1000.0 / (k * DELIB_TOKEN_UNITS + (n-k) * CHEAP_TOKEN_UNITS)),
            "oracle_delta_MRR_per_1000_token_units": float(
                (omrr - cheap_u.mean()) * 1000.0 / (k * DELIB_TOKEN_UNITS + (n-k) * CHEAP_TOKEN_UNITS)),
            "selected_actual_winner_share": float((events.gate_target.to_numpy()[order[:k]]).mean()),
        })
    return pd.DataFrame(rows), gain


def plot_curve(curve, out):
    import matplotlib.pyplot as plt
    plt.figure(figsize=(7, 4.5))
    plt.plot(curve.budget_fraction * 100, curve.learned_gate_MRR, marker="o", label="learned gate")
    plt.plot(curve.budget_fraction * 100, curve.oracle_gate_MRR, marker="s", label="oracle gate")
    plt.plot(curve.budget_fraction * 100, curve.random_expected_MRR, marker="^", label="random expected")
    plt.xlabel("events receiving deliberation (%)")
    plt.ylabel("sampled-pool MRR")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="artifacts/ranker_samples")
    ap.add_argument("--structural-features",
                    default="artifacts/exgraph_structural_features.csv")
    ap.add_argument("--outdir", default="artifacts/nc_v1")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    df = load_samples(args.workdir)
    struct = load_struct(args.structural_features)
    event_context = add_event_context(df)
    tr = df[df.snapshot_date == "2022-06-01"]
    va = df[df.snapshot_date == "2022-07-01"]
    te = df[df.snapshot_date == "2022-08-01"]

    # June-only model gives honest July gate labels; June+July model is the
    # frozen deployed August candidate ranker.
    june_model = candidate_ranker(tr)
    frozen_model = candidate_ranker(tr, va)
    july_events = gate_table(df, june_model, event_context, struct,
                             "2022-07-01", "june_oof_score")
    aug_events = gate_table(df, frozen_model, event_context, struct,
                            "2022-08-01", "frozen_score")
    gate = fit_gate(july_events)
    aug_events["gate_p"] = gate.predict_proba(aug_events[GATE_FEATS])[:, 1]

    curve, realized_gain = policy_curve(aug_events, aug_events.gate_p.to_numpy())
    result = {
        "protocol": {
            "candidate_space": "sampled up-to-50 non-neighbor top-2000 candidate rows per new event",
            "train_snapshot": "2022-06-01",
            "gate_tuning_snapshot": "2022-07-01 out-of-sample June ranker",
            "frozen_test_snapshot": "2022-08-01 ranker trained on June+July",
            "gate_features_are_event_level": True,
            "positive_candidate_excluded_from_context_aggregates": True,
            "token_unit_proxy": {"cheap": CHEAP_TOKEN_UNITS, "deliberation": DELIB_TOKEN_UNITS},
        },
        "rows_by_snapshot": df.snapshot_date.value_counts().sort_index().to_dict(),
        "july_gate_fit": {
            "n_events": int(len(july_events)),
            "learned_wins_share": float(july_events.gate_target.mean()),
            "feature_count": len(GATE_FEATS),
        },
        "august_event_count": int(len(aug_events)),
        "august_gate_discrimination": {
            "AUROC": float(roc_auc_score(aug_events.gate_target, aug_events.gate_p)),
            "AUPRC": float(average_precision_score(aug_events.gate_target, aug_events.gate_p)),
            "base_rate_learned_wins": float(aug_events.gate_target.mean()),
        },
        "august_scorers": {
            "cheap_global_sampled_pool": metrics_from_ranks(aug_events, "global_rank"),
            "frozen_learned_sampled_pool": metrics_from_ranks(aug_events, "learned_rank"),
            "oracle_best_per_event_sampled_pool": {
                "MRR": float(np.maximum(1.0 / aug_events.global_rank,
                                        1.0 / aug_events.learned_rank).mean()),
            },
        },
        "budget_curve": curve.to_dict(orient="records"),
    }
    top10 = curve[curve.budget_fraction == 0.10].iloc[0]
    result["gate_top10pct"] = {
        "selected_actual_winner_share": float(top10.selected_actual_winner_share),
        "mean_realized_gain_selected": float(realized_gain[
            np.argsort(-aug_events.gate_p.to_numpy(), kind="mergesort")[:int(round(0.1*len(aug_events)))]].mean()),
        "positive_realized_gain_share": float((realized_gain[
            np.argsort(-aug_events.gate_p.to_numpy(), kind="mergesort")[:int(round(0.1*len(aug_events)))] ] > 0).mean()),
    }
    json.dump(result, open(os.path.join(args.outdir, "gate_budget_v1.json"), "w"), indent=2)
    aug_events.to_csv(os.path.join(args.outdir, "aug_gate_events.csv"), index=False)
    july_events.to_csv(os.path.join(args.outdir, "july_gate_fit_events.csv"), index=False)
    curve.to_csv(os.path.join(args.outdir, "gate_budget_curve.csv"), index=False)
    plot_curve(curve, os.path.join(args.outdir, "gate_budget_curve.png"))
    print(json.dumps(result["august_scorers"], indent=2))
    print(curve.to_string(index=False))


if __name__ == "__main__":
    main()
