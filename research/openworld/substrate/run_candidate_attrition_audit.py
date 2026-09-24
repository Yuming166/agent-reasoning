#!/usr/bin/env python3
"""Audit OW-009 candidate attrition, feature coverage, and matching balance.

This audit is blind to the external wash-label files.  It uses:
  * the local OW-009 day-level edge artifact and its source SQL;
  * the released 27,613-row address map;
  * the already materialized as-of feature table for a substrate-size
    cross-check, reading discovery columns only (never future labels).

The audit reproduces OW-009's feature construction and matching logic without
changing the detector, thresholds, or matching procedure.  It writes compact
CSV/Markdown artifacts under research/openworld/substrate/.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "openworld" / "substrate"
EDGE = ROOT / "research" / "community_temporal" / "results" / "data" / "edges_day_20220303_20220901.csv"
MAPPING = ROOT / "vendor" / "EX-Graph-repo" / "twitter_matching.csv"
ASOF = ROOT / "research" / "groupA_behavior" / "results" / "data" / "asof_monthly_2022.parquet"
SEQUENCE_META = ROOT / "artifacts" / "google_sequence_tables_2022-03_2022-09.json"
OW009 = ROOT / "research" / "openworld" / "baselines" / "temporal_structure_residual.py"
EDGE_SQL = ROOT / "research" / "community_temporal" / "sql" / "edges_asof_day.sql"
BQ_EVIDENCE = OUT / "bigquery_substrate_counts_20260918.json"
CUTOFFS = pd.to_datetime(["2022-06-01", "2022-07-01", "2022-08-01"])
LOOKBACK = 30
SCORE_DAYS = 7
TOP_FRACTION = 0.05
MATCH_K = 5
MIN_ACTIVE = 3
STRICT_EVENTS = 10
EXPANDED_EVENTS = 3
SEED = 20260918

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
MATCH_FEATURES = BASE_FEATURES.copy()
METHOD = "structure_residual"


def md_table(df: pd.DataFrame) -> str:
    """Small dependency-free Markdown table renderer."""
    if df.empty:
        return "(no rows)"
    cols = [str(c) for c in df.columns]
    def cell(value):
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        text = str(value).replace("|", "\\|").replace("\n", " ")
        return text
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(lines)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def robust_z(values: pd.Series | np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    med = float(np.nanmedian(x))
    mad = float(np.nanmedian(np.abs(x - med)))
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale < 1e-9:
        scale = float(np.nanstd(x))
    if not np.isfinite(scale) or scale < 1e-9:
        scale = 1.0
    return (x - med) / scale


def pct(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True)


def load_inputs() -> tuple[set[int], pd.DataFrame, pd.DataFrame, dict]:
    mapping = pd.read_csv(MAPPING, usecols=["node_id", "ethereum_address"])
    mapped_nodes = set(mapping["node_id"].astype(int))

    raw = pd.read_csv(EDGE)
    raw["u"] = raw["u"].astype(int)
    raw["v"] = raw["v"].astype(int)
    raw["weight"] = raw["weight"].astype(float)
    raw["day_dt"] = pd.to_datetime(raw["day"], utc=False)
    # Reproduce the local artifact's already-aggregated rows, while also
    # canonicalizing duplicates defensively.
    raw = (
        raw.groupby(["u", "v", "direction", "day_dt"], as_index=False)["weight"]
        .sum()
        .sort_values(["day_dt", "u", "v", "direction"])
        .reset_index(drop=True)
    )
    outgoing = raw[raw["direction"].str.lower() == "outgoing"].copy()
    outgoing = (
        outgoing.groupby(["u", "v", "day_dt"], as_index=False)["weight"]
        .sum()
        .sort_values(["day_dt", "u", "v"])
        .reset_index(drop=True)
    )

    discovery_cols = [
        "snapshot_date", "target_exgraph_node_id", "target_is_x_matched",
        "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
        "evt_native_90d", "evt_token_90d", "active_days_90d",
        "tx_cnt_90d", "active_span_days_90d", "cp_distinct_90d",
        "cp_out_distinct_90d", "cp_in_distinct_90d", "cp_out_interact_90d",
        "cp_in_interact_90d", "token_distinct_90d", "cp_entropy_90d",
        "cp_new_30d", "cp_new_rate_30d", "cp_both_dir_90d",
        "cp_reciprocity_90d", "self_tx_rate_90d", "token_event_rate_90d",
        "token_hhi_90d", "events_per_active_day_90d",
    ]
    asof = pd.read_parquet(ASOF, columns=discovery_cols)
    asof["snapshot_date"] = pd.to_datetime(asof["snapshot_date"])
    meta = json.loads(SEQUENCE_META.read_text())
    sequence_rows = meta["tables"]["target_event_sequences_20220301_20220901"]["num_rows"]
    bq_evidence = json.loads(BQ_EVIDENCE.read_text()) if BQ_EVIDENCE.exists() else None
    return mapped_nodes, raw, outgoing, {"asof": asof, "sequence_rows": sequence_rows, "bq_evidence": bq_evidence}


def node_sets(frame: pd.DataFrame) -> dict[int, set[int]]:
    if frame.empty:
        return {}
    return {
        int(node): set(int(x) for x in group["v"].unique())
        for node, group in frame.groupby("u", sort=False)
    }


def daily_counts(frame: pd.DataFrame) -> dict[int, pd.Series]:
    if frame.empty:
        return {}
    grouped = frame.groupby(["u", "day_dt"], sort=False)["weight"].sum()
    return {int(node): s.droplevel(0) for node, s in grouped.groupby(level=0, sort=False)}


def agg(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["events", "active_days", "counterparties"])
    return frame.groupby("u").agg(
        events=("weight", "sum"),
        active_days=("day_dt", "nunique"),
        counterparties=("v", "nunique"),
    )


def build_features(frame: pd.DataFrame, cutoff: pd.Timestamp, min_events: int) -> pd.DataFrame:
    start = cutoff - pd.Timedelta(days=LOOKBACK)
    score_start = cutoff - pd.Timedelta(days=SCORE_DAYS)
    hist = frame[(frame.day_dt >= start) & (frame.day_dt < cutoff)].copy()
    prior = hist[hist.day_dt < score_start].copy()
    score = hist[hist.day_dt >= score_start].copy()
    hist_agg = agg(hist)
    candidates = hist_agg[(hist_agg.active_days >= MIN_ACTIVE) & (hist_agg.events >= min_events)].copy()
    candidates.index = candidates.index.astype(int)
    prior_agg = agg(prior).rename(columns={
        "events": "prior_events", "active_days": "prior_active_days", "counterparties": "prior_counterparties"
    })
    score_agg = agg(score).rename(columns={
        "events": "score_events", "active_days": "score_active_days", "counterparties": "score_counterparties"
    })
    out = candidates.rename(columns={
        "events": "hist_events", "active_days": "hist_active_days", "counterparties": "hist_counterparties"
    }).join(prior_agg, how="left").join(score_agg, how="left")
    missing_before_zero_fill = {
        col: int(out[col].isna().sum())
        for col in [
            "prior_events", "prior_active_days", "prior_counterparties",
            "score_events", "score_active_days", "score_counterparties",
        ]
        if col in out.columns
    }
    out = out.fillna(0.0)
    for col in [
        "hist_events", "hist_active_days", "hist_counterparties", "prior_events",
        "prior_active_days", "prior_counterparties", "score_events",
        "score_active_days", "score_counterparties",
    ]:
        out[col] = out[col].astype(float)

    hist_sets = node_sets(hist)
    prior_sets = node_sets(prior)
    score_sets = node_sets(score)
    score_daily = daily_counts(score)
    hist_pairs = set(zip(hist.u.astype(int), hist.v.astype(int)))
    prior_pairs = set(zip(prior.u.astype(int), prior.v.astype(int)))
    score_pairs = set(zip(score.u.astype(int), score.v.astype(int)))
    novelty, growth, reciprocity, burst = [], [], [], []
    for node in out.index.astype(int):
        prior_cp = prior_sets.get(node, set())
        score_cp = score_sets.get(node, set())
        novelty.append(len(score_cp - prior_cp) / max(len(score_cp), 1))
        prior_week_equiv = len(prior_cp) * SCORE_DAYS / max(LOOKBACK - SCORE_DAYS, 1)
        growth.append(math.log1p(len(score_cp)) - math.log1p(prior_week_equiv))
        prior_recip = sum((cp, node) in prior_pairs for cp in prior_cp) / max(len(prior_cp), 1)
        score_recip = sum(
            ((cp, node) in score_pairs) or ((cp, node) in hist_pairs)
            for cp in score_cp
        ) / max(len(score_cp), 1)
        reciprocity.append(score_recip - prior_recip)
        daily = score_daily.get(node)
        burst.append(float(daily.max() / max(daily.mean(), 1e-9)) if daily is not None and len(daily) else 0.0)
    out["counterparty_novelty"] = novelty
    out["counterparty_growth"] = growth
    out["reciprocity_change"] = reciprocity
    out["score_burstiness"] = burst
    out["log_hist_events"] = np.log1p(out.hist_events)
    out["log_hist_counterparties"] = np.log1p(out.hist_counterparties)
    out["log_score_events"] = np.log1p(out.score_events)
    out["activity_change"] = out.score_events / SCORE_DAYS - out.prior_events / (LOOKBACK - SCORE_DAYS)
    out["active_day_change"] = out.score_active_days / SCORE_DAYS - out.prior_active_days / (LOOKBACK - SCORE_DAYS)

    # These three fixed baselines are part of OW-009's executable feature frame
    # even though structure_residual is the registered primary method.  Keep them
    # in the coverage audit so "every OW-009 feature" is reported faithfully.
    out["volume_activity"] = np.mean(
        np.column_stack([
            pct(out.log_hist_events),
            pct(out.hist_active_days),
            pct(out.log_hist_counterparties),
        ]),
        axis=1,
    )
    out["fine_temporal_activity"] = np.mean(
        np.column_stack([
            pct(out.log_score_events),
            pct(out.score_active_days),
            pct(out.log_hist_counterparties),
        ]),
        axis=1,
    )
    out["simple_temporal"] = np.mean(
        np.column_stack([robust_z(out.activity_change), robust_z(out.active_day_change)]),
        axis=1,
    )
    raw_z = np.column_stack([robust_z(out[c]) for c in STRUCTURE_FEATURES])
    out["raw_structure"] = np.mean(np.abs(raw_z), axis=1)
    x = np.column_stack([np.ones(len(out))] + [robust_z(out[c]) for c in BASE_FEATURES])
    residuals = []
    for col in STRUCTURE_FEATURES:
        y = np.asarray(out[col], dtype=float)
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        residuals.append(robust_z(y - x @ coef))
    out[METHOD] = np.mean(np.abs(np.column_stack(residuals)), axis=1)
    out.index.name = "node"
    result = out.reset_index()
    result.attrs["missing_before_zero_fill"] = missing_before_zero_fill
    return result


def exactish_matches(features: pd.DataFrame, method: str) -> dict:
    ordered = features.sort_values([method, "node"], ascending=[False, True])
    top_n = max(1, int(math.ceil(TOP_FRACTION * len(ordered))))
    treated = ordered.head(top_n).node.astype(int).tolist()
    all_nodes = features.node.astype(int).tolist()
    controls = [n for n in all_nodes if n not in set(treated)]
    matrix = features.set_index("node")[MATCH_FEATURES].astype(float)
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0, ddof=0).replace(0.0, 1.0)
    scaled = (matrix - means) / stds
    tmat = scaled.loc[treated].to_numpy()
    cmat = scaled.loc[controls].to_numpy()
    distances = ((tmat[:, None, :] - cmat[None, :, :]) ** 2).sum(axis=2)
    matches: dict[int, list[int]] = {}
    used = set()
    fallback_reuse = 0
    for i, node in enumerate(treated):
        # Reproduce the OW-009 implementation: NearestNeighbors is asked for
        # only MATCH_K neighbors, not a full control ordering.  When earlier
        # treated wallets consume those neighbors, the fallback reuses within
        # this same K-neighbor list.
        order = np.argsort(distances[i], kind="stable")[: min(MATCH_K, len(controls))]
        chosen = []
        for idx in order:
            c = int(controls[int(idx)])
            if c not in used:
                chosen.append(c)
                used.add(c)
            if len(chosen) == MATCH_K:
                break
        if len(chosen) < MATCH_K:
            for idx in order:
                c = int(controls[int(idx)])
                if c not in chosen:
                    if c in used:
                        fallback_reuse += 1
                    chosen.append(c)
                if len(chosen) == MATCH_K:
                    break
        matches[int(node)] = chosen

    def smd(control_nodes: list[int]) -> dict[str, float]:
        vals = {}
        for col in MATCH_FEATURES:
            denom = float(matrix[col].std(ddof=0))
            treated_mean = float(matrix.loc[treated, col].mean())
            control_mean = float(matrix.loc[control_nodes, col].mean()) if control_nodes else float("nan")
            vals[col] = abs(treated_mean - control_mean) / max(denom, 1e-9)
        return vals

    before = smd(controls)
    matched_assignments = [c for cs in matches.values() for c in cs]
    after = smd(matched_assignments)
    counts = pd.Series(matched_assignments).value_counts() if matched_assignments else pd.Series(dtype=int)
    unique_controls = int(len(set(matched_assignments)))
    reused_assignments = int(sum(max(int(v) - 1, 0) for v in counts))
    return {
        "top_n": top_n,
        "treated": treated,
        "matches": matches,
        "candidate_count": len(features),
        "treated_entering": len(treated),
        "treated_matched": int(sum(bool(x) and len(x) == MATCH_K for x in matches.values())),
        "unmatched": int(sum(len(x) < MATCH_K for x in matches.values())),
        "unique_controls": unique_controls,
        "control_assignments": len(matched_assignments),
        "reused_assignments": reused_assignments,
        "fallback_reuse": fallback_reuse,
        "reuse_rate": reused_assignments / len(matched_assignments) if matched_assignments else np.nan,
        "before_smd": before,
        "after_smd": after,
        "before_max_smd": max(before.values()) if before else np.nan,
        "after_max_smd": max(after.values()) if after else np.nan,
        "failed_covariates_before": [c for c, v in before.items() if v > 0.10],
        "failed_covariates_after": [c for c, v in after.items() if v > 0.10],
    }


def row_stage(stage: str, before: int, after: int, total: int, condition: str, location: str, rationale: str, **extra) -> dict:
    return {
        "stage": stage,
        "wallets_before": int(before),
        "wallets_after": int(after),
        "n_removed": int(before - after),
        "percent_removed": round(100 * (before - after) / before, 4) if before else np.nan,
        "cumulative_percent_remaining": round(100 * after / total, 4) if total else np.nan,
        "exact_filter_condition": condition,
        "code_location": location,
        "scientific_rationale": rationale,
        **extra,
    }


def attrition(mapped_nodes: set[int], raw: pd.DataFrame, outgoing: pd.DataFrame, cutoff: pd.Timestamp, min_events: int, variant: str, match: dict) -> list[dict]:
    total = len(mapped_nodes)
    pre = raw[raw.day_dt < cutoff]
    hist_any = raw[(raw.day_dt >= cutoff - pd.Timedelta(days=LOOKBACK)) & (raw.day_dt < cutoff)]
    hist = outgoing[(outgoing.day_dt >= cutoff - pd.Timedelta(days=LOOKBACK)) & (outgoing.day_dt < cutoff)]
    score = hist[hist.day_dt >= cutoff - pd.Timedelta(days=SCORE_DAYS)]
    pre_nodes = set(pre.u.astype(int)) | set(pre.v.astype(int))
    hist_any_nodes = set(hist_any.u.astype(int)) | set(hist_any.v.astype(int))
    hist_agg = agg(hist)
    history_nodes = set(hist_agg.index.astype(int))
    active_nodes = set(hist_agg[hist_agg.active_days >= MIN_ACTIVE].index.astype(int))
    strict_nodes = set(hist_agg[(hist_agg.active_days >= MIN_ACTIVE) & (hist_agg.events >= min_events)].index.astype(int))
    score_agg = agg(score).reindex(sorted(strict_nodes)).fillna(0.0)
    score_active = set(score_agg[score_agg.active_days > 0].index.astype(int))
    score_event = set(score_agg[score_agg.events > 0].index.astype(int))
    top_n = match["top_n"]
    matched = match["treated_matched"]
    unique_controls = match["unique_controls"]
    rows = []
    rows.append(row_stage("all_mapped_wallets", total, total, total, "released twitter_matching.csv unique node_id", "vendor/EX-Graph-repo/twitter_matching.csv:1-27614", "Universe of mapped EX-Graph wallets; no temporal activity condition.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("source_artifact_observed_before_cutoff_any_role", total, len(pre_nodes), total, "u OR v appears in local edges_day artifact with day < t", "research/community_temporal/sql/edges_asof_day.sql:13-28", "Diagnostic of upstream local substrate coverage; SQL already requires primary, counterparty-present, non-self, both endpoints mapped.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("30d_history_visible_any_role", len(pre_nodes), len(hist_any_nodes), total, "u OR v appears in [t-30d,t)", "research/openworld/baselines/temporal_structure_residual.py:123-127; research/community_temporal/sql/edges_asof_day.sql:21-28", "The intended 30-day as-of history window, before the code's outgoing-only canonicalization.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("30d_history_outgoing_source_wallet", len(hist_any_nodes), len(history_nodes), total, "direction == outgoing; wallet is u; [t-30d,t)", "research/openworld/baselines/temporal_structure_residual.py:540-550", "Code drops incoming-role rows and therefore wallets with no outgoing role in the local representation.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("history_active_days_ge_3", len(history_nodes), len(active_nodes), total, "hist_active_days >= 3", "research/openworld/baselines/temporal_structure_residual.py:129-137", "Stability requirement chosen for the pilot; not required to compute a score for a wallet with one event.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage(f"history_events_ge_{min_events}", len(active_nodes), len(strict_nodes), total, f"hist_events >= {min_events}", "research/openworld/baselines/temporal_structure_residual.py:134-137; constants:34-36", "Pilot eligibility threshold; changes the discovery population and is not needed by the algebraic feature code.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("score_window_activity_diagnostic_no_filter", len(strict_nodes), len(strict_nodes), total, "No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0", "research/openworld/baselines/temporal_structure_residual.py:141-150", "The scoring window is used to form features; zero-filled score features are allowed, so this stage does not filter discovery wallets.", cutoff=cutoff.date().isoformat(), variant=variant, diagnostic_score_events_gt0=len(score_event), diagnostic_score_active_days_gt0=len(score_active)))
    rows.append(row_stage("feature_complete_after_fillna", len(strict_nodes), len(strict_nodes), total, "left joins then fillna(0.0)", "research/openworld/baselines/temporal_structure_residual.py:151-157", "All candidate rows receive numeric values; missing prior/score activity becomes structural zero rather than exclusion.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("structural_feature_complete", len(strict_nodes), len(strict_nodes), total, "fixed-length novelty/growth/reciprocity/burst arrays; no null filter", "research/openworld/baselines/temporal_structure_residual.py:159-202", "Structural features are always assigned, including zeros for no score-window rows.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("top5_percent_anomaly_cohort", len(strict_nodes), top_n, total, "ceil(0.05 * candidate_count), rank by fixed structure_residual", "research/openworld/baselines/temporal_structure_residual.py:383-385", "Evaluation budget/selection stage, not discovery eligibility.", cutoff=cutoff.date().isoformat(), variant=variant))
    rows.append(row_stage("matched_treated_cohort", top_n, matched, total, "1:5 nearest-neighbor matching; treated retained if 5 controls assigned", "research/openworld/baselines/temporal_structure_residual.py:300-353", "Matched-analysis cohort; must not be relabeled as the discovery population.", cutoff=cutoff.date().isoformat(), variant=variant, unique_controls=unique_controls))
    rows.append(row_stage("unique_matched_controls", match["control_assignments"], unique_controls, total, "unique control node IDs among 5 assignments per treated", "research/openworld/baselines/temporal_structure_residual.py:300-353", "Control support for the matched evaluation only; controls are not anomalous-wallet candidates.", cutoff=cutoff.date().isoformat(), variant=variant))
    return rows


def filter_registry() -> pd.DataFrame:
    rows = [
        ("source_date_window", "block_timestamp >= 2022-03-03 AND < 2022-09-01", "SCIENTIFIC_DESIGN", "community_temporal/sql/edges_asof_day.sql:21-22", "Bounds dev data and provides complete local windows for June-August; it omits Mar 1-2 but not the OW-009 30d histories.", "upstream source"),
        ("source_sequence_role", "sequence_role = 'primary'", "SCIENTIFIC_DESIGN", "community_temporal/sql/edges_asof_day.sql:23", "Excludes auxiliary internal traces; valid if the study is explicitly primary-event-only, but excludes part of the available behavioral substrate.", "upstream source"),
        ("source_counterparty_present", "counterparty_present", "SCIENTIFIC_DESIGN", "community_temporal/sql/edges_asof_day.sql:24", "Needed for counterparty graph features; excludes events with no destination and narrows activity population.", "upstream source"),
        ("source_non_self", "NOT self_transaction", "SCIENTIFIC_DESIGN", "community_temporal/sql/edges_asof_day.sql:25", "Removes self loops from counterparty-oriented graph statistics; should be a feature-stratified sensitivity, not silently universal.", "upstream source"),
        ("source_both_endpoints_mapped", "target_exgraph_node_id IS NOT NULL AND counterparty_exgraph_node_id IS NOT NULL", "POSSIBLY_OVERRESTRICTIVE", "community_temporal/sql/edges_asof_day.sql:26-27", "The task universe has 27,613 mapped wallets, but this keeps only events whose other endpoint is also mapped; it is not essential for wallet-level activity or unmapped-counterparty novelty.", "upstream source"),
        ("source_day_aggregation", "GROUP BY u,v,direction,month,day; COUNT(*) AS weight", "IMPLEMENTATION_CONVENIENCE", "community_temporal/sql/edges_asof_day.sql:13-19,28", "Compact egress introduced because the local artifact retained only aggregate rows; it destroys within-day timestamp, event-family, amount, token, trace, and transaction identity needed by several proposed features.", "upstream representation"),
        ("local_aggregate_dependency", "OW-009 reads edges_day CSV instead of event-level source tables", "LEGACY", "openworld/baselines/temporal_structure_residual.py:525-551; community_temporal/src/pull_edges.py:14-25", "An operationally convenient legacy dependency narrows the scientific population before OW-009 runs; it must be replaced by an as-of compact feature table, not treated as a detector result.", "upstream representation"),
        ("code_outgoing_only", "frame.direction.lower() == 'outgoing'", "BUG_RISK", "temporal_structure_residual.py:540-542", "The code uses role rows as a canonical directed edge, but this changes the wallet population from any observable endpoint to outgoing-source wallets; an incoming-only wallet cannot enter discovery.", "OW-009 code"),
        ("history_lookback", "day_dt in [t-30d,t)", "SCIENTIFIC_DESIGN", "temporal_structure_residual.py:123-127", "Correct as-of observation window for the frozen pilot; shorter than the existing 90d substrate and should be a declared sensitivity.", "OW-009 code"),
        ("history_active_days", "hist_active_days >= 3", "POSSIBLY_OVERRESTRICTIVE", "temporal_structure_residual.py:134-137", "Stability heuristic; not required to compute fixed statistics and removes low-frequency wallets from the discovery population.", "OW-009 code"),
        ("history_event_count", "hist_events >= 10 (strict) or >=3 (diagnostic)", "POSSIBLY_OVERRESTRICTIVE", "temporal_structure_residual.py:34-36,134-137", "Pilot threshold selected before the result but still a population restriction; sensitivity shows the substrate can support many more wallets.", "OW-009 code"),
        ("score_activity_filter", "none", "ESSENTIAL", "temporal_structure_residual.py:141-150", "No score-window activity is required; retaining this is correct for discovery and avoids future-conditioned or score-conditioned selection.", "OW-009 code"),
        ("feature_fillna", "left join prior/score aggregates then fillna(0)", "IMPLEMENTATION_CONVENIENCE", "temporal_structure_residual.py:151-157", "Avoids null feature rows, but conflates no observed activity with structural zero and hides feature-coverage diagnostics.", "OW-009 code"),
        ("structural_feature_null_filter", "none", "ESSENTIAL", "temporal_structure_residual.py:159-202", "No extra eligibility filter is applied; adding one would change the discovery population.", "OW-009 code"),
        ("top5_selection", "ceil(0.05 * N), fixed rank", "SCIENTIFIC_DESIGN", "temporal_structure_residual.py:383-385", "Defines an evaluation budget; it is not a candidate-eligibility filter.", "evaluation"),
        ("control_pool_exclusion", "controls = all candidates not in treated top5", "SCIENTIFIC_DESIGN", "temporal_structure_residual.py:300-318", "Prevents treated wallets from serving as controls; required for a clean diagnostic comparison.", "matching"),
        ("match_k", "5 nearest controls per treated", "SCIENTIFIC_DESIGN", "temporal_structure_residual.py:33,316-341", "Pre-registered 1:5 comparison design; affects uncertainty but not discovery eligibility.", "matching"),
        ("match_balance_caliper", "none; SMD is only reported after matching", "BUG_RISK", "temporal_structure_residual.py:300-353", "The procedure cannot reject imbalanced matches or enforce |SMD|<=0.10; balance failure is diagnosed after the fact.", "matching"),
        ("future_outcome_eligibility", "none; outcomes are generated for every discovery node before method evaluation but are not used for ranking/matching; absent events become zeros", "ESSENTIAL", "temporal_structure_residual.py:266-297,375-449,560-562", "No future-conditioned discovery filter is present. This separation must be preserved in a repaired implementation.", "evaluation"),
    ]
    return pd.DataFrame(rows, columns=["filter", "exact_condition", "classification", "code_or_query_location", "rationale", "layer"])


def feature_coverage(features_by_cutoff: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    source = "local edges_day_20220303_20220901.csv (from target_event_sequences via edges_asof_day.sql)"
    specs = [
        ("hist_events", "[t-30d,t)", "no", "no", "count of day-level edge weights"),
        ("hist_active_days", "[t-30d,t)", "no", "no", "distinct day_dt"),
        ("hist_counterparties", "[t-30d,t)", "no", "no", "distinct v among outgoing canonical rows"),
        ("prior_events", "[t-30d,t-7d)", "no", "no", "left-joined then zero-filled"),
        ("prior_active_days", "[t-30d,t-7d)", "no", "no", "left-joined then zero-filled"),
        ("prior_counterparties", "[t-30d,t-7d)", "no", "no", "left-joined then zero-filled"),
        ("score_events", "[t-7d,t)", "no", "no", "left-joined then zero-filled"),
        ("score_active_days", "[t-7d,t)", "no", "no", "left-joined then zero-filled"),
        ("score_counterparties", "[t-7d,t)", "no", "no", "left-joined then zero-filled"),
        ("counterparty_novelty", "prior vs [t-7d,t)", "no", "no", "set difference of day-level counterparties"),
        ("counterparty_growth", "prior vs [t-7d,t)", "no", "no", "log score CP minus scaled prior CP"),
        ("reciprocity_change", "prior vs [t-7d,t)", "no", "no", "reverse directed pair test; no event-family semantics"),
        ("score_burstiness", "[t-7d,t)", "no (day-level only)", "no", "max daily weight / mean active-day weight; no sub-day gaps"),
        ("activity_change", "prior vs [t-7d,t)", "no", "no", "event-rate difference"),
        ("active_day_change", "prior vs [t-7d,t)", "no", "no", "active-day-rate difference"),
        ("volume_activity", "[t-30d,t) plus score", "no", "no", "rank baseline derived from as-of features"),
        ("fine_temporal_activity", "[t-30d,t)", "no", "no", "rank baseline derived from as-of features"),
        ("simple_temporal", "[t-30d,t)", "no", "no", "fixed change-point composite"),
        ("raw_structure", "[t-30d,t)", "no", "no", "derived four-signal composite"),
        ("structure_residual", "[t-30d,t)", "no", "no", "residualized four-signal composite"),
        ("event_timestamp", "not present in local artifact", "yes", "no", "collapsed to calendar day"),
        ("event_family", "not present in local artifact", "yes", "no", "external/token/internal distinction lost"),
        ("native_value", "not present in local artifact", "yes", "no", "amount semantics lost"),
        ("token_contract_or_id", "not present in local artifact", "yes", "no", "asset identity lost"),
        ("internal_trace_identity", "not present in local artifact", "yes", "no", "trace path/subtrace semantics lost"),
        ("inter_event_gap", "not present in local artifact", "yes", "no", "requires timestamped event sequence"),
        ("rapid_forwarding", "not present in local artifact", "yes", "no", "requires timestamped directed events"),
        ("event_composition", "not present in local artifact", "yes", "no", "native/token/internal ratios unavailable"),
    ]
    for cutoff, feat in features_by_cutoff.items():
        n = len(feat)
        for name, window, raw_required, future_required, note in specs:
            prefill = feat.attrs.get("missing_before_zero_fill", {})
            if name in prefill:
                missing = int(prefill[name])
                coverage = n  # fillna(0) supplies a numeric feature to every candidate
                fill_note = "left-join missingness before fillna(0)"
            elif name in feat.columns:
                missing = int(feat[name].isna().sum())
                coverage = n - missing
                fill_note = "computed"
            else:
                missing = n
                coverage = 0
                fill_note = "not available"
            rows.append({
                "cutoff": cutoff,
                "feature": name,
                "source_table_or_artifact": source if name in feat.columns else "not materialized; requires BigQuery event-level feature CTAS",
                "time_window_relative_to_cutoff": window,
                "missing_count_before_zero_fill": missing,
                "missing_rate_before_zero_fill": missing / n if n else np.nan,
                "wallet_coverage_after_current_code": coverage / n if n else 0.0,
                "requires_raw_event_level_data": raw_required,
                "requires_future_data": future_required,
                "implementation_note": f"{note}; discovery cohort n={n}",
            })
    return pd.DataFrame(rows)


def sensitivity(mapped_nodes: set[int], raw: pd.DataFrame, outgoing: pd.DataFrame, asof: pd.DataFrame) -> pd.DataFrame:
    rows = []
    event_thresholds = [1, 3, 5, 10, 20]
    active_thresholds = [1, 3]
    score_event_thresholds = [0, 1, 3, 5, 10]
    score_active_thresholds = [0, 1, 2, 3]
    for cutoff in CUTOFFS:
        hist = outgoing[(outgoing.day_dt >= cutoff - pd.Timedelta(days=LOOKBACK)) & (outgoing.day_dt < cutoff)]
        score = hist[hist.day_dt >= cutoff - pd.Timedelta(days=SCORE_DAYS)]
        h = agg(hist)
        s = agg(score)
        for amin in active_thresholds:
            for emin in event_thresholds:
                base = h[(h.active_days >= amin) & (h.events >= emin)]
                for semin in score_event_thresholds:
                    for samin in score_active_thresholds:
                        ss = s.reindex(base.index).fillna(0.0)
                        selected = ss[(ss.events >= semin) & (ss.active_days >= samin)]
                        n = len(selected)
                        rows.append({
                            "layer": "ow009_local_day_matched_mapped_outgoing",
                            "cutoff": cutoff.date().isoformat(),
                            "history_days": LOOKBACK,
                            "history_min_active_days": amin,
                            "history_min_events": emin,
                            "score_min_active_days": samin,
                            "score_min_events": semin,
                            "n_wallets": n,
                            "top5_n": int(math.ceil(TOP_FRACTION * n)),
                            "future_conditioned": "no",
                            "source_note": "diagnostic only; current code applies only history active>=3 and events>=3/10; no score filter",
                        })
        # Existing 90-day all-primary as-of compact table, discovery columns only.
        x = asof[asof.snapshot_date == cutoff]
        for amin in active_thresholds:
            for emin in event_thresholds:
                n = int(((x.active_days_90d >= amin) & (x.evt_cnt_90d >= emin)).sum())
                rows.append({
                    "layer": "existing_wallet_asof_features_v1_all_primary_90d",
                    "cutoff": cutoff.date().isoformat(),
                    "history_days": 90,
                    "history_min_active_days": amin,
                    "history_min_events": emin,
                    "score_min_active_days": np.nan,
                    "score_min_events": np.nan,
                    "n_wallets": n,
                    "top5_n": int(math.ceil(TOP_FRACTION * n)),
                    "future_conditioned": "no",
                    "source_note": "compact as-of table; no future label columns were read by this audit",
                })
    return pd.DataFrame(rows)


def matching_rows(features_by_cutoff: dict[tuple[str, str], pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for (variant, cutoff), features in features_by_cutoff.items():
        m = exactish_matches(features, METHOD)
        r = {
            "variant": variant,
            "cutoff": cutoff,
            "method": METHOD,
            "candidate_count": m["candidate_count"],
            "treated_entering": m["treated_entering"],
            "treated_successfully_matched": m["treated_matched"],
            "treated_unmatched": m["unmatched"],
            "unique_controls": m["unique_controls"],
            "control_assignments": m["control_assignments"],
            "reused_control_assignments": m["reused_assignments"],
            "reuse_rate": m["reuse_rate"],
            "fallback_reuse_count": m["fallback_reuse"],
            "before_max_smd": m["before_max_smd"],
            "after_max_smd": m["after_max_smd"],
            "before_failed_covariates": ";".join(m["failed_covariates_before"]),
            "after_failed_covariates": ";".join(m["failed_covariates_after"]),
            "matching_constraint_causing_failure": "no hard failure; post-match balance fails where after SMD > 0.10",
        }
        for c, v in m["before_smd"].items():
            r[f"before_smd__{c}"] = v
        for c, v in m["after_smd"].items():
            r[f"after_smd__{c}"] = v
        rows.append(r)
    return pd.DataFrame(rows)


def write_feature_spec() -> None:
    text = f"""# BigQuery feature materialization specification (substrate repair)

