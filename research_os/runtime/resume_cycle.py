#!/usr/bin/env python3
"""Resume only incomplete Astra6 tasks from a watchdog-paused first cycle.

Completed role calls are read from their frozen response files and are never
repeated. Incomplete role calls receive fresh task ids with an explicit resume
parent. Calls are serialized to reduce relay queue pressure and bounded by an
absolute per-call watchdog in the main thread.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import signal
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import researchd as r  # noqa: E402

CYCLE_ID = "20260920T101512Z"
CYCLE_DIR = r.RUNTIME / f"cycle_{CYCLE_ID}"
STATUS = r.RUNTIME / "RESEARCHD_STATUS.json"


class HardDeadline(Exception):
    pass


def alarm_handler(signum, frame):  # noqa: ARG001
    raise HardDeadline("absolute Astra6 call deadline exceeded")


def call_bounded(client: r.Astra6Client, *, task_id: str, role: str, prompt: str, max_tokens: int) -> str:
    previous = signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(360)
    try:
        return client.call(task_id=task_id, role=role, branch_id="A-F", prompt=prompt, parent_task_id=CYCLE_ID, max_tokens=max_tokens)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def compact_context() -> str:
    priority = r.read_bounded(CYCLE_DIR / "priority_summary.json", 5000)
    neg = r.read_bounded(r.ROS / "NEGATIVE_RESULTS.md", 5000)
    ds = r.read_bounded(r.ROOT / "research/decision_state/DECISION_STATE_DECISION_20260919.md", 7000)
    ow = r.read_bounded(r.ROOT / "research/openworld/ow010b/reports/OW010B_DECISION.md", 5000)
    reports = []
    for role in r.ROLE_SPECS:
        p = CYCLE_DIR / f"{role}.md"
        if p.exists():
            reports.append(f"===== completed {role} =====\n{r.read_bounded(p, 7000)}")
    return f"""EX-GRAPH ASTRA6-ONLY AUTORESEARCH RESUME CONTEXT
CHARTER_SHA256={r.CHARTER_HASH}

PRIORITY AUDIT:
{priority}

DECISION-STATE V1:
{ds}

OW-010B:
{ow}

NEGATIVE MEMORY:
{neg}

COMPLETED INDEPENDENT REPORTS:
{chr(10).join(reports)}

Do not repeat completed calls. This is still discovery-only. Do not start a large LLM experiment, do not retune a frozen test, and do not claim true owner psychology or causality.
"""


def update(state: str, **extra):
    payload = {
        "cycle_id": CYCLE_ID,
        "cycle_dir": str(CYCLE_DIR),
        "pid": os.getpid(),
        "updated_at": r.now_utc(),
        "state": state,
        "astra_only": True,
        "requested_model": r.MODEL,
        "charter_sha256": r.CHARTER_HASH,
        **extra,
    }
    r.write_json(STATUS, payload)


def main() -> int:
    update("RESUMING_INCOMPLETE_ASTRA_TASKS", parent_pid=555402)
    client = r.Astra6Client(CYCLE_DIR)
    identity = client.identity_check(CYCLE_ID)
    r.write_json(CYCLE_DIR / "identity_check_resume.json", identity)
    context = compact_context()
    reports = {}
    completed_roles = []
    incomplete_roles = []
    for role, spec in r.ROLE_SPECS.items():
        original = CYCLE_DIR / f"{role}.md"
        if original.exists():
            reports[role] = original.read_text(encoding="utf-8")
            completed_roles.append(role)
            continue
        incomplete_roles.append(role)
        prompt = f"""You are the independent Astra6 role {role}, resumed after an incomplete prior request.

Assignment:
{spec}

Return a concise report with exactly these headings:
1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)
2. Strongest evidence
3. Strongest counterargument
4. Cheapest decisive experiment
5. Stop condition
6. Literature/novelty verification still required

