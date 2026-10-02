#!/usr/bin/env python3
"""Astra6-only first-cycle research orchestrator for EX-Graph.

This process deliberately implements only the charter's deployment-first cycle:
- deterministic ingestion/audit of frozen artifacts;
- case-level Decision-State Evidence--Validity discovery analysis;
- independent Astra6 literature/phenomenon/NLP/design/falsifier audits;
- Astra6 research-manager synthesis;
- no automatic large LLM experiment before the first falsification gate.

It is fail-closed: no fallback provider, no local cognitive model, and a
non-200/mismatched Astra response pauses the cognitive queue.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
import re
import threading
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
ROS = ROOT / "research_os"
RUNTIME = ROS / "runtime"
RESULTS = ROOT / "research/decision_state/results"
CONFIG = Path("/home/gaoym/.codex/astra.config.toml")
MODEL = "gpt-6-astra"
CHARTER_HASH = (RUNTIME / "CHARTER_SHA256.txt").read_text().strip().split()[0]

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
BRANCHES = {
    "A": "Evidence-Validity Gap",
    "B": "Behavioral Equifinality",
    "C": "Falsifiable Behavioral Hypothesis Induction",
    "D": "Behavioral Hypothesis Revision",
    "E": "Predictability x Interpretability",
    "F": "Identifiability-Aware Selective Inference",
}

LOG_LOCK = threading.Lock()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
    with LOG_LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(value.rstrip("\n") + "\n", encoding="utf-8")
    tmp.replace(path)


def read_bounded(path: Path, max_chars: int = 14000) -> str:
    if not path.exists():
        return f"[missing: {path}]"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n[truncated at {max_chars} chars]"


def update_status(status_path: Path, cycle_id: str, state: str, **extra: Any) -> None:
    payload = {
        "cycle_id": cycle_id,
        "updated_at": now_utc(),
        "state": state,
        "astra_only": True,
        "requested_model": MODEL,
        "charter_sha256": CHARTER_HASH,
        **extra,
    }
    write_json(status_path, payload)


class AstraUnavailable(RuntimeError):
    pass


class IncompleteAstraCall(RuntimeError):
    pass


class Astra6Client:
    def __init__(self, cycle_dir: Path):
        cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        provider = cfg.get("model_providers", {}).get("astra", {})
        self.base_url = str(provider.get("base_url", "")).rstrip("/")
        self.api_key = str(provider.get("experimental_bearer_token", ""))
        self.model = str(cfg.get("model", ""))
        if self.model != MODEL:
            raise AstraUnavailable(f"configured model mismatch: {self.model!r}")
        if not self.base_url.endswith("/v1") or not self.api_key:
            raise AstraUnavailable("Astra configuration is incomplete")
        self.audit = cycle_dir / "ASTRA6_CALL_AUDIT.jsonl"
        self.call_dir = cycle_dir / "calls"
        self.call_dir.mkdir(parents=True, exist_ok=True)
        self.identity_audit = cycle_dir / "MODEL_IDENTITY_AUDIT.jsonl"

    def _task_state(self, task_id: str) -> tuple[bool, bool]:
        response_path = self.call_dir / f"{task_id}.response.txt"
        started = False
        completed = response_path.exists()
        if self.audit.exists():
            for line in self.audit.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("task_id") == task_id and row.get("event") == "call_started":
                    started = True
        return started, completed

    def identity_check(self, cycle_id: str) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + "/models", method="GET")
        req.add_header("Authorization", "Bearer " + self.api_key)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read())
                status = int(response.status)
        except Exception as exc:
            row = {
                "event": "identity_check_failed",
                "cycle_id": cycle_id,
                "timestamp": now_utc(),
                "requested_model": self.model,
                "error": f"{type(exc).__name__}:{exc}",
            }
            append_jsonl(self.identity_audit, row)
            raise AstraUnavailable(str(exc)) from exc
        listed = sorted(str(x.get("id")) for x in payload.get("data", []) if isinstance(x, dict))
        result = {
            "event": "identity_check",
            "cycle_id": cycle_id,
            "timestamp": now_utc(),
            "requested_model": self.model,
            "http_status": status,
            "listed_model_count": len(listed),
            "requested_model_listed": self.model in listed,
            "latency_seconds": round(time.monotonic() - started, 3),
        }
        append_jsonl(self.identity_audit, result)
        if status != 200 or self.model not in listed:
            raise AstraUnavailable("Astra6 model identity check failed")
        return result

    def call(self, *, task_id: str, role: str, branch_id: str, prompt: str, parent_task_id: str | None = None,
             max_tokens: int = 4200) -> str:
        started_before, completed = self._task_state(task_id)
        response_path = self.call_dir / f"{task_id}.response.txt"
        if completed:
            return response_path.read_text(encoding="utf-8")
        if started_before:
            raise IncompleteAstraCall(f"incomplete prior call detected for {task_id}; fail-closed")
        prompt_hash = sha256_text(prompt)
        append_jsonl(self.audit, {
            "event": "call_started",
            "task_id": task_id,
            "timestamp": now_utc(),
            "role": role,
            "branch_id": branch_id,
            "parent_task_id": parent_task_id,
            "requested_model": self.model,
            "prompt_hash": prompt_hash,
            "result_path": str(response_path),
        })
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an Astra6 scientific research agent. Do not reveal private chain-of-thought; return only the requested concise report or JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "reasoning_effort": "max",
            "max_tokens": max_tokens,
        }
        body = canonical(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.api_key)
        max_attempts = 3
        last_error: str | None = None
        started_at = time.monotonic()
        for attempt in range(1, max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=300) as response:
                    raw = response.read(8_000_000)
                    status = int(response.status)
                data = json.loads(raw)
                returned = data.get("model")
                choices = data.get("choices") or []
                content = ""
                if choices and isinstance(choices[0], dict):
                    content = str((choices[0].get("message") or {}).get("content") or "")
                if status != 200 or returned != MODEL or not content.strip():
                    raise AstraUnavailable(f"status={status}, returned_model={returned!r}, content={bool(content.strip())}")
                response_hash = sha256_text(content)
                response_path.write_text(content, encoding="utf-8")
                append_jsonl(self.audit, {
                    "event": "call_completed",
                    "task_id": task_id,
                    "timestamp": now_utc(),
                    "role": role,
                    "branch_id": branch_id,
                    "parent_task_id": parent_task_id,
                    "requested_model": self.model,
                    "returned_model": returned,
                    "prompt_hash": prompt_hash,
                    "response_hash": response_hash,
                    "http_status": status,
                    "usage": data.get("usage") or {},
                    "attempts": attempt,
                    "latency_seconds": round(time.monotonic() - started_at, 3),
                    "result_path": str(response_path),
                })
                return content
            except urllib.error.HTTPError as exc:
                detail = exc.read(4096).decode("utf-8", errors="replace")
                last_error = f"http_{exc.code}:{detail[:300]}"
                retryable = exc.code in {429, 500, 502, 503, 504}
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"transport:{type(exc).__name__}:{exc}"
                retryable = True
            except AstraUnavailable as exc:
                last_error = str(exc)
                retryable = False
            except Exception as exc:
                last_error = f"{type(exc).__name__}:{exc}"
                retryable = False
            if not retryable or attempt >= max_attempts:
                append_jsonl(self.audit, {
                    "event": "call_failed",
                    "task_id": task_id,
                    "timestamp": now_utc(),
                    "role": role,
                    "branch_id": branch_id,
                    "parent_task_id": parent_task_id,
                    "requested_model": self.model,
                    "prompt_hash": prompt_hash,
                    "attempts": attempt,
                    "error": last_error,
                })
                raise AstraUnavailable(last_error or "Astra6 call failed")
            time.sleep(min(10 * attempt, 30))
        raise AstraUnavailable(last_error or "Astra6 call failed")


def rank_corr(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3 or frame.x.nunique() < 2 or frame.y.nunique() < 2:
        return float("nan")
    return float(frame.x.rank(method="average").corr(frame.y.rank(method="average")))


def pearson(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3 or frame.x.nunique() < 2 or frame.y.nunique() < 2:
        return float("nan")
    return float(frame.x.corr(frame.y))


def jsonable(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def run_priority_analysis(cycle_dir: Path) -> dict[str, Any]:
    source = RESULTS / "decision_state_case_degradation_analysis.csv"
    df = pd.read_csv(source, low_memory=False)
    required = ["oos_loss_available", "intervention_sensitivity", "delta_B4_vs_B0_macro"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"priority source missing columns: {missing}")
    work = df[df["oos_loss_available"].astype(bool)].copy()
    work = work[work["split"].isin(["dev", "test"])].copy()
    work["F_intervention_sensitivity"] = pd.to_numeric(work["intervention_sensitivity"], errors="coerce")
    work["Delta_B4_minus_B0"] = pd.to_numeric(work["delta_B4_vs_B0_macro"], errors="coerce")
    work["prospective_validity_proxy"] = -work["Delta_B4_minus_B0"]
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=["F_intervention_sensitivity", "Delta_B4_minus_B0"])
    if len(work) < 100:
        raise RuntimeError(f"too few OOS rows for priority analysis: {len(work)}")
    try:
        work["F_quintile"] = pd.qcut(work["F_intervention_sensitivity"], 5, labels=["Q1_low", "Q2", "Q3", "Q4", "Q5_high"], duplicates="drop").astype(str)
    except ValueError:
        work["F_quintile"] = "all"
    work.to_csv(cycle_dir / "priority_case_level.csv", index=False)

    quintile_rows = []
    for (split, bucket), g in work.groupby(["split", "F_quintile"], dropna=False):
        quintile_rows.append({
            "split": split,
            "F_quintile": bucket,
            "n": int(len(g)),
            "F_mean": float(g.F_intervention_sensitivity.mean()),
            "Delta_mean_B4_minus_B0": float(g.Delta_B4_minus_B0.mean()),
            "Delta_median": float(g.Delta_B4_minus_B0.median()),
            "validity_gain_rate_Delta_lt_0": float((g.Delta_B4_minus_B0 < 0).mean()),
            "severe_failure_rate_Delta_gt_0_1": float((g.Delta_B4_minus_B0 > 0.1).mean()),
        })
    pd.DataFrame(quintile_rows).to_csv(cycle_dir / "priority_by_F_quintile.csv", index=False)

    controls = [
        "history_length_log1p_events_30d", "history_event_count_30d", "event_count_7d",
        "llm_top_probability", "llm_abstain", "hypothesis_entropy_nats", "panel_repeat_wallet",
    ]
    numeric = [c for c in controls if c in work.columns]
    categorical = [c for c in ["split", "activity_bin", "dominant_event_family_30d"] if c in work.columns]
    x_parts = []
    for c in numeric:
        values = pd.to_numeric(work[c], errors="coerce")
        med = values.median()
        if not np.isfinite(med):
            med = 0.0
        x_parts.append(values.fillna(med).replace([np.inf, -np.inf], 0.0).to_numpy(dtype=float))
    if categorical:
        dummies = pd.get_dummies(work[categorical].astype(str), drop_first=True, dtype=float)
        x_parts.extend(dummies.to_numpy(dtype=float).T)
    X = np.column_stack([np.ones(len(work))] + x_parts) if x_parts else np.ones((len(work), 1))
    yF = work.F_intervention_sensitivity.to_numpy(dtype=float)
    yD = work.Delta_B4_minus_B0.to_numpy(dtype=float)
    betaF = np.linalg.lstsq(X, yF, rcond=None)[0]
    betaD = np.linalg.lstsq(X, yD, rcond=None)[0]
    residF = yF - X @ betaF
    residD = yD - X @ betaD
    partial = pearson(pd.Series(residF), pd.Series(residD))

    high_fail = work[(work.F_intervention_sensitivity >= work.F_intervention_sensitivity.quantile(0.75)) & (work.Delta_B4_minus_B0 > 0)].sort_values("Delta_B4_minus_B0", ascending=False).head(50)
    low_success = work[(work.F_intervention_sensitivity <= work.F_intervention_sensitivity.quantile(0.25)) & (work.Delta_B4_minus_B0 < 0)].sort_values("Delta_B4_minus_B0").head(50)
    cols = [c for c in ["case_id", "split", "anchor_wallet", "F_intervention_sensitivity", "Delta_B4_minus_B0", "activity_bin", "history_event_count_30d", "event_count_7d", "panel_repeat_wallet", "llm_top_probability", "hypothesis_entropy_nats", "dominant_event_family_30d"] if c in work.columns]
    high_fail[cols].to_csv(cycle_dir / "high_F_failure_cases.csv", index=False)
    low_success[cols].to_csv(cycle_dir / "low_F_success_cases.csv", index=False)

    summary = {
        "source": str(source),
        "source_sha256": sha256_bytes(source.read_bytes()),
        "n_all_source_rows": int(len(df)),
        "n_oos_rows": int(len(work)),
        "splits": {str(k): int(v) for k, v in work.split.value_counts().to_dict().items()},
        "F_definition": "existing frozen intervention_sensitivity = average of self/market JS distances over four consequence dimensions",
        "Delta_definition": "existing frozen B4_M1_VERIFIED_LLM macro log-loss minus B0_M1 macro log-loss",
        "F_vs_Delta_pearson": pearson(work.F_intervention_sensitivity, work.Delta_B4_minus_B0),
        "F_vs_validity_proxy_spearman": rank_corr(work.F_intervention_sensitivity, work.prospective_validity_proxy),
        "F_vs_Delta_spearman": rank_corr(work.F_intervention_sensitivity, work.Delta_B4_minus_B0),
        "partial_pearson_F_vs_Delta_controls": partial,
        "controls_numeric": numeric,
        "controls_categorical": categorical,
        "mean_Delta_B4_minus_B0": float(work.Delta_B4_minus_B0.mean()),
        "median_Delta_B4_minus_B0": float(work.Delta_B4_minus_B0.median()),
        "B4_gain_rate": float((work.Delta_B4_minus_B0 < 0).mean()),
        "B4_failure_rate": float((work.Delta_B4_minus_B0 > 0).mean()),
        "high_F_failure_n": int(len(high_fail)),
        "low_F_success_n": int(len(low_success)),
        "discovery_only": True,
        "no_new_llm_calls": True,
        "future_outcomes_used_only_from_frozen_evaluation_artifact": True,
        "status": "DISCOVERY_AUDIT_COMPLETE",
    }
    write_json(cycle_dir / "priority_summary.json", jsonable(summary))
    report = [
        "# Decision-State case-level Evidence–Validity discovery audit",
        "",
        "This is a deterministic, discovery-only audit of frozen OOS predictions. It is not a confirmatory result and does not modify the V1 protocol or test set.",
        "",
        f"- OOS rows: **{summary['n_oos_rows']}** ({summary['splits']})",
        f"- F = frozen intervention sensitivity; Delta = B4 macro log-loss minus B0 macro log-loss.",
        f"- Pearson(F, Delta): **{summary['F_vs_Delta_pearson']:.4f}**",
        f"- Spearman(F, validity proxy -Delta): **{summary['F_vs_validity_proxy_spearman']:.4f}**",
        f"- Partial Pearson(F, Delta | predeclared controls): **{summary['partial_pearson_F_vs_Delta_controls']:.4f}**",
        f"- Mean Delta: **{summary['mean_Delta_B4_minus_B0']:.6f}**; median Delta: **{summary['median_Delta_B4_minus_B0']:.6f}**",
        f"- B4 gain rate (Delta < 0): **{summary['B4_gain_rate']:.3f}**; failure rate (Delta > 0): **{summary['B4_failure_rate']:.3f}**",
        "",
        "## Outputs",
        "",
        "- `priority_case_level.csv`: case-level F/Delta and frozen descriptors.",
        "- `priority_by_F_quintile.csv`: discovery strata by intervention sensitivity.",
        "- `high_F_failure_cases.csv`: high-sensitivity cases where B4 degraded.",
        "- `low_F_success_cases.csv`: low-sensitivity cases where B4 improved.",
        "",
        "## Boundary",
        "",
        "This audit cannot establish causality, true belief, owner psychology, generalization beyond the frozen panel, or a final paper claim. Any follow-up requires Astra6 adversarial review and a new preregistered protocol/untouched holdout.",
    ]
    write_text(cycle_dir / "PRIORITY_DISCOVERY_REPORT.md", "\n".join(report))
    return jsonable(summary)


def build_dossier(cycle_dir: Path, priority: dict[str, Any]) -> str:
    phase1 = read_bounded(ROOT / "research/final_handoff/PHASE1_SUMMARY.md", 9000)
    phase2 = read_bounded(ROOT / "research/phase2/PHASE2_HANDOFF.md", 9000)
    ow = read_bounded(ROOT / "research/openworld/ow010b/reports/OW010B_DECISION.md", 8000)
    ds = read_bounded(ROOT / "research/decision_state/DECISION_STATE_DECISION_20260919.md", 9000)
    neg = read_bounded(ROS / "NEGATIVE_RESULTS.md", 5000)
    priority_text = read_bounded(cycle_dir / "PRIORITY_DISCOVERY_REPORT.md", 7000)
    branches = "\n".join(f"- {k}: {v}" for k, v in BRANCHES.items())
    return f"""PROJECT: EX-Graph Ethereum on-chain behavioral inference, NAACL-oriented autoresearch.
