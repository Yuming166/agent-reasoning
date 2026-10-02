#!/usr/bin/env python3
"""Fail-closed continuation of the paused EX-Graph Astra6 cycle.

Only role calls without a frozen report are attempted. Every continuation gets
an unused task id and records the immediately preceding task as its parent.
Each HTTP request runs in an isolated child process so the parent can enforce
an absolute wall-clock deadline even if urllib is stuck in a socket read.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import researchd as r  # noqa: E402

CYCLE_ID = "20260920T101512Z"
CYCLE_DIR = r.RUNTIME / f"cycle_{CYCLE_ID}"
STATUS = r.RUNTIME / "RESEARCHD_STATUS.json"
WORKER = HERE / "astra6_call_worker.py"
PYTHON = Path(sys.executable)
HARD_DEADLINE_SECONDS = int(os.environ.get("ASTRA_HARD_DEADLINE_SECONDS", "420"))


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


def _kill_process_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _adopt_worker_result(
    client: r.Astra6Client,
    *,
    task_id: str,
    role: str,
    prompt: str,
    parent_task_id: str,
    response_path: Path,
    result_path: Path,
    started_at: float,
) -> str:
    """Finalize a result produced by an orphaned worker without resending."""
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise r.AstraUnavailable(f"worker_result_parse:{type(exc).__name__}:{exc}") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        raise r.AstraUnavailable(str((result or {}).get("error") if isinstance(result, dict) else "invalid worker result"))
    returned = result.get("returned_model")
    content = str(result.get("content") or "")
    status = int(result.get("http_status", 0))
    if status != 200 or returned != r.MODEL or not content.strip():
        raise r.AstraUnavailable(f"status={status}, returned_model={returned!r}, content={bool(content.strip())}")
    response_hash = r.sha256_text(content)
    r.write_text(response_path, content)
    r.append_jsonl(client.audit, {
        "event": "call_completed",
        "task_id": task_id,
        "timestamp": r.now_utc(),
        "role": role,
        "branch_id": "A-F",
        "parent_task_id": parent_task_id,
        "requested_model": client.model,
        "returned_model": returned,
        "prompt_hash": r.sha256_text(prompt),
        "response_hash": response_hash,
        "http_status": status,
        "usage": result.get("usage") or {},
        "attempts": 1,
        "latency_seconds": round(time.monotonic() - started_at, 3),
        "result_path": str(response_path),
        "execution": "adopted_orphan_worker_result",
    })
    return content


def hard_call(
    client: r.Astra6Client,
    *,
    task_id: str,
    role: str,
    prompt: str,
    parent_task_id: str,
    max_tokens: int,
    deadline_seconds: int = HARD_DEADLINE_SECONDS,
) -> str:
    """Run one new task id with a parent-owned wall-clock deadline."""
    started_before, completed = client._task_state(task_id)
    response_path = client.call_dir / f"{task_id}.response.txt"
    result_path = client.call_dir / f"{task_id}.worker.json"
    prompt_path = client.call_dir / f"{task_id}.prompt.txt"
    if completed:
        return response_path.read_text(encoding="utf-8")
    if started_before:
        # A prior hard-deadline parent may have disappeared while its isolated
        # worker continued. Adopt that one in-flight result; never issue a
        # second HTTP request for the same task id.
        if prompt_path.exists():
            wait_started = time.monotonic()
            while not result_path.exists() and time.monotonic() - wait_started < deadline_seconds:
                time.sleep(2)
            if result_path.exists():
                return _adopt_worker_result(
                    client, task_id=task_id, role=role, prompt=prompt,
                    parent_task_id=parent_task_id, response_path=response_path,
                    result_path=result_path, started_at=wait_started,
                )
        raise r.IncompleteAstraCall(f"incomplete prior call detected for {task_id}; fail-closed")

    prompt_hash = r.sha256_text(prompt)
    r.append_jsonl(client.audit, {
        "event": "call_started",
        "task_id": task_id,
        "timestamp": r.now_utc(),
        "role": role,
        "branch_id": "A-F",
        "parent_task_id": parent_task_id,
        "requested_model": client.model,
        "prompt_hash": prompt_hash,
        "result_path": str(response_path),
        "execution": "isolated_worker_hard_deadline",
        "deadline_seconds": deadline_seconds,
    })

    worker_log = client.call_dir / f"{task_id}.worker.stderr.log"
    r.write_text(prompt_path, prompt)
    if result_path.exists():
        result_path.unlink()

    command = [
        str(PYTHON),
        str(WORKER),
        "--prompt-file", str(prompt_path),
        "--result-file", str(result_path),
        "--max-tokens", str(max_tokens),
        "--socket-timeout", str(float(deadline_seconds)),
    ]
    started_at = time.monotonic()
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=worker_log.open("wb"),
        start_new_session=True,
        close_fds=True,
    )
    timeout = False
    try:
        proc.wait(timeout=deadline_seconds)
    except subprocess.TimeoutExpired:
        timeout = True
        _kill_process_tree(proc)
    finally:
        try:
            proc.stderr.close()  # type: ignore[union-attr]
        except Exception:
            pass
    latency = round(time.monotonic() - started_at, 3)

    if timeout:
        error = f"HardDeadline:absolute Astra6 call deadline exceeded ({deadline_seconds}s)"
        r.append_jsonl(client.audit, {
            "event": "call_failed",
            "task_id": task_id,
            "timestamp": r.now_utc(),
            "role": role,
            "branch_id": "A-F",
            "parent_task_id": parent_task_id,
            "requested_model": client.model,
            "prompt_hash": prompt_hash,
            "attempts": 1,
            "latency_seconds": latency,
            "error": error,
            "execution": "isolated_worker_hard_deadline",
        })
        raise r.AstraUnavailable(error)

    result = None
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            result = {"ok": False, "error": f"worker_result_parse:{type(exc).__name__}:{exc}"}
    if not isinstance(result, dict) or not result.get("ok"):
        worker_error = (result or {}).get("error") if isinstance(result, dict) else None
        error = worker_error or f"worker_exit_code={proc.returncode}; no valid result"
        r.append_jsonl(client.audit, {
            "event": "call_failed",
            "task_id": task_id,
            "timestamp": r.now_utc(),
            "role": role,
            "branch_id": "A-F",
            "parent_task_id": parent_task_id,
            "requested_model": client.model,
            "prompt_hash": prompt_hash,
            "attempts": 1,
            "latency_seconds": latency,
            "error": error,
            "worker_returncode": proc.returncode,
            "execution": "isolated_worker_hard_deadline",
        })
        raise r.AstraUnavailable(error)

    returned = result.get("returned_model")
    content = str(result.get("content") or "")
    status = int(result.get("http_status", 0))
    if status != 200 or returned != r.MODEL or not content.strip():
        error = f"status={status}, returned_model={returned!r}, content={bool(content.strip())}"
        r.append_jsonl(client.audit, {
            "event": "call_failed",
            "task_id": task_id,
            "timestamp": r.now_utc(),
            "role": role,
            "branch_id": "A-F",
            "parent_task_id": parent_task_id,
            "requested_model": client.model,
            "prompt_hash": prompt_hash,
            "attempts": 1,
            "latency_seconds": latency,
            "error": error,
            "execution": "isolated_worker_hard_deadline",
        })
        raise r.AstraUnavailable(error)

    response_hash = r.sha256_text(content)
    r.write_text(response_path, content)
    r.append_jsonl(client.audit, {
        "event": "call_completed",
        "task_id": task_id,
        "timestamp": r.now_utc(),
        "role": role,
        "branch_id": "A-F",
        "parent_task_id": parent_task_id,
        "requested_model": client.model,
        "returned_model": returned,
        "prompt_hash": prompt_hash,
        "response_hash": response_hash,
        "http_status": status,
        "usage": result.get("usage") or {},
        "attempts": 1,
        "latency_seconds": latency,
        "result_path": str(response_path),
        "execution": "isolated_worker_hard_deadline",
    })
    return content


def compact_context() -> str:
    priority = r.read_bounded(CYCLE_DIR / "priority_summary.json", 5000)
    neg = r.read_bounded(r.ROS / "NEGATIVE_RESULTS.md", 5500)
    ds = r.read_bounded(r.ROOT / "research/decision_state/DECISION_STATE_DECISION_20260919.md", 7000)
    ow = r.read_bounded(r.ROOT / "research/openworld/ow010b/reports/OW010B_DECISION.md", 3500)
    reports = []
    for role in r.ROLE_SPECS:
        p = CYCLE_DIR / f"{role}.md"
        if p.exists():
            reports.append(f"===== completed {role} =====\n{r.read_bounded(p, 2600)}")
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


def role_prompt(role: str, spec: str, context: str) -> str:
    return f"""You are the independent Astra6 role {role}, continuing a paused first-cycle audit.

