#!/usr/bin/env python3
"""Verify the frozen V2 templates, assignments, roster, and Pass-B lock state."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from phase1_v2_annotation_common import sha256_file


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rows(path: Path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    p = Path(args.package_dir)
    lock = json.loads((p / "V2_PROTOCOL_LOCK.json").read_text(encoding="utf-8"))
    assign = json.loads((p / "ANNOTATOR_ASSIGNMENT_MANIFEST.json").read_text(encoding="utf-8"))
    row_map = json.loads((p / "internal/SAMPLE_ROW_MAP.json").read_text(encoding="utf-8"))
    case_map = {x["case_id"]: x for x in row_map}
    handle_to_case = {x["row_handle"]: x["case_id"] for x in row_map}
    double_handles = {r["row_handle"] for r in rows(p / "DOUBLE_CODE_ROW_HANDLES.csv")}
    assignment_rows = {coder: rows(p / f"annotator_release/{coder}/PASS_A_ASSIGNMENT.csv") for coder in ["CODER_A", "CODER_B"]}
    assignment_handles = {coder: {r["row_handle"] for r in rs} for coder, rs in assignment_rows.items()}
    checks = {}
    checks["protocol_state_frozen"] = lock.get("state") == "FROZEN_PRE_ANNOTATION"
    checks["schema_frozen"] = lock.get("schema_freeze", {}).get("schema_change_allowed") is False
    checks["template_hash"] = sha256_file(p / "PASS_A_TEXT_ONLY_BLIND.csv") == lock["frozen_artifacts"]["pass_a_blank"]["sha256"]
    checks["assignment_a_hash"] = sha256_file(p / "annotator_release/CODER_A/PASS_A_ASSIGNMENT.csv") == assign["assignments"]["CODER_A"]["assignment_sha256"]
    checks["assignment_b_hash"] = sha256_file(p / "annotator_release/CODER_B/PASS_A_ASSIGNMENT.csv") == assign["assignments"]["CODER_B"]["assignment_sha256"]
    checks["100_cases"] = len(case_map) == 100
    checks["300_rows"] = len(row_map) == 300
    checks["no_august"] = all(x.get("cutoff_date") != "2022-08-01" for x in case_map.values())
    checks["balanced_sample"] = Counter(x["cutoff_date"] for x in case_map.values()) == Counter({"2022-06-01": 50, "2022-07-01": 50})
    checks["20_shared_cases"] = len({x["case_id"] for x in row_map if x.get("double_code_case")}) == 20
    checks["60_shared_rows"] = len(double_handles) == 60
    checks["shared_assignment_intersection"] = assignment_handles["CODER_A"] & assignment_handles["CODER_B"] == double_handles
    checks["assignment_union"] = assignment_handles["CODER_A"] | assignment_handles["CODER_B"] == set(x["row_handle"] for x in row_map)
    checks["balanced_unique_a"] = Counter(case_map[handle_to_case[h]]["cutoff_date"] for h in assignment_handles["CODER_A"] - double_handles) == Counter({"2022-06-01": 60, "2022-07-01": 60})
    checks["balanced_unique_b"] = Counter(case_map[handle_to_case[h]]["cutoff_date"] for h in assignment_handles["CODER_B"] - double_handles) == Counter({"2022-06-01": 60, "2022-07-01": 60})
    checks["pass_b_mode_zero"] = all((os.stat(p / name).st_mode & 0o777) == 0 for name in ["PASS_B_STRUCTURED_REVIEW_LOCKED.csv", "PASS_B_CODER_A_BLANK.csv", "PASS_B_CODER_B_BLANK.csv"])
    checks["pass_b_release_absent"] = not (p / "PASS_B_RELEASE_MANIFEST.json").exists() and not list((p / "annotator_release").glob("*/PASS_B_ASSIGNMENT.csv"))
    checks["no_pass_a_lock"] = not (p / "PASS_A_SUBMISSION_LOCK.json").exists()
    checks["no_future_outcomes"] = lock.get("future_outcomes_read") is False
    checks["no_prediction_scores"] = lock.get("prediction_scores_read") is False
    checks["no_phase2_3"] = lock.get("phase_2_or_phase_3_accessed") is False
    report = {
        "created_at": utc_now(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "hashes": {
            "blank_template": sha256_file(p / "PASS_A_TEXT_ONLY_BLIND.csv"),
            "coder_a_assignment": sha256_file(p / "annotator_release/CODER_A/PASS_A_ASSIGNMENT.csv"),
            "coder_b_assignment": sha256_file(p / "annotator_release/CODER_B/PASS_A_ASSIGNMENT.csv"),
            "double_code_handles": sha256_file(p / "DOUBLE_CODE_ROW_HANDLES.csv"),
            "protocol_lock": sha256_file(p / "V2_PROTOCOL_LOCK.json"),
        },
        "roster": {
            "cases": len(case_map), "rows": len(row_map), "shared_cases": len({x["case_id"] for x in row_map if x.get("double_code_case")}),
            "shared_rows": len(double_handles), "coder_a_rows": len(assignment_handles["CODER_A"]), "coder_b_rows": len(assignment_handles["CODER_B"]),
        },
        "pass_b_access": "LOCKED_PRE_PASS_A" if checks["pass_b_mode_zero"] and checks["pass_b_release_absent"] else "CHECK_FAILED",
        "future_outcomes_read": False, "prediction_scores_read": False, "phase_2_or_phase_3_accessed": False,
    }
    out = Path(args.out); out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "pass_b_access": report["pass_b_access"], "out": str(out)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
