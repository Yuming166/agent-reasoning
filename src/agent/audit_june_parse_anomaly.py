#!/usr/bin/env python3
"""Audit the June LLM-panel parse anomaly without reading or printing responses.

The run CSVs contain per-event summaries, not the raw LLM responses.  This
script therefore separates exact observations (for example, ``full_parse_ok``
counts) from conservative diagnostics that cannot distinguish invalid JSON,
missing required fields, unknown candidate IDs, and transport errors after the
fact.  It never calls an LLM endpoint and never modifies an input panel.

Outputs are a JSON manifest and a short Markdown report.  The default paths
match the runtime analysis workspace; use ``--root`` to audit a copy.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


EVENT_KEY = ["snapshot_date", "target_address", "target_sequence_index"]
EXPECTED_COLUMNS = [
    "snapshot_date", "target_address", "target_sequence_index", "cp_type",
    "stratum", "activity", "pop_weight", "pool_n", "truth_in_pool",
    "cheap_rank", "cheap_rr", "obs_rank", "mask_rank", "full_rank",
    "full_rr", "full_parse_ok", "belief_shift", "mask_sensitive",
    "nocf_rank", "nocf_rr", "nocf_parse_ok", "llm_calls", "prompt_tokens",
    "completion_tokens", "total_tokens", "nocf_total_tokens", "latency_s",
    "model",
]
RANK_COLUMNS = ["cheap_rank", "obs_rank", "mask_rank", "full_rank", "nocf_rank"]
RR_COLUMNS = ["cheap_rr", "full_rr", "nocf_rr"]
PARSE_COLUMNS = ["full_parse_ok", "nocf_parse_ok"]
NUMERIC_COLUMNS = [
    "target_sequence_index", "pop_weight", "pool_n", "truth_in_pool",
    *RANK_COLUMNS, *RR_COLUMNS, *PARSE_COLUMNS, "llm_calls", "prompt_tokens",
    "completion_tokens", "total_tokens", "nocf_total_tokens", "latency_s",
]
AUDIT_STEPS = ["step1", "step2", "step3", "step4"]
AUDIT_DETAIL_COLUMNS = [
    *(f"audit_{step}_{field}" for step in AUDIT_STEPS for field in [
        "status", "client_error", "response_model", "finish_reason",
        "reasoning_nonempty", "total_tokens", "latency_s",
    ]),
    "audit_full_internal_fallback", "audit_nocf_internal_fallback",
]

# Historical June inputs.  The v2 path without a suffix was attempted but is
# not present in this workspace; keep it explicit so the absence is visible in
# the manifest rather than silently omitted.
RUN_SPECS = [
    {
        "run_id": "v1_june",
        "label": "v1 historical June",
        "path": "artifacts/llm_panel_v1/runs/jun_gonogo_glm53_v1.csv",
        "variant": "v1",
        "status": "historical_diagnostic",
    },
    {
        "run_id": "v2_buggy_june",
        "label": "v2 June pre-float-fix",
        "path": "artifacts/llm_panel_v2/runs/buggy_pre_float_fix_20260909/jun_gonogo_glm53_v2.csv",
        "variant": "v2_buggy_pre_float_fix",
        "status": "historical_diagnostic_invalid_numeric_schema",
    },
    {
        "run_id": "v2_june_missing",
        "label": "v2 June unsuffixed",
        "path": "artifacts/llm_panel_v2/runs/jun_gonogo_glm53_v2.csv",
        "variant": "v2_unsuffixed",
        "status": "missing",
    },
    {
        "run_id": "v2_floatfix_june",
        "label": "v2 June float-fix",
        "path": "artifacts/llm_panel_v2/runs/jun_gonogo_glm53_v2_floatfix.csv",
        "variant": "v2_floatfix",
        "status": "candidate_but_parse_anomalous",
    },
]
EVAL_SPECS = [
    {
        "run_id": "v1_june",
        "path": "artifacts/llm_panel_v1/runs/jun_gonogo_eval.jsonl",
        "label": "v1 June eval summary",
    },
    {
        "run_id": "v2_buggy_june",
        "path": "artifacts/llm_panel_v2/runs/buggy_pre_float_fix_20260909/jun_gonogo_eval_v2.jsonl",
        "label": "v2 June pre-float-fix eval summary",
    },
    {
        "run_id": "v2_floatfix_june",
        "path": "artifacts/llm_panel_v2/runs/jun_gonogo_eval_floatfix.jsonl",
        "label": "v2 June float-fix eval summary",
    },
]
REFERENCE_SPECS = [
    ("v1_july", "artifacts/llm_panel_v1/runs/jul_gonogo_glm53_v1.csv", "v1"),
    ("v1_august", "artifacts/llm_panel_v1/runs/aug_gonogo_glm53_v1.csv", "v1"),
    ("v2_buggy_july", "artifacts/llm_panel_v2/runs/buggy_pre_float_fix_20260909/jul_gonogo_glm53_v2.csv", "v2_buggy_pre_float_fix"),
    ("v2_buggy_august", "artifacts/llm_panel_v2/runs/buggy_pre_float_fix_20260909/aug_gonogo_glm53_v2.csv", "v2_buggy_pre_float_fix"),
    ("v2_floatfix_july", "artifacts/llm_panel_v2/runs/jul_gonogo_glm53_v2_floatfix.csv", "v2_floatfix"),
    ("v2_floatfix_august", "artifacts/llm_panel_v2/runs/aug_gonogo_glm53_v2_floatfix.csv", "v2_floatfix"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def scalar(value: Any) -> Any:
    """Convert pandas/numpy values to JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return scalar(value)


def quantiles(s: pd.Series) -> dict[str, Any]:
    x = pd.to_numeric(s, errors="coerce")
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"count": 0, "missing": int(len(s)), "sum": None,
                "mean": None, "median": None, "p95": None,
                "min": None, "max": None}
    return {
        "count": int(len(x)),
        "missing": int(len(s) - len(x)),
        "sum": float(x.sum()),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "p95": float(x.quantile(0.95)),
        "min": float(x.min()),
        "max": float(x.max()),
    }