{context}
"""
        task_id = f"{CYCLE_ID}_{role}_resume1"
        try:
            text = call_bounded(client, task_id=task_id, role=role, prompt=prompt, max_tokens=2400)
        except Exception as exc:
            update("PAUSED_FAIL_CLOSED", completed_roles=completed_roles, incomplete_roles=incomplete_roles, error=f"{type(exc).__name__}:{exc}", resume_task=task_id)
            r.append_jsonl(CYCLE_DIR / "FAILURE.jsonl", {"timestamp": r.now_utc(), "event": "resume_call_failed", "role": role, "task_id": task_id, "error": f"{type(exc).__name__}:{exc}"})
            return 2
        reports[role] = text
        r.write_text(CYCLE_DIR / f"{role}.md", text)
        completed_roles.append(role)
        update("RESUMING_INCOMPLETE_ASTRA_TASKS", completed_roles=completed_roles, incomplete_roles=[x for x in incomplete_roles if x not in completed_roles])

    manager_prompt = f"""You are the Astra6 RESEARCH_MANAGER completing the first deployment cycle for EX-Graph.

Return JSON only:
{{
  "cycle_verdict":"...",
  "active_branches":[{{"branch_id":"A-F","state":"PROPOSED|LIT_AUDIT|PROBE|HOLD|KILLED|MODIFY","reason":"...","falsifier":"...","cheapest_next_experiment":"..."}}],
  "killed_or_deferred":["..."],
  "next_experiment":{{"experiment_id":"...","branch_id":"A-F","type":"deterministic_discovery|astra_literature_audit|new_protocol_required|HOLD","primary_outcome":"...","controls":["..."],"stop_rule":"...","large_llm_run_allowed":false}},
  "claim_ledger_updates":["..."],
  "reviewer_risks":["..."],
  "nightly_decision":"..."
}}

Rules: at most 2-3 active branches; do not use textual voting; no large new LLM experiment before the first falsification gate; preserve all NO-GO boundaries; natural language must be central; no owner psychology or causal-belief claim.

CONTEXT:
{context}

INDEPENDENT REPORTS:
{chr(10).join(f'===== {k} =====\n{v}' for k,v in sorted(reports.items()))}
"""
    update("RUNNING_ASTRA_MANAGER_SYNTHESIS", completed_roles=completed_roles)
    try:
        synthesis = call_bounded(client, task_id=f"{CYCLE_ID}_RESEARCH_MANAGER_resume1", role="RESEARCH_MANAGER", prompt=manager_prompt, max_tokens=3000)
    except Exception as exc:
        update("PAUSED_FAIL_CLOSED", completed_roles=completed_roles, error=f"{type(exc).__name__}:{exc}", resume_task=f"{CYCLE_ID}_RESEARCH_MANAGER_resume1")
        r.append_jsonl(CYCLE_DIR / "FAILURE.jsonl", {"timestamp": r.now_utc(), "event": "resume_manager_failed", "error": f"{type(exc).__name__}:{exc}"})
        return 2
    r.write_text(CYCLE_DIR / "RESEARCH_MANAGER_RAW.md", synthesis)
    parsed = r.parse_json_loose(synthesis)
    r.write_json(CYCLE_DIR / "manager_synthesis.json", parsed if parsed is not None else {"parse_status":"failed","raw":synthesis})
    r.make_nightly_memo(CYCLE_DIR, CYCLE_ID, json.loads((CYCLE_DIR / "priority_summary.json").read_text()), dict(sorted(reports.items())), synthesis)
    r.write_json(CYCLE_DIR / "RUN_COMPLETE.json", {"cycle_id":CYCLE_ID,"completed_at":r.now_utc(),"status":"INITIAL_CYCLE_COMPLETE_WAITING_FOR_NEXT_PROTOCOL","no_large_llm_experiment_started":True,"resumed_incomplete_calls":incomplete_roles})
    update("WAITING_FOR_NEXT_PROTOCOL", completed_roles=completed_roles, incomplete_roles=[], next_rule="No large new LLM experiment before first falsification gate; inspect manager_synthesis.json and create a new protocol for continuation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