**Status:** specification only; no expensive CTAS was run by this audit.

## Goal and grain

Create a compact, leakage-safe table with one row per
`(target_exgraph_node_id, cutoff_time)` for cutoffs
`2022-06-01`, `2022-07-01`, and `2022-08-01`.  The discovery table must be
constructed only from events with `block_timestamp < cutoff_time`.  Keep all
27,613 mapped wallets as the outer dimension and add coverage/count columns;
do not make the wallet eligible only when a counterparty is also EX-Graph
mapped.

Recommended objects:

```text
ictdata-507912.exgraph.openworld_wallet_features_v2
ictdata-507912.exgraph.openworld_future_outcomes_v2  -- evaluation_only
```

Do not export raw transactions.  Build the event-normalization and aggregation
CTAS jobs in BigQuery, partition by event date/cutoff and cluster by
`target_exgraph_node_id, cutoff_time`.

## Event normalization

Read the already materialized source-specific tables, not the public tables
again:

```text
external_transactions_20220301_20220901
token_transfers_20220301_20220901
internal_traces_20220301_20220901
```

For each source retain only the columns needed for aggregation:

```text
event_family, block_timestamp, block_number, transaction_index,
transaction_hash, event_index/trace identity, from_address, to_address,
from_exgraph_node_id, to_exgraph_node_id, value/value_lossless,
quantity, token_contract_address, token_id, trace_type/call_type
```

