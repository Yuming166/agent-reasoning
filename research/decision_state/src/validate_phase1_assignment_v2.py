#!/usr/bin/env python3
"""Validate one completed assignment against the frozen V2 schema."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from phase1_v2_annotation_common import validate_pass_a_submission, validate_pass_b_submission


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["pass_a", "pass_b"], required=True)
    ap.add_argument("--expected-assignment", required=True)
    ap.add_argument("--submission", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-blank", action="store_true")
    args = ap.parse_args()
    expected = Path(args.expected_assignment)
    submission = Path(args.submission)
    report = (validate_pass_a_submission if args.kind == "pass_a" else validate_pass_b_submission)(expected, submission, args.allow_blank)
    report.update({"created_at": utc_now(), "kind": args.kind, "expected_assignment": str(expected), "submission": str(submission)})
    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "kind": args.kind, "errors": len(report.get("errors", [])), "out": str(out)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