DATE: {now_utc()}
CHARTER_SHA256: {CHARTER_HASH}

NON-NEGOTIABLE BOUNDARIES:
- Astra6 is the only cognitive model; no fallback.
- Address-level actor proxy, not verified owner psychology or true belief.
- Existing August frozen tests cannot be retuned.
- No large new LLM experiment before initial falsification/literature gate.
- Natural language must be a scientific object, not merely a reporting layer.
- Discovery results are not confirmatory.

INITIAL BRANCHES:
{branches}

FROZEN PROJECT HISTORY — PHASE I:
{phase1}

FROZEN PROJECT HISTORY — PHASE II-A:
{phase2}

FROZEN PROJECT HISTORY — OW-010B:
{ow}

FROZEN PROJECT HISTORY — DECISION-STATE V1:
{ds}

APPEND-ONLY NEGATIVE MEMORY:
{neg}

NEW DETERMINISTIC PRIORITY AUDIT SUMMARY:
{json.dumps(priority, ensure_ascii=False, indent=2)}

NEW PRIORITY AUDIT REPORT:
{priority_text}
"""


ROLE_SPECS = {
    "LIT_SCOUT": "Audit nearest literature/task/method/terminology overlap for Branches A-F. Do not invent exact citations; mark verification-needed items. Decide which branches are genuinely NLP-central.",
    "GAP_AUDITOR": "Attack novelty and NLP centrality. Try to collapse each branch into existing intent classification, explanation, uncertainty, graph prediction, or anomaly detection. State which claims survive only as hypotheses.",
    "PHENOMENON_SCOUT": "Inspect the frozen Decision-State case-level discovery audit. Identify only reproducible descriptive patterns, alternative explanations, and whether an Evidence-Validity Gap exists at case level.",
    "NLP_ARCHITECT": "Design the smallest language-centered representation/evaluation that would make a surviving branch genuinely NLP-central: semantic non-redundancy, evidence alignment, future implications, falsifiers, or revision. Reject cosmetic text.",
    "EXPERIMENT_DESIGNER": "Design the cheapest decisive next experiment for the strongest 1-3 branches. Include sample, target, controls, primary metric, stop/no-go rule, untouched holdout, and deterministic-vs-Astra6 boundaries. Do not propose a large experiment first.",
    "FALSIFIER": "Assume the current preferred story is wrong. Find confounds and construct kill tests for A-F, especially equifinality versus ordinary uncertainty, intervention sensitivity versus prompt sensitivity, and activity/autoregression.",
}


def role_prompt(role: str, spec: str, dossier: str) -> str:
    return f"""You are the independent Astra6 role {role} in an Astra6-only scientific autoresearch system.