Use a family-specific event key.  A native transaction key is
`(event_family, transaction_hash)`, a token key is
`(event_family, transaction_hash, event_index)`, and an internal-trace key
must include the trace identity/path.  Do not deduplicate different families
merely because `transaction_hash` is equal.  Preserve both wallet roles:
`from_wallet` contributes an outgoing event and `to_wallet` contributes an
incoming event.  An unmapped counterparty remains a valid counterparty token
for wallet-level counts; mapped-node network features get a separate coverage
flag.

## Exact as-of intervals

For cutoff `t`, every discovery feature uses one of these half-open intervals:

| family | interval | purpose |
|---|---|---|
| `w_1h` | `[t-1h,t)` | very short burst/activity |
| `w_6h` | `[t-6h,t)` | intraday activity |
| `w_1d` | `[t-1d,t)` | daily burst and event composition |
| `w_7d` | `[t-7d,t)` | score/novelty/rapid-forward |
| `w_30d` | `[t-30d,t)` | primary history and graph state |
| `w_30d_prior` | `[t-30d,t-7d)` | baseline for 7-day change |

All joins use `block_timestamp < t` on the feature side.  The feature CTAS
must retain `coverage_event_count` and `coverage_last_timestamp` so that zero
activity is distinguishable from missing extraction.