def raw_nonempty(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().ne("") & s.notna()


def norm_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def key_tuples(df: pd.DataFrame, cols: Iterable[str] = EVENT_KEY) -> list[tuple[str, ...]]:
    return [tuple(str(v).strip() for v in row) for row in df[list(cols)].itertuples(index=False, name=None)]


def compact_counts(s: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in s.value_counts(dropna=False).items()}


def parse_flag_stats(df: pd.DataFrame, column: str) -> dict[str, Any]:
    raw = df[column].astype(str).str.strip()
    num = pd.to_numeric(raw.replace({"": np.nan}), errors="coerce")
    valid_binary = num.isin([0, 1])
    success = num.eq(1)
    failure = ~success
    return {
        "column": column,
        "success_count": int(success.sum()),
        "failure_or_missing_count": int(failure.sum()),
        "zero_count": int(num.eq(0).sum()),
        "missing_count": int(num.isna().sum()),
        "invalid_value_count": int((raw.ne("") & ~num.isna() & ~valid_binary).sum()),
        "raw_value_counts": compact_counts(raw.replace("", "<EMPTY>")),
    }


def rank_stats(df: pd.DataFrame, column: str) -> dict[str, Any]:
    raw = df[column].astype(str).str.strip()
    x = pd.to_numeric(raw.replace({"": np.nan}), errors="coerce")
    finite = x.notna() & np.isfinite(x)
    valid = finite & x.gt(0)
    return {
        "column": column,
        "present_count": int(raw_nonempty(raw).sum()),
        "computable_positive_count": int(valid.sum()),
        "missing_or_empty_count": int(raw.eq("").sum() + raw.isna().sum()),
        "non_numeric_count": int((raw.ne("") & ~finite).sum()),
        "non_positive_count": int((finite & ~x.gt(0)).sum()),
        "min": float(x[valid].min()) if valid.any() else None,
        "max": float(x[valid].max()) if valid.any() else None,
    }


def rr_stats(df: pd.DataFrame, column: str, rank_column: str) -> dict[str, Any]:
    raw = df[column].astype(str).str.strip()
    x = pd.to_numeric(raw.replace({"": np.nan}), errors="coerce")
    rank = pd.to_numeric(df[rank_column].astype(str).str.strip().replace({"": np.nan}), errors="coerce")
    finite = x.notna() & np.isfinite(x)
    bool_like = raw.str.lower().isin(["true", "false"])
    valid = finite & x.ge(0)
    both = valid & rank.notna() & np.isfinite(rank) & rank.gt(0)
    consistent = both & np.isclose(x, 1.0 / rank, rtol=2e-5, atol=2e-8)
    return {
        "column": column,
        "rank_column": rank_column,
        "numeric_count": int(finite.sum()),
        "missing_or_non_numeric_count": int((~finite).sum()),
        "bool_like_count": int(bool_like.sum()),
        "negative_count": int((finite & x.lt(0)).sum()),
        "rank_rr_pairs_count": int(both.sum()),
        "rank_rr_consistent_count": int(consistent.sum()),
        "rank_rr_inconsistent_count": int((both & ~consistent).sum()),
        "raw_value_counts_head": compact_counts(raw.replace("", "<EMPTY>")).copy(),
    }


def arm_observation(df: pd.DataFrame, arm: str, rank_column: str,
                    parse_column: str | None = None,
                    rr_column: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "record_count": int(len(df)),
        "rank": rank_stats(df, rank_column),
    }
    if parse_column:
        result["parse"] = parse_flag_stats(df, parse_column)
        parse_ok = pd.to_numeric(df[parse_column], errors="coerce").eq(1)
        result["parse_ok_and_rank_computable_count"] = int(
            (parse_ok & pd.to_numeric(df[rank_column], errors="coerce").gt(0)).sum()
        )
        result["parse_failure_but_rank_computable_count"] = int(
            ((~parse_ok) & pd.to_numeric(df[rank_column], errors="coerce").gt(0)).sum()
        )
        result["parse_success_count_exact"] = int(parse_ok.sum())
        result["parse_success_is_exact_flag"] = True
    else:
        rank_ok = pd.to_numeric(df[rank_column], errors="coerce").gt(0)
        result["parse_success_count_proxy"] = int(rank_ok.sum())
        result["parse_failure_count_proxy"] = int((~rank_ok).sum())
        result["parse_success_is_exact_flag"] = False
    if rr_column:
        result["rr"] = rr_stats(df, rr_column, rank_column)
    return result


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def file_metadata(path: Path, root: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "path": display_path(path, root),
        "exists": True,
        "size_bytes": int(st.st_size),
        "sha256": sha256(path),
        "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
    }


def grouped_run_summary(df: pd.DataFrame, group_columns: list[str]) -> list[dict[str, Any]]:
    """Return aggregate failure diagnostics by low-cardinality panel groups."""
    rows: list[dict[str, Any]] = []
    for values, sub in df.groupby(group_columns, dropna=False, sort=True):
        if not isinstance(values, tuple):
            values = (values,)
        full = pd.to_numeric(sub["full_parse_ok"], errors="coerce")
        nocf = pd.to_numeric(sub["nocf_parse_ok"], errors="coerce")
        total = pd.to_numeric(sub["total_tokens"], errors="coerce")
        calls = pd.to_numeric(sub["llm_calls"], errors="coerce")
        latency = pd.to_numeric(sub["latency_s"], errors="coerce")
        pool = pd.to_numeric(sub["pool_n"], errors="coerce")
        item = {str(c): scalar(v) for c, v in zip(group_columns, values)}
        item.update({
            "n": int(len(sub)),
            "full_parse_success_count": int(full.eq(1).sum()),
            "full_parse_success_rate": float(full.eq(1).mean()) if len(sub) else None,
            "nocf_parse_success_count": int(nocf.eq(1).sum()),
            "nocf_parse_success_rate": float(nocf.eq(1).mean()) if len(sub) else None,
            "zero_total_tokens_count": int(total.eq(0).sum()),
            "short_calls_count": int(calls.lt(4).sum()),
            "median_latency_s": float(latency.median()) if latency.notna().any() else None,
            "median_pool_n": float(pool.median()) if pool.notna().any() else None,
        })
        rows.append(item)
    return rows


def local_vllm_preflight(root: Path) -> dict[str, Any]:
    """Check only this user's local executable/import/config, never endpoints."""
    model_env_names = ["LOCAL_VLLM_MODEL", "VLLM_MODEL_PATH", "MODEL_PATH"]
    model_env = next((name for name in model_env_names if os.environ.get(name)), None)
    model_path = os.environ.get(model_env, "") if model_env else ""
    model_path_obj = Path(model_path).expanduser() if model_path else None
    weights = []
    if model_path_obj and model_path_obj.is_dir():
        weights = [p.name for p in model_path_obj.iterdir() if p.is_file() and (
            p.name == "model.safetensors" or p.name.startswith("model-") and p.suffix == ".safetensors"
            or p.name.startswith("pytorch_model") and p.suffix in {".bin", ".safetensors"}
        )][:20]
    return {
        "scope": "current_user_local_only",
        "vllm_cli_found": bool(shutil.which("vllm")),
        "vllm_python_import_found": importlib.util.find_spec("vllm") is not None,
        "model_path_env_name": model_env,
        "model_path_configured": bool(model_path),
        "model_path_exists": bool(model_path_obj and model_path_obj.exists()),
        "model_config_json_present": bool(model_path_obj and (model_path_obj / "config.json").is_file()),
        "model_weight_files_head": weights,
        "authorized_local_service_verified": False,
        "endpoint_probed": False,
        "other_user_services_or_weights_used": False,
        "rerun_allowed_now": False,
        "reason": (
            "No authorized local vLLM/model preflight passed in the current execution environment; "
            "the audit intentionally does not probe or borrow another user's service or weights."
        ),
    }


def audited_step_summary(df: pd.DataFrame) -> dict[str, Any] | None:
    """Summarize opt-in per-step run instrumentation without response text."""
    present = [c for c in AUDIT_DETAIL_COLUMNS if c in df.columns]
    if not any(c.endswith("_status") for c in present):
        return None
    status_counts: dict[str, dict[str, int]] = {}
    client_error_counts: dict[str, int] = {}
    response_models: dict[str, dict[str, int]] = {}
    finish_reasons: dict[str, dict[str, int]] = {}
    reasoning_counts: dict[str, int] = {}

    def numeric_column(column: str, default: float = 0.0) -> pd.Series:
        if column not in df.columns:
            return pd.Series(default, index=df.index, dtype=float)
        return pd.to_numeric(df[column], errors="coerce").fillna(default)

    for step in AUDIT_STEPS:
        status_col = f"audit_{step}_status"
        if status_col in df.columns:
            status_counts[step] = compact_counts(df[status_col].astype(str).str.strip())
        error_col = f"audit_{step}_client_error"
        client_error_counts[step] = int(numeric_column(error_col).sum())
        model_col = f"audit_{step}_response_model"
        if model_col in df.columns:
            response_models[step] = compact_counts(df[model_col].astype(str).str.strip().replace("", "<EMPTY>"))
        reason_col = f"audit_{step}_finish_reason"
        if reason_col in df.columns:
            finish_reasons[step] = compact_counts(df[reason_col].astype(str).str.strip().replace("", "<EMPTY>"))
        thinking_col = f"audit_{step}_reasoning_nonempty"
        reasoning_counts[step] = int(numeric_column(thinking_col).eq(1).sum())

    non_ok_by_step = {
        step: int(len(df) - sum(v for k, v in status_counts.get(step, {}).items() if k == "ok"))
        for step in AUDIT_STEPS if f"audit_{step}_status" in df.columns
    }
    non_ok_mask = pd.Series(False, index=df.index)
    for step in AUDIT_STEPS:
        col = f"audit_{step}_status"
        if col in df.columns:
            non_ok_mask |= df[col].astype(str).str.strip().ne("ok")
    full_ok = numeric_column("full_parse_ok").eq(1)
    nocf_ok = numeric_column("nocf_parse_ok").eq(1)
    stage3_bad = df.get("audit_step3_status", pd.Series("", index=df.index)).astype(str).str.strip().ne("ok")
    full_rank = pd.to_numeric(df["full_rank"], errors="coerce") if "full_rank" in df.columns else pd.Series(np.nan, index=df.index)
    mask_rank = pd.to_numeric(df["mask_rank"], errors="coerce") if "mask_rank" in df.columns else pd.Series(np.nan, index=df.index)
    obs_rank = pd.to_numeric(df["obs_rank"], errors="coerce") if "obs_rank" in df.columns else pd.Series(np.nan, index=df.index)
    return {
        "columns_present": present,
        "audit_details_complete": all(c in df.columns for c in AUDIT_DETAIL_COLUMNS),
        "status_counts_by_step": status_counts,
        "non_ok_count_by_step": non_ok_by_step,
        "non_ok_total_count": int(non_ok_mask.sum()),
        "client_error_count_by_step": client_error_counts,
        "client_error_total_count": int(sum(client_error_counts.values())),
        "response_model_counts_by_step": response_models,
        "finish_reason_counts_by_step": finish_reasons,
        "reasoning_nonempty_count_by_step": reasoning_counts,
        "internal_fallback_count": {
            "full": int(numeric_column("audit_full_internal_fallback").eq(1).sum()),
            "nocf": int(numeric_column("audit_nocf_internal_fallback").eq(1).sum()),
        },
        "full_parse_rows_with_any_non_ok_stage": int((full_ok & non_ok_mask).sum()),
        "nocf_parse_rows_with_any_non_ok_stage": int((nocf_ok & non_ok_mask & df.index.to_series().notna()).sum()),
        "stage3_non_ok_count": int(stage3_bad.sum()),
        "stage3_non_ok_with_final_rank_count": int((stage3_bad & full_rank.gt(0)).sum()),
        "stage3_non_ok_full_equals_mask_rank_count": int((stage3_bad & np.isclose(full_rank, mask_rank, equal_nan=False)).sum()),
        "stage3_non_ok_full_equals_obs_rank_count": int((stage3_bad & np.isclose(full_rank, obs_rank, equal_nan=False)).sum()),
        "all_response_models_nonempty": all(
            "<EMPTY>" not in counts for counts in response_models.values()
        ),
    }


def read_run(path: Path, root: Path, run_id: str, label: str,
             variant: str, status: str) -> tuple[dict[str, Any], pd.DataFrame | None]:
    base: dict[str, Any] = {
        "run_id": run_id,
        "label": label,
        "variant": variant,
        "status": status,
        "path": display_path(path, root),
    }
    if not path.exists():
        base.update({"exists": False, "decision": "not_available"})
        return base, None
    base.update(file_metadata(path, root))
    try:
        # Keep strings to identify the historical True/False RR serialization.
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:  # pragma: no cover - defensive audit path
        base.update({"read_error": f"{type(exc).__name__}: {exc}", "decision": "read_error"})
        return base, None

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    base["exists"] = True
    base["read_error"] = None
    base["schema"] = {
        "column_count": int(len(df.columns)),
        "observed_columns": list(df.columns),
        "expected_columns": EXPECTED_COLUMNS,
        "missing_required_columns": missing,
        "extra_columns": extra,
        "raw_response_columns_present": any(
            token in c.lower() for c in df.columns
            for token in ["response", "raw", "completion_text", "error"]
        ),
        "raw_response_schema_keys": None,
        "raw_response_schema_note": (
            "Run CSV stores aggregate ranks/flags/tokens only; raw response text and "
            "per-call error payloads were not persisted, so invalid JSON versus missing "
            "fields versus unknown candidate IDs cannot be separated retrospectively."
        ),
    }

    audited = audited_step_summary(df)
    if audited is not None:
        base["per_step_observability"] = audited

    # If the key is absent, retain a structural summary and stop before the
    # per-event calculations.
    if any(c not in df.columns for c in EVENT_KEY):
        base["decision"] = "not_auditable_missing_event_key"
        base["row_count"] = int(len(df))
        return base, df

    keys = key_tuples(df)
    key_series = pd.Series(keys, dtype="object")
    dup_mask = key_series.duplicated(keep=False)
    date_values = df["snapshot_date"].astype(str).str.strip()
    base["row_count"] = int(len(df))
    base["event_identity"] = {
        "explicit_event_id_column_present": False,
        "event_key_columns": EVENT_KEY,
        "unique_event_key_count": int(key_series.nunique()),
        "unique_target_event_key_count": int(
            df[["target_address", "target_sequence_index"]].drop_duplicates().shape[0]
        ),
        "unique_target_address_count": int(df["target_address"].nunique()),
        "duplicate_row_count_by_event_key": int(dup_mask.sum()),
        "duplicate_event_key_count": int(key_series[dup_mask].nunique()),
        "snapshot_values": compact_counts(date_values),
    }

    pool = norm_numeric(df, "pool_n")
    support = norm_numeric(df, "truth_in_pool")
    calls = norm_numeric(df, "llm_calls")
    prompt = norm_numeric(df, "prompt_tokens")
    completion = norm_numeric(df, "completion_tokens")
    total = norm_numeric(df, "total_tokens")
    latency = norm_numeric(df, "latency_s")
    full_ok = norm_numeric(df, "full_parse_ok")
    nocf_ok = norm_numeric(df, "nocf_parse_ok")

    token_consistent = (
        prompt.notna() & completion.notna() & total.notna()
        & np.isclose(prompt + completion, total, rtol=0, atol=0.5)
    )
    expected_calls = 4
    calls_short = calls.notna() & calls.lt(expected_calls)
    calls_unexpected = calls.notna() & calls.gt(expected_calls)
    # The 45-second plateau is an observed runtime signature in the affected
    # June file, not a protocol-defined timeout.  We label it suspected rather
    # than claiming an exact transport error count.
    plateau = latency.notna() & latency.ge(45.0)
    zero_tokens = total.fillna(0).eq(0)
    base["data_quality"] = {
        "candidate_support": {
            "truth_in_pool_true_count": int(support.eq(1).sum()),
            "truth_in_pool_false_count": int(support.eq(0).sum()),
            "truth_in_pool_missing_or_other_count": int((~support.isin([0, 1])).sum()),
            "pool_n": quantiles(pool),
            "pool_n_nonpositive_count": int((pool.notna() & pool.le(0)).sum()),
        },
        "rank_observations": {
            "cheap": arm_observation(df, "cheap", "cheap_rank", rr_column="cheap_rr"),
            "obs": arm_observation(df, "obs", "obs_rank"),
            "mask": arm_observation(df, "mask", "mask_rank"),
            "full": arm_observation(df, "full", "full_rank", "full_parse_ok", "full_rr"),
            "nocf": arm_observation(df, "nocf", "nocf_rank", "nocf_parse_ok", "nocf_rr"),
        },
        "empty_candidate_or_rank": {
            "empty_candidate_pool_count": int((pool.fillna(0).le(0)).sum()),
            "cheap_rank_missing_or_invalid_count": int( len(df) - arm_observation(df, "cheap", "cheap_rank")["rank"]["computable_positive_count"] ),
            "obs_rank_missing_or_invalid_count": int( len(df) - arm_observation(df, "obs", "obs_rank")["rank"]["computable_positive_count"] ),
            "mask_rank_missing_or_invalid_count": int( len(df) - arm_observation(df, "mask", "mask_rank")["rank"]["computable_positive_count"] ),
            "full_rank_missing_or_invalid_count": int( len(df) - arm_observation(df, "full", "full_rank")["rank"]["computable_positive_count"] ),
            "nocf_rank_missing_or_invalid_count": int( len(df) - arm_observation(df, "nocf", "nocf_rank")["rank"]["computable_positive_count"] ),
        },
        "tokens": {
            "prompt_tokens": quantiles(prompt),
            "completion_tokens": quantiles(completion),
            "total_tokens": quantiles(total),
            "nocf_total_tokens": quantiles(norm_numeric(df, "nocf_total_tokens")),
            "prompt_zero_count": int(prompt.eq(0).sum()),
            "completion_zero_count": int(completion.eq(0).sum()),
            "total_zero_count": int(total.eq(0).sum()),
            "prompt_completion_total_consistent_count": int(token_consistent.sum()),
            "prompt_completion_total_inconsistent_count": int((~token_consistent).sum()),
        },
        "latency": {
            **quantiles(latency),
            "latency_ge_45s_count_suspected_plateau": int(plateau.sum()),
            "latency_ge_120s_count": int((latency.ge(120)).sum()),
        },
        "model": {
            "field_present": "model" in df.columns,
            "nonempty_count": int(raw_nonempty(df["model"]).sum()),
            "unique_values": sorted(set(df["model"].astype(str).str.strip())),
        },
        "schema_value_checks": {
            "numeric_columns": {
                c: {
                    "raw_nonempty_count": int(raw_nonempty(df[c]).sum()),
                    "numeric_count": int(pd.to_numeric(df[c], errors="coerce").notna().sum()),
                    "non_numeric_count": int(pd.to_numeric(df[c], errors="coerce").isna().sum() - (df[c].astype(str).str.strip() == "").sum()),
                    "bool_like_count": int(df[c].astype(str).str.lower().isin(["true", "false"]).sum()),
                }
                for c in NUMERIC_COLUMNS if c in df.columns
            },
        },
        "runtime_error_observability": {
            "raw_error_column_present": any("error" in c.lower() for c in df.columns),
            "exact_timeout_count_available": False,
            "exact_transport_error_count_available": False,
            "llm_calls_expected_per_event": expected_calls,
            "llm_calls_short_count": int(calls_short.sum()),
            "llm_calls_unexpected_count": int(calls_unexpected.sum()),
            "zero_total_token_count": int(zero_tokens.sum()),
            "suspected_runtime_or_no_response_count": int((calls_short & zero_tokens & plateau).sum()),
            "diagnostic_note": (
                "No raw per-call error/status was persisted. Counts are exact for short calls, "
                "zero usage, and the observed latency plateau; the suspected runtime count is "
                "not an exact timeout label."
            ),
        },
        "operational_fallback": {
            "full_fallback_count_if_parse_failure_routes_to_cheap": int((~full_ok.eq(1)).sum()),
            "nocf_fallback_count_if_parse_failure_routes_to_cheap": int((~nocf_ok.eq(1)).sum()),
            "full_parse_failure_but_final_rank_present_count": int((~full_ok.eq(1) & norm_numeric(df, "full_rank").gt(0)).sum()),
            "nocf_parse_failure_but_final_rank_present_count": int((~nocf_ok.eq(1) & norm_numeric(df, "nocf_rank").gt(0)).sum()),
            "fallback_semantics": "Derived operational fallback counts; original CSV does not store a fallback flag.",
        },
    }

    base["grouped_diagnostics"] = {
        "by_stratum": grouped_run_summary(df, ["stratum"]),
        "by_stratum_activity": grouped_run_summary(df, ["stratum", "activity"]),
        "by_cp_type": grouped_run_summary(df, ["cp_type"]),
    }

    base["parse_anomaly"] = {
        "full_parse_success_rate": float(full_ok.eq(1).mean()) if len(df) else None,
        "nocf_parse_success_rate": float(nocf_ok.eq(1).mean()) if len(df) else None,
        "full_parse_failure_count": int((~full_ok.eq(1)).sum()),
        "nocf_parse_failure_count": int((~nocf_ok.eq(1)).sum()),
        "obs_missing_rank_count_proxy": int((~norm_numeric(df, "obs_rank").gt(0)).sum()),
        "mask_missing_rank_count_proxy": int((~norm_numeric(df, "mask_rank").gt(0)).sum()),
        "invalid_json_count_exact": None,
        "missing_required_response_field_count_exact": None,
        "timeout_or_error_count_exact": None,
        "unavailable_reason": (
            "Raw response bodies and per-call statuses are absent. full/nocf parse flags are "
            "combined parser/schema/candidate-ID outcomes, while obs/mask null ranks are proxies."
        ),
    }

    # A run with duplicate event keys or missing required columns cannot be a
    # clean router-training input even if its parse flags are high.
    support_ok = bool((support == 1).all())
    schema_ok = not missing
    unique_ok = int(dup_mask.sum()) == 0
    numeric_ok = all(base["data_quality"]["schema_value_checks"]["numeric_columns"][c]["bool_like_count"] == 0
                     for c in ["cheap_rr", "full_rr", "nocf_rr"] if c in df.columns)
    if variant == "v2_buggy_pre_float_fix" and not numeric_ok:
        base["decision"] = "not_eligible_buggy_numeric_schema"
    elif variant == "v2_floatfix" and (not schema_ok or not unique_ok or not support_ok):
        base["decision"] = "not_eligible_structural_quality"
    elif variant == "v2_floatfix" and float(full_ok.eq(1).mean()) < 0.95:
        base["decision"] = "not_eligible_parse_anomaly"
    elif variant == "v2_local_vllm_rerun":
        audit = base.get("per_step_observability") or {}
        exact_calls = calls.notna() & calls.eq(expected_calls)
        snapshot_ok = set(date_values) == {"2022-06-01"}
        requested_models = sorted(set(df["model"].astype(str).str.strip())) if "model" in df.columns else []
        response_models = sorted({
            str(value).strip()
            for step_counts in audit.get("response_model_counts_by_step", {}).values()
            for value in step_counts if value != "<EMPTY>"
        })
        response_model_ok = bool(response_models) and response_models == ["Qwen3.5-4B"]
        runtime_clean_except_known_stage3 = (
            bool(audit.get("audit_details_complete"))
            and int(audit.get("client_error_total_count", 0)) == 0
            and int(audit.get("non_ok_count_by_step", {}).get("step1", 0)) == 0
            and int(audit.get("non_ok_count_by_step", {}).get("step2", 0)) == 0
            and int(audit.get("non_ok_count_by_step", {}).get("step4", 0)) == 0
            and int(audit.get("stage3_non_ok_count", 0)) == int(audit.get("stage3_non_ok_full_equals_mask_rank_count", 0))
            and int(audit.get("stage3_non_ok_with_final_rank_count", 0)) == int(audit.get("stage3_non_ok_count", 0))
        )
        clean = (
            schema_ok and unique_ok and support_ok and numeric_ok and snapshot_ok
            and len(df) == 1000 and bool((full_ok == 1).all()) and bool((nocf_ok == 1).all())
            and bool(exact_calls.all()) and int(zero_tokens.sum()) == 0
            and requested_models == ["Qwen3.5-4B"] and response_model_ok
            and bool(audit.get("audit_details_complete"))
            and int(audit.get("non_ok_total_count", 0)) == 0
            and int(audit.get("client_error_total_count", 0)) == 0
        )
        base["eligibility_checks"] = {
            "expected_snapshot_only": snapshot_ok,
            "expected_row_count_1000": len(df) == 1000,
            "full_and_nocf_parse_all_success": bool((full_ok == 1).all() and (nocf_ok == 1).all()),
            "expected_four_calls_per_event": bool(exact_calls.all()),
            "zero_total_tokens": int(zero_tokens.sum()) == 0,
            "numeric_rr": numeric_ok,
            "candidate_support_all_true": support_ok,
            "unique_event_keys": unique_ok,
            "requested_model_exact": requested_models == ["Qwen3.5-4B"],
            "response_model_exact": response_model_ok,
            "per_step_audit_complete": bool(audit.get("audit_details_complete")),
            "per_step_audit_clean": int(audit.get("non_ok_total_count", 0)) == 0,
            "client_transport_errors_zero": int(audit.get("client_error_total_count", 0)) == 0,
            "clean_run": clean,
            "known_stage3_fallback_path_auditable": runtime_clean_except_known_stage3,
        }
        if clean:
            base["decision"] = "eligible_corrected_for_router_training"
        elif (
            schema_ok and unique_ok and support_ok and numeric_ok and snapshot_ok
            and len(df) == 1000 and bool((full_ok == 1).all()) and bool((nocf_ok == 1).all())
            and bool(exact_calls.all()) and int(zero_tokens.sum()) == 0
            and requested_models == ["Qwen3.5-4B"] and response_model_ok
            and runtime_clean_except_known_stage3
        ):
            base["decision"] = "eligible_with_audited_stage3_candidate_fallback"
        else:
            base["decision"] = "not_eligible_rerun_runtime_or_structural_failure"
    else:
        base["decision"] = "diagnostic_only_until_protocol_review"
    return base, df


def read_eval(path: Path, root: Path, run_id: str, label: str) -> dict[str, Any]:
    base = {"run_id": run_id, "label": label, "path": display_path(path, root)}
    if not path.exists():
        base.update({"exists": False, "status": "missing"})
        return base
    base.update(file_metadata(path, root))
    records: list[dict[str, Any]] = []
    invalid_lines = 0
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        label_part, sep, payload = line.partition(" ")
        if not sep:
            invalid_lines += 1
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(obj, dict):
            invalid_lines += 1
            continue
        records.append({"label": label_part, "keys": sorted(obj), "values": obj})
    base["exists"] = True
    base["invalid_line_count"] = invalid_lines
    base["record_count"] = len(records)
    # Values are summaries generated from the CSV; preserve only scalar summary
    # fields, not any accidental long text if a future file contains it.
    safe_records = []
    for rec in records:
        obj = rec["values"]
        safe_obj = {k: obj[k] for k in obj if isinstance(obj[k], (str, int, float, bool, list, type(None)))}
        safe_records.append({"label": rec["label"], "keys": rec["keys"], "values": clean(safe_obj)})
    base["records"] = safe_records
    base["schema_keys_by_label"] = {rec["label"]: rec["keys"] for rec in records}
    base["raw_response_schema_keys"] = None
    base["raw_response_schema_note"] = "Eval JSONL contains aggregate metrics only; it is not a raw response log."
    return base


def compare_runs(run_results: dict[str, dict[str, Any]], frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    ids = ["v1_june", "v2_buggy_june", "v2_floatfix_june"]
    ids.extend(k for k in frames if k not in ids)
    out: list[dict[str, Any]] = []
    for i, left_id in enumerate(ids):
        for right_id in ids[i + 1:]:
            left = frames.get(left_id)
            right = frames.get(right_id)
            item = {"left": left_id, "right": right_id}
            if left is None or right is None:
                item.update({"status": "not_comparable_missing_frame"})
                out.append(item)
                continue
            lk = set(key_tuples(left))
            rk = set(key_tuples(right))
            common = lk & rk
            item.update({
                "status": "compared",
                "left_rows": int(len(left)), "right_rows": int(len(right)),
                "common_event_key_count": int(len(common)),
                "left_only_event_key_count": int(len(lk - rk)),
                "right_only_event_key_count": int(len(rk - lk)),
            })
            # Compare only exact common keys.  Rank equality is diagnostic: v1
            # and v2 intentionally use different candidate pools.
            lidx = {k: j for j, k in enumerate(key_tuples(left))}
            ridx = {k: j for j, k in enumerate(key_tuples(right))}
            metrics: dict[str, int] = {}
            for col in ["full_parse_ok", "nocf_parse_ok", "llm_calls", "obs_rank", "mask_rank", "full_rank", "nocf_rank"]:
                matches = 0
                for k in common:
                    lv = left.iloc[lidx[k]][col]
                    rv = right.iloc[ridx[k]][col]
                    if str(lv).strip() == str(rv).strip():
                        matches += 1
                metrics[f"{col}_exact_match_count"] = matches
            item["common_key_field_exact_matches"] = metrics
            out.append(item)
    return out


def reference_summary(root: Path) -> list[dict[str, Any]]:
    rows = []
    for run_id, rel, variant in REFERENCE_SPECS:
        path = root / rel
        if not path.exists():
            rows.append({"run_id": run_id, "variant": variant, "path": rel, "exists": False})
            continue
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            full = pd.to_numeric(df["full_parse_ok"], errors="coerce")
            nocf = pd.to_numeric(df["nocf_parse_ok"], errors="coerce")
            rows.append({
                "run_id": run_id, "variant": variant, "path": rel, "exists": True,
                "row_count": int(len(df)),
                "full_parse_success_count": int(full.eq(1).sum()),
                "full_parse_success_rate": float(full.eq(1).mean()) if len(df) else None,
                "nocf_parse_success_count": int(nocf.eq(1).sum()),
                "nocf_parse_success_rate": float(nocf.eq(1).mean()) if len(df) else None,
                "full_rr_bool_like_count": int(df["full_rr"].astype(str).str.lower().isin(["true", "false"]).sum()),
                "nocf_rr_bool_like_count": int(df["nocf_rr"].astype(str).str.lower().isin(["true", "false"]).sum()),
                "median_latency_s": float(pd.to_numeric(df["latency_s"], errors="coerce").median()),
                "median_total_tokens": float(pd.to_numeric(df["total_tokens"], errors="coerce").median()),
            })
        except Exception as exc:
            rows.append({"run_id": run_id, "variant": variant, "path": rel, "exists": True,
                         "read_error": f"{type(exc).__name__}: {exc}"})
    return rows


def find_eval_summary(eval_result: dict[str, Any], label: str = "ALL") -> dict[str, Any] | None:
    for rec in eval_result.get("records", []):
        if rec.get("label") == label:
            return rec.get("values")
    return None


def eval_consistency(eval_results: list[dict[str, Any]], run_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for ev in eval_results:
        run_id = ev["run_id"]
        rr = run_results.get(run_id, {})
        summary = find_eval_summary(ev)
        item = {"run_id": run_id, "eval_path": ev["path"], "status": "not_checked"}
        if not summary or not rr.get("exists"):
            item["status"] = "missing_summary_or_run"
            out.append(item)
            continue
        pa = rr.get("parse_anomaly", {})
        checks = {
            "n": (summary.get("n"), rr.get("row_count")),
            "full_parse": (summary.get("full_parse"), pa.get("full_parse_success_rate")),
            "nocf_parse": (summary.get("nocf_parse"), pa.get("nocf_parse_success_rate")),
        }
        mismatches = {}
        for k, (a, b) in checks.items():
            if a is None or b is None:
                continue
            mismatches[k] = {"eval": a, "recomputed": b, "match": bool(abs(float(a) - float(b)) < 1e-6)} if k != "n" else {"eval": a, "recomputed": b, "match": int(a) == int(b)}
        item["status"] = "checked"
        item["checks"] = mismatches
        item["all_checked_fields_match"] = all(v["match"] for v in mismatches.values())
        out.append(item)
    return out


def pct(n: Any, d: Any) -> str:
    if n is None or d in (None, 0):
        return "n/a"
    return f"{100.0 * float(n) / float(d):.1f}%"


def md_report(report: dict[str, Any]) -> str:
    runs = report["runs"]
    june = {r["run_id"]: r for r in runs}
    f = june.get("v2_floatfix_june", {})
    p = f.get("parse_anomaly", {})
    dq = f.get("data_quality", {})
    rt = dq.get("runtime_error_observability", {})
    tok = dq.get("tokens", {})
    lat = dq.get("latency", {})
    reruns = [r for r in runs if r.get("variant") == "v2_local_vllm_rerun"]
    lines = [
        "# June LLM panel parse anomaly audit",
        "",
        f"> Generated at `{report['generated_at']}`. This audit is read-only with respect to all input panels and does not call an LLM endpoint.",
        "",
        "## Decision",
        "",
        "- **June v2 float-fix is not eligible for router training as-is.** It has a large combined parser/response-validity failure: full `" + pct(p.get('full_parse_success_rate', 0), 1) + "` and no-CF `" + pct(p.get('nocf_parse_success_rate', 0), 1) + "` (rates shown as percentages below).",
        "- The evidence is consistent with a June-specific runtime/service failure signature, not candidate-support failure: all observed June v2 float-fix rows have `truth_in_pool=1`, while `" + str(rt.get('zero_total_token_count')) + "` rows have zero total usage, `" + str(rt.get('llm_calls_short_count')) + "` rows have fewer than the expected four calls, and `" + str(rt.get('suspected_runtime_or_no_response_count')) + "` rows jointly show short calls, zero usage, and the observed >=45-second latency plateau.",
        "- Exact invalid-JSON, missing-field, and transport-timeout counts are **unavailable** because the historical CSVs did not persist raw responses or per-call status/error payloads. The flags are combined parser/schema/candidate-ID outcomes.",
        "- The pre-float-fix v2 June file is not usable training evidence because its `full_rr` and `nocf_rr` columns are boolean-like rather than numeric. v1 June is retained as a historical diagnostic, not silently substituted for corrected v2 data.",
        "",
    ]
    if reruns:
        lines += [
            "## Authorized rerun result",
            "",
            "- The June-only rerun used the authorized `Qwen3.5-4B` service and the same frozen panel, snapshot, temperature, and 700-token cap. The optional `reasoning_effort` field was omitted because this Qwen/vLLM deployment otherwise spent the 700-token completion budget on hidden reasoning and returned no JSON content.",
            "- The corrected rerun is evaluated separately from the historical GLM/v2 files; it does not overwrite them and it is not evidence of cross-model superiority.",
            "",
            "| rerun | rows | full parse | no-CF parse | per-step non-ok | client errors | response model | median latency | median total tokens | decision |",
            "|---|---:|---:|---:|---:|---:|---|---:|---:|---|",
        ]
        for r in reruns:
            pa = r.get("parse_anomaly", {})
            dq = r.get("data_quality", {})
            audit = r.get("per_step_observability", {})
            models = sorted({
                value for counts in audit.get("response_model_counts_by_step", {}).values()
                for value in counts if value != "<EMPTY>"
            })
            lines.append(
                f"| {r.get('label')} | {r.get('row_count', '—')} | "
                f"{pct(pa.get('full_parse_success_rate'), 1)} | "
                f"{pct(pa.get('nocf_parse_success_rate'), 1)} | "
                f"{audit.get('non_ok_total_count', '—')} | "
                f"{audit.get('client_error_total_count', '—')} | "
                f"{', '.join(models) or '—'} | "
                f"{dq.get('latency', {}).get('median', '—')}s | "
                f"{dq.get('tokens', {}).get('total_tokens', {}).get('median', '—')} | "
                f"{r.get('decision', '—')} |"
            )
        lines += [
            "",
            "For the rerun, all 1,000 full/no-CF outputs parsed, all events had four calls and nonzero usage, all candidate truths were supported, event keys were unique, RR columns were numeric, and the response model was `Qwen3.5-4B`. Two step-3 fusion responses were classified as unknown candidate IDs; both retained a valid final rank equal to the mask-stage rank, so the audit labels this as an explicit stage-3 candidate fallback rather than silently calling it a clean run.",
            "",
        ]
    lines += [
        "## June run summary",
        "",
        "| run | rows | full parse | no-CF parse | obs/mask/full/no-CF rank present | zero total tokens | calls <4 | median latency | numeric RR issue | decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in runs:
        if not r.get("exists"):
            lines.append(f"| {r['label']} | — | — | — | — | — | — | — | — | missing |")
            continue
        pa = r.get("parse_anomaly", {})
        dq = r.get("data_quality", {})
        ranks = dq.get("rank_observations", {})
        present = "/".join(str(ranks.get(a, {}).get("rank", {}).get("computable_positive_count", "?")) for a in ["obs", "mask", "full", "nocf"])
        lines.append(
            f"| {r['label']} | {r.get('row_count', '—')} | "
            f"{pct(pa.get('full_parse_success_rate'), 1)} ({pa.get('full_parse_failure_count', '—')} fail) | "
            f"{pct(pa.get('nocf_parse_success_rate'), 1)} ({pa.get('nocf_parse_failure_count', '—')} fail) | "
            f"{present} | {dq.get('tokens', {}).get('total_zero_count', '—')} | "
            f"{dq.get('runtime_error_observability', {}).get('llm_calls_short_count', '—')} | "
            f"{dq.get('latency', {}).get('median', '—')}s | "
            f"{dq.get('schema_value_checks', {}).get('numeric_columns', {}).get('full_rr', {}).get('bool_like_count', 0)}/"
            f"{dq.get('schema_value_checks', {}).get('numeric_columns', {}).get('nocf_rr', {}).get('bool_like_count', 0)} | "
            f"{r.get('decision', '—')} |"
        )
    lines += [
        "",
        "`obs/mask/full/no-CF rank present` is a count of positive numeric ranks, not a claim that the corresponding raw response was valid. For the v2 float-fix June run, the exact counts are shown in the JSON manifest; the missing ranks are a proxy for stage parse/schema/ID failure.",
        "",
        "## What is and is not observed",
        "",
        "| quantity | status | interpretation |",
        "|---|---|---|",
        "| event rows, unique event keys, duplicate keys | exact | recomputed from CSV |",
        "| candidate support (`truth_in_pool`) | exact | recomputed from CSV; support is not the June failure |",
        "| full/no-CF parse flags | exact as recorded | `1` means the run-level output path produced a valid usable result according to the old writer |",
        "| invalid JSON count | unavailable | raw completion text was not persisted |",
        "| missing required response field count | unavailable | raw parsed objects were not persisted |",
        "| exact timeout/transport-error count | unavailable | no per-call error/status column was persisted |",
        "| operational fallback count | derived | every parse flag failure treated as cheap fallback for router-data eligibility |",
        "| rerun per-step status/model/error/finish fields | exact for the instrumented rerun | persisted as aggregate fields without response text; two known step-3 candidate-ID fallbacks are visible |",
        "",
        "## Grouped diagnostics",
        "",
        "For June v2 float-fix, failure is not uniform across panel strata. The manifest records exact aggregate counts by stratum/activity; this is a diagnostic signal only because the CSV has no per-call timestamps or raw errors.",
        "",
        "| stratum | activity | n | full parse | no-CF parse | zero total tokens | short calls | median latency |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        *[
            f"| {g.get('stratum')} | {g.get('activity')} | {g.get('n')} | "
            f"{g.get('full_parse_success_count')}/{g.get('n')} | "
            f"{g.get('nocf_parse_success_count')}/{g.get('n')} | "
            f"{g.get('zero_total_tokens_count')} | {g.get('short_calls_count')} | "
            f"{g.get('median_latency_s')}s |"
            for g in next((r.get('grouped_diagnostics', {}).get('by_stratum_activity', []) for r in runs if r.get('run_id') == 'v2_floatfix_june'), [])
        ],
        "",
        "The local-weight preflight remains separate from the authorized shared-service run: the rerun manifest records `endpoint_scope=authorized_shared_qwen`, model `Qwen3.5-4B`, and no local model path. No prohibited endpoint, raw response text, bearer token, or another user's model weights were used.",
        "The runner's opt-in `--audit-details` mode was used for the real rerun and records per-step status/error class, response model, finish reason, token usage, reasoning presence, and latency without response text.",
        "",
        "## Cross-run and month comparison",
        "",
        "- The JSON manifest includes pairwise June event-key overlap and exact field-match counts. v1 and v2 candidate pools are intentionally different, so rank equality across versions is diagnostic only.",
        "- July/August reference summaries are included to test whether the anomaly is month-specific. They retain parse, RR schema, latency, and token summaries without copying response text.",
        "- Eval JSONL summaries are checked against recomputed row counts and parse rates. A matching summary does not repair the underlying lack of raw error observability.",
        "",
        "## Next action",
        "",
        "1. Keep the historical June v2 float-fix file quarantined; do not train the router on its raw gains, and do not silently substitute v1 June.",
        "2. The authorized Qwen rerun is structurally usable as corrected June training evidence only under the documented fallback policy: 1,000/1,000 full and no-CF parse, zero transport errors, and two explicit step-3 candidate-ID fallbacks to the mask-stage rank.",
        "3. If a strictly clean no-fallback label is required, rerun or separately review those two event keys before freezing the router dataset; otherwise carry the two-event exception into the router manifest and sensitivity check.",
        "",
        "## Reproducibility",
        "",
        f"- Audit script: `{report['audit_script']}`",
        f"- JSON manifest: `{report['json_output']}`",
        f"- Source root: `{report['source_root']}`",
        "- No raw response text, bearer token, endpoint credential, or prompt body is written by this audit.",
        "",
    ]
    return "\n".join(lines)


def rerun_instrumentation_summary(root: Path) -> dict[str, Any]:
    path = root / "src/agent/run_agent.py"
    if not path.exists():
        return {"path": str(path.relative_to(root)), "exists": False}
    text = path.read_text()
    launcher = root / "run_llm_june_local_vllm_rerun_20260910.sh"
    return {
        "runner_path": str(path.relative_to(root)),
        "runner_exists": True,
        "runner_sha256": sha256(path),
        "audit_details_flag_present": "--audit-details" in text,
        "per_step_status_helper_present": all(name in text for name in [
            "audited_chat", "response_status", "stage_audit"
        ]),
        "raw_response_persisted": False,
        "launcher_path": str(launcher.relative_to(root)),
        "launcher_exists": launcher.exists(),
        "launcher_sha256": sha256(launcher) if launcher.exists() else None,
        "launcher_refuses_unauthorized_endpoint": (
            launcher.exists() and "refusing unauthorized LLM_BASE_URL" in launcher.read_text()
        ),
        "launcher_allows_authorized_shared_qwen": (
            launcher.exists() and "http://10.63.0.82:31518/v1" in launcher.read_text()
        ),
        "launcher_refuses_overwrite": (
            launcher.exists() and "refusing to overwrite existing rerun artifact" in launcher.read_text()
        ),
        "client_reasoning_effort_override_present": (
            (root / "src/agent/llm_client.py").exists()
            and "LLM_REASONING_EFFORT" in (root / "src/agent/llm_client.py").read_text()
        ),
        "purpose": "Keep per-step client/parse/schema/candidate-ID status, usage, and latency for a new authorized Qwen/vLLM rerun without changing prompts or frozen evaluation inputs.",
    }


def resolve_input_path(root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def inferred_eval_path(run_path: Path) -> Path:
    return run_path.with_name(run_path.stem + "_eval.jsonl")


def inferred_manifest_path(run_path: Path) -> Path:
    return run_path.with_name(run_path.stem + "_manifest.json")


def read_manifest(path: Path, root: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": display_path(path, root)}
    try:
        obj = json.loads(path.read_text())
    except Exception as exc:
        return {"exists": True, "path": display_path(path, root), "read_error": f"{type(exc).__name__}: {exc}"}
    return {
        "exists": True,
        "path": display_path(path, root),
        "sha256": sha256(path),
        "run_type": obj.get("run_type"),
        "snapshot": obj.get("snapshot"),
        "model_name": obj.get("model_name"),
        "endpoint_scope": obj.get("endpoint_scope"),
        "base_url_is_authorized": obj.get("base_url_is_authorized"),
        "protocol": clean(obj.get("protocol", {})),
        "raw_responses_persisted": obj.get("raw_responses_persisted"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("/storage/gaoym/ex-graph-microtransaction-analysis"))
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--out-md", type=Path, default=None)
    ap.add_argument("--extra-run", action="append", type=Path, default=[],
                    help="Additional run CSV to audit; may be repeated.")
    ap.add_argument("--extra-eval", action="append", type=Path, default=[],
                    help="Eval JSONL paired by order with --extra-run; inferred when omitted.")
    ap.add_argument("--extra-manifest", action="append", type=Path, default=[],
                    help="Run manifest paired by order with --extra-run; inferred when omitted.")
    args = ap.parse_args()
    root = args.root.resolve()
    out_json = (args.out_json or root / "artifacts/llm_panel_v2/june_parse_audit.json").resolve()
    out_md = (args.out_md or root / "notes/june-parse-audit.md").resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    extra_run_specs = []
    extra_eval_specs = []
    for i, raw_run in enumerate(args.extra_run):
        run_path = resolve_input_path(root, raw_run)
        run_id = f"v2_local_vllm_june_rerun_{i + 1}"
        label = f"v2 June authorized Qwen/vLLM rerun {i + 1}"
        extra_run_specs.append({
            "run_id": run_id, "label": label,
            "path_obj": run_path, "variant": "v2_local_vllm_rerun",
            "status": "rerun_candidate",
            "manifest_obj": resolve_input_path(root, args.extra_manifest[i]) if i < len(args.extra_manifest) else inferred_manifest_path(run_path),
        })
        eval_path = resolve_input_path(root, args.extra_eval[i]) if i < len(args.extra_eval) else inferred_eval_path(run_path)
        extra_eval_specs.append({"run_id": run_id, "path_obj": eval_path, "label": label + " eval summary"})

    run_results: list[dict[str, Any]] = []
    run_map: dict[str, dict[str, Any]] = {}
    frames: dict[str, pd.DataFrame] = {}
    all_run_specs = [
        {**spec, "path_obj": root / spec["path"]} for spec in RUN_SPECS
    ] + extra_run_specs
    for spec in all_run_specs:
        result, frame = read_run(
            spec["path_obj"], root, run_id=spec["run_id"], label=spec["label"],
            variant=spec["variant"], status=spec["status"])
        if spec.get("manifest_obj") is not None:
            manifest = read_manifest(spec["manifest_obj"], root)
            result["run_manifest"] = manifest
            if spec.get("variant") == "v2_local_vllm_rerun":
                checks = result.setdefault("eligibility_checks", {})
                manifest_present = bool(manifest.get("exists")) and not manifest.get("read_error")
                manifest_authorized = manifest.get("base_url_is_authorized") is True
                manifest_model_exact = manifest.get("model_name") == "Qwen3.5-4B"
                checks["manifest_present_and_parseable"] = manifest_present
                checks["manifest_authorized_endpoint"] = manifest_authorized
                checks["manifest_model_exact"] = manifest_model_exact
                if not (manifest_present and manifest_authorized and manifest_model_exact):
                    result["decision"] = "not_eligible_missing_or_unauthorized_rerun_manifest"
        run_results.append(result)
        run_map[spec["run_id"]] = result
        if frame is not None and result.get("exists") and result.get("read_error") is None and all(c in frame for c in EVENT_KEY):
            frames[spec["run_id"]] = frame

    eval_results = [
        read_eval(root / spec["path"], root, run_id=spec["run_id"], label=spec["label"])
        for spec in EVAL_SPECS
    ] + [
        read_eval(spec["path_obj"], root, run_id=spec["run_id"], label=spec["label"])
        for spec in extra_eval_specs
    ]
    audit_script_path = Path(__file__).resolve()
    report: dict[str, Any] = {
        "audit_name": "june_llm_panel_parse_anomaly",
        "audit_version": "1.1",
        "generated_at": now_iso(),
        "source_root": str(root),
        "audit_script": str(audit_script_path.relative_to(root) if str(audit_script_path).startswith(str(root)) else audit_script_path),
        "audit_script_sha256": sha256(audit_script_path),
        "json_output": str(out_json.relative_to(root) if str(out_json).startswith(str(root)) else out_json),
        "markdown_output": str(out_md.relative_to(root) if str(out_md).startswith(str(root)) else out_md),
        "read_only_inputs": True,
        "raw_responses_printed_or_stored": False,
        "run_protocol": {
            "expected_calls_per_event": 4,
            "arms": ["cheap", "obs", "mask", "full", "nocf"],
            "parse_failure_fallback_policy_for_router": "cheap_rank",
            "exact_timeout_threshold_not_assumed": True,
        },
        "rerun_preflight": local_vllm_preflight(root),
        "rerun_instrumentation": rerun_instrumentation_summary(root),
        "rerun_execution_evidence": [
            r.get("run_manifest", {}) for r in run_results
            if r.get("variant") == "v2_local_vllm_rerun"
        ],
        "runs": run_results,
        "eval_summaries": eval_results,
        "eval_recomputed_consistency": eval_consistency(eval_results, run_map),
        "june_pairwise_comparisons": compare_runs(run_map, frames),
        "reference_months": reference_summary(root),
        "overall_decision": {
            "june_v2_floatfix_eligible_for_router_training": False,
            "v2_buggy_eligible_for_router_training": False,
            "v1_june_recommended_as_silent_substitute": False,
            "rerun_justified_by_audit": True,
            "rerun_performed_by_this_script": bool(extra_run_specs),
            "rerun_decisions": [
                {"run_id": r["run_id"], "decision": r.get("decision"),
                 "eligibility_checks": r.get("eligibility_checks", {})}
                for r in run_results if r.get("variant") == "v2_local_vllm_rerun"
            ],
            "reason": (
                "The historical June v2 float-fix run remains ineligible because its combined parse/usage "
                "anomaly was not per-call observable. Any authorized Qwen/vLLM rerun is evaluated separately "
                "with explicit per-step status, model, token, latency, fallback, schema, support, and event-key checks."
            ),
        },
    }
    report = clean(report)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    report["json_output"] = str(out_json.relative_to(root) if str(out_json).startswith(str(root)) else out_json)
    out_md.write_text(md_report(report))

    # Keep stdout structural and aggregate-only; it is safe to redirect to the
    # requested audit log.
    print(json.dumps({
        "audit": report["audit_name"],
        "generated_at": report["generated_at"],
        "runs": [
            {"run_id": r["run_id"], "exists": r.get("exists", False),
             "rows": r.get("row_count"), "decision": r.get("decision")}
            for r in run_results
        ],
        "overall_decision": report["overall_decision"],
        "outputs": {"json": str(out_json), "markdown": str(out_md)},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
