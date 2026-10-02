#!/usr/bin/env python3
"""Validate an adjudicated 231-row workbook without changing its frozen design.

Offline only. Verifies immutable workbook cells against the pinned source frame,
checks verdict/evidence requirements, and (only when all 60 probability rows are
complete) exports those 60 rows back onto the original frozen sample schema for
the existing design-weighted summarizer. The 171-row targeted complement is
always reported separately and never included in weighted estimates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_ens_x_full_frame_review_packet import (  # noqa: E402
    OUTPUT_FIELDS, REVIEW_FIELDS, build as build_expected_workbook, read_csv,
)

VERDICTS = {"account_confirms", "ens_only", "conflict", "unverifiable"}
REVIEW_COLS = set(REVIEW_FIELDS) | {"review_state"}
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_error(value: str, label: str, key: str) -> str | None:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return f"{key}: {label} must include a timezone"
    except (ValueError, AttributeError):
        return f"{key}: {label} must be ISO-8601 with timezone"
    return None


def evidence_errors(row: dict[str, str], line: int) -> list[str]:
    errs: list[str] = []
    verdict = row.get("manual_verdict", "").strip()
    key = f"line {line} ({row.get('address','')[:12]}…/{row.get('x_user_id','')})"
    if verdict in {"", "pending"}:
        # Pending rows may be untouched or partially documented, but can never
        # be counted as decided. Preserve partial notes for an ongoing review.
        return errs
    if verdict not in VERDICTS:
        return [f"{key}: invalid verdict {verdict!r}"]
    for field in ("reviewer", "reviewed_at_utc", "review_notes"):
        if not row.get(field, "").strip():
            errs.append(f"{key}: completed verdict requires {field}")
    if row.get("reviewed_at_utc", "").strip():
        err = utc_error(row["reviewed_at_utc"], "reviewed_at_utc", key)
        if err: errs.append(err)
    if verdict in {"account_confirms", "conflict"}:
        if not row.get("x_profile_evidence_url", "").strip() and not row.get("evidence_quote_or_capture_id", "").strip():
            errs.append(f"{key}: {verdict} requires evidence URL or durable capture ID")
        if not row.get("evidence_quote_or_capture_id", "").strip():
            errs.append(f"{key}: {verdict} requires a short quote or capture ID")
        observed_id = row.get("evidence_verified_x_user_id", "").strip()
        target_id = row.get("x_user_id", "").strip()
        if not observed_id:
            errs.append(f"{key}: {verdict} requires evidence_verified_x_user_id")
        elif not observed_id.isdigit() or observed_id != target_id:
            errs.append(f"{key}: evidence_verified_x_user_id must equal the frozen target x_user_id")
        if not row.get("evidence_seen_at_utc", "").strip():
            errs.append(f"{key}: {verdict} requires evidence_seen_at_utc")
    if row.get("evidence_seen_at_utc", "").strip():
        err = utc_error(row["evidence_seen_at_utc"], "evidence_seen_at_utc", key)
        if err: errs.append(err)
    return errs


def validate(args: argparse.Namespace) -> tuple[dict, list[dict[str, str]] | None]:
    manifest_hash = sha256(args.workbook_manifest)
    if manifest_hash != args.expected_workbook_manifest_sha256.lower():
        raise ValueError("workbook manifest SHA-256 differs from out-of-band pinned digest")
    manifest = json.loads(args.workbook_manifest.read_text(encoding="utf-8"))
    expected_rows, expected_meta = build_expected_workbook(
        args.candidate, args.sample, args.frozen_manifest, args.queue, args.queue_report
    )
    for key, digest in expected_meta["source_sha256"].items():
        if manifest.get("source_sha256", {}).get(key) != digest:
            raise ValueError(f"workbook manifest source hash mismatch: {key}")
    baseline_buffer = io.StringIO(newline="")
    baseline_writer = csv.DictWriter(baseline_buffer, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
    baseline_writer.writeheader(); baseline_writer.writerows(expected_rows)
    baseline_sha = hashlib.sha256(baseline_buffer.getvalue().encode("utf-8")).hexdigest()
    if manifest.get("output_csv_sha256") != baseline_sha:
        raise ValueError("workbook manifest does not bind the reconstructed baseline workbook")
    workbook = read_csv(args.workbook)
    if not workbook or list(workbook[0].keys()) != OUTPUT_FIELDS:
        raise ValueError("workbook columns/order differ from the frozen workbook schema")
    if len(workbook) != 231 or manifest.get("output_rows") != 231:
        raise ValueError("expected exactly 231 workbook rows")
    errors: list[str] = []
    id_fields = ("review_order", "review_arm", "targeted_review_rank", "address", "x_user_id")
    immutable_fields = [f for f in OUTPUT_FIELDS if f not in REVIEW_COLS]
    for i, (actual, expected) in enumerate(zip(workbook, expected_rows), 2):
        key = f"line {i} ({actual.get('address','')[:12]}…/{actual.get('x_user_id','')})"
        for field in immutable_fields:
            if actual.get(field, "") != expected.get(field, ""):
                errors.append(f"{key}: immutable field {field} changed")
        if not ADDRESS_RE.fullmatch(actual.get("address", "")):
            errors.append(f"{key}: invalid Ethereum address")
        if not actual.get("x_user_id", "").isdigit():
            errors.append(f"{key}: x_user_id is not a stable numeric ID")
        errors.extend(evidence_errors(actual, i))

    pairs = [(r.get("address", "").lower(), r.get("x_user_id", "")) for r in workbook]
    if len(set(pairs)) != 231:
        errors.append("workbook contains duplicate address/X ID pairs")
    arms = Counter(r.get("review_arm", "") for r in workbook)
    if arms != Counter({"stratified_probability_sample_60": 60,
                        "targeted_nonprobability_complement_171": 171}):
        errors.append(f"review-arm allocation changed: {dict(arms)}")

    counts = {arm: Counter() for arm in (
        "stratified_probability_sample_60", "targeted_nonprobability_complement_171")}
    for row in workbook:
        v = row.get("manual_verdict", "").strip() or "pending"
        counts[row.get("review_arm", "")][v] += 1
    probability = [r for r in workbook if r.get("review_arm") == "stratified_probability_sample_60"]
    sample_complete = (len(probability) == 60 and all(r.get("manual_verdict", "").strip() in VERDICTS for r in probability)
                       and not errors)
    projected: list[dict[str, str]] | None = None
    if sample_complete:
        base_sample = read_csv(args.sample)
        by_pair = {(r["address"].lower(), r["x_user_id"]): r for r in probability}
        projected = []
        for base in base_sample:
            review = by_pair[(base["address"].lower(), base["x_user_id"])]
            merged = dict(base)
            for f in REVIEW_FIELDS:
                merged[f] = review.get(f, "")
            # retain the existing state field only if the frozen sample has it
            if "review_state" in merged:
                merged["review_state"] = review.get("review_state", "")
            projected.append(merged)

    report = {
        "mode": "offline_full_frame_review_workbook_validation_v1",
        "workbook_path": str(args.workbook), "workbook_sha256": sha256(args.workbook),
        "workbook_manifest_sha256": manifest_hash,
        "row_count": len(workbook), "review_arm_counts": dict(arms),
        "verdict_counts_by_arm": {arm: dict(counter) for arm, counter in counts.items()},
        "probability_sample_complete": sample_complete,
        "weighted_estimate_allowed": sample_complete,
        "targeted_complement_weighted_estimate_allowed": False,
        "validation_errors": errors,
        "network_requests": 0, "paid_queries_usd": 0,
        "interpretation": "Only the 60-row stratified probability sample may feed the design-weighted estimator for this 231-row frame. The 171-row targeted complement is descriptive/nonprobability and must be reported separately. Current account-side evidence is not historical as-of validity.",
    }
    return report, projected


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, required=True)
    ap.add_argument("--workbook-manifest", type=Path, required=True)
    ap.add_argument("--expected-workbook-manifest-sha256", required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--sample", type=Path, required=True)
    ap.add_argument("--frozen-manifest", type=Path, required=True)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--queue-report", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--sample-out", type=Path,
                    help="optional; written only after all 60 probability-sample reviews pass")
    args = ap.parse_args()
    report, projected = validate(args)
    if args.sample_out and projected is not None:
        if args.sample_out.exists():
            ap.error("sample-out exists; refusing to overwrite a prior adjudication export")
        args.sample_out.parent.mkdir(parents=True, exist_ok=True)
        with args.sample_out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(projected[0]), extrasaction="ignore")
            writer.writeheader(); writer.writerows(projected)
        report["probability_sample_projection_path"] = str(args.sample_out)
        report["probability_sample_projection_sha256"] = sha256(args.sample_out)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": report["row_count"], "sample_complete": report["probability_sample_complete"],
                      "errors": len(report["validation_errors"]), "out": str(args.out_json)}, ensure_ascii=False))
    if report["validation_errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
