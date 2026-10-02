#!/usr/bin/env python3
"""Release assignment-specific Pass B only after the Pass-A lock exists."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from phase1_v2_annotation_common import read_csv_exact, sha256_file


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    args = ap.parse_args()
    package = Path(args.package_dir)
    pass_a_lock_path = package / "PASS_A_SUBMISSION_LOCK.json"
    if not pass_a_lock_path.exists():
        raise SystemExit("PASS_A_SUBMISSION_LOCK.json is absent; Pass B remains locked")
    pass_a_lock = json.loads(pass_a_lock_path.read_text(encoding="utf-8"))
    if pass_a_lock.get("status") != "LOCKED":
        raise SystemExit("Pass A submissions are not hash-locked; Pass B remains locked")

    status_path = package / "PASS_B_ACCESS_STATUS.json"
    current = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    if current.get("state") == "RELEASED_AFTER_PASS_A_LOCK":
        print(json.dumps({"status": "ALREADY_RELEASED", "pass_b_access": current.get("state")}, ensure_ascii=False))
        return 0

    source = package / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv"
    # The source was chmod 000 by the protocol-freeze step. This script is the
    # only release path and opens it only after the Pass-A lock is verified.
    original_mode = os.stat(source).st_mode & 0o777
    os.chmod(source, 0o444)
    try:
        source_hash = sha256_file(source)
        lock = json.loads((package / "V2_PROTOCOL_LOCK.json").read_text(encoding="utf-8"))
        expected_hash = lock["frozen_artifacts"]["pass_b_locked"]["sha256"]
        if source_hash != expected_hash:
            raise SystemExit(f"Pass-B source hash mismatch: expected {expected_hash}, got {source_hash}")
        columns, rows = read_csv_exact(source)
        row_map = json.loads((package / "internal/ASSIGNMENT_CASE_MAP.json").read_text(encoding="utf-8"))
        coder_cases = {
            "CODER_A": {x["case_id"] for x in row_map if "CODER_A" in x["assigned_to"]},
            "CODER_B": {x["case_id"] for x in row_map if "CODER_B" in x["assigned_to"]},
        }
        handles_by_coder = {}
        by_case = {x["case_id"]: set(x["row_handles"]) for x in row_map}
        release_dir = package / "annotator_release"
        outputs = {}
        for coder, cases in coder_cases.items():
            handles = set().union(*(by_case[case] for case in cases))
            selected = [row for row in rows if str(row.get("row_handle", "")).strip() in handles]
            if len(selected) != len(handles):
                raise SystemExit(f"Pass-B row count mismatch for {coder}: expected {len(handles)}, got {len(selected)}")
            out = release_dir / coder / "PASS_B_ASSIGNMENT.csv"
            if out.exists():
                raise SystemExit(f"refusing to overwrite existing Pass-B assignment: {out}")
            with out.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader(); writer.writerows(selected)
            os.chmod(out, 0o444)
            outputs[coder] = {"path": str(out.relative_to(package)), "rows": len(selected), "sha256": sha256_file(out)}
        release_manifest = {
            "created_at": utc_now(),
            "status": "RELEASED_AFTER_PASS_A_LOCK",
            "pass_a_lock_sha256": sha256_file(pass_a_lock_path),
            "pass_b_source_sha256": source_hash,
            "pass_b_assignments": outputs,
            "future_outcomes_read": False,
            "prediction_scores_read": False,
            "phase_2_or_phase_3_accessed": False,
            "release_condition_verified": True,
        }
        (package / "PASS_B_RELEASE_MANIFEST.json").write_text(json.dumps(release_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        status = {
            "state": "RELEASED_AFTER_PASS_A_LOCK",
            "pass_b_release_exists": True,
            "release_manifest": "PASS_B_RELEASE_MANIFEST.json",
            "pass_a_lock": "PASS_A_SUBMISSION_LOCK.json",
            "checked_at": utc_now(),
            "source_root_remains_protected": True,
        }
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": status["state"], "outputs": outputs}, ensure_ascii=False))
        return 0
    finally:
        os.chmod(source, original_mode)


if __name__ == "__main__":
    raise SystemExit(main())
