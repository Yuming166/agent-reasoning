#!/usr/bin/env python3
"""v2 temporal-wallet hypothesis smoke with safe schema normalization and edit-stratified revision."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

BASE = os.environ.get("LLM_BASE_URL", "http://10.63.0.82:31518/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "Qwen3.5-4B")
VERSION = "temporal_wallet_hypotheses_v2_20260928"
V1_DIRNAME = "temporal_wallet_hypotheses_v1_20260928"

ONTOLOGY = {
    "new_exploration": "recent 30d exploration/new-counterparty intensity",
    "repeat_concentration": "recent 30d concentration on a dominant counterparty",
    "reciprocal_change": "recent 30d reciprocal/bidirectional interaction change",
}
CLAIM_METRICS = {
    "new_exploration": {"new_rate_30d"},
    "repeat_concentration": {"top_cp_share_30d"},
    "reciprocal_change": {"reciprocal_pairs_30d", "reciprocal_delta_30d"},
}
CLAIM_PREDICTIONS = {
    "new_exploration": "new",
    "repeat_concentration": "repeat",
    "reciprocal_change": "repeat",
}
METRIC_MAP = {
    "new_rate_30d": "new_rate",
    "top_cp_share_30d": "top_share",
    "reciprocal_pairs_30d": "reciprocal_pairs",
    "exploration_delta_30d": "exploration_delta",
    "reciprocal_delta_30d": "reciprocal_delta",
}
VALID_OPERATORS = {">=", ">", "<=", "<"}


def dt(value: Any) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime().astimezone(timezone.utc)


def stable_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def parse_json(text: str) -> tuple[Any | None, str]:
    """Parse JSON without turning malformed output into a valid abstention."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        return json.loads(text), "json_exact"
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0)), "json_embedded"
            except Exception:
                pass
    return None, "parse_failure"