Assignment:
{spec}

Return a concise report with exactly these headings:
1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)
2. Strongest evidence
3. Strongest counterargument
4. Cheapest decisive experiment
5. Stop condition
6. Literature/novelty verification still required

Use only the project evidence below. Do not invent citations. Do not relabel prior NO-GO findings as positive. Natural language must be central; do not claim true owner belief, causal intent, or social exposure. No large LLM experiment before the first falsification/literature gate.

{context}
"""


def manager_prompt(context: str, reports: dict[str, str]) -> str:
    joined = "\n\n".join(f"===== {k} =====\n{v}" for k, v in sorted(reports.items()))
    return f"""You are the Astra6 RESEARCH_MANAGER completing the first deployment cycle for EX-Graph.

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

Rules: at most 2-3 active branches; do not use textual voting; preserve NO-GO boundaries; downgrade Branch A if the case-level gap is absent or ambiguous; natural language must be central; no owner psychology or causal-belief claim; no large new LLM experiment before the first falsification gate; require an untouched temporal holdout for any continuation.

CONTEXT:
{context}

INDEPENDENT REPORTS:
{joined}
"""


def main() -> int:
    update("RESUMING_INCOMPLETE_ASTRA_TASKS", parent_pid=563546, hard_deadline_seconds=HARD_DEADLINE_SECONDS)
    client = r.Astra6Client(CYCLE_DIR)
    identity = client.identity_check(CYCLE_ID)
    r.write_json(CYCLE_DIR / "identity_check_resume_hard.json", identity)
    context = compact_context()

    reports: dict[str, str] = {}
    completed_roles: list[str] = []
    for role in r.ROLE_SPECS:
        report_path = CYCLE_DIR / f"{role}.md"
        if report_path.exists():
            reports[role] = report_path.read_text(encoding="utf-8")
            completed_roles.append(role)

    # Only these roles lacked a frozen report in the paused cycle. New task ids
    # are mandatory after an incomplete request; successful calls are never repeated.
    pending = [role for role in r.ROLE_SPECS if role not in reports]
    update("RESUMING_INCOMPLETE_ASTRA_TASKS", completed_roles=completed_roles, incomplete_roles=pending, hard_deadline_seconds=HARD_DEADLINE_SECONDS)

    for role in pending:
        prior = f"{CYCLE_ID}_{role}"
        audit_rows = []
        audit_path = CYCLE_DIR / "ASTRA6_CALL_AUDIT.jsonl"
        if audit_path.exists():
            for line in audit_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("role") == role:
                    audit_rows.append(row)
        existing_task_ids = {str(row.get("task_id")) for row in audit_rows}
        resume_n = 1
        while f"{prior}_resume{resume_n}" in existing_task_ids:
            resume_n += 1
        task_id = f"{prior}_resume{resume_n}"
        if resume_n == 1:
            parent_task_id = prior
        else:
            parent_task_id = f"{prior}_resume{resume_n - 1}"
        prompt = role_prompt(role, r.ROLE_SPECS[role], context)
        try:
            update("RUNNING_ASTRA_ROLE", current_role=role, completed_roles=completed_roles, incomplete_roles=pending, task_id=task_id, parent_task_id=parent_task_id, hard_deadline_seconds=HARD_DEADLINE_SECONDS)
            text = hard_call(
                client,
                task_id=task_id,
                role=role,
                prompt=prompt,
                parent_task_id=parent_task_id,
                max_tokens=2400,
            )
        except Exception as exc:
            update("PAUSED_FAIL_CLOSED", completed_roles=completed_roles, incomplete_roles=[x for x in pending if x not in completed_roles], current_role=role, task_id=task_id, error=f"{type(exc).__name__}:{exc}", hard_deadline_seconds=HARD_DEADLINE_SECONDS)
            r.append_jsonl(CYCLE_DIR / "FAILURE.jsonl", {
                "timestamp": r.now_utc(),
                "event": "hard_resume_call_failed",
                "role": role,
                "task_id": task_id,
                "parent_task_id": parent_task_id,
                "error": f"{type(exc).__name__}:{exc}",
                "hard_deadline_seconds": HARD_DEADLINE_SECONDS,
            })
            return 2
        reports[role] = text
        r.write_text(CYCLE_DIR / f"{role}.md", text)
        completed_roles.append(role)
        pending = [x for x in pending if x != role]
        update("RESUMING_INCOMPLETE_ASTRA_TASKS", completed_roles=completed_roles, incomplete_roles=pending, last_completed_role=role, hard_deadline_seconds=HARD_DEADLINE_SECONDS)

    manager_task_id = f"{CYCLE_ID}_RESEARCH_MANAGER_resume1"
    manager_parent = CYCLE_ID
    if (CYCLE_DIR / "ASTRA6_CALL_AUDIT.jsonl").exists() and manager_task_id in (CYCLE_DIR / "ASTRA6_CALL_AUDIT.jsonl").read_text(encoding="utf-8", errors="replace"):
        manager_task_id = f"{CYCLE_ID}_RESEARCH_MANAGER_resume2"
        manager_parent = f"{CYCLE_ID}_RESEARCH_MANAGER_resume1"
    update("RUNNING_ASTRA_MANAGER_SYNTHESIS", completed_roles=completed_roles, task_id=manager_task_id, hard_deadline_seconds=HARD_DEADLINE_SECONDS)
    try:
        synthesis = hard_call(
            client,
            task_id=manager_task_id,
            role="RESEARCH_MANAGER",
            prompt=manager_prompt(context, reports),
            parent_task_id=manager_parent,
            max_tokens=3200,
        )
    except Exception as exc:
        update("PAUSED_FAIL_CLOSED", completed_roles=completed_roles, incomplete_roles=[], current_role="RESEARCH_MANAGER", task_id=manager_task_id, error=f"{type(exc).__name__}:{exc}", hard_deadline_seconds=HARD_DEADLINE_SECONDS)
        r.append_jsonl(CYCLE_DIR / "FAILURE.jsonl", {
            "timestamp": r.now_utc(),
            "event": "hard_resume_manager_failed",
            "task_id": manager_task_id,
            "parent_task_id": manager_parent,
            "error": f"{type(exc).__name__}:{exc}",
            "hard_deadline_seconds": HARD_DEADLINE_SECONDS,
        })
        return 2

    r.write_text(CYCLE_DIR / "RESEARCH_MANAGER_RAW.md", synthesis)
    parsed = r.parse_json_loose(synthesis)
    r.write_json(CYCLE_DIR / "manager_synthesis.json", parsed if parsed is not None else {"parse_status": "failed", "raw": synthesis})
    priority = json.loads((CYCLE_DIR / "priority_summary.json").read_text(encoding="utf-8"))
    r.make_nightly_memo(CYCLE_DIR, CYCLE_ID, priority, dict(sorted(reports.items())), synthesis)
    r.write_json(CYCLE_DIR / "RUN_COMPLETE.json", {
        "cycle_id": CYCLE_ID,
        "completed_at": r.now_utc(),
        "status": "INITIAL_CYCLE_COMPLETE_WAITING_FOR_NEXT_PROTOCOL",
        "no_large_llm_experiment_started": True,
        "resumed_incomplete_calls": pending,
        "hard_deadline_seconds": HARD_DEADLINE_SECONDS,
    })
    update("WAITING_FOR_NEXT_PROTOCOL", completed_roles=completed_roles, incomplete_roles=[], next_rule="No large new LLM experiment before first falsification gate; inspect manager_synthesis.json and create a new protocol for continuation.", hard_deadline_seconds=HARD_DEADLINE_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
