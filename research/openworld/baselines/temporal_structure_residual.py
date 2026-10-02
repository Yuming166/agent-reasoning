#!/usr/bin/env python3
"""Bounded temporal structure-residual pilot for the EX-Graph open-world track.

This pilot is deliberately limited to the already-materialized day-level,
matched-matched primary edge extract.  It does *not* use external labels and
it does not claim to reproduce event-level direction/rapid-forward features.
The registered primary detector is a fixed residual score over four structural
signals, conditional on pre-cutoff volume/activity features.

The script emits compact CSV/JSON artifacts only.  All thresholds and windows
are fixed in code; future windows are used only after ranking/matching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

SEED = 20260918
CUTOFFS = pd.to_datetime(["2022-06-01", "2022-07-01", "2022-08-01"])
LOOKBACK_DAYS = 30
SCORE_DAYS = 7
SHORT_HORIZON_DAYS = 7
HORIZON_DAYS = 30
TOP_FRACTION = 0.05
MATCH_K = 5
STRICT_MIN_EVENTS = 10
EXPANDED_MIN_EVENTS = 3
MIN_ACTIVE_DAYS = 3
COVERAGE_MIN_CANDIDATES = 2000
COVERAGE_MIN_TOP = 100
BOOTSTRAP_DRAWS = 2000

METHODS = [
    "volume_activity",
    "fine_temporal_activity",
    "simple_temporal",
    "raw_structure",
    "structure_residual",
]
PRIMARY_METHOD = "structure_residual"
BASE_FEATURES = [
    "log_hist_events",
    "hist_active_days",
    "log_hist_counterparties",
    "log_score_events",
    "score_active_days",
    "activity_change",
]
STRUCTURE_FEATURES = [
    "counterparty_novelty",
    "counterparty_growth",
    "reciprocity_change",
    "score_burstiness",
]
MATCH_FEATURES = [
    "log_hist_events",
    "hist_active_days",
    "log_hist_counterparties",
    "log_score_events",
    "score_active_days",
    "activity_change",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def zscore(values: pd.Series | np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    med = float(np.nanmedian(x))
    mad = float(np.nanmedian(np.abs(x - med)))
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale < 1e-9:
        scale = float(np.nanstd(x))
    if not np.isfinite(scale) or scale < 1e-9:
        scale = 1.0
    return (x - med) / scale


def percentile(values: pd.Series) -> pd.Series:
    # Stable rank-based score; all ties receive the same average percentile.
    return values.rank(method="average", pct=True)


def build_node_sets(frame: pd.DataFrame) -> dict[int, set[int]]:
    if frame.empty:
        return {}
    return {
        int(node): set(int(x) for x in group["v"].unique())
        for node, group in frame.groupby("u", sort=False)
    }


def build_daily_counts(frame: pd.DataFrame) -> dict[int, pd.Series]:
    if frame.empty:
        return {}
    grouped = frame.groupby(["u", "day_dt"], sort=False)["weight"].sum()
    return {
        int(node): series.droplevel(0)
        for node, series in grouped.groupby(level=0, sort=False)
    }


def build_features(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    eligibility: str,
    min_events: int,
) -> tuple[pd.DataFrame, dict[str, int]]:
    start = cutoff - pd.Timedelta(days=LOOKBACK_DAYS)
    score_start = cutoff - pd.Timedelta(days=SCORE_DAYS)
    hist = frame[(frame.day_dt >= start) & (frame.day_dt < cutoff)].copy()
    prior = hist[hist.day_dt < score_start].copy()
    score = hist[hist.day_dt >= score_start].copy()

    hist_agg = hist.groupby("u").agg(
        hist_events=("weight", "sum"),
        hist_active_days=("day_dt", "nunique"),
        hist_counterparties=("v", "nunique"),
    )
    candidates = hist_agg[
        (hist_agg.hist_active_days >= MIN_ACTIVE_DAYS)
        & (hist_agg.hist_events >= min_events)
    ].copy()
    candidates.index = candidates.index.astype(int)
    nodes = [int(x) for x in candidates.index]

    prior_agg = prior.groupby("u").agg(
        prior_events=("weight", "sum"),
        prior_active_days=("day_dt", "nunique"),
        prior_counterparties=("v", "nunique"),
    )
    score_agg = score.groupby("u").agg(
        score_events=("weight", "sum"),
        score_active_days=("day_dt", "nunique"),
        score_counterparties=("v", "nunique"),
    )
    out = candidates.join(prior_agg, how="left").join(score_agg, how="left").fillna(0.0)
    for col in [
        "hist_events", "hist_active_days", "hist_counterparties",
        "prior_events", "prior_active_days", "prior_counterparties",
        "score_events", "score_active_days", "score_counterparties",
    ]:
        out[col] = out[col].astype(float)

    hist_sets = build_node_sets(hist)
    prior_sets = build_node_sets(prior)
    score_sets = build_node_sets(score)
    hist_daily = build_daily_counts(hist)
    score_daily = build_daily_counts(score)
    hist_pairs = set(zip(hist["u"].astype(int), hist["v"].astype(int)))
    prior_pairs = set(zip(prior["u"].astype(int), prior["v"].astype(int)))
    score_pairs = set(zip(score["u"].astype(int), score["v"].astype(int)))

    novelty = []
    growth = []
    reciprocal_change = []
    burstiness = []
    for node in nodes:
        hist_cp = hist_sets.get(node, set())
        prior_cp = prior_sets.get(node, set())
        score_cp = score_sets.get(node, set())
        new_cp = score_cp - prior_cp
        novelty.append(len(new_cp) / max(len(score_cp), 1))
        prior_week_equiv = len(prior_cp) * SCORE_DAYS / max(LOOKBACK_DAYS - SCORE_DAYS, 1)
        growth.append(math.log1p(len(score_cp)) - math.log1p(prior_week_equiv))

        prior_node_pairs = {(node, cp) for cp in prior_cp}
        score_node_pairs = {(node, cp) for cp in score_cp}
        prior_recip = sum((cp, node) in prior_pairs for cp in prior_cp) / max(len(prior_cp), 1)
        score_recip = sum(
            ((cp, node) in score_pairs) or ((cp, node) in hist_pairs)
            for cp in score_cp
        ) / max(len(score_cp), 1)
        # Keep the local daily extract's direction semantics explicit: reciprocal
        # means the reverse directed pair was observed in the same pre-cutoff data.
        _ = prior_node_pairs, score_node_pairs
        reciprocal_change.append(score_recip - prior_recip)

        daily = score_daily.get(node)
        if daily is None or daily.empty:
            burstiness.append(0.0)
        else:
            burstiness.append(float(daily.max() / max(daily.mean(), 1e-9)))

    out["counterparty_novelty"] = novelty
    out["counterparty_growth"] = growth
    out["reciprocity_change"] = reciprocal_change
    out["score_burstiness"] = burstiness
    out["log_hist_events"] = np.log1p(out.hist_events)
    out["log_hist_counterparties"] = np.log1p(out.hist_counterparties)
    out["log_score_events"] = np.log1p(out.score_events)
    out["activity_change"] = (
        out.score_events / SCORE_DAYS - out.prior_events / max(LOOKBACK_DAYS - SCORE_DAYS, 1)
    )
    out["active_day_change"] = (
        out.score_active_days / SCORE_DAYS
        - out.prior_active_days / max(LOOKBACK_DAYS - SCORE_DAYS, 1)
    )

    # Rank baselines are fixed and use no post-cutoff information.
    out["volume_activity"] = np.mean(
        np.column_stack(
            [
                percentile(out.log_hist_events),
                percentile(out.hist_active_days),
                percentile(out.log_hist_counterparties),
            ]
        ),
        axis=1,
    )
    out["fine_temporal_activity"] = np.mean(
        np.column_stack(
            [
                percentile(out.log_score_events),
                percentile(out.score_active_days),
                percentile(out.log_hist_counterparties),
            ]
        ),
        axis=1,
    )
    out["simple_temporal"] = np.mean(
        np.column_stack([zscore(out.activity_change), zscore(out.active_day_change)]),
        axis=1,
    )

    # Raw structure is a fixed, unconditional reference.  The primary score
    # residualizes the same four signals on pre-cutoff volume/activity.
    raw_z = np.column_stack([zscore(out[x]) for x in STRUCTURE_FEATURES])
    out["raw_structure"] = np.mean(np.abs(raw_z), axis=1)
    x = np.column_stack([np.ones(len(out))] + [zscore(out[c]) for c in BASE_FEATURES])
    residual_z = []
    for col in STRUCTURE_FEATURES:
        y = np.asarray(out[col], dtype=float)
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        residual_z.append(zscore(y - x @ coef))
    residual_z_arr = np.column_stack(residual_z)
    out[PRIMARY_METHOD] = np.mean(np.abs(residual_z_arr), axis=1)
    out.index.name = "node"

    meta = {
        "history_rows": int(len(hist)),
        "prior_rows": int(len(prior)),
        "score_rows": int(len(score)),
        "candidate_count": int(len(out)),
        "min_events": int(min_events),
        "min_active_days": MIN_ACTIVE_DAYS,
        "missing_event_level_features": 1,
    }
    return out.reset_index(), meta


def future_outcomes(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    candidates: Iterable[int],
) -> pd.DataFrame:
    hist_start = cutoff - pd.Timedelta(days=LOOKBACK_DAYS)
    hist = frame[(frame.day_dt >= hist_start) & (frame.day_dt < cutoff)]
    f7 = frame[
        (frame.day_dt >= cutoff)
        & (frame.day_dt < cutoff + pd.Timedelta(days=SHORT_HORIZON_DAYS))
    ]
    f30 = frame[
        (frame.day_dt >= cutoff)
        & (frame.day_dt < cutoff + pd.Timedelta(days=HORIZON_DAYS))
    ]
    hist_sets = build_node_sets(hist)
    rows = []
    for node in [int(x) for x in candidates]:
        hcp = hist_sets.get(node, set())
        row = {"node": node}
        for label, future in [("future7", f7), ("future30", f30)]:
            nf = future[future.u == node]
            cps = set(int(x) for x in nf.v.unique())
            row[f"{label}_events"] = float(nf.weight.sum())
            row[f"{label}_active_days"] = int(nf.day_dt.nunique())
            row[f"{label}_new_counterparties"] = int(len(cps - hcp))
        row["open_world_outcome"] = int(
            row["future30_active_days"] >= 3
            and row["future30_new_counterparties"] >= 2
        )
        rows.append(row)
    return pd.DataFrame(rows)


def greedy_matches(
    features: pd.DataFrame,
    treated_nodes: list[int],
    k: int = MATCH_K,
) -> tuple[dict[int, list[int]], float, int]:
    candidate_nodes = features.node.astype(int).tolist()
    control_nodes = [n for n in candidate_nodes if n not in set(treated_nodes)]
    if not treated_nodes or not control_nodes:
        return {}, float("nan"), 0
    matrix = features.set_index("node")[MATCH_FEATURES].astype(float)
    # Standardization is fitted only on the current cutoff's pre-cutoff pool.
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0, ddof=0).replace(0.0, 1.0)
    scaled = (matrix - means) / stds
    tmat = scaled.loc[treated_nodes].to_numpy()
    cmat = scaled.loc[control_nodes].to_numpy()
    nn = NearestNeighbors(n_neighbors=min(k, len(control_nodes)), metric="euclidean")
    nn.fit(cmat)
    distances, indices = nn.kneighbors(tmat)
    # Greedy no-reuse assignment in treated-node order. A fallback permits reuse
    # only when the candidate pool is too small; the diagnostic reports it.
    matches: dict[int, list[int]] = {}
    used: set[int] = set()
    reuse = 0
    for i, node in enumerate(treated_nodes):
        chosen: list[int] = []
        for distance, idx in zip(distances[i], indices[i]):
            cnode = int(control_nodes[int(idx)])
            if cnode not in used:
                chosen.append(cnode)
                used.add(cnode)
            if len(chosen) >= k:
                break
        if len(chosen) < k:
            for idx in indices[i]:
                cnode = int(control_nodes[int(idx)])
                if cnode not in chosen:
                    chosen.append(cnode)
                    reuse += 1
                if len(chosen) >= k:
                    break
        matches[int(node)] = chosen
    # Calculate the mean standardized difference over all matched pairs.
    smds = []
    for col in MATCH_FEATURES:
        tv = features.set_index("node").loc[treated_nodes, col].astype(float).mean()
        cv = np.mean([
            features.set_index("node").loc[c, col]
            for cs in matches.values() for c in cs
        ]) if matches else np.nan
        pooled = features.set_index("node")[col].astype(float).std(ddof=0)
        smds.append(abs(float(tv - cv)) / max(float(pooled), 1e-9))
    max_smd = float(np.nanmax(smds)) if smds else float("nan")
    return matches, max_smd, reuse


def bootstrap_ratio_ci(
    treated: np.ndarray,
    controls: np.ndarray,
    rng: np.random.Generator,
) -> tuple[float, float]:
    if len(treated) == 0:
        return float("nan"), float("nan")
    ratios = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    n = len(treated)
    for i in range(BOOTSTRAP_DRAWS):
        idx = rng.integers(0, n, size=n)
        denom = float(np.mean(controls[idx]))
        ratios[i] = float(np.mean(treated[idx]) / denom) if denom > 1e-12 else np.nan
    ratios = ratios[np.isfinite(ratios)]
    if len(ratios) == 0:
        return float("nan"), float("nan")
    return float(np.quantile(ratios, 0.025)), float(np.quantile(ratios, 0.975))


def evaluate_method(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    method: str,
    cutoff: pd.Timestamp,
    eligibility: str,
    rng: np.random.Generator,
) -> tuple[dict, pd.DataFrame]:
    ordered = features.sort_values([method, "node"], ascending=[False, True])
    top_n = max(1, int(math.ceil(TOP_FRACTION * len(ordered))))
    top = ordered.head(top_n).copy()
    treated_nodes = top.node.astype(int).tolist()
    matches, max_smd, reuse = greedy_matches(features, treated_nodes)
    outcome = outcomes.set_index("node")
    treated_rows = outcome.loc[treated_nodes]
    control_rows = []
    pair_rows = []
    for node in treated_nodes:
        cs = matches.get(node, [])
        if not cs:
            continue
        c = outcome.loc[cs]
        control_rows.append(c.mean(numeric_only=True))
        pair_rows.append(
            {
                "node": node,
                "control_future7_new_counterparties": float(c.future7_new_counterparties.mean()),
                "control_future7_active_days": float(c.future7_active_days.mean()),
                "control_open_world_outcome": float(c.open_world_outcome.mean()),
            }
        )
    pair = pd.DataFrame(pair_rows).set_index("node") if pair_rows else pd.DataFrame()
    matched_treated = outcome.loc[pair.index] if not pair.empty else outcome.iloc[0:0]
    rng_local = np.random.default_rng(int(rng.integers(0, 2**32 - 1)))
    t_new = matched_treated.future7_new_counterparties.to_numpy(dtype=float)
    c_new = pair.control_future7_new_counterparties.to_numpy(dtype=float)
    t_open = matched_treated.open_world_outcome.to_numpy(dtype=float)
    c_open = pair.control_open_world_outcome.to_numpy(dtype=float)
    new_lo, new_hi = bootstrap_ratio_ci(t_new, c_new, rng_local)
    open_lo, open_hi = bootstrap_ratio_ci(t_open, c_open, rng_local)
    t_active = matched_treated.future7_active_days.to_numpy(dtype=float)
    c_active = pair.control_future7_active_days.to_numpy(dtype=float)
    new_lift = float(np.mean(t_new) / np.mean(c_new)) if len(t_new) and np.mean(c_new) > 0 else np.nan
    active_lift = float(np.mean(t_active) / np.mean(c_active)) if len(t_active) and np.mean(c_active) > 0 else np.nan
    open_lift = float(np.mean(t_open) / np.mean(c_open)) if len(t_open) and np.mean(c_open) > 0 else np.nan
    row = {
        "eligibility": eligibility,
        "cutoff": cutoff.date().isoformat(),
        "method": method,
        "candidate_count": int(len(features)),
        "top_n": int(top_n),
        "matched_treated_count": int(len(matched_treated)),
        "match_k": MATCH_K,
        "match_reuse_count": int(reuse),
        "max_match_smd": max_smd,
        "future7_new_cp_treated_mean": float(np.mean(t_new)) if len(t_new) else np.nan,
        "future7_new_cp_control_mean": float(np.mean(c_new)) if len(c_new) else np.nan,
        "future7_new_cp_lift": new_lift,
        "future7_new_cp_lift_ci_lo": new_lo,
        "future7_new_cp_lift_ci_hi": new_hi,
        "future7_active_days_treated_mean": float(np.mean(t_active)) if len(t_active) else np.nan,
        "future7_active_days_control_mean": float(np.mean(c_active)) if len(c_active) else np.nan,
        "future7_active_days_lift": active_lift,
        "open_world_rate_treated": float(np.mean(t_open)) if len(t_open) else np.nan,
        "open_world_rate_control": float(np.mean(c_open)) if len(c_open) else np.nan,
        "open_world_lift": open_lift,
        "open_world_lift_ci_lo": open_lo,
        "open_world_lift_ci_hi": open_hi,
    }
    selected = top[["node", method]].copy()
    selected["eligibility"] = eligibility
    selected["cutoff"] = cutoff.date().isoformat()
    selected["method"] = method
    selected = selected.merge(outcomes, on="node", how="left")
    return row, selected


def add_stability(panel: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (eligibility, method), group in selected.groupby(["eligibility", "method"]):
        sets = {
            cutoff: set(g.node.astype(int))
            for cutoff, g in group.groupby("cutoff")
        }
        ordered = sorted(sets)
        jaccards = []
        for a, b in zip(ordered, ordered[1:]):
            union = sets[a] | sets[b]
            jaccards.append(len(sets[a] & sets[b]) / len(union) if union else np.nan)
        rows.append({
            "eligibility": eligibility,
            "method": method,
            "mean_adjacent_jaccard": float(np.nanmean(jaccards)) if jaccards else np.nan,
            "cutoff_count": len(ordered),
        })
    return panel.merge(pd.DataFrame(rows), on=["eligibility", "method"], how="left")


def decision_for(panel: pd.DataFrame, eligibility: str) -> dict:
    x = panel[(panel.eligibility == eligibility)]
    p = x[x.method == PRIMARY_METHOD].copy()
    if p.empty:
        return {"eligibility": eligibility, "decision": "NO_RESULT"}
    coverage_ok = bool(
        (p.candidate_count >= COVERAGE_MIN_CANDIDATES).all()
        and (p.top_n >= COVERAGE_MIN_TOP).all()
    )
    lift_ok = bool(
        np.nanmedian(p.future7_new_cp_lift) >= 1.10
        and (p.future7_new_cp_lift_ci_lo > 1.0).sum() >= max(1, len(p) - 1)
    )
    open_ok = bool(
        np.nanmedian(p.open_world_lift) >= 1.15
        and np.nanmean(p.open_world_rate_treated) >= 0.10
    )
    stability = float(p.mean_adjacent_jaccard.iloc[0])
    stability_ok = bool(np.isfinite(stability) and stability >= 0.30)
    baseline = x[x.method != PRIMARY_METHOD].groupby("cutoff", as_index=False).agg(
        best_new_cp_lift=("future7_new_cp_lift", "max"),
        best_open_world_lift=("open_world_lift", "max"),
    )
    p2 = p.merge(baseline, on="cutoff", how="left")
    delta_ok = bool(
        (p2.future7_new_cp_lift - p2.best_new_cp_lift >= -0.05).all()
        and (p2.open_world_lift - p2.best_open_world_lift >= 0.05).sum() >= max(1, len(p2) - 1)
    )
    if not coverage_ok:
        decision = "NO_GO_UNDERPOWERED_COVERAGE"
    elif lift_ok and open_ok and stability_ok and delta_ok:
        decision = "GO_GRAPH_ONLY_GATE"
    else:
        decision = "NO_GO_PRIMARY_THRESHOLD"
    return {
        "eligibility": eligibility,
        "decision": decision,
        "coverage_ok": coverage_ok,
        "primary_median_new_cp_lift": float(np.nanmedian(p.future7_new_cp_lift)),
        "primary_new_cp_ci_lower_pass_count": int((p.future7_new_cp_lift_ci_lo > 1.0).sum()),
        "primary_median_open_world_lift": float(np.nanmedian(p.open_world_lift)),
        "primary_mean_open_world_rate": float(np.nanmean(p.open_world_rate_treated)),
        "primary_mean_adjacent_jaccard": stability,
        "lift_ok": lift_ok,
        "open_world_ok": open_ok,
        "stability_ok": stability_ok,
        "baseline_delta_ok": delta_ok,
        "coverage_min_candidates": COVERAGE_MIN_CANDIDATES,
        "coverage_min_top": COVERAGE_MIN_TOP,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--edge-csv",
        type=Path,
        default=Path("research/community_temporal/results/data/edges_day_20220303_20220901.csv"),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("research/openworld/results"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(args.edge_csv)
    required = {"u", "v", "direction", "day", "weight"}
    missing = required - set(frame.columns)
    if missing:
        raise SystemExit(f"missing columns: {sorted(missing)}")
    # The day extract contains paired incoming/outgoing role rows. Keep one
    # canonical source->destination row per actual directed edge.
    frame = frame[frame.direction.astype(str).str.lower() == "outgoing"].copy()
    frame["u"] = frame["u"].astype(int)
    frame["v"] = frame["v"].astype(int)
    frame["weight"] = frame["weight"].astype(float)
    frame["day_dt"] = pd.to_datetime(frame["day"], utc=False)
    frame = (
        frame.groupby(["u", "v", "day_dt"], as_index=False)["weight"].sum()
        .sort_values(["day_dt", "u", "v"])
        .reset_index(drop=True)
    )
    rng = np.random.default_rng(SEED)
    panel_rows: list[dict] = []
    selected_frames: list[pd.DataFrame] = []
    feature_diagnostics: list[dict] = []
    for eligibility, min_events in [
        ("registered_strict_10_events", STRICT_MIN_EVENTS),
        ("expanded_diagnostic_3_events", EXPANDED_MIN_EVENTS),
    ]:
        for cutoff in CUTOFFS:
            features, meta = build_features(frame, cutoff, eligibility, min_events)
            outcomes = future_outcomes(frame, cutoff, features.node)
            feature_diagnostics.append({
                "eligibility": eligibility,
                "cutoff": cutoff.date().isoformat(),
                **meta,
            })
            for method in METHODS:
                row, selected = evaluate_method(
                    features, outcomes, method, cutoff, eligibility, rng
                )
                panel_rows.append(row)
                selected_frames.append(selected)
    panel = pd.DataFrame(panel_rows)
    selected = pd.concat(selected_frames, ignore_index=True)
    panel = add_stability(panel, selected)
    decisions = [
        decision_for(panel, "registered_strict_10_events"),
        decision_for(panel, "expanded_diagnostic_3_events"),
    ]
    panel_path = args.out_dir / "temporal_structure_residual_panel.csv"
    selected_path = args.out_dir / "temporal_structure_residual_selected.csv"
    summary_path = args.out_dir / "temporal_structure_residual_summary.csv"
    manifest_path = args.out_dir / "temporal_structure_residual_manifest.json"
    panel.to_csv(panel_path, index=False)
    selected.to_csv(selected_path, index=False)
    summary = panel.groupby(["eligibility", "method"], as_index=False).agg(
        candidate_count_median=("candidate_count", "median"),
        top_n_median=("top_n", "median"),
        new_cp_lift_median=("future7_new_cp_lift", "median"),
        new_cp_ci_lower_min=("future7_new_cp_lift_ci_lo", "min"),
        open_world_lift_median=("open_world_lift", "median"),
        open_world_rate_treated_mean=("open_world_rate_treated", "mean"),
        active_days_lift_median=("future7_active_days_lift", "median"),
        max_match_smd=("max_match_smd", "max"),
        mean_adjacent_jaccard=("mean_adjacent_jaccard", "first"),
    )
    summary.to_csv(summary_path, index=False)
    manifest = {
        "experiment_id": "OW-009",
        "date": "2026-09-18",
        "experiment": "temporal_structure_residual_pilot",
        "input": str(args.edge_csv),
        "input_sha256": sha256_file(args.edge_csv),
        "source_boundary": "local day-level matched-matched primary edge extract; no external labels",
        "event_level_limitation": "timestamp/event_family/native_value/token fields are unavailable in this local extract; rapid-forward and in/out-change signals are not claimed",
        "canonicalization": "keep direction=outgoing rows; aggregate u,v,day; paired incoming role rows are excluded",
        "cutoffs": [x.date().isoformat() for x in CUTOFFS],
        "lookback_days": LOOKBACK_DAYS,
        "score_days": SCORE_DAYS,
        "short_horizon_days": SHORT_HORIZON_DAYS,
        "horizon_days": HORIZON_DAYS,
        "top_fraction": TOP_FRACTION,
        "match_k": MATCH_K,
        "seed": SEED,
        "primary_method": PRIMARY_METHOD,
        "methods": METHODS,
        "base_features": BASE_FEATURES,
        "structure_features": STRUCTURE_FEATURES,
        "match_features": MATCH_FEATURES,
        "coverage_gate": {
            "min_candidates_per_cutoff": COVERAGE_MIN_CANDIDATES,
            "min_top_per_cutoff": COVERAGE_MIN_TOP,
        },
        "feature_diagnostics": feature_diagnostics,
        "decisions": decisions,
        "outputs": {
            "panel": str(panel_path),
            "selected": str(selected_path),
            "summary": str(summary_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(summary.round(4).to_string(index=False))
    print(json.dumps({"decisions": decisions, "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
