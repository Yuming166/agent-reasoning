#!/usr/bin/env python3
"""Prepare two balanced, outcome-blind Pass-A assignment sheets.

This script never reads Pass B.  It uses the already-frozen V2 roster and
schema, keeps 20 cases shared for double coding, and splits the other 80
cases 40/40 with 20 June and 20 July unique cases per coder.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")
FORBIDDEN_RE = re.compile(r"(?i)(?:\bdelta\b|\baugust\b|\bjuly\b|\bsplit\b|\blog[_ -]?loss\b|\bF\s*=)")
SAMPLE_SALT = "|phase1-v2-assignment-case|"
ORDER_SALTS = {"CODER_A": "|phase1-v2-coder-a-order|", "CODER_B": "|phase1-v2-coder-b-order|"}
CUTOFFS = ["2022-06-01", "2022-07-01"]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    args = ap.parse_args()
    package = Path(args.package_dir)
    lock = json.loads((package / "V2_PROTOCOL_LOCK.json").read_text(encoding="utf-8"))
    if lock.get("state") != "FROZEN_PRE_ANNOTATION":
        raise SystemExit("V2 protocol is not in FROZEN_PRE_ANNOTATION state")
    template = package / "PASS_A_TEXT_ONLY_BLIND.csv"
    rows = list(csv.DictReader(template.open(encoding="utf-8", newline="")))
    fieldnames = list(rows[0]) if rows else []
    if not rows or fieldnames[:2] != ["row_handle", "hypothesis_text"]:
        raise SystemExit("Pass A template is missing or has an unexpected schema")
    if any(any(str(row.get(field, "")) for field in fieldnames[2:]) for row in rows):
        raise SystemExit("Pass A template is not blank")

    internal = json.loads((package / "internal/SAMPLE_ROW_MAP.json").read_text(encoding="utf-8"))
    by_handle = {str(x["row_handle"]): x for x in internal}
    if set(by_handle) != {str(row["row_handle"]) for row in rows}:
        raise SystemExit("template and internal row map handles differ")
    row_handles_by_case: dict[str, list[str]] = {}
    case_meta: dict[str, dict] = {}
    for item in internal:
        case = str(item["case_id"])
        row_handles_by_case.setdefault(case, []).append(str(item["row_handle"]))
        case_meta[case] = item
    if len(case_meta) != 100 or any(len(v) != 3 for v in row_handles_by_case.values()):
        raise SystemExit("V2 roster must contain 100 cases with exactly 3 rows each")

    shared_handles = {str(x["row_handle"]) for x in csv.DictReader((package / "DOUBLE_CODE_ROW_HANDLES.csv").open(encoding="utf-8", newline=""))}
    shared_cases = {by_handle[h]["case_id"] for h in shared_handles}
    if len(shared_cases) != 20 or len(shared_handles) != 60:
        raise SystemExit(f"double-code roster integrity failure: {len(shared_cases)} cases / {len(shared_handles)} rows")

    unique_cases_by_cutoff: dict[str, list[str]] = {}
    for cutoff in CUTOFFS:
        pool = sorted(case for case, item in case_meta.items() if item["cutoff_date"] == cutoff and case not in shared_cases)
        if len(pool) != 40:
            raise SystemExit(f"expected 40 unique {cutoff} cases, found {len(pool)}")
        ranked = sorted((sha256_text(case + SAMPLE_SALT), case) for case in pool)
        unique_cases_by_cutoff[cutoff] = [case for _, case in ranked]

    coder_cases = {
        "CODER_A": set(shared_cases),
        "CODER_B": set(shared_cases),
    }
    for cutoff in CUTOFFS:
        ranked = unique_cases_by_cutoff[cutoff]
        coder_cases["CODER_A"].update(ranked[:20])
        coder_cases["CODER_B"].update(ranked[20:])
    if coder_cases["CODER_A"] & coder_cases["CODER_B"] != shared_cases:
        raise SystemExit("coder assignment overlap is not exactly the shared roster")
    if coder_cases["CODER_A"] | coder_cases["CODER_B"] != set(case_meta):
        raise SystemExit("coder assignment union does not cover all 100 cases")

    release_dir = package / "annotator_release"
    internal_dir = package / "internal"
    release_dir.mkdir(exist_ok=False)
    (release_dir / "CODER_A").mkdir()
    (release_dir / "CODER_B").mkdir()
    assignment_rows: dict[str, list[dict]] = {}
    for coder, cases in coder_cases.items():
        handles = {h for case in cases for h in row_handles_by_case[case]}
        selected = [row for row in rows if str(row["row_handle"]) in handles]
        selected.sort(key=lambda row: sha256_text(str(row["row_handle"]) + ORDER_SALTS[coder]))
        assignment_rows[coder] = selected
        out = release_dir / coder / "PASS_A_ASSIGNMENT.csv"
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader(); writer.writerows(selected)
        (release_dir / coder / "README.md").write_text(
            f"""# Phase 1 V2 Pass A assignment — {coder}

This file contains only your assigned text-only Pass A rows. The V2 protocol
and exact schema are frozen; do not add, remove, reorder, or rename columns.
Annotate only commitments visible in `hypothesis_text`. Do not infer missing
horizons from instructions or structured outputs. Do not access Pass B, future
outcomes, prediction scores, or Phase 2/3 materials.

