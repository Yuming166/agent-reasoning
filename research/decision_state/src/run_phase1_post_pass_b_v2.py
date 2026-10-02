#!/usr/bin/env python3
"""Validate Pass B and compute separate pre-adjudication Gate 1A/1B reports.

This command refuses to run before the Pass-A lock and Pass-B release. It reads
only the frozen annotation artifacts and human submissions; it never reads
future outcomes, prediction scores, or Phase 2/3 modules.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

from phase1_v2_annotation_common import sha256_file, validate_pass_b_submission

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
SCORER_A = ROOT / "research/decision_state/src/score_phase1_reliability_v2.py"
SCORER_B = ROOT / "research/decision_state/src/score_phase1_gate1b_v2.py"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    ap.add_argument("--pass-b-coder-a", default=None)
    ap.add_argument("--pass-b-coder-b", default=None)
    args = ap.parse_args()
    package = Path(args.package_dir)
    pass_a_lock_path = package / "PASS_A_SUBMISSION_LOCK.json"
    release_manifest_path = package / "PASS_B_RELEASE_MANIFEST.json"
    if not pass_a_lock_path.exists():
        raise SystemExit("Pass A is not hash-locked; do not access Pass B")
    pass_a_lock = json.loads(pass_a_lock_path.read_text(encoding="utf-8"))
    if pass_a_lock.get("status") != "LOCKED":
        raise SystemExit("Pass A lock status is not LOCKED")
    if not release_manifest_path.exists():
        raise SystemExit("Pass B has not been released; do not access Pass B submissions")
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    if release_manifest.get("status") != "RELEASED_AFTER_PASS_A_LOCK":
        raise SystemExit("Pass B release manifest is not valid")

    source_a = package / "annotator_release/CODER_A/PASS_B_ASSIGNMENT.csv"
    source_b = package / "annotator_release/CODER_B/PASS_B_ASSIGNMENT.csv"
    sub_a = Path(args.pass_b_coder_a) if args.pass_b_coder_a else package / "submissions/PASS_B_CODER_A.csv"
    sub_b = Path(args.pass_b_coder_b) if args.pass_b_coder_b else package / "submissions/PASS_B_CODER_B.csv"
    status = {"created_at": utc_now(), "status": None, "future_outcomes_joined": False, "prediction_scores_joined": False, "phase_2_or_phase_3_accessed": False}
    missing = [str(p) for p in [sub_a, sub_b] if not p.exists()]
    if missing:
        status.update({"status": "WAITING_FOR_TWO_PASS_B_SUBMISSIONS", "missing": missing})
        (package / "PASS_B_INTAKE_STATUS.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": status["status"], "missing": missing}, ensure_ascii=False))
        return 3

    result_a = validate_pass_b_submission(source_a, sub_a, allow_blank=False)
    result_b = validate_pass_b_submission(source_b, sub_b, allow_blank=False)
    status["submissions"] = {"CODER_A": result_a, "CODER_B": result_b}
    if result_a["status"] != "PASS" or result_b["status"] != "PASS":
        status["status"] = "PASS_B_SUBMISSIONS_INVALID"
        (package / "PASS_B_INTAKE_STATUS.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": status["status"], "coder_a": result_a["status"], "coder_b": result_b["status"]}, ensure_ascii=False))
        return 2

    locked_dir = package / "locked_submissions"
    locked_a = locked_dir / "PASS_B_CODER_A.csv"
    locked_b = locked_dir / "PASS_B_CODER_B.csv"
    if locked_a.exists() or locked_b.exists():
        raise SystemExit("refusing to overwrite existing locked Pass-B submission")
    shutil.copyfile(sub_a, locked_a); shutil.copyfile(sub_b, locked_b)
    pass_b_lock = {
        "created_at": utc_now(), "status": "LOCKED", "protocol_version": "phase1_annotation_gate_v2_dev",
        "pass_a_lock_sha256": sha256_file(pass_a_lock_path),
        "submissions": {
            "CODER_A": {"path": str(locked_a.relative_to(package)), "sha256": sha256_file(locked_a)},
            "CODER_B": {"path": str(locked_b.relative_to(package)), "sha256": sha256_file(locked_b)},
        },
        "future_outcomes_read": False, "prediction_scores_read": False, "phase_2_or_phase_3_accessed": False,
    }
    (package / "PASS_B_SUBMISSION_LOCK.json").write_text(json.dumps(pass_b_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    gate1a_out = package / "PRE_ADJUDICATION_GATE1A_RELIABILITY.json"
    gate1b_out = package / "PRE_ADJUDICATION_GATE1B_SUBSTANTIVE_VALIDITY.json"
    locked_pa = locked_dir / "PASS_A_CODER_A.csv"
    locked_pb = locked_dir / "PASS_A_CODER_B.csv"
    commands = [
        ["python", str(SCORER_A), "--package-dir", str(package), "--pass-a-coder-a", str(locked_pa), "--pass-a-coder-b", str(locked_pb), "--pass-b-coder-a", str(locked_a), "--pass-b-coder-b", str(locked_b), "--out", str(gate1a_out)],
        ["python", str(SCORER_B), "--package-dir", str(package), "--pass-a-coder-a", str(locked_pa), "--pass-a-coder-b", str(locked_pb), "--pass-b-coder-a", str(locked_a), "--pass-b-coder-b", str(locked_b), "--out", str(gate1b_out)],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=str(ROOT), check=False)
        if completed.returncode != 0:
            raise SystemExit(f"scoring command failed with exit {completed.returncode}: {' '.join(command)}")
    gate1a = json.loads(gate1a_out.read_text(encoding="utf-8"))
    gate1b = json.loads(gate1b_out.read_text(encoding="utf-8"))
    final = {
        "created_at": utc_now(),
        "status": "PRE_ADJUDICATION_GATES_COMPUTED",
        "gate_1a": {"status": gate1a.get("status"), "report": str(gate1a_out.relative_to(package))},
        "gate_1b": {"status": gate1b.get("status"), "report": str(gate1b_out.relative_to(package))},
        "adjudication_included": False,
        "future_outcomes_read": False,
        "prediction_scores_read": False,
        "phase_2_or_phase_3_accessed": False,
        "interpretation": "Gate 1A reliability and Gate 1B substantive validity are computed separately before adjudication; no disagreement is silently resolved.",
    }
    (package / "PRE_ADJUDICATION_GATE_STATUS.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status.update({"status": final["status"], "gate_status": final})
    (package / "PASS_B_INTAKE_STATUS.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