Your assigned responsibility:
{spec}

Read the dossier below as the only project evidence. Do not use hidden future outcomes beyond what is explicitly identified as frozen evaluation. Do not claim that any previous NO-GO is positive by renaming it. Do not claim true owner belief or causal intent. Do not prescribe a large LLM run before the charter's first falsification gate.

Return a concise report with exactly these headings:
1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)
2. Strongest evidence
3. Strongest counterargument
4. Cheapest decisive experiment
5. Stop condition
6. Literature/novelty verification still required

DOSSIER:
{dossier}
"""


def synthesis_prompt(dossier: str, reports: dict[str, str]) -> str:
    joined = "\n\n".join(f"===== {role} =====\n{text}" for role, text in reports.items())
    return f"""You are the Astra6 RESEARCH_MANAGER. Synthesize independent reports for the first deployment cycle of the EX-Graph NAACL autoresearch.

Charter constraints:
- select at most 2-3 high-value live branches;
- do not decide by textual majority alone; prefer the cheapest information-gain experiment;
- keep discovery, freeze, replication, and scaling separate;
- no large new LLM experiment before the first falsification gate;
- if the case-level evidence-validity gap is absent or ambiguous, downgrade Branch A rather than forcing an identifiability story;
- every proposed claim needs a falsifier and an untouched-holdout plan;
- reject owner-psychology, causal-belief, social-crosswalk, and graph-as-temporal-stream claims.