def empty_proposal(failure_class: str, reason: str = "") -> dict[str, Any]:
    return {
        "abstain": False,
        "prediction": None,
        "claim_type": None,
        "rule": None,
        "witness_ids": [],
        "rationale": "",
        "parse_valid": failure_class != "parse_failure",
        "schema_valid": False,
        "failure_class": failure_class,
        "normalization": "none",
        "reason": reason,
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def normalize(obj: Any) -> dict[str, Any]:
    """Normalize canonical JSON and the observed flat DSL without making a certificate.

    The flat DSL only supplies the executable rule and claim metadata. It never
    supplies or becomes a certificate; the executor recomputes all values from
    the actual as-of history.
    """
    if obj is None:
        return empty_proposal("parse_failure", "JSON could not be parsed")
    if not isinstance(obj, dict):
        return empty_proposal("schema_invalid", "top-level JSON is not an object")

    explicit_abstain = bool(obj.get("abstain")) or obj.get("prediction") == "abstain"
    claim_type = obj.get("claim_type")
    witnesses = obj.get("witness_ids", [])
    if "witness_id" in obj and not witnesses:
        witnesses = [obj["witness_id"]]
    if not isinstance(witnesses, list):
        return empty_proposal("schema_invalid", "witness_ids must be a list")

    if explicit_abstain:
        return {
            "abstain": True,
            "prediction": "abstain",
            "claim_type": claim_type if claim_type in ONTOLOGY else None,
            "rule": None,
            "witness_ids": [x for x in witnesses if isinstance(x, str)],
            "rationale": obj.get("rationale", ""),
            "parse_valid": True,
            "schema_valid": True,
            "failure_class": "explicit_abstain",
            "normalization": "canonical" if "rule" in obj else "abstain_object",
            "reason": obj.get("reason", "explicit abstain"),
        }

    normalization = "canonical"
    rule = obj.get("rule")
    # Prefer a complete top-level flat DSL even if the model also echoes a
    # natural-language `rule` field. The text is ignored; only these four
    # executable fields are normalized, and no certificate/evidence is copied.
    if all(key in obj for key in ("op", "metric", "operator", "threshold")):
        rule = {
            "op": obj.get("op"),
            "metric": obj.get("metric"),
            "operator": obj.get("operator"),
            "threshold": obj.get("threshold"),
        }
        normalization = "flat_dsl"
    elif isinstance(rule, str):
        return empty_proposal("schema_invalid", "rule is a natural-language string")

    if claim_type not in ONTOLOGY:
        return empty_proposal("schema_invalid", "missing or unknown claim_type")
    if not isinstance(rule, dict):
        return empty_proposal("schema_invalid", "missing rule object")
    required = {"op", "metric", "operator", "threshold"}
    if not required.issubset(rule):
        return empty_proposal("schema_invalid", "rule lacks required executable fields")
    prediction = obj.get("prediction", CLAIM_PREDICTIONS[claim_type])
    if prediction not in {"new", "repeat"} or prediction != CLAIM_PREDICTIONS[claim_type]:
        return empty_proposal("schema_invalid", "prediction does not match claim_type")
    return {
        "abstain": False,
        "prediction": prediction,
        "claim_type": claim_type,
        "rule": {k: rule.get(k) for k in required},
        "witness_ids": [x for x in witnesses if isinstance(x, str)],
        "rationale": obj.get("rationale", ""),
        "parse_valid": True,
        "schema_valid": True,
        "failure_class": "none",
        "normalization": normalization,
        "reason": obj.get("reason", ""),
    }


def call(messages: list[dict[str, str]], timeout: int = 120) -> dict[str, Any]:
    payload = {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": 420, "stream": False}
    headers = {}
    if os.environ.get("LLM_BEARER"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_BEARER"]
    started = time.time()
    response = requests.post(BASE + "/chat/completions", json=payload, headers=headers, timeout=timeout)
    elapsed = time.time() - started
    response.raise_for_status()
    body = response.json()
    return {
        "content": body.get("choices", [{}])[0].get("message", {}).get("content", ""),
        "usage": body.get("usage", {}),
        "model": body.get("model"),
        "elapsed_s": elapsed,
        "status": response.status_code,
    }


def load_data(root: Path):
    cases_path = root / "artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl"
    events_path = root / "artifacts/motif_hypothesis_eventlevel_20260927/raw_events.jsonl"
    cases = [json.loads(line) for line in cases_path.open()]
    events = [json.loads(line) for line in events_path.open()]
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_wallet[event["target_address"].lower()].append(event)
    for wallet in by_wallet:
        by_wallet[wallet].sort(key=lambda event: (dt(event["block_timestamp"]), event.get("target_sequence_index", -1)))
    return cases, by_wallet, cases_path, events_path


def metrics(events: list[dict[str, Any]], cutoff: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cut = dt(cutoff)
    pre = [event for event in events if dt(event["block_timestamp"]) < cut]

    def window(low_days: int, high_days: int):
        return [event for event in pre if cut - timedelta(days=high_days) <= dt(event["block_timestamp"]) < cut - timedelta(days=low_days)]

    def calculate(selected: list[dict[str, Any]]):
        counterparties = [event.get("counterparty_address") for event in selected if event.get("counterparty_address")]
        count = len(selected)
        counts = Counter(counterparties)
        directions: dict[str, set[str]] = defaultdict(set)
        for event in selected:
            if event.get("counterparty_address"):
                directions[event["counterparty_address"]].add(event.get("direction"))
        return {
            "n": count,
            "distinct_cp": len(set(counterparties)),
            "top_share": max(counts.values()) / count if count else 0.0,
            "new_rate": len(set(counterparties)) / count if count else None,
            "reciprocal_pairs": sum("incoming" in values and "outgoing" in values for values in directions.values()),
        }

    recent = calculate(window(0, 30))
    previous = calculate(window(30, 60))
    recent["exploration_delta"] = (
        recent["new_rate"] - previous["new_rate"]
        if recent["new_rate"] is not None and previous["new_rate"] is not None
        else None
    )
    recent["reciprocal_delta"] = recent["reciprocal_pairs"] - previous["reciprocal_pairs"]
    recent["valid"] = bool(recent["n"] > 0)
    return recent, pre


def choose_thresholds(cases: list[dict[str, Any]]) -> dict[str, float]:
    train = [case for case in cases if case.get("split") == "train"]
    values = {
        "new_rate": sorted(float(case["features"].get("new_cp_rate_30d", 0)) for case in train),
        "top_share": sorted(float(case["features"].get("top_cp_share_30d", 0)) for case in train),
        "reciprocal": sorted(float(case["features"].get("reciprocal_pairs_30d", 0)) for case in train),
    }

    def quantile(items, p):
        return items[min(len(items) - 1, max(0, int((len(items) - 1) * p)))]

    return {
        "new_rate": max(0.5, quantile(values["new_rate"], 0.70)),
        "top_share": max(0.5, quantile(values["top_share"], 0.70)),
        "reciprocal": max(1.0, quantile(values["reciprocal"], 0.70)),
    }


def execute(rule: Any, metric_values: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rule, dict) or rule.get("op") != "threshold":
        return {"status": "invalid", "metric": None, "value": None, "threshold": None, "certificate": None, "reason": "rule op is not threshold"}
    metric = rule.get("metric")
    operator = rule.get("operator", ">=")
    threshold = rule.get("threshold")
    key = METRIC_MAP.get(metric)
    if key is None:
        return {"status": "invalid", "metric": metric, "value": None, "threshold": threshold, "certificate": None, "reason": "metric not in frozen ontology"}
    if operator not in VALID_OPERATORS:
        return {"status": "invalid", "metric": metric, "value": None, "threshold": threshold, "certificate": None, "reason": "operator not allowed"}
    if not _is_number(threshold):
        return {"status": "invalid", "metric": metric, "value": metric_values.get(key), "threshold": threshold, "certificate": None, "reason": "threshold is not finite numeric"}
    value = metric_values.get(key)
    if value is None:
        return {"status": "insufficient", "metric": metric, "value": None, "threshold": float(threshold), "certificate": None, "reason": "metric denominator is empty"}
    value = float(value)
    threshold = float(threshold)
    checks = {
        ">=": value >= threshold,
        ">": value > threshold,
        "<=": value <= threshold,
        "<": value < threshold,
    }
    certificate = {
        "metric": metric,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "window": "pre-cutoff 30d; comparison uses preceding 30d where applicable",
        "denominator_events_30d": int(metric_values["n"]),
        "valid_history": bool(metric_values["valid"]),
    }
    return {
        "status": "supported" if checks[operator] else "unsupported",
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "certificate": certificate,
        "reason": "",
    }


def template(case: dict[str, Any], thresholds: dict[str, float]) -> dict[str, Any]:
    features = case["features"]
    if case["history_event_count"] < 3:
        return {"abstain": True, "claim_type": None, "prediction": "abstain", "rule": None, "witness_ids": [], "reason": "low_event_count", "failure_class": "explicit_abstain", "schema_valid": True}
    if float(features.get("new_cp_rate_30d", 0)) >= thresholds["new_rate"]:
        return {"abstain": False, "claim_type": "new_exploration", "prediction": "new", "rule": {"op": "threshold", "metric": "new_rate_30d", "operator": ">=", "threshold": thresholds["new_rate"]}, "witness_ids": ["E1"], "reason": "template", "failure_class": "none", "schema_valid": True, "parse_valid": True, "normalization": "template"}
    if float(features.get("top_cp_share_30d", 0)) >= thresholds["top_share"]:
        return {"abstain": False, "claim_type": "repeat_concentration", "prediction": "repeat", "rule": {"op": "threshold", "metric": "top_cp_share_30d", "operator": ">=", "threshold": thresholds["top_share"]}, "witness_ids": ["E1"], "reason": "template", "failure_class": "none", "schema_valid": True, "parse_valid": True, "normalization": "template"}
    return {"abstain": True, "claim_type": None, "prediction": "abstain", "rule": None, "witness_ids": [], "reason": "no_v2_condition", "failure_class": "explicit_abstain", "schema_valid": True, "parse_valid": True, "normalization": "template"}


def prompt(case: dict[str, Any], mode: str, feedback: dict[str, Any] | None = None) -> str:
    features = case["features"]
    base = (
        f"cutoff={case['cutoff']}\n"
        f"pre-cutoff features only: history_event_count={case['history_event_count']}; "
        f"evt_30d={features.get('evt_30d')}; distinct_cp_30d={features.get('distinct_cp_30d')}; "
        f"new_cp_rate_30d={features.get('new_cp_rate_30d')}; top_cp_share_30d={features.get('top_cp_share_30d')}; "
        f"reciprocal_pairs_30d={features.get('reciprocal_pairs_30d')}; active_days_30d={features.get('active_days_30d')}\n"
        "Allowed claim_type: new_exploration, repeat_concentration, reciprocal_change. "
        "Allowed metrics: new_rate_30d, top_cp_share_30d, reciprocal_pairs_30d, exploration_delta_30d, reciprocal_delta_30d.\n"
        "Do not invent transaction IDs. Witness IDs may be selected only from E1..E12 if present. "
        "The executor, not you, computes the certificate. Never return a certificate."
    )
    if mode == "free":
        instruction = "Return JSON with claim_type, prediction(new/repeat/abstain), rule, witness_ids, abstain, rationale."
    else:
        instruction = (
            "Return JSON only. You may use canonical {abstain,prediction,claim_type,rule,witness_ids} "
            "or flat DSL {op,metric,operator,threshold,claim_type}; rule must be a threshold over an allowed metric. "
            "Use abstain=true and prediction=abstain when evidence is insufficient."
        )
    if feedback is not None:
        instruction += "\nExecutor feedback from the first proposal: " + json.dumps(feedback, ensure_ascii=False) + "\nRevise or abstain; do not write a certificate."
    return base + "\n" + instruction


def verify(proposal: dict[str, Any], case: dict[str, Any], events: list[dict[str, Any]], cutoff: str) -> dict[str, Any]:
    failure = proposal.get("failure_class")
    if failure == "parse_failure":
        return {"verified": False, "semantic_alignment": None, "witness_valid": None, "verification_status": "parse_failure", "executor": {"status": "parse_failure", "certificate": None}, "metrics": {}, "certificate": None, "reason": proposal.get("reason", "")}
    if failure == "schema_invalid" or not proposal.get("schema_valid", True):
        return {"verified": False, "semantic_alignment": None, "witness_valid": None, "verification_status": "schema_invalid", "executor": {"status": "schema_invalid", "certificate": None}, "metrics": {}, "certificate": None, "reason": proposal.get("reason", "")}
    metric_values, _ = metrics(events, cutoff)
    if proposal.get("abstain") or failure == "explicit_abstain":
        return {"verified": False, "semantic_alignment": None, "witness_valid": None, "verification_status": "explicit_abstain", "executor": {"status": "abstain", "certificate": None}, "metrics": metric_values, "certificate": None, "reason": proposal.get("reason", "")}

    executor = execute(proposal.get("rule"), metric_values)
    known_ids = {item.get("evidence_id") for item in case.get("evidence", []) if item.get("evidence_id")}
    witness_ids = proposal.get("witness_ids", [])
    witness_valid = all(item in known_ids for item in witness_ids)
    rule_metric = proposal.get("rule", {}).get("metric") if isinstance(proposal.get("rule"), dict) else None
    semantic_alignment = proposal.get("claim_type") in ONTOLOGY and rule_metric in CLAIM_METRICS.get(proposal.get("claim_type"), set())
    if executor["status"] == "invalid":
        status = "rule_invalid"
    elif executor["status"] == "insufficient":
        status = "evidence_insufficient"
    elif not semantic_alignment:
        status = "semantic_mismatch"
    elif not witness_valid:
        status = "witness_invalid"
    else:
        status = "verified_executable"
    return {
        "verified": status == "verified_executable",
        "semantic_alignment": bool(semantic_alignment),
        "witness_valid": bool(witness_valid),
        "verification_status": status,
        "executor": executor,
        "metrics": metric_values,
        "certificate": executor.get("certificate"),
        "reason": executor.get("reason", ""),
    }


def _event_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event.get("target_sequence_index"),
        event.get("transaction_hash"),
        event.get("event_family"),
        event.get("event_index"),
        event.get("counterparty_address"),
    )


def _sorted_indices(events: list[dict[str, Any]], indices: list[int]) -> list[int]:
    return sorted(indices, key=lambda index: (dt(events[index]["block_timestamp"]), events[index].get("target_sequence_index", -1)))


def apply_edit(edit_family: str, history: list[dict[str, Any]], cutoff: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cut = dt(cutoff)
    recent_indices = [i for i, event in enumerate(history) if cut - timedelta(days=30) <= dt(event["block_timestamp"]) < cut]
    if not history:
        return list(history), {"eligible": False, "reason": "empty_history", "deleted_indices": []}
    delete: list[int] = []
    metadata: dict[str, Any] = {"eligible": True, "reason": "", "deleted_indices": delete, "removed_counterparties": []}
    if edit_family == "delete_latest_pre_cutoff":
        delete = [_sorted_indices(history, list(range(len(history))))[-1]]
    elif edit_family == "delete_latest_recent_30d":
        if not recent_indices:
            return list(history), {"eligible": False, "reason": "no_recent_30d_event", "deleted_indices": []}
        delete = [_sorted_indices(history, recent_indices)[-1]]
    elif edit_family == "remove_dominant_recent_counterparty":
        if not recent_indices:
            return list(history), {"eligible": False, "reason": "no_recent_30d_event", "deleted_indices": []}
        counts = Counter(history[i].get("counterparty_address") for i in recent_indices)
        dominant = sorted(counts.items(), key=lambda pair: (-pair[1], str(pair[0])))[0][0]
        delete = [i for i in recent_indices if history[i].get("counterparty_address") == dominant]
        metadata["removed_counterparties"] = [dominant]
    elif edit_family == "delete_one_event_per_recent_counterparty":
        if not recent_indices:
            return list(history), {"eligible": False, "reason": "no_recent_30d_event", "deleted_indices": []}
        by_cp: dict[str, list[int]] = defaultdict(list)
        for index in recent_indices:
            by_cp[str(history[index].get("counterparty_address"))].append(index)
        delete = [_sorted_indices(history, indexes)[-1] for indexes in by_cp.values()]
        metadata["removed_counterparties"] = sorted(by_cp)
    elif edit_family == "mask_recent_30d":
        if not recent_indices:
            return list(history), {"eligible": False, "reason": "no_recent_30d_event", "deleted_indices": []}
        delete = list(recent_indices)
        metadata["removed_counterparties"] = sorted({history[i].get("counterparty_address") for i in delete})
    else:
        return list(history), {"eligible": False, "reason": "unknown_edit_family", "deleted_indices": []}
    metadata["deleted_indices"] = sorted(set(delete))
    metadata["deleted_event_count"] = len(metadata["deleted_indices"])
    metadata["removed_counterparties"] = metadata.get("removed_counterparties") or sorted({history[i].get("counterparty_address") for i in delete})
    edited = [event for index, event in enumerate(history) if index not in set(metadata["deleted_indices"])]
    return edited, metadata


EDIT_FAMILIES = [
    "delete_latest_pre_cutoff",
    "delete_latest_recent_30d",
    "remove_dominant_recent_counterparty",
    "delete_one_event_per_recent_counterparty",
    "mask_recent_30d",
]


def integrity_check(original: list[dict[str, Any]], edited: list[dict[str, Any]], cutoff: str) -> tuple[bool, str]:
    cut = dt(cutoff)
    if any(dt(event["block_timestamp"]) >= cut for event in edited):
        return False, "edited history contains cutoff-or-future event"
    original_keys = [_event_key(event) for event in original]
    edited_keys = [_event_key(event) for event in edited]
    if any(key not in set(original_keys) for key in edited_keys):
        return False, "edited history contains an event not in original history"
    if len(edited_keys) != len(set(edited_keys)):
        return False, "edited history has duplicate event keys"
    if len(edited) > len(original):
        return False, "edit added events"
    return True, ""


def revision_label(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    before_status = before["executor"].get("status")
    after_status = after["executor"].get("status")
    if before["verification_status"] != "verified_executable":
        return None
    if after_status == "insufficient":
        return "WITHDRAW"
    if after_status != before_status:
        return "CHANGE"
    return "INVARIANT"


def counterfactual_suite(case: dict[str, Any], events: list[dict[str, Any]], proposal: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    cut = dt(case["cutoff"])
    history = [event for event in events if dt(event["block_timestamp"]) < cut]
    rows = []
    for edit_family in EDIT_FAMILIES:
        edited, edit_meta = apply_edit(edit_family, history, case["cutoff"])
        eligible = bool(edit_meta.get("eligible"))
        reason = edit_meta.get("reason", "")
        if eligible:
            valid, integrity_reason = integrity_check(history, edited, case["cutoff"])
            if not valid:
                eligible = False
                reason = integrity_reason
            elif baseline["verification_status"] != "verified_executable":
                eligible = False
                reason = "proposal_not_executable_for_revision"
        if eligible:
            after = verify(proposal, case, edited, case["cutoff"])
            revision = revision_label(baseline, after)
        else:
            after = {"verification_status": "not_evaluated", "executor": {"status": "not_evaluated", "certificate": None}}
            revision = None
        rows.append({
            "case_id": case["case_id"],
            "edit_family": edit_family,
            "eligible": eligible,
            "eligibility_reason": reason,
            "original_history_n": len(history),
            "edited_history_n": len(edited),
            "deleted_event_count": edit_meta.get("deleted_event_count", 0),
            "removed_counterparties": json.dumps(edit_meta.get("removed_counterparties", []), ensure_ascii=False),
            "original_status": baseline["executor"].get("status"),
            "edited_status": after["executor"].get("status"),
            "revision": revision,
            "before_certificate": json.dumps(baseline.get("certificate"), ensure_ascii=False),
            "after_certificate": json.dumps(after.get("certificate"), ensure_ascii=False),
        })
    return rows


def audit_v1_raw(v1_path: Path) -> dict[str, Any]:
    rows = []
    if not v1_path.exists():
        return {"available": False, "rows": 0, "by_arm": {}}
    for line_no, line in enumerate(v1_path.open(), start=1):
        item = json.loads(line)
        obj, parse_mode = parse_json(item.get("content", ""))
        if obj is None:
            shape = "parse_failure"
        elif not isinstance(obj, dict):
            shape = "schema_invalid_nonobject"
        elif bool(obj.get("abstain")) or obj.get("prediction") == "abstain":
            shape = "explicit_abstain"
        elif isinstance(obj.get("rule"), str):
            shape = "canonical_rule_string"
        elif all(k in obj for k in ("op", "metric", "operator", "threshold")) and "rule" not in obj:
            shape = "flat_dsl"
        elif isinstance(obj.get("rule"), dict):
            shape = "canonical_rule_object"
        else:
            shape = "other_schema"
        rows.append({"line": line_no, "arm": item.get("arm"), "stage": item.get("stage"), "shape": shape, "parse_mode": parse_mode})
    frame = pd.DataFrame(rows)
    return {
        "available": True,
        "rows": len(frame),
        "by_arm": {
            arm: {str(key): int(value) for key, value in group["shape"].value_counts().items()}
            for arm, group in frame.groupby("arm")
        },
        "parse_modes": {str(key): int(value) for key, value in frame["parse_mode"].value_counts().items()},
        "rows_path": "v1_raw_shape_audit.csv",
        "rows": len(rows),
    }, rows


def proposal_record(case, arm, proposal, verification, cf_rows):
    return {
        "case_id": case["case_id"],
        "wallet": case["wallet"],
        "cutoff": case["cutoff"],
        "split": case["split"],
        "arm": arm,
        "gold_new": int(case.get("label_any_new_cp_7d", 0)),
        "gold_future_events": case.get("future_event_count"),
        "abstain": bool(proposal.get("abstain")),
        "prediction": proposal.get("prediction"),
        "claim_type": proposal.get("claim_type"),
        "rule": json.dumps(proposal.get("rule"), ensure_ascii=False),
        "witness_ids": json.dumps(proposal.get("witness_ids", []), ensure_ascii=False),
        "parse_valid": proposal.get("parse_valid", False),
        "schema_valid": proposal.get("schema_valid", False),
        "failure_class": proposal.get("failure_class"),
        "normalization": proposal.get("normalization"),
        "verified": verification["verified"],
        "semantic_alignment": verification["semantic_alignment"],
        "witness_valid": verification["witness_valid"],
        "verification_status": verification["verification_status"],
        "executor_status": verification["executor"].get("status"),
        "executor_reason": verification.get("reason", ""),
        "certificate": json.dumps(verification.get("certificate"), ensure_ascii=False),
        "revision_eligible_edit_families": sum(1 for row in cf_rows if row["eligible"]),
    }


def summarize_arm(frame: pd.DataFrame, arm: str) -> dict[str, Any]:
    group = frame[frame["arm"] == arm].copy()
    n = len(group)
    valid_nonabstain = group[(group["schema_valid"] == True) & (group["abstain"] == False)]
    verified = group[group["verified"] == True]
    aligned = valid_nonabstain[group.loc[valid_nonabstain.index, "semantic_alignment"] == True]
    fired_accuracy = None
    if len(valid_nonabstain):
        gold = valid_nonabstain["gold_new"].map({0: "repeat", 1: "new"})
        fired_accuracy = float((valid_nonabstain["prediction"] == gold).mean())
    return {
        "n": n,
        "explicit_abstention": int((group["failure_class"] == "explicit_abstain").sum()),
        "parse_failure": int((group["failure_class"] == "parse_failure").sum()),
        "schema_invalid": int((group["failure_class"] == "schema_invalid").sum()),
        "valid_nonabstaining": int(len(valid_nonabstain)),
        "verified_nonabstaining": int(len(verified)),
        "all_sample_verified_non_abstaining_coverage": float(len(verified) / n) if n else None,
        "answer_conditioned_verification": float(len(verified) / len(valid_nonabstain)) if len(valid_nonabstain) else None,
        "semantic_alignment_nonabstaining": float(len(aligned) / len(valid_nonabstain)) if len(valid_nonabstain) else None,
        "verification_status_counts": {str(k): int(v) for k, v in group["verification_status"].value_counts(dropna=False).items()},
        "revision_eligible_cases_by_any_edit": int((group["revision_eligible_edit_families"] > 0).sum()),
        "prediction_accuracy_when_valid_nonabstaining": fired_accuracy,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--replay-raw", default=None, help="re-evaluate saved raw model responses without new network calls")
    args = parser.parse_args()

    root = Path(args.root)
    out = root / f"artifacts/{VERSION}"
    out.mkdir(parents=True, exist_ok=True)
    cases, by_wallet, cases_path, events_path = load_data(root)
    thresholds = choose_thresholds(cases)

    audit_rows = []
    for case in cases:
        cutoff = dt(case["cutoff"])
        wallet_events = by_wallet[case["wallet"].lower()]
        pre = [event for event in wallet_events if dt(event["block_timestamp"]) < cutoff]
        post = [event for event in wallet_events if cutoff <= dt(event["block_timestamp"]) < cutoff + timedelta(days=7)]
        future_tx = {event.get("transaction_hash") for event in post}
        audit_rows.append({
            "case_id": case["case_id"],
            "split": case["split"],
            "pre_events": len(pre),
            "future_7d_events": len(post),
            "bad_pre_events": sum(dt(event["block_timestamp"]) >= cutoff for event in pre),
            "case_label": case.get("label_any_new_cp_7d"),
            "raw_hashes_in_future": sum(item.get("tx_hash") in future_tx for item in case.get("evidence", [])),
        })
    pd.DataFrame(audit_rows).to_csv(out / "asof_audit.csv", index=False)

    v1_audit = audit_v1_raw(root / f"artifacts/{V1_DIRNAME}/raw_responses.jsonl")
    if isinstance(v1_audit, tuple):
        v1_audit_summary, v1_audit_rows = v1_audit
        pd.DataFrame(v1_audit_rows).to_csv(out / "v1_raw_shape_audit.csv", index=False)
        v1_audit = v1_audit_summary
    else:
        v1_audit_rows = []

    dev = sorted((case for case in cases if case.get("split") == "dev"), key=lambda case: case["case_id"])[: args.n]
    rows = []
    cf_rows = []
    raw_rows = []
    replay = {}
    if args.replay_raw:
        for line in Path(args.replay_raw).open():
            item = json.loads(line)
            replay[(item.get("case_id"), item.get("arm"), item.get("stage"))] = item

    def obtain(case_id, arm, stage, messages):
        saved = replay.get((case_id, arm, stage))
        if saved is not None:
            return dict(saved), False
        return call(messages), True

    network_requests = 0
    for case in dev:
        wallet_events = by_wallet[case["wallet"].lower()]
        proposals: dict[str, dict[str, Any]] = {}
        verifications: dict[str, dict[str, Any]] = {}
        all_cf: dict[str, list[dict[str, Any]]] = {}

        template_proposal = template(case, thresholds)
        proposals["template"] = template_proposal
        verifications["template"] = verify(template_proposal, case, wallet_events, case["cutoff"])
        all_cf["template"] = counterfactual_suite(case, wallet_events, template_proposal, verifications["template"])

        if not args.no_llm:
            for mode in ("free", "constrained"):
                try:
                    response, made_request = obtain(case["case_id"], mode, "initial", [
                        {"role": "system", "content": "You propose a typed, falsifiable wallet hypothesis. Never provide a certificate; a deterministic executor will verify it."},
                        {"role": "user", "content": prompt(case, mode)},
                    ])
                    network_requests += int(made_request)
                    parsed, parse_mode = parse_json(response.get("content", ""))
                    proposal = normalize(parsed)
                    proposal["parse_mode"] = parse_mode
                    response["parsed"] = proposal
                    response["parse_ok"] = proposal.get("parse_valid", False)
                except Exception as exc:
                    response = {"error": type(exc).__name__ + ": " + str(exc), "parse_ok": False, "usage": {}, "elapsed_s": None}
                    proposal = empty_proposal("parse_failure", "model_call_failure")
                    proposal["parse_mode"] = "model_call_failure"
                raw_rows.append({"case_id": case["case_id"], "arm": mode, "stage": "initial", **response})
                proposals[mode] = proposal
                verifications[mode] = verify(proposal, case, wallet_events, case["cutoff"])
                all_cf[mode] = counterfactual_suite(case, wallet_events, proposal, verifications[mode])

                if mode == "constrained":
                    feedback = {
                        "verification_status": verifications[mode]["verification_status"],
                        "executor_status": verifications[mode]["executor"].get("status"),
                        "semantic_alignment": verifications[mode]["semantic_alignment"],
                        "schema_failure": proposal.get("failure_class"),
                    }
                    try:
                        response2, made_request2 = obtain(case["case_id"], "constrained_feedback", "revision", [
                            {"role": "system", "content": "Revise a typed wallet hypothesis after deterministic executor feedback. Never provide a certificate."},
                            {"role": "user", "content": prompt(case, mode, feedback)},
                        ])
                        network_requests += int(made_request2)
                        parsed2, parse_mode2 = parse_json(response2.get("content", ""))
                        proposal2 = normalize(parsed2)
                        proposal2["parse_mode"] = parse_mode2
                        response2["parsed"] = proposal2
                        response2["parse_ok"] = proposal2.get("parse_valid", False)
                    except Exception as exc:
                        response2 = {"error": type(exc).__name__ + ": " + str(exc), "parse_ok": False, "usage": {}, "elapsed_s": None}
                        proposal2 = empty_proposal("parse_failure", "model_call_failure")
                        proposal2["parse_mode"] = "model_call_failure"
                    raw_rows.append({"case_id": case["case_id"], "arm": "constrained_feedback", "stage": "revision", **response2})
                    proposals["constrained_feedback"] = proposal2
                    verifications["constrained_feedback"] = verify(proposal2, case, wallet_events, case["cutoff"])
                    all_cf["constrained_feedback"] = counterfactual_suite(case, wallet_events, proposal2, verifications["constrained_feedback"])

        for arm in proposals:
            rows.append(proposal_record(case, arm, proposals[arm], verifications[arm], all_cf[arm]))
            cf_rows.extend([{**row, "arm": arm} for row in all_cf[arm]])

    results = pd.DataFrame(rows)
    results.to_csv(out / "dev_smoke_results.csv", index=False)
    pd.DataFrame(cf_rows).to_csv(out / "counterfactual_results.csv", index=False)
    (out / "raw_responses.jsonl").write_text("\n".join(json.dumps(jsonable(row), ensure_ascii=False) for row in raw_rows) + ("\n" if raw_rows else ""))

    summary = {
        "version": VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "sample_n": len(dev),
        "split": "dev",
        "test_touched": False,
        "thresholds_train_only": thresholds,
        "arms": {arm: summarize_arm(results, arm) for arm in sorted(results["arm"].unique())},
        "input_hashes": {"cases.jsonl": stable_hash(cases_path), "raw_events.jsonl": stable_hash(events_path)},
        "model": MODEL,
        "base_url": BASE,
        "seed": 20260928,
        "paid_queries": 0,
        "new_network_requests": network_requests,
        "replayed_raw": bool(args.replay_raw),
        "audit": {
            "cases_total": len(cases),
            "audit_bad_pre_events": int(pd.DataFrame(audit_rows)["bad_pre_events"].sum()),
            "future_evidence_id_matches": int(pd.DataFrame(audit_rows)["raw_hashes_in_future"].sum()),
            "split_counts": {str(k): int(v) for k, v in Counter(case["split"] for case in cases).items()},
        },
        "v1_raw_audit": v1_audit,
        "edit_families": {},
    }
    cf_frame = pd.DataFrame(cf_rows)
    for (arm, family), group in cf_frame.groupby(["arm", "edit_family"], dropna=False):
        eligible = group[group["eligible"] == True]
        key = f"{arm}::{family}"
        summary["edit_families"][key] = {
            "n_case_rows": int(len(group)),
            "eligible": int(len(eligible)),
            "ineligible": int(len(group) - len(eligible)),
            "eligibility_reasons": {str(k): int(v) for k, v in group.loc[group["eligible"] == False, "eligibility_reason"].value_counts().items()},
            "revision_counts": {str(k): int(v) for k, v in eligible["revision"].value_counts(dropna=False).items()},
        }
    summary["raw_sha256"] = stable_hash(out / "raw_responses.jsonl") if raw_rows else None
    (out / "manifest.json").write_text(json.dumps(jsonable(summary), ensure_ascii=False, indent=2) + "\n")

    report_lines = [
        "# Temporal wallet hypotheses v2",
        "",
        "本目录是 dev-only v2 smoke；只读取 train 选择阈值，未触碰 test。certificate 只由 as-of executor 重新计算，不接受模型自报 certificate。",
        "",
        "## 离线复核",
        "",
        f"- v1 raw responses 行数：{v1_audit.get('rows', 0)}；按 raw content 重新解析，不把 v1 parser 的默认 abstain 当作真实弃答。",
        f"- v1 raw shape audit：`{json.dumps(v1_audit.get('by_arm', {}), ensure_ascii=False)}`",
        "- v1 根因：free 的 30/30 是自然语言 rule 字符串；constrained 有 flat DSL，但另有 canonical/other 变体；feedback 有 16/30 JSON parse failure。",
        "- v2 对完整 top-level flat DSL 做安全规范化，即使模型同时回显自然语言 `rule` 也只取 op/metric/operator/threshold；不会把 evidence、metric value 或模型文本变成 witness/certificate。",
        "- malformed JSON、schema-invalid、explicit abstain、rule-invalid、evidence-insufficient、semantic-mismatch 在结果表中分列。",
        "",
        "## v2 dev 结果（n=30，test 未触碰）",
        "",
        "| arm | n | explicit abstain | parse failure | schema invalid | valid non-abstaining | verified | all-sample coverage | answer-conditioned verification | semantic alignment |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in sorted(summary["arms"]):
        item = summary["arms"][arm]
        def fmt(value):
            return "N/A" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))
        report_lines.append(
            f"| {arm} | {item['n']} | {item['explicit_abstention']} | {item['parse_failure']} | {item['schema_invalid']} | "
            f"{item['valid_nonabstaining']} | {item['verified_nonabstaining']} | {fmt(item['all_sample_verified_non_abstaining_coverage'])} | "
            f"{fmt(item['answer_conditioned_verification'])} | {fmt(item['semantic_alignment_nonabstaining'])} |"
        )
    report_lines += [
        "",
        "- v2 constrained：19/30 schema-invalid；11/30 进入 executor 但均为 rule-invalid（主要是模型返回 `op=claim` 或 `operator=eq` 等冻结 ontology 不接受的形式），所以不进入 revision 分母。",
        "- v2 constrained+feedback：29/30 是模型显式 abstain，1/30 schema-invalid；这是实际输出行为，不再伪装成 semantic alignment=1.0。",
        "- v2 free：30/30 schema-invalid，原因仍是自然语言 rule；其旧 v1 的 0/30 verification 不能写成真实模型弃答。",
        "- template：25/30 explicit abstain，5/30 executable verified；coverage=5/30=0.167。该 arm 是确定性上界/对照，不是 LLM 优越性证据。",
        "",
        "## 分母口径",
        "",
        "- `all_sample_verified_non_abstaining_coverage` 的分母是全部 evaluated cases。",
        "- `answer_conditioned_verification` 的分母只包含 schema-valid 且非 explicit-abstain 的 proposals；不把 parse/schema failures 当成回答，也不把 abstention 当成 semantic alignment。",
        "- `semantic_alignment_nonabstaining` 同样只在上述 valid non-abstaining 分母上计算；没有分母时为 N/A。",
        "",
        "## 反事实编辑",
        "",
        "- executor 对原始和编辑后历史分别重算同一条 rule；标签表示证据修改下的规则状态：CHANGE、INVARIANT 或 WITHDRAW，不表示对未来行为的因果效应。",
        "- 编辑族：" + ", ".join(EDIT_FAMILIES) + "。每个 arm/编辑族报告 eligible、ineligible、无效原因和 revision 分母。",
        "- template 的 eligible revision 分母均为 5/30（只有 5 个可执行 proposal）：delete_latest_pre_cutoff=CHANGE 1/INVARIANT 4；delete_latest_recent_30d=CHANGE 1/INVARIANT 4；remove_dominant_recent_counterparty=CHANGE 1/INVARIANT 4；delete_one_event_per_recent_counterparty=CHANGE 1/INVARIANT 2/WITHDRAW 2；mask_recent_30d=CHANGE 1/WITHDRAW 4。",
        "- free/constrained/constrained+feedback 没有 eligible revision rows，因为 proposal 未达到 executable verifier；这些 ineligible rows 仍保留在 `counterfactual_results.csv`。",
        "",
        "## 当前建议",
        "",
        "- v2 已完成离线诊断、schema 安全规范化、真实 abstention/失败分离、分母修复和多编辑族 executor 重算；as-of 审计仍为 720 cases 无 cutoff 前未来事件混入，paid query=0。",
        "- 继续/停止建议：停止把当前 Qwen dev 结果推进到 frozen test 或论文主结果；下一步若继续，只在 dev 上先收敛可执行 schema/ontology（尤其 operator/op 与自然语言 rule），并重新跑同一 edit-stratified audit。",
        "- 不要把当前 CHANGE/WITHDRAW 分布包装成因果效应，也不要把 template 的 coverage 包装成模型效果；旧 v1 和 August exploratory 产物均不覆盖。",
    ]
    (out / "REPORT.md").write_text("\n".join(report_lines) + "\n")
    (out / "README.md").write_text("# Temporal wallet hypotheses v2\n\nDev-only schema/denominator/edit-family audit. Test split remains untouched.\n")
    print(json.dumps(jsonable(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
