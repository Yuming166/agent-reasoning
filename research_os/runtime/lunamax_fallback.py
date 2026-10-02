#!/usr/bin/env python3
"""Off-charter Luna Max exploratory continuation.

This is deliberately separate from the Astra6-only cycle. It never writes
Astra6 role reports, manager synthesis, claim ledger, experiment registry, or
RUN_COMPLETE.json. Its outputs are exploratory and must not be promoted to
official evidence without a new human-approved protocol and Astra6 review.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
ROS = ROOT / "research_os"
RUNTIME = ROS / "runtime"
SOURCE_CYCLE_ID = "20260920T101512Z"
SOURCE_CYCLE = RUNTIME / f"cycle_{SOURCE_CYCLE_ID}"
MODEL = "gpt-5.6-luna"
CLI = "codex"
DEADLINE = int(os.environ.get("LUNAMAX_HARD_DEADLINE_SECONDS", "1800"))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()


def bounded(path: Path, chars: int) -> str:
    if not path.exists():
        return f"[missing: {path}]"
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= chars else text[:chars] + f"\n[truncated at {chars} chars]"


def kill_tree(proc: subprocess.Popen) -> None:
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


def context() -> str:
    priority = bounded(SOURCE_CYCLE / "priority_summary.json", 4000)
    negative = bounded(ROS / "NEGATIVE_RESULTS.md", 5000)
    decision = bounded(ROOT / "research/decision_state/DECISION_STATE_DECISION_20260919.md", 5500)
    openworld = bounded(ROOT / "research/openworld/ow010b/reports/OW010B_DECISION.md", 2500)
    reports = []
    for role in ("LIT_SCOUT", "GAP_AUDITOR", "PHENOMENON_SCOUT"):
        reports.append(f"===== {role} =====\n{bounded(SOURCE_CYCLE / (role + '.md'), 3000)}")
    return f"""EX-GRAPH NAACL AUTORESEARCH — OFF-CHARTER LUNAMAX EXPLORATORY MODE

This is a temporary fallback because the Astra6 relay is unavailable. You are
not Astra6. Your output is exploratory only and must not be represented as an
Astra6 result, official claim, preregistered result, or final scientific
conclusion. Do not modify files. Do not reveal private chain-of-thought; return
only the requested concise report.

The official Astra6 cycle remains paused and immutable. Existing boundaries:
- no true owner psychology, causal intent, or verified social exposure;
- address-level behavior is only an actor proxy;
- no retuning of the August frozen test;
- no large new LLM experiment before falsification/literature gates;
- natural language must be scientifically central, not cosmetic;
- discovery evidence is not confirmatory.

PRIORITY AUDIT:
{priority}

DECISION-STATE V1:
{decision}

OW-010B:
{openworld}

NEGATIVE MEMORY:
{negative}

COMPLETED ASTRA6 REPORT EXCERPTS:
{chr(10).join(reports)}
"""


ROLE_SPECS = {
    "NLP_ARCHITECT": "Design the smallest language-centered representation/evaluation that would make a surviving branch genuinely NLP-central: semantic non-redundancy, evidence alignment, future implications, falsifiers, or revision. Reject cosmetic text.",
    "EXPERIMENT_DESIGNER": "Design the cheapest decisive next experiment for the strongest 1-3 branches. Include sample, target, controls, primary metric, stop/no-go rule, untouched holdout, and deterministic-vs-model boundaries. Do not propose a large experiment first.",
    "FALSIFIER": "Assume the current preferred story is wrong. Find confounds and construct kill tests for A-F, especially equifinality versus ordinary uncertainty, intervention sensitivity versus prompt sensitivity, and activity/autoregression.",
}


def role_prompt(role: str, context_text: str) -> str:
    return f"""You are the exploratory fallback role {role} in a temporary Luna Max run.

Assignment:
{ROLE_SPECS[role]}

Return a concise report with exactly these headings:
1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)
2. Strongest evidence
3. Strongest counterargument
4. Cheapest decisive experiment
5. Stop condition
6. Literature/novelty verification still required

Do not invent exact citations. Do not relabel prior NO-GO findings as positive.
Keep the distinction between deterministic evidence and model-generated advice.
Do not propose a large LLM experiment before a falsification gate.