Return JSON only with this schema:
{{
  "cycle_verdict": "...",
  "active_branches": [
    {{"branch_id":"A-F","state":"PROPOSED|LIT_AUDIT|PROBE|HOLD|KILLED|MODIFY","reason":"...","falsifier":"...","cheapest_next_experiment":"..."}}
  ],
  "killed_or_deferred": ["..."],
  "next_experiment": {{"experiment_id":"...","branch_id":"A-F","type":"deterministic_discovery|astra_literature_audit|new_protocol_required|HOLD","primary_outcome":"...","controls":["..."],"stop_rule":"...","large_llm_run_allowed":false}},
  "claim_ledger_updates": ["..."],
  "reviewer_risks": ["..."],
  "nightly_decision": "..."
}}

PROJECT DOSSIER:
{dossier}

INDEPENDENT REPORTS:
{joined}
"""


def parse_json_loose(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def make_nightly_memo(cycle_dir: Path, cycle_id: str, priority: dict[str, Any], reports: dict[str, str], synthesis_text: str) -> None:
    synthesis = parse_json_loose(synthesis_text)
    if synthesis is None:
        synthesis_section = synthesis_text
        verdict = "ASTRA_SYNTHESIS_NOT_JSON_REQUIRES_REVIEW"
    else:
        synthesis_section = json.dumps(synthesis, ensure_ascii=False, indent=2)
        verdict = str(synthesis.get("cycle_verdict", "UNSPECIFIED"))
    active = synthesis.get("active_branches", []) if isinstance(synthesis, dict) else []
    memo = [
        f"# NIGHTLY RESEARCH DECISION — {cycle_id}",
        "",
        f"Cycle verdict: **{verdict}**",
        "",
        "## Deterministic priority audit",
        "",
        f"- OOS rows: {priority['n_oos_rows']}",
        f"- Pearson(F, Delta): {priority['F_vs_Delta_pearson']}",
        f"- Spearman(F, -Delta): {priority['F_vs_validity_proxy_spearman']}",
        f"- Partial Pearson after predeclared controls: {priority['partial_pearson_F_vs_Delta_controls']}",
        "- Status: discovery-only; no new LLM calls; no frozen test retuning.",
        "",
        "## Astra6 manager synthesis",
        "",
        "```json",
        synthesis_section,
        "```",
        "",
        "## Independent reports",
        "",
    ]
    for role, text in reports.items():
        memo += [f"### {role}", "", text, ""]
    memo += [
        "## Runtime boundary",
        "",
        "The first cycle stops before a large new LLM experiment. Any next experiment must be represented by a new frozen protocol/experiment id and use an untouched temporal holdout.",
    ]
    write_text(cycle_dir / "NIGHTLY_RESEARCH_DECISION.md", "\n".join(memo))
    write_json(cycle_dir / "manager_synthesis.json", synthesis if synthesis is not None else {"raw": synthesis_text, "parse_status": "failed"})


def main() -> int:
    cycle_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cycle_dir = RUNTIME / f"cycle_{cycle_id}"
    cycle_dir.mkdir(parents=True, exist_ok=False)
    current = RUNTIME / "current_cycle"
    if current.exists() or current.is_symlink():
        current.unlink()
    current.symlink_to(cycle_dir, target_is_directory=True)
    status_path = RUNTIME / "RESEARCHD_STATUS.json"
    write_json(cycle_dir / "RUN_MANIFEST.json", {
        "cycle_id": cycle_id,
        "started_at": now_utc(),
        "charter_sha256": CHARTER_HASH,
        "root": str(ROOT),
        "model": MODEL,
        "python": os.sys.executable,
        "pid": os.getpid(),
        "mode": "initial_deployment_cycle_discovery_first",
        "no_fallback": True,
    })
    update_status(status_path, cycle_id, "STARTING", cycle_dir=str(cycle_dir), pid=os.getpid())
    try:
        update_status(status_path, cycle_id, "RUNNING_DETERMINISTIC_PRIORITY_AUDIT", cycle_dir=str(cycle_dir), pid=os.getpid())
        priority = run_priority_analysis(cycle_dir)
        dossier = build_dossier(cycle_dir, priority)
        write_text(cycle_dir / "EVIDENCE_DOSSIER.md", dossier)
        update_status(status_path, cycle_id, "ASTRA_IDENTITY_CHECK", cycle_dir=str(cycle_dir), pid=os.getpid(), priority_summary=priority)
        client = Astra6Client(cycle_dir)
        identity = client.identity_check(cycle_id)
        write_json(cycle_dir / "identity_check.json", identity)
        update_status(status_path, cycle_id, "RUNNING_INDEPENDENT_ASTRA_AUDITS", cycle_dir=str(cycle_dir), pid=os.getpid(), priority_summary=priority)
        reports: dict[str, str] = {}
        errors: list[str] = []
        concurrency = min(3, len(ROLE_SPECS))
        def one(role_spec: tuple[str, str]) -> tuple[str, str]:
            role, spec = role_spec
            prompt = role_prompt(role, spec, dossier)
            text = client.call(task_id=f"{cycle_id}_{role}", role=role, branch_id="A-F", prompt=prompt)
            return role, text
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(one, item) for item in ROLE_SPECS.items()]
            for future in concurrent.futures.as_completed(futures):
                try:
                    role, text = future.result()
                    reports[role] = text
                    write_text(cycle_dir / f"{role}.md", text)
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}:{exc}")
        if errors or len(reports) != len(ROLE_SPECS):
            raise AstraUnavailable("independent Astra audit failure: " + "; ".join(errors))
        update_status(status_path, cycle_id, "RUNNING_ASTRA_MANAGER_SYNTHESIS", cycle_dir=str(cycle_dir), pid=os.getpid(), reports=list(reports))
        synthesis = client.call(
            task_id=f"{cycle_id}_RESEARCH_MANAGER",
            role="RESEARCH_MANAGER",
            branch_id="A-F",
            prompt=synthesis_prompt(dossier, reports),
            parent_task_id=cycle_id,
            max_tokens=5000,
        )
        write_text(cycle_dir / "RESEARCH_MANAGER_RAW.md", synthesis)
        make_nightly_memo(cycle_dir, cycle_id, priority, dict(sorted(reports.items())), synthesis)
        update_status(status_path, cycle_id, "WAITING_FOR_NEXT_PROTOCOL", cycle_dir=str(cycle_dir), pid=os.getpid(), priority_summary=priority, completed_roles=sorted(reports), next_rule="No large new LLM experiment before first falsification gate; inspect manager_synthesis.json and create a new protocol for any continuation.")
        write_json(cycle_dir / "RUN_COMPLETE.json", {"cycle_id": cycle_id, "completed_at": now_utc(), "status": "INITIAL_CYCLE_COMPLETE_WAITING_FOR_NEXT_PROTOCOL", "no_large_llm_experiment_started": True})
        return 0
    except Exception as exc:
        update_status(status_path, cycle_id, "PAUSED_FAIL_CLOSED", cycle_dir=str(cycle_dir), pid=os.getpid(), error=f"{type(exc).__name__}:{exc}", resume_rule="Do not repeat an incomplete Astra6 call automatically; inspect ASTRA6_CALL_AUDIT.jsonl and resume with explicit task handling.")
        append_jsonl(cycle_dir / "FAILURE.jsonl", {"timestamp": now_utc(), "error": f"{type(exc).__name__}:{exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