Return the completed file under the submission intake names specified in
`SUBMISSION_INTAKE.md`. The other coder's file and the shared-case markers are
not disclosed.
""", encoding="utf-8")
        # Assignment files must not contain raw identity or outcome-like leakage.
        for row in selected:
            if WALLET_RE.search(str(row["hypothesis_text"])) or FORBIDDEN_RE.search(str(row["hypothesis_text"])):
                raise SystemExit(f"blinding leak in assignment {coder}: {row['row_handle']}")

    assignment_internal = []
    for case, item in sorted(case_meta.items()):
        assignment_internal.append({
            "case_id": case,
            "cutoff_date": item["cutoff_date"],
            "split": item["split"],
            "shared_double_code": case in shared_cases,
            "assigned_to": [coder for coder in ["CODER_A", "CODER_B"] if case in coder_cases[coder]],
            "row_handles": sorted(row_handles_by_case[case]),
        })
    (internal_dir / "ASSIGNMENT_CASE_MAP.json").write_text(json.dumps(assignment_internal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "created_at": utc_now(),
        "status": "ASSIGNMENTS_PREPARED_AWAITING_SUBMISSIONS",
        "protocol_lock": "V2_PROTOCOL_LOCK.json",
        "protocol_lock_sha256": sha256_file(package / "V2_PROTOCOL_LOCK.json"),
        "schema_frozen": True,
        "source_template_sha256": sha256_file(template),
        "source_double_code_handles_sha256": sha256_file(package / "DOUBLE_CODE_ROW_HANDLES.csv"),
        "shared_double_code_cases": 20,
        "shared_double_code_rows": 60,
        "unique_cases": 80,
        "assignments": {
            coder: {
                "cases": len(coder_cases[coder]),
                "rows": len(assignment_rows[coder]),
                "shared_cases": len(coder_cases[coder] & shared_cases),
                "unique_cases": len(coder_cases[coder] - shared_cases),
                "cases_by_cutoff": {cutoff: sum(case_meta[c]["cutoff_date"] == cutoff for c in coder_cases[coder]) for cutoff in CUTOFFS},
                "unique_cases_by_cutoff": {cutoff: sum(case_meta[c]["cutoff_date"] == cutoff for c in coder_cases[coder] - shared_cases) for cutoff in CUTOFFS},
                "assignment_path": f"annotator_release/{coder}/PASS_A_ASSIGNMENT.csv",
                "assignment_sha256": sha256_file(release_dir / coder / "PASS_A_ASSIGNMENT.csv"),
            } for coder in ["CODER_A", "CODER_B"]
        },
        "shared_case_rule": "All 20 fixed double-code cases are assigned to both coders.",
        "unique_case_rule": "Within each cutoff, hash-rank the 40 non-shared cases; first 20 to CODER_A and remaining 20 to CODER_B.",
        "order_rule": dict(ORDER_SALTS),
        "outcome_blind": True,
        "future_outcomes_read": False,
        "prediction_scores_read": False,
        "phase_2_or_phase_3_accessed": False,
        "pass_b_access": "LOCKED_PRE_PASS_A",
        "submission_status": "PENDING_CODER_A_AND_CODER_B",
    }
    (package / "ANNOTATOR_ASSIGNMENT_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package / "ASSIGNMENT_INTEGRITY.json").write_text(json.dumps({
        "created_at": manifest["created_at"],
        "status": manifest["status"],
        "template_rows": len(rows),
        "template_cases": len(case_meta),
        "shared_cases": len(shared_cases),
        "shared_rows": len(shared_handles),
        "union_rows": len(set(r["row_handle"] for r in assignment_rows["CODER_A"]) | set(r["row_handle"] for r in assignment_rows["CODER_B"])),
        "intersection_rows": len(set(r["row_handle"] for r in assignment_rows["CODER_A"]) & set(r["row_handle"] for r in assignment_rows["CODER_B"])),
        "coder_a": manifest["assignments"]["CODER_A"],
        "coder_b": manifest["assignments"]["CODER_B"],
        "integrity_ok": True,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package / "SUBMISSION_INTAKE.md").write_text("""# Phase 1 V2 submission intake

Protocol state: `FROZEN_PRE_ANNOTATION`  
Pass B state: `LOCKED_PRE_PASS_A`

Submit exactly two completed CSV files, using the frozen assignment schemas:

- `submissions/PASS_A_CODER_A.csv`
- `submissions/PASS_A_CODER_B.csv`

Each file must contain exactly its assigned 180 rows and the exact frozen Pass-A
columns. Do not include case IDs, cutoff dates, wallet IDs, outcomes, scores,
model metadata, or any extra columns. The intake workflow will reject blank,
changed, duplicated, missing, or extra rows. It will hash and lock each file
only after independent validation succeeds.

Pass B is not present in this release directory. It can be released only by the
workflow after both Pass A submissions validate and their hashes are recorded in
`PASS_A_SUBMISSION_LOCK.json`.
""", encoding="utf-8")
    (package / "PASS_B_ACCESS_STATUS.json").write_text(json.dumps({
        "state": "LOCKED_PRE_PASS_A",
        "pass_b_release_exists": False,
        "release_condition": "PASS_A_CODER_A and PASS_A_CODER_B validate and are hash-locked",
        "checked_at": utc_now(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"], "shared_cases": len(shared_cases), "shared_rows": len(shared_handles),
        "coder_a": manifest["assignments"]["CODER_A"], "coder_b": manifest["assignments"]["CODER_B"],
        "pass_b_access": "LOCKED_PRE_PASS_A",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