{context_text}
"""


def run_codex(*, run_dir: Path, task_id: str, role: str, prompt: str, parent_task_id: str | None, max_wait: int = DEADLINE) -> str:
    out_path = run_dir / f"{role}.md"
    stdout_path = run_dir / "calls" / f"{task_id}.stdout.log"
    stderr_path = run_dir / "calls" / f"{task_id}.stderr.log"
    prompt_path = run_dir / "calls" / f"{task_id}.prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(prompt_path, prompt)
    prompt_hash = sha256_text(prompt)
    append_jsonl(run_dir / "LUNAMAX_CALL_AUDIT.jsonl", {
        "event": "call_started",
        "timestamp": utc_now(),
        "task_id": task_id,
        "role": role,
        "parent_task_id": parent_task_id,
        "model": MODEL,
        "provider_mode": "codex_cli_fallback",
        "prompt_hash": prompt_hash,
        "result_path": str(out_path),
        "deadline_seconds": max_wait,
    })
    command = [
        CLI, "exec", "-m", MODEL,
        "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
        "-C", str(ROOT), "-o", str(out_path), "-",
    ]
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            proc.communicate(input=prompt.encode("utf-8"), timeout=max_wait)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            error = f"HardDeadline:LunaMax call exceeded {max_wait}s"
            append_jsonl(run_dir / "LUNAMAX_CALL_AUDIT.jsonl", {
                "event": "call_failed", "timestamp": utc_now(), "task_id": task_id,
                "role": role, "parent_task_id": parent_task_id, "model": MODEL,
                "prompt_hash": prompt_hash, "error": error,
                "latency_seconds": round(time.monotonic() - started, 3),
            })
            raise RuntimeError(error)
    latency = round(time.monotonic() - started, 3)
    if proc.returncode != 0 or not out_path.exists():
        error = f"codex_exit={proc.returncode}; output_exists={out_path.exists()}"
        append_jsonl(run_dir / "LUNAMAX_CALL_AUDIT.jsonl", {
            "event": "call_failed", "timestamp": utc_now(), "task_id": task_id,
            "role": role, "parent_task_id": parent_task_id, "model": MODEL,
            "prompt_hash": prompt_hash, "error": error,
            "latency_seconds": latency,
        })
        raise RuntimeError(error)
    text = out_path.read_text(encoding="utf-8", errors="replace")
    response_hash = sha256_text(text)
    append_jsonl(run_dir / "LUNAMAX_CALL_AUDIT.jsonl", {
        "event": "call_completed", "timestamp": utc_now(), "task_id": task_id,
        "role": role, "parent_task_id": parent_task_id, "model": MODEL,
        "prompt_hash": prompt_hash, "response_hash": response_hash,
        "result_path": str(out_path), "latency_seconds": latency,
        "response_chars": len(text),
    })
    return text


def main() -> int:
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNTIME / f"lunamax_fallback_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id,
        "started_at": utc_now(),
        "mode": "OFF_CHARTER_EXPLORATORY_FALLBACK",
        "model": MODEL,
        "source_cycle": SOURCE_CYCLE_ID,
        "official_astra_cycle_untouched": True,
        "promotion_to_claim_ledger": False,
        "promotion_to_experiment_registry": False,
        "no_large_llm_experiment": True,
        "reason": "user explicitly requested temporary Luna Max reasoning after Astra6 upstream failures",
        "deadline_seconds_per_call": DEADLINE,
    }
    write_json(run_dir / "RUN_MANIFEST.json", manifest)
    write_text(run_dir / "BOUNDARY.md", """# Luna Max fallback boundary\n\nThis directory contains exploratory, off-charter outputs. The official Astra6-only cycle remains paused and unchanged. These outputs are not Astra6 evidence, not preregistered results, and not eligible for claim-ledger or experiment-registry promotion without explicit human review and a new protocol.\n""")
    write_json(run_dir / "STATUS.json", {"state": "RUNNING", **manifest})
    ctx = context()
    reports = {}
    try:
        for index, role in enumerate(ROLE_SPECS, start=1):
            task_id = f"{run_id}_{role}_fallback{index}"
            reports[role] = run_codex(
                run_dir=run_dir,
                task_id=task_id,
                role=role,
                prompt=role_prompt(role, ctx),
                parent_task_id=SOURCE_CYCLE_ID,
            )
        manager_prompt = f"""You are the exploratory Luna Max RESEARCH_MANAGER in an OFF-CHARTER fallback run.\n\nSynthesize the independent reports below, but do not present them as Astra6 results or final claims. Return JSON only with: cycle_verdict, active_branches, killed_or_deferred, next_experiment, claim_ledger_updates, reviewer_risks, nightly_decision. Set large_llm_run_allowed to false. Preserve all no-go boundaries, require a falsifier and untouched holdout, and explicitly state that this is exploratory fallback advice.\n\nCONTEXT:\n{ctx}\n\nREPORTS:\n{chr(10).join(f'===== {k} =====\\n{v}' for k, v in reports.items())}\n"""
        manager_id = f"{run_id}_RESEARCH_MANAGER_fallback4"
        manager = run_codex(run_dir=run_dir, task_id=manager_id, role="RESEARCH_MANAGER", prompt=manager_prompt, parent_task_id=run_id)
        write_text(run_dir / "RESEARCH_MANAGER_RAW.md", manager)
        write_json(run_dir / "STATUS.json", {"state": "COMPLETE_EXPLORATORY_ONLY", **manifest, "completed_at": utc_now(), "roles_completed": list(reports) + ["RESEARCH_MANAGER"]})
        return 0
    except Exception as exc:
        append_jsonl(run_dir / "FAILURE.jsonl", {"timestamp": utc_now(), "error": f"{type(exc).__name__}:{exc}"})
        write_json(run_dir / "STATUS.json", {"state": "PAUSED_FAIL_CLOSED_FALLBACK", **manifest, "updated_at": utc_now(), "error": f"{type(exc).__name__}:{exc}", "completed_roles": list(reports)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