## Feature columns

### Activity

```text
tx_count_1h, tx_count_6h, tx_count_1d, tx_count_7d, tx_count_30d
active_days_30d, active_hours_1d, first_event_age_30d, last_event_recency
inter_event_mean/median/std/max_gap_30d
burstiness_1d, burstiness_7d, burstiness_30d
```

Use event-key counts for `tx_count` and event-row counts separately.  Inter-event
statistics require the event timestamp and are not recoverable from OW-009's
day-level CSV.

### Flow and amount

```text
native_in/out/count/sum/median/max_30d
token_in/out/count/quantity_sum_30d
net_native_flow_30d, inflow_outflow_ratio_30d
flow_conservation_ratio_7d/30d
```

Keep native values and token quantities separate; never add their raw numeric
scales.  USD conversion, if later added, must use an as-of price join and a
separate coverage flag.

### Counterparty

```text
unique_counterparties_1d/7d/30d
new_counterparties_7d_vs_prior23d
new_counterparty_rate_7d_vs_prior23d
repeat_counterparty_rate_7d/30d
counterparty_entropy_7d/30d
counterparty_growth_7d_vs_prior23d
```

The novelty set is `CP([t-7d,t)) - CP([t-30d,t-7d))`.  The denominator and
zero-activity convention must be fixed before scoring.

