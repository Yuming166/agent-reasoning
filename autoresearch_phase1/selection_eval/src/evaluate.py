"""Evaluation metrics for budgeted wallet selection.

For a selector with support S and top-K set T_K at cutoff t, we report:
  - U(K) per label dimension: sum and mean over T_K (fwd30_evt_cnt,
    fwd30_cp_distinct, fwd30_new_cp)
  - U(K)/K  == mean over T_K (per selected wallet)
  - Recall@K: share of positive wallets (new_cp>0 / evt>0) inside support
    that are captured by T_K
  - event-mass coverage: share of total future event mass (within support)
    captured by T_K
  - positive-support coverage: share of universe positives that lie inside
    the selector's support (the 'support coverage' discipline metric)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LABELS = {"lbl_evt": "fwd30_evt_cnt", "lbl_cp": "fwd30_cp_distinct", "lbl_new": "fwd30_new_cp"}
KS = [10, 25, 50, 100, 250, 500, 1000]


def support_metrics(base: pd.DataFrame, support_mask: pd.Series, universe_pos: pd.Series,
                    support_name: str) -> dict:
    """Support-set boundary descriptors (support coverage, size, label bias)."""
    sup = base.loc[support_mask]
    pos_new_total = int((universe_pos > 0).sum())
    pos_new_sup = int((sup["lbl_new"] > 0).sum())
    out = {
        "support": support_name,
        "n_support": int(len(sup)),
        "universe_n": int(len(base)),
        "n_positive_new_cp": pos_new_total,
        "n_positive_new_cp_in_support": pos_new_sup,
        "positive_support_coverage": float(pos_new_sup / pos_new_total) if pos_new_total else None,
        "label_bias_mean_new_cp_support": float(sup["lbl_new"].mean()),
        "label_bias_mean_new_cp_universe": float(base["lbl_new"].mean()),
    }
    return out


def evaluate_selector(base: pd.DataFrame, key: str, k: int, support_name: str) -> dict:
    """Metrics for one selector at one K on its own native support."""
    from selector_defs import SELECTORS, get_topk
    spec = SELECTORS[key]
    col = spec["score"]
    sup_mask = base[col].notna()
    sup = base.loc[sup_mask].copy()
    topk = get_topk(base, key, k)
    n = len(topk)
    row = {
        "selector": key,
        "label": spec["label"],
        "tier": spec["tier"],
        "scope": spec["scope"],
        "support": support_name,
        "k": k,
        "n_support": int(len(sup)),
        "n_selected": n,
    }
    for lcol, lname in LABELS.items():
        total_sup = float(sup[lcol].sum())
        sel_sum = float(topk[lcol].sum())
        row[f"u_{lname}_sum"] = sel_sum
        row[f"u_{lname}_mean"] = sel_sum / n if n else float("nan")
        row[f"mass_share_{lname}"] = sel_sum / total_sup if total_sup else float("nan")
    pos_new = int((sup["lbl_new"] > 0).sum())
    pos_evt = int((sup["lbl_evt"] > 0).sum())
    row["recall_new_pos"] = float((topk["lbl_new"] > 0).sum() / pos_new) if pos_new else float("nan")
    row["recall_evt_pos"] = float((topk["lbl_evt"] > 0).sum() / pos_evt) if pos_evt else float("nan")
    row["support_frac"] = k / len(sup) if len(sup) else float("nan")
    return row


def evaluate_restricted(base: pd.DataFrame, keys: list[str], support_mask: pd.Series,
                        support_name: str, k: int) -> list[dict]:
    """Evaluate a set of selectors on a common restricted support (apples-to-apples)."""
    from selector_defs import SELECTORS, get_topk
    rows = []
    sup = base.loc[support_mask]
    for key in keys:
        spec_rows = sup.dropna(subset=[SELECTORS[key]["score"]])
        # re-derive topk from the restricted frame so support is exactly the
        # restricted pool
        topk = get_topk(spec_rows, key, k)
        n = len(topk)
        row = {
            "selector": key, "label": SELECTORS[key]["label"],
            "tier": SELECTORS[key]["tier"], "scope": support_name,
            "support": support_name, "k": k, "n_support": int(len(spec_rows)),
            "n_selected": n,
        }
        for lcol, lname in LABELS.items():
            total_sup = float(spec_rows[lcol].sum())
            sel_sum = float(topk[lcol].sum())
            row[f"u_{lname}_sum"] = sel_sum
            row[f"u_{lname}_mean"] = sel_sum / n if n else float("nan")
            row[f"mass_share_{lname}"] = sel_sum / total_sup if total_sup else float("nan")
        pos_new = int((spec_rows["lbl_new"] > 0).sum())
        pos_evt = int((spec_rows["lbl_evt"] > 0).sum())
        row["recall_new_pos"] = float((topk["lbl_new"] > 0).sum() / pos_new) if pos_new else float("nan")
        row["recall_evt_pos"] = float((topk["lbl_evt"] > 0).sum() / pos_evt) if pos_evt else float("nan")
        row["support_frac"] = k / len(spec_rows) if len(spec_rows) else float("nan")
        rows.append(row)
    return rows


def oracle_rows(base: pd.DataFrame, support_mask: pd.Series, support_name: str) -> list[dict]:
    """Post-hoc oracle (top-K by future labels) as a reference upper bound."""
    sup = base.loc[support_mask].copy()
    rows = []
    for k in KS:
        for lcol, lname in LABELS.items():
            sel = sup.sort_values([lcol, "target_address"], ascending=[False, True]).head(k)
            rows.append({
                "selector": f"oracle_{lname}", "label": f"Oracle (future {lname})",
                "tier": "oracle_posthoc", "scope": support_name, "support": support_name,
                "k": k, "n_support": int(len(sup)), "n_selected": len(sel),
                f"u_{lname}_sum": float(sel[lcol].sum()),
                f"u_{lname}_mean": float(sel[lcol].sum() / len(sel)),
                "recall_new_pos": float((sel["lbl_new"] > 0).sum() / max((sup["lbl_new"] > 0).sum(), 1)),
                "recall_evt_pos": float((sel["lbl_evt"] > 0).sum() / max((sup["lbl_evt"] > 0).sum(), 1)),
            })
    return rows


def random_expected_rows(base: pd.DataFrame, support_mask: pd.Series, support_name: str) -> list[dict]:
    """Expected random utility: E[sum over K draws] = K * mean(label|support)."""
    sup = base.loc[support_mask]
    rows = []
    for k in KS:
        row = {"selector": "random_expected", "label": "Random (expected)",
               "tier": "random", "scope": support_name, "support": support_name,
               "k": k, "n_support": int(len(sup)), "n_selected": k}
        for lcol, lname in LABELS.items():
            mean_sup = float(sup[lcol].mean())
            row[f"u_{lname}_sum"] = k * mean_sup
            row[f"u_{lname}_mean"] = mean_sup
        rows.append(row)
    return rows
