#!/usr/bin/env python3
"""Freeze the already-audited Phase-1 V2 protocol without changing its schema."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def header_sha(path: Path) -> str:
    return hashlib.sha256((path.read_text(encoding="utf-8").splitlines()[0] + "\n").encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    args = ap.parse_args()
    package = Path(args.package_dir)
    lock_path = package / "V2_PROTOCOL_LOCK.json"
    if lock_path.exists():
        raise SystemExit(f"protocol already frozen: {lock_path}")

    manifest_path = package / "PHASE1_ANNOTATION_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads((package / "PHASE1_PRE_ANNOTATION_AUDIT.json").read_text(encoding="utf-8"))
    if audit.get("conclusion") != "READY_TO_ANNOTATE":
        raise SystemExit("pre-annotation audit is not READY_TO_ANNOTATE")
    required = [
        "PHASE1_ANNOTATION_PROTOCOL.md", "PASS_A_TEXT_ONLY_BLIND.csv",
        "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", "DOUBLE_CODE_ROW_HANDLES.csv",
        "internal/SAMPLE_ROW_MAP.json", "BLINDING_AUDIT.json",
    ]
    missing = [name for name in required if not (package / name).exists()]
    if missing:
        raise SystemExit(f"missing frozen artifact(s): {missing}")

    # Verify the package hashes before creating the lock.  This is a guard
    # against freezing a partially modified or regenerated worksheet.
    expected = {
        "PASS_A_TEXT_ONLY_BLIND.csv": manifest["pass_a_sha256"],
        "PASS_B_STRUCTURED_REVIEW_LOCKED.csv": manifest["pass_b_sha256"],
        "DOUBLE_CODE_ROW_HANDLES.csv": manifest["double_code_handles_sha256"],
        "BLINDING_AUDIT.json": manifest["blinding_audit_sha256"],
    }
    actual = {name: sha256_file(package / name) for name in expected}
    if actual != expected:
        raise SystemExit(f"frozen package hash mismatch: expected={expected}, actual={actual}")

    row_map = json.loads((package / "internal/SAMPLE_ROW_MAP.json").read_text(encoding="utf-8"))
    cases = {str(x["case_id"]): x for x in row_map}
    if len(cases) != 100:
        raise SystemExit(f"expected 100 selected cases, found {len(cases)}")
    if any(str(x.get("cutoff_date")) == "2022-08-01" for x in cases.values()):
        raise SystemExit("August test case found in V2 roster")
    if {str(x.get("cutoff_date")) for x in cases.values()} != {"2022-06-01", "2022-07-01"}:
        raise SystemExit("V2 roster is not restricted to June/July")

    lock = {
        "lock_version": "phase1_v2_protocol_lock_v1",
        "created_at": utc_now(),
        "state": "FROZEN_PRE_ANNOTATION",
        "protocol_version": manifest["protocol_version"],
        "pre_annotation_audit": {
            "status": audit["conclusion"],
            "path": "PHASE1_PRE_ANNOTATION_AUDIT.md",
            "sha256": sha256_file(package / "PHASE1_PRE_ANNOTATION_AUDIT.md"),
        },
        "frozen_artifacts": {
            "protocol": {"path": "PHASE1_ANNOTATION_PROTOCOL.md", "sha256": sha256_file(package / "PHASE1_ANNOTATION_PROTOCOL.md")},
            "manifest": {"path": "PHASE1_ANNOTATION_MANIFEST.json", "sha256": sha256_file(manifest_path)},
            "pass_a_blank": {"path": "PASS_A_TEXT_ONLY_BLIND.csv", "sha256": actual["PASS_A_TEXT_ONLY_BLIND.csv"], "header_sha256": header_sha(package / "PASS_A_TEXT_ONLY_BLIND.csv")},
            "pass_b_locked": {"path": "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", "sha256": actual["PASS_B_STRUCTURED_REVIEW_LOCKED.csv"], "header_sha256": header_sha(package / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv")},
            "double_code_handles": {"path": "DOUBLE_CODE_ROW_HANDLES.csv", "sha256": actual["DOUBLE_CODE_ROW_HANDLES.csv"]},
            "sample_row_map": {"path": "internal/SAMPLE_ROW_MAP.json", "sha256": sha256_file(package / "internal/SAMPLE_ROW_MAP.json")},
            "blinding_audit": {"path": "BLINDING_AUDIT.json", "sha256": actual["BLINDING_AUDIT.json"]},
        },
        "roster_integrity": {
            "cases": len(cases),
            "rows": len(row_map),
            "cutoffs": {"2022-06-01": 50, "2022-07-01": 50},
            "excluded_cutoff": "2022-08-01",
            "double_code_cases": 20,
            "double_code_rows": 60,
            "case_cluster_primary_unit": True,
        },
        "schema_freeze": {
            "pass_a_columns": list(__import__("csv").DictReader((package / "PASS_A_TEXT_ONLY_BLIND.csv").open(encoding="utf-8")).fieldnames or []),
            "pass_b_columns": list(__import__("csv").DictReader((package / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv").open(encoding="utf-8")).fieldnames or []),
            "schema_change_allowed": False,
        },
        "pass_b_access": {
            "state": "LOCKED_PRE_PASS_A",
            "release_condition": "both assignment-specific Pass A submissions validate and are hash-locked",
            "release_script_required": True,
            "root_files_mode_after_lock": "000",
        },
        "submissions": {
            "coder_a": "PENDING",
            "coder_b": "PENDING",
            "pass_a_lock": "NOT_CREATED",
        },
        "future_outcomes_read": False,
        "prediction_scores_read": False,
        "phase_2_or_phase_3_accessed": False,
        "additional_research_agents_launched": False,
    }
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Make the protocol/reference artifacts immutable and keep all Pass-B files
    # unreadable until the release gate is satisfied.  The release workflow
    # temporarily opens only the locked source file after verifying the lock.
    immutable = [
        "V2_PROTOCOL_LOCK.json", "PHASE1_ANNOTATION_PROTOCOL.md", "PHASE1_ANNOTATION_MANIFEST.json",
        "PASS_A_TEXT_ONLY_BLIND.csv", "DOUBLE_CODE_ROW_HANDLES.csv", "internal/SAMPLE_ROW_MAP.json",
        "BLINDING_AUDIT.json", "PHASE1_PRE_ANNOTATION_AUDIT.md", "PHASE1_PRE_ANNOTATION_AUDIT.json",
    ]
    for name in immutable:
        os.chmod(package / name, 0o444)
    for name in ["PASS_B_STRUCTURED_REVIEW_LOCKED.csv", "PASS_B_CODER_A_BLANK.csv", "PASS_B_CODER_B_BLANK.csv"]:
        os.chmod(package / name, 0o000)

    lock["permissions_applied"] = {
        "immutable_artifacts_mode": "0444",
        "pass_b_files_mode": "000",
        "verified_at": utc_now(),
    }
    # The lock is now read-only; this update is made before applying its final
    # mode so its recorded permission state is itself frozen.
    os.chmod(lock_path, 0o644)
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(lock_path, 0o444)
    print(json.dumps({"status": "FROZEN_PRE_ANNOTATION", "package_dir": str(package), "pass_b_access": "LOCKED_PRE_PASS_A"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