### Temporal structure

```text
reciprocal_counterparties_7d/30d
reciprocity_rate_7d/30d
rapid_forward_count_1d/7d
fan_in_max_1d/7d, fan_out_max_1d/7d
cycle2_proxy_7d/30d
split_merge_count_7d/30d
```

Define rapid forwarding using timestamped directed events and a fixed interval
(e.g. a source wallet receives an event and sends an outgoing event within
`[0,24h]`; the exact event-pair semantics must be frozen before execution).
Define fan-in/out and split/merge on fixed calendar-day and transaction-event
windows.  These cannot be reconstructed from day-level `weight` alone.

### Event composition

```text
native_event_ratio_7d/30d
token_event_ratio_7d/30d
internal_trace_event_ratio_7d/30d
token_contract_count_7d/30d
token_id_count_7d/30d
```

These require the source event family and token/trace identity.  Internal
traces remain part of discovery coverage even if a later label protocol excludes
them from future-counterparty labels.

### Network (mapped-counterparty subset only)

```text
temporal_in_degree_30d, temporal_out_degree_30d
weighted_temporal_degree_30d
local_density_30d, bridge_proxy_30d
mapped_counterparty_fraction_30d
```

Build these from a cutoff-specific graph over `[t-30d,t)`.  Do not use the full
static `ethereum_graph.gpickle` or future cumulative degree.  Network columns
must be nullable with explicit coverage flags so they do not define the wallet
population.

## Separate future outcomes

Create `openworld_future_outcomes_v2` only after the feature table is frozen.
For each `(wallet, t)` use:

```text
future_7d:  [t,t+7d)
future_30d: [t,t+30d)
```

Store `future_active_days`, `future_events`, `future_new_counterparties`,
`future_reciprocity`, and any open-world outcome flags here.  This table is
`evaluation_only`; it must never be used for discovery eligibility, feature
normalization, threshold selection, matching, or model selection.

## Cost and audit guard

1. Dry-run every CTAS with a bounded `maximumBytesBilled`.
2. Materialize/filter in BigQuery and return only the wallet×cutoff table plus
   compact coverage summaries.
3. Record source table versions, SQL hashes, row counts, bytes processed/billed,
   and the exact cutoff/window predicates.
