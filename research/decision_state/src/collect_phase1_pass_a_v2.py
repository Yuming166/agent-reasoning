#!/usr/bin/env python3
"""Collect, validate, and hash-lock the two frozen V2 Pass-A submissions.

This command never reads Pass B.  It creates a Pass-A lock only when both
assignment-specific human submissions exist and independently pass validation.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

from phase1_v2_annotation_common import sha256_file, validate_pass_a_submission


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_handles(path: Path) -> set[str]:
    with path.open(encoding="utf-8", newline="") as f:
        return {str(row["row_handle"]).strip() for row in csv.DictReader(f)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    ap.add_argument("--coder-a", default=None)
    ap.add_argument("--coder-b", default=None)
    args = ap.parse_args()
    package = Path(args.package_dir)
    lock_path = package / "PASS_A_SUBMISSION_LOCK.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        print(json.dumps({"status": "ALREADY_LOCKED", "lock": str(lock_path), "submission_status": lock.get("status")}, ensure_ascii=False))
        return 0

    assignment_a = package / "annotator_release/CODER_A/PASS_A_ASSIGNMENT.csv"
    assignment_b = package / "annotator_release/CODER_B/PASS_A_ASSIGNMENT.csv"
    sub_a = Path(args.coder_a) if args.coder_a else package / "submissions/PASS_A_CODER_A.csv"
    sub_b = Path(args.coder_b) if args.coder_b else package / "submissions/PASS_A_CODER_B.csv"
    report = {
        "created_at": utc_now(),
        "status": None,
        "protocol_version": "phase1_annotation_gate_v2_dev",
        "pass_b_access": "LOCKED_PRE_PASS_A",
        "future_outcomes_read": False,
        "prediction_scores_read": False,
        "phase_2_or_phase_3_accessed": False,
        "submissions": {},
    }
    missing = [str(p) for p in [sub_a, sub_b] if not p.exists()]
    if missing:
        report["status"] = "WAITING_FOR_TWO_SUBMISSIONS"
        report["missing"] = missing
        (package / "PASS_A_INTAKE_STATUS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "missing": missing, "pass_b_access": "LOCKED_PRE_PASS_A"}, ensure_ascii=False))
        return 3

    result_a = validate_pass_a_submission(assignment_a, sub_a, allow_blank=False)
    result_b = validate_pass_a_submission(assignment_b, sub_b, allow_blank=False)
    report["submissions"] = {"CODER_A": result_a, "CODER_B": result_b}
    if result_a["status"] != "PASS" or result_b["status"] != "PASS":
        report["status"] = "SUBMISSIONS_INVALID"
        (package / "PASS_A_INTAKE_STATUS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "coder_a": result_a["status"], "coder_b": result_b["status"], "pass_b_access": "LOCKED_PRE_PASS_A"}, ensure_ascii=False))
        return 2

    handles_a = read_handles(sub_a); handles_b = read_handles(sub_b)
    shared_expected = read_handles(package / "DOUBLE_CODE_ROW_HANDLES.csv")
    if handles_a & handles_b != shared_expected:
        report["status"] = "ROSTER_INTEGRITY_FAILURE"
        report["roster_error"] = {
            "intersection": len(handles_a & handles_b),
            "expected_shared": len(shared_expected),
            "missing_shared": sorted(shared_expected - (handles_a & handles_b)),
            "unexpected_overlap": sorted((handles_a & handles_b) - shared_expected),
        }
        (package / "PASS_A_INTAKE_STATUS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "pass_b_access": "LOCKED_PRE_PASS_A"}, ensure_ascii=False))
        return 2

    locked_dir = package / "locked_submissions"
    locked_dir.mkdir(exist_ok=False)
    locked_a = locked_dir / "PASS_A_CODER_A.csv"
    locked_b = locked_dir / "PASS_A_CODER_B.csv"
    shutil.copyfile(sub_a, locked_a); shutil.copyfile(sub_b, locked_b)
    hash_a, hash_b = sha256_file(locked_a), sha256_file(locked_b)
    report.update({
        "status": "LOCKED",
        "lock_created_at": utc_now(),
        "locked_submissions": {
            "CODER_A": {"path": str(locked_a.relative_to(package)), "sha256": hash_a, "rows": len(handles_a)},
            "CODER_B": {"path": str(locked_b.relative_to(package)), "sha256": hash_b, "rows": len(handles_b)},
        },
        "shared_double_code_rows": len(handles_a & handles_b),
        "union_rows": len(handles_a | handles_b),
        "pass_b_release_condition": "both Pass A submissions are validated and hash-locked",
    })
    lock_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package / "PASS_A_INTAKE_STATUS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "LOCKED", "coder_a_sha256": hash_a, "coder_b_sha256": hash_b, "pass_b_access": "LOCKED_PRE_PASS_A"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
