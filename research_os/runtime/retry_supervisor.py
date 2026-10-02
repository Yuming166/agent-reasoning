#!/usr/bin/env python3
"""User-authorized Astra6-only retry supervisor for the EX-Graph cycle.

This does not add a fallback model or perform local scientific reasoning. It
relaunches the existing fail-closed continuation runner only for transient
Astra upstream failures (HTTP 502/503, upstream-unavailable, or bounded
transport timeouts). Every relaunch lets the runner allocate a fresh task id
and keeps the previous task as parent history. Non-transient failures stop the
supervisor rather than being hidden.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RUNTIME = ROOT / "research_os/runtime"
CYCLE_ID = "20260920T101512Z"
CYCLE_DIR = RUNTIME / f"cycle_{CYCLE_ID}"
STATUS_PATH = RUNTIME / "RESEARCHD_STATUS.json"
RUNNER = RUNTIME / "resume_cycle_hard_deadline.py"
PYTHON = ROOT / ".venv-cuda/bin/python"
LOCK_PATH = RUNTIME / "astra6_retry_supervisor.lock"
EVENTS_PATH = RUNTIME / "ASTRA6_RETRY_SUPERVISOR.jsonl"
LOG_PATH = RUNTIME / "astra6_retry_supervisor.log"
INITIAL_BACKOFF = int(os.environ.get("ASTRA_RETRY_INITIAL_SECONDS", "60"))
MAX_BACKOFF = int(os.environ.get("ASTRA_RETRY_MAX_SECONDS", "300"))
HARD_DEADLINE = int(os.environ.get("ASTRA_HARD_DEADLINE_SECONDS", "420"))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_event(event: str, **extra: Any) -> None:
    row = {"timestamp": now(), "event": event, "cycle_id": CYCLE_ID, **extra}
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()


def read_status() -> dict[str, Any]:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(**extra: Any) -> None:
    state = read_status()
    state.update(extra)
    state["updated_at"] = now()
    tmp = STATUS_PATH.with_suffix(".json.partial")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATUS_PATH)


def latest_worker_error() -> str:
    workers = sorted(CYCLE_DIR.glob("calls/*.worker.json"), key=lambda p: p.stat().st_mtime)
    if workers:
        try:
            value = json.loads(workers[-1].read_text(encoding="utf-8"))
            if not value.get("ok", False):
                return str(value.get("error", ""))
        except Exception:
            pass
    status = read_status()
    return str(status.get("error") or status.get("last_attempt_error") or "")


def latest_audit_error() -> str:
    path = CYCLE_DIR / "ASTRA6_CALL_AUDIT.jsonl"
    if not path.exists():
        return ""
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in reversed(rows):
            if row.get("event") == "call_failed":
                return str(row.get("error", ""))
    except Exception:
        pass
    return ""


def failure_text() -> str:
    return " ".join(x for x in (latest_worker_error(), latest_audit_error()) if x).lower()


def is_transient_failure(text: str) -> bool:
    markers = (
        "http_502", "http_503", "http 502", "http 503",
        "bad gateway", "service unavailable", "upstream",
        "temporarily unavailable", "read operation timed out",
        "timed out", "timeouterror", "deadline exceeded",
        "harddeadline:absolute astra6 call deadline exceeded", "transport:",
    )
    return any(marker in text for marker in markers)


def is_complete() -> bool:
    if (CYCLE_DIR / "RUN_COMPLETE.json").exists():
        return True
    status = read_status()
    return status.get("state") == "WAITING_FOR_NEXT_PROTOCOL"


def set_paused(error: str, attempt: int, next_retry_seconds: int | None) -> None:
    status = read_status()
    write_status(
        state="PAUSED_FAIL_CLOSED" if next_retry_seconds is None else "PAUSED_RETRY_PENDING",
        astra_only=True,
        requested_model="gpt-6-astra",
        error=error,
        last_attempt_error=error,
        next_action="WAIT_FOR_ASTRA6_UPSTREAM_RECOVERY" if next_retry_seconds is not None else "MANUAL_REVIEW_REQUIRED",
        retry_supervisor=True,
        retry_attempt=attempt,
        retry_next_seconds=next_retry_seconds,
        pid=None,
        completed_roles=status.get("completed_roles", []),
        incomplete_roles=status.get("incomplete_roles", []),
    )


def sleep_interruptibly(seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(min(5, max(0.1, deadline - time.monotonic())))


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            append_event("already_running")
            return 3

        attempt = 0
        backoff = max(1, INITIAL_BACKOFF)
        append_event("supervisor_started", pid=os.getpid(), hard_deadline_seconds=HARD_DEADLINE,
                     initial_backoff_seconds=backoff, max_backoff_seconds=MAX_BACKOFF,
                     fallback_forbidden=True, model="gpt-6-astra")
        while True:
            if is_complete():
                append_event("cycle_already_complete")
                return 0
            attempt += 1
            append_event("continuation_started", attempt=attempt)
            write_status(
                state="RETRY_SUPERVISOR_RUNNING",
                retry_supervisor=True,
                retry_attempt=attempt,
                retry_pid=os.getpid(),
                requested_model="gpt-6-astra",
                astra_only=True,
                fallback_forbidden=True,
            )
            env = os.environ.copy()
            env.update({
                "ASTRA_ONLY": "1",
                "ASTRA_ALLOW_FALLBACK": "0",
                "CODEX_LLM_DISABLED": "1",
                "LUNAMAX_DISABLED": "1",
                "ASTRA_HARD_DEADLINE_SECONDS": str(HARD_DEADLINE),
            })
            for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                        "CODEX_MODEL", "CODEX_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
                env.pop(key, None)
            started = time.monotonic()
            proc = subprocess.Popen(
                [str(PYTHON), str(RUNNER)],
                cwd=str(ROOT),
                env=env,
                stdout=LOG_PATH.open("a", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            rc = proc.wait()
            latency = round(time.monotonic() - started, 3)
            if is_complete() or rc == 0:
                append_event("continuation_finished", attempt=attempt, returncode=rc, latency_seconds=latency)
                return 0 if rc == 0 else 1

            error = latest_worker_error() or latest_audit_error() or str(read_status().get("error", "unknown failure"))
            transient = is_transient_failure(error.lower())
            append_event("continuation_failed", attempt=attempt, returncode=rc, latency_seconds=latency,
                         transient=transient, error=error)
            if not transient:
                set_paused(error, attempt, None)
                append_event("supervisor_stopped_nontransient", attempt=attempt, error=error)
                return rc or 2

            set_paused(error, attempt, backoff)
            append_event("retry_scheduled", attempt=attempt, sleep_seconds=backoff, error=error)
            sleep_interruptibly(backoff)
            backoff = min(MAX_BACKOFF, max(backoff + 1, backoff * 2))


if __name__ == "__main__":
    raise SystemExit(main())