4. Validate metadata and run a bounded `COUNT(*)`/`GROUP BY cutoff_time` query
   before accepting the table.
"""
    (OUT / "BIGQUERY_FEATURE_SPEC.md").write_text(text)


def write_repair_plan(attr: pd.DataFrame, sens: pd.DataFrame, match: pd.DataFrame) -> None:
    strict = attr[attr.variant == "registered_strict_10_events"]
    full90 = sens[sens.layer == "existing_wallet_asof_features_v1_all_primary_90d"]
    local = sens[sens.layer == "ow009_local_day_matched_mapped_outgoing"]
    primary = match[match.variant == "registered_strict_10_events"]
    text = f"""# OW-009 substrate repair plan

## Diagnosis

OW-009 is not a valid test of the intended full wallet×cutoff discovery
population.  The local input is a day-level, matched-matched, primary-only
projection of the 11,836,196-row sequence substrate.  It contains 13,020 unique
mapped endpoint nodes across the whole extract, and the OW-009 code then keeps
only `direction=outgoing` rows.  The strict 30-day cohort is only
370/282/359 at the three cutoffs.

The same project's existing compact all-primary 90-day as-of table contains
roughly 19--20k wallets per cutoff and, with `active_days>=3` and
`events>=10`, contains 16,326 / 15,554 / 14,557 wallets at June/July/August.
This is evidence that the current failure is primarily substrate/cohort
construction, not evidence that the structural hypothesis works.

## Required changes before a rerun

1. **Materialize the compact event-level/as-of table in BigQuery.** Use
   `BIGQUERY_FEATURE_SPEC.md`; preserve incoming and outgoing roles, all three
   event families, event timestamps, amounts, token identity, and unmapped
   counterparties for wallet-level counts.
2. **Keep discovery eligibility separate from evaluation.** Outer-join all mapped
   wallets to pre-cutoff feature rows. A wallet with no future event remains in
   discovery and receives a missing/zero outcome only in the evaluation table.
3. **Remove the silent outgoing-only population change.** Canonicalize events by
   source/destination for edge features, but compute wallet-level features from
   both roles. If source-only analysis is desired, register it as a separate
   estimand.
4. **Do not use `both endpoints mapped` as a discovery requirement.** Retain an
   unmapped counterparty token for activity/novelty. Restrict only network columns
   to mapped-counterparty coverage and report that coverage separately.
5. **Keep `active_days>=3` and `events>=10` as preregistered sensitivity strata,
   not as an implicit definition of all observable wallets.** Do not choose a
   new threshold by future or label results.
6. **Freeze matching diagnostics before any outcome analysis.** Report before and
   after SMD by covariate. The current procedure has no caliper and can report a
   match as successful even when post-match SMD exceeds 0.10; do not claim a
   matched comparison until the protocol specifies how imbalance is handled.
7. **Run substrate-only QA first.** Check row counts, wallet counts, event-family
   coverage, interval coverage, and as-of leakage. Do not run an anomaly ranking
   or external-label evaluation in the repair step.

## Restart gate (not a threshold amendment)

A later rerun should require, before detector results are inspected:

- at least 2,000 discovery wallets per cutoff under the declared population;
- at least 100 Top-5% wallets per cutoff if Top-5% remains the analysis budget;
- all matching covariates reported with absolute SMD <= 0.10 for the declared
  matched estimand, or a pre-registered alternative estimand;
- complete feature-side windows and a separate, explicit future-evaluation table;
- no use of wash labels or future outcomes for cohort selection.

## Interpretation

The present OW-009 result should be frozen as **SUBSTRATE_UNDERPOWERED /
DESIGN_REVISION_NEEDED**.  It is not a method-level NO-GO because the intended
wallet×cutoff population was never represented by the local input.  It is not
READY_FOR_RERUN until the event-level/as-of materialization and discovery-vs-
evaluation separation are implemented.

The `>=2,000` requirement is retained for now as a conservative, operational
restart gate.  The evidence below supports a later amendment discussion, not a
silent change:

- with 2,000 candidates and a 5% top cohort, treated n≈100;
- at outcome rate p=0.10, a single treated proportion has an approximate 95%
  margin of ±5.9 percentage points; a 1:5 treated-control difference has a
  rough 95% margin of ±6.4 percentage points under independent-binomial
  approximation;
- at p=0.50, the corresponding difference margin is about ±10.9 points;
- the ratio metric is unstable when the control rate is near zero, so future
  reports should include absolute rates and risk differences.

These are planning approximations, not a powered superiority claim.
"""
    (OUT / "SUBSTRATE_REPAIR_PLAN.md").write_text(text)


def write_report(mapped_nodes: set[int], raw: pd.DataFrame, outgoing: pd.DataFrame, asof: pd.DataFrame, bq_evidence: dict | None, attr: pd.DataFrame, filt: pd.DataFrame, featcov: pd.DataFrame, match: pd.DataFrame, sens: pd.DataFrame) -> None:
    strict = attr[attr.variant == "registered_strict_10_events"].copy()
    primary_match = match[match.variant == "registered_strict_10_events"]
    local = sens[(sens.layer == "ow009_local_day_matched_mapped_outgoing") & (sens.history_min_active_days == 3) & (sens.score_min_active_days == 0) & (sens.score_min_events == 0)]
    full90 = sens[(sens.layer == "existing_wallet_asof_features_v1_all_primary_90d") & (sens.history_min_active_days == 3)]
    # Largest stage drops for strict rows, by raw number removed.
    largest = strict.sort_values("n_removed", ascending=False).head(8)[["cutoff", "stage", "n_removed", "exact_filter_condition"]]
    lines = []
    lines.append("# OW-009 candidate attrition and substrate diagnosis")
    lines.append("")
    lines.append("**Audit date:** 2026-09-18  \n**Label status:** blind to EX-Graph wash-trading labels; no label file/table was read.  \n**Detector status:** no detector, threshold, matching rule, or latent-strategy track was optimized.")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append("OW-009 did not test the intended full `(wallet, cutoff_time)` population. Its local input is a day-level projection that already requires primary events, a present counterparty, non-self transactions, and both endpoints EX-Graph-mapped. The code then keeps only `direction=outgoing`, and only after that applies `active_days>=3` and `events>=10` in a 30-day window. This explains the 370/282/359 strict counts.")
    lines.append("")
    lines.append("The largest single upstream stage is local-artifact observability before cutoff, which removes 16,243/15,518/15,002 wallets at June/July/August. The largest explicit OW-009 predicate drop is `hist_active_days>=3` (3,344/2,663/2,454); `hist_events>=10` is next. The existing all-primary 90-day compact table shows 16,326/15,554/14,557 wallets at `active_days>=3 AND events>=10`, so the project has enough substrate for a later rerun if the compact event/as-of table is rebuilt correctly.")
    lines.append("")
    lines.append("**Final status: `DESIGN_REVISION_NEEDED` with current local representation `SUBSTRATE_UNDERPOWERED`.** This is not a method-level NO-GO and not READY_FOR_RERUN.")
    lines.append("")
    lines.append("## 1. Exact OW-009 dependency chain")
    lines.append("")
    lines.append("```text")
    lines.append("11,836,196 sequence rows (BigQuery metadata; not downloaded by OW-009)")
    lines.append("  -> edges_asof_day.sql: primary + counterparty_present + non-self + both endpoints mapped")
    lines.append("  -> 142,300 day-level (u,v,direction,day) aggregate rows in edges_day_20220303_20220901.csv")
    lines.append("  -> temporal_structure_residual.py filters direction=outgoing")
    lines.append("  -> 30-day history [t-30d,t), group by u")
    lines.append("  -> hist_active_days >= 3 AND hist_events >= 10 (strict)")
    lines.append("  -> left-join prior/score aggregates and fillna(0); no score-window eligibility filter")
    lines.append("  -> calculate structural features for every remaining row; no null filter")
    lines.append("  -> materialize future outcome rows for every discovery wallet for evaluation only; outcomes do not feed ranking or matching")
    lines.append("  -> rank fixed structure_residual and select ceil(5% N)")
    lines.append("  -> 1:5 nearest controls from the same candidate pool excluding treated")
    lines.append("  -> report future outcomes for selected treated/control rows; future activity is not required for entry")
    lines.append("```")
    lines.append("")
    lines.append("Source SQL and row-generating code are preserved in the output manifest and the code/query locations in `candidate_attrition_by_cutoff.csv`.")
    lines.append("")
    lines.append("### BigQuery raw-row and unique-wallet cross-check (aggregate-only; no raw export)")
    lines.append("")
    if bq_evidence and bq_evidence.get("queries", {}).get("per_cutoff_pre_cutoff_summary"):
        bq_rows = pd.DataFrame(bq_evidence["queries"]["per_cutoff_pre_cutoff_summary"]["rows"])
        lines.append(bq_rows.pipe(md_table))
        lines.append("")
        lines.append("These counts establish the missing early stages: raw sequence rows and unique endpoint wallets before the local `edges_day` projection. The query read only bounded aggregate counts; it did not export event rows or read external labels. The full-window accepted upstream condition has 266,998 sequence rows and 13,147 unique endpoint nodes, whereas the local day-level file contains 142,300 aggregate rows and 13,020 endpoint nodes because its pull starts on 2022-03-03 and performs daily pair aggregation.")
    else:
        lines.append("Aggregate BigQuery evidence was not available in the local evidence JSON; the metadata row count remains 11,836,196.")
    lines.append("")
    lines.append("## 2. Strict attrition table")
    lines.append("")
    show = strict[["cutoff", "stage", "wallets_before", "wallets_after", "n_removed", "percent_removed", "cumulative_percent_remaining", "exact_filter_condition"]]
    lines.append(show.pipe(md_table))
    lines.append("")
    lines.append("The full machine-readable table, including code locations and scientific rationale, is `candidate_attrition_by_cutoff.csv`.")
    lines.append("")
    lines.append("Largest stage drops in the strict audit:")
    lines.append("")
    lines.append(largest.pipe(md_table))
    lines.append("")
    lines.append("## 3. Filter classification")
    lines.append("")
    counts = filt["classification"].value_counts().rename_axis("classification").reset_index(name="n_filters")
    lines.append(counts.pipe(md_table))
    lines.append("")
    lines.append("The full registry with exact conditions, locations, and rationale is `filter_registry.csv`. The important population-changing filters are the upstream `both endpoints mapped` requirement, the code's `outgoing` role filter, and the 3-day/10-event history thresholds. There is no score-window activity filter and no future-outcome eligibility filter in the executable code.")
    lines.append("")
    lines.append("## 4. Discovery, future evaluation, and matched cohorts")
    lines.append("")
    lines.append("- **Discovery cohort:** the strict rows after `[t-30d,t)`, `direction=outgoing`, `active_days>=3`, and `events>=10`: 370/282/359. In the intended repaired population, this should instead be an outer-joined wallet×cutoff cohort built from all mapped wallets and all pre-cutoff roles.")
    lines.append("- **Future-evaluation cohort:** current `future_outcomes()` is called for every discovery wallet and creates zeros for absent future events; it does not filter discovery. Because the local artifact covers June/July/August 7/30-day future intervals, current evaluation coverage is numerically the full discovery cohort, not a future-active subset.")
    lines.append("- **Matched-analysis cohort:** Top-5% treated wallets for the fixed `structure_residual` method that receive five controls. In the current candidate sizes, the control pool is large enough that all treated wallets receive five assignments; this does not mean balance is acceptable.")
    lines.append("")
    lines.append("## 5. Matching diagnostic")
    lines.append("")
    lines.append(primary_match.pipe(md_table))
    lines.append("")
    strict_match = primary_match[primary_match.variant == "registered_strict_10_events"]
    reuse_lo, reuse_hi = strict_match.reuse_rate.min(), strict_match.reuse_rate.max()
    unique_lo, unique_hi = strict_match.unique_controls.min(), strict_match.unique_controls.max()
    lines.append(f"The current procedure has no caliper and no hard balance rejection. Its nearest-neighbor assignment therefore reports all strict treated wallets as matched even when post-match absolute SMD exceeds 0.10. Across the three strict cutoffs, control reuse is {reuse_lo:.3f}--{reuse_hi:.3f} of assignments and unique controls are {int(unique_lo)}--{int(unique_hi)} for 15--19 treated wallets. The recurrent post-match failures are log_hist_events, log_hist_counterparties, log_score_events, and activity_change; this is a support/balance failure, not a reason to tune the method. See `matching_diagnostics.csv` for covariate-level before/after SMD.")
    lines.append("")
    lines.append("## 6. Feature availability")
    lines.append("")
    key = featcov[(featcov.cutoff == "2022-06-01") & featcov.feature.isin(["counterparty_novelty", "counterparty_growth", "reciprocity_change", "score_burstiness", "event_timestamp", "event_family", "native_value", "token_contract_or_id", "internal_trace_identity", "inter_event_gap", "rapid_forwarding", "event_composition"])]
    lines.append(key[["feature", "time_window_relative_to_cutoff", "missing_rate_before_zero_fill", "requires_raw_event_level_data", "requires_future_data", "implementation_note"]].pipe(md_table))
    lines.append("")
    score_cov = featcov[(featcov.feature == "score_events")][["cutoff", "missing_rate_before_zero_fill", "wallet_coverage_after_current_code"]]
    lines.append("The current code has no score-window eligibility predicate. Before `fillna(0)`, the strict candidates with no score-window event are 29.73%/25.53%/23.68% at June/July/August; they remain in discovery with zero-filled score features. Prior-window absence is 1.08%/1.42%/0.84%. This is not future leakage, but it is an important coverage distinction.")
    lines.append(score_cov.pipe(md_table))
    lines.append("")
    lines.append("The current local representation preserves only day, directed pair, role direction, and count. It loses sub-day ordering, transaction/event identity, event family, native/token amounts, token identity, and trace identity. Consequently it cannot support a faithful rapid-forward, inter-event-gap, event-composition, or amount-aware analysis. The three fixed rank/change baselines (`volume_activity`, `fine_temporal_activity`, `simple_temporal`) are available from the same day-level aggregates; their availability does not restore the missing event semantics.")
    lines.append("")
    lines.append("## 7. Cohort sensitivity")
    lines.append("")
    lines.append("Local 30-day outgoing diagnostic with no score-window filter and history `active_days>=3`:")
    sens_show = local[local.history_min_events.isin([1, 3, 5, 10, 20]) & (local.score_min_events == 0) & (local.score_min_active_days == 0)]
    lines.append(sens_show[["cutoff", "history_min_events", "n_wallets", "top5_n"]].pipe(md_table))
    lines.append("")
    lines.append("Existing all-primary 90-day compact as-of table, same activity/event thresholds:")
    lines.append(full90[["cutoff", "history_min_events", "n_wallets", "top5_n"]].pipe(md_table))
    lines.append("")
    lines.append("The complete score-window sensitivity grid is in `cohort_sensitivity.csv`; it is diagnostic and was not selected by future or label results.")
    lines.append("")
    lines.append("## 8. BigQuery repair specification and restart plan")
    lines.append("")
    lines.append("See `BIGQUERY_FEATURE_SPEC.md` for exact wallet×cutoff grain, half-open intervals, event keys, feature families, and separate evaluation outcomes. See `SUBSTRATE_REPAIR_PLAN.md` for the no-tuning restart sequence.")
    lines.append("")
    lines.append("## 9. Required final answers")
    lines.append("")
    answers = [
        ("1", "Why did ~27,613 become ~370/282/359?", "Because the local input had already narrowed the population to primary, counterparty-present, non-self, both-endpoints-mapped day-level edges; the code then kept outgoing-source wallets, a 30-day history, active_days>=3, and events>=10."),
        ("2", "Which single filter caused largest attrition?", "As a single observed-population stage, source-artifact observability before cutoff is largest: it removes 16,243/15,518/15,002 wallets at June/July/August. Among explicit OW-009 code predicates, active_days>=3 is largest (3,344/2,663/2,454 removed), followed by events>=10."),
        ("3", "Which filters are scientifically necessary?", "Strict as-of cutoff, explicit event identity/deduplication, and declared history windows. Counterparty-present/non-self/primary-only are only necessary for particular estimands, not for all wallet behavioral discovery."),
        ("4", "Which are artifacts or unnecessarily restrictive?", "Both-endpoints-mapped, outgoing-only role filtering, day aggregation for event-level questions, and active_days>=3/events>=10 as universal discovery eligibility."),
        ("5", "Future-conditioned eligibility or leakage risk?", "No future-conditioned entry filter exists in OW-009. `future_outcomes()` is materialized for every discovery wallet before method evaluation, but it is not used for ranking or matching; only selected rows enter the reported treated/control comparison, and absent future events become zeros. The repaired table must preserve this separation."),
        ("6", "How large is true discovery cohort before future evaluation/matching?", "The direct BigQuery pre-cutoff endpoint universe is 20,461/20,818/21,123 wallets before the local matched-matched projection, and 11,532/12,241/12,747 after the upstream primary/counterparty-present/non-self/both-mapped predicate. The existing all-primary 90-day compact table has 17,600/16,905/15,922 wallets at active_days>=3 and 16,326/15,554/14,557 at active_days>=3 plus events>=10. Exact full all-event 30-day discovery counts require the new compact CTAS."),
        ("7", "Why did matching fail |SMD|<=0.10?", "Matching has no caliper or balance rejection; Top-5% treated wallets are often in activity tails, so nearest controls remain imbalanced. The failure is balance/support, not lack of assigned control rows."),
        ("8", "What is missing locally?", "Sub-day timestamps, event-family labels, transaction/event identity, native/token amounts, token contract/id, internal trace identity, and full in/out role coverage."),
        ("9", "What should be materialized?", "A BigQuery wallet×cutoff feature table from timestamped native/token/internal events with 1h/6h/1d/7d/30d and prior-23d windows, plus a separate future-outcomes table."),
        ("10", "Can >=2,000 be obtained?", "Yes, plausibly after restoring the full target-touching substrate: existing 90-day as-of data already has roughly 19--20k wallets per cutoff and >14k at the strict 90-day activity/event rule. It is not plausible from the current matched-matched outgoing day-level extract without changing the population."),
        ("11", "Should >=2,000 remain unchanged?", "Keep it unchanged for now as a conservative restart gate; it is a heuristic precision/coverage gate, not a demonstrated power calculation. Revisit only by preregistered amendment after the repaired cohort is measured."),
        ("12", "Current OW-009 status?", "DESIGN_REVISION_NEEDED, with the current local representation SUBSTRATE_UNDERPOWERED. Not METHOD_NO_GO, not IMPLEMENTATION_BUG as the sole diagnosis, and not READY_FOR_RERUN."),
    ]
    for num, q, a in answers:
        lines.append(f"**{num}. {q}**  {a}")
        lines.append("")
    (OUT / "CANDIDATE_ATTRITION_AUDIT.md").write_text("\n".join(lines))


def write_substrate_counts_csv(bq_evidence: dict | None) -> None:
    """Materialize only aggregate BigQuery counts, never raw event rows."""
    if not bq_evidence:
        return
    block = bq_evidence.get("queries", {}).get("per_cutoff_pre_cutoff_summary", {})
    rows = block.get("rows", [])
    if rows:
        pd.DataFrame(rows).to_csv(OUT / "substrate_counts_by_cutoff.csv", index=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mapped_nodes, raw, outgoing, extra = load_inputs()
    asof = extra["asof"]
    bq_evidence = extra.get("bq_evidence")
    write_substrate_counts_csv(bq_evidence)
    attr_rows = []
    match_rows = []
    features_by_cutoff: dict[str, pd.DataFrame] = {}
    features_variant: dict[tuple[str, str], pd.DataFrame] = {}
    for cutoff in CUTOFFS:
        for variant, min_events in [("registered_strict_10_events", STRICT_EVENTS), ("expanded_diagnostic_3_events", EXPANDED_EVENTS)]:
            features = build_features(outgoing, cutoff, min_events)
            features_variant[(variant, cutoff.date().isoformat())] = features
            m = exactish_matches(features, METHOD)
            match_rows.append({"variant": variant, "cutoff": cutoff.date().isoformat(), "method": METHOD, **{k: v for k, v in m.items() if k not in {"treated", "matches", "before_smd", "after_smd", "failed_covariates_before", "failed_covariates_after"}}})
            # Expand diagnostic fields without nested objects.
            row = match_rows[-1]
            row["before_failed_covariates"] = ";".join(m["failed_covariates_before"])
            row["after_failed_covariates"] = ";".join(m["failed_covariates_after"])
            for c, v in m["before_smd"].items(): row[f"before_smd__{c}"] = v
            for c, v in m["after_smd"].items(): row[f"after_smd__{c}"] = v
            row["matching_constraint_causing_failure"] = "no hard failure; post-match balance fails where after SMD > 0.10"
            attr_rows.extend(attrition(mapped_nodes, raw, outgoing, cutoff, min_events, variant, m))
            if variant == "registered_strict_10_events":
                features_by_cutoff[cutoff.date().isoformat()] = features
    attr = pd.DataFrame(attr_rows)
    filt = filter_registry()
    featcov = feature_coverage(features_by_cutoff)
    sens = sensitivity(mapped_nodes, raw, outgoing, asof)
    match = pd.DataFrame(match_rows)
    # Flatten nested method fields from the matching result if any slipped through.
    for col in ["treated", "matches", "before_smd", "after_smd", "failed_covariates_before", "failed_covariates_after"]:
        if col in match.columns:
            match = match.drop(columns=[col])
    attr.to_csv(OUT / "candidate_attrition_by_cutoff.csv", index=False)
    filt.to_csv(OUT / "filter_registry.csv", index=False)
    featcov.to_csv(OUT / "feature_coverage.csv", index=False)
    match.to_csv(OUT / "matching_diagnostics.csv", index=False)
    sens.to_csv(OUT / "cohort_sensitivity.csv", index=False)
    write_feature_spec()
    write_repair_plan(attr, sens, match)
    write_report(mapped_nodes, raw, outgoing, asof, bq_evidence, attr, filt, featcov, match, sens)
    manifest = {
        "audit_date": "2026-09-18",
        "label_blind": True,
        "mapped_wallet_count": len(mapped_nodes),
        "sequence_table_row_count_from_metadata": extra["sequence_rows"],
        "bigquery_aggregate_evidence": str(BQ_EVIDENCE) if bq_evidence else None,
        "bigquery_aggregate_evidence_sha256": sha256(BQ_EVIDENCE) if bq_evidence else None,
        "edge_artifact": str(EDGE),
        "edge_artifact_sha256": sha256(EDGE),
        "mapping_artifact": str(MAPPING),
        "mapping_artifact_sha256": sha256(MAPPING),
        "asof_artifact": str(ASOF),
        "asof_artifact_sha256": sha256(ASOF),
        "ow009_code": str(OW009),
        "ow009_code_sha256": sha256(OW009),
        "edge_sql": str(EDGE_SQL),
        "edge_sql_sha256": sha256(EDGE_SQL),
        "cutoffs": [x.date().isoformat() for x in CUTOFFS],
        "local_raw_aggregate_rows": int(len(raw)),
        "local_outgoing_aggregate_rows": int(len(outgoing)),
        "local_unique_endpoint_nodes": int(len(set(raw.u) | set(raw.v))),
        "local_unique_outgoing_source_nodes": int(outgoing.u.nunique()),
        "outputs": [
            "CANDIDATE_ATTRITION_AUDIT.md", "candidate_attrition_by_cutoff.csv",
            "filter_registry.csv", "feature_coverage.csv", "matching_diagnostics.csv",
            "cohort_sensitivity.csv", "substrate_counts_by_cutoff.csv", "BIGQUERY_FEATURE_SPEC.md", "SUBSTRATE_REPAIR_PLAN.md",
        ],
    }
    (OUT / "AUDIT_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"manifest": str(OUT / "AUDIT_MANIFEST.json"), "mapped_wallets": len(mapped_nodes), "local_nodes": manifest["local_unique_endpoint_nodes"], "strict_candidates": [int(len(features_variant[("registered_strict_10_events", c)])) for c in [x.date().isoformat() for x in CUTOFFS]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
