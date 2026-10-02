#!/usr/bin/env python3
"""Validate a completed stratified ENS↔X review and estimate weighted rates.

Offline only. Does not mutate the review CSV, access X/ENS, or contact BigQuery.
Incomplete reviews produce a progress report only; no population estimate is emitted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = {"account_confirms", "ens_only", "conflict", "unverifiable"}
REQUIRED = {
    "address", "x_user_id", "sampling_stratum", "stratum_population_N",
    "stratum_sample_n", "design_weight", "manual_verdict", "reviewer",
    "reviewed_at_utc", "evidence_seen_at_utc", "x_profile_evidence_url",
    "evidence_quote_or_capture_id", "review_notes",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_utc(value: str, field: str, row_key: str) -> list[str]:
    if not value.strip():
        return [f"{row_key}: missing {field}"]
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return [f"{row_key}: {field} must include a timezone (UTC offset or Z)"]
    except ValueError:
        return [f"{row_key}: invalid ISO-8601 {field}: {value!r}"]
    return []


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"input missing columns: {', '.join(sorted(missing))}")
        return list(reader)


def frozen_frame_errors(rows: list[dict[str, str]], manifest: dict) -> list[str]:
    """Ensure review rows still match the pre-adjudication frame exactly."""
    errors: list[str] = []
    fields = manifest.get("immutable_fields", [])
    digests = manifest.get("ordered_row_digests", [])
    if not fields or not digests:
        return ["frozen manifest lacks immutable fields or row digests"]
    if len(rows) != manifest.get("row_count"):
        errors.append(f"review row count {len(rows)} differs from frozen frame {manifest.get('row_count')}")
    for i, row in enumerate(rows):
        if i >= len(digests):
            break
        payload = {k: row.get(k, "") for k in fields}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if digest != digests[i]:
            errors.append(f"line {i + 2}: immutable sample/design fields differ from frozen frame")
    expected_strata = manifest.get("strata", {})
    observed = Counter(r.get("sampling_stratum", "") for r in rows)
    for h, design in expected_strata.items():
        if observed[h] != int(design["n_h"]):
            errors.append(f"frozen stratum {h!r}: expected n_h={design['n_h']}, observed {observed[h]}")
    extra = set(observed) - set(expected_strata)
    if extra:
        errors.append(f"unexpected frozen strata: {sorted(extra)}")
    return errors


def validate(rows: list[dict[str, str]]) -> tuple[list[str], dict[str, dict]]:
    errors: list[str] = []
    pair_ids: set[tuple[str, str]] = set()
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    strata_meta: dict[str, tuple[int, int]] = {}
    for i, row in enumerate(rows, 2):
        addr = row["address"].strip().lower()
        uid = row["x_user_id"].strip()
        key = f"line {i} ({addr[:12]}…/{uid})"
        if not addr.startswith("0x") or len(addr) != 42:
            errors.append(f"{key}: address is not a 20-byte hex address")
        if not uid.isdigit():
            errors.append(f"{key}: x_user_id must be a stable numeric ID")
        pair = (addr, uid)
        if pair in pair_ids:
            errors.append(f"{key}: duplicate address/x_user_id pair")
        pair_ids.add(pair)
        verdict = row["manual_verdict"].strip()
        if verdict and verdict != "pending" and verdict not in VERDICTS:
            errors.append(f"{key}: invalid manual_verdict {verdict!r}")
        completed = verdict in VERDICTS
        if completed:
            if not row["reviewer"].strip():
                errors.append(f"{key}: reviewer is required")
            errors.extend(parse_utc(row["reviewed_at_utc"], "reviewed_at_utc", key))
            if not row["review_notes"].strip():
                errors.append(f"{key}: review_notes must state the adjudication rationale")
            if verdict in {"account_confirms", "conflict"}:
                if not row["x_profile_evidence_url"].strip() and not row["evidence_quote_or_capture_id"].strip():
                    errors.append(f"{key}: {verdict} requires an evidence URL or durable capture ID")
                if not row["evidence_quote_or_capture_id"].strip():
                    errors.append(f"{key}: {verdict} requires a short quote or capture ID")
                errors.extend(parse_utc(row["evidence_seen_at_utc"], "evidence_seen_at_utc", key))
            elif row["evidence_seen_at_utc"].strip():
                errors.extend(parse_utc(row["evidence_seen_at_utc"], "evidence_seen_at_utc", key))

        try:
            N = int(row["stratum_population_N"])
            n = int(row["stratum_sample_n"])
            w = float(row["design_weight"])
        except (TypeError, ValueError):
            errors.append(f"{key}: invalid N_h/n_h/design_weight")
            continue
        stratum = row["sampling_stratum"].strip()
        if not stratum or N < 1 or n < 1 or n > N:
            errors.append(f"{key}: invalid sampling stratum or N_h/n_h")
            continue
        if not math.isclose(w, N / n, rel_tol=1e-9, abs_tol=1e-9):
            errors.append(f"{key}: design_weight does not equal N_h/n_h")
        meta = (N, n)
        if stratum in strata_meta and strata_meta[stratum] != meta:
            errors.append(f"{key}: inconsistent N_h/n_h within stratum {stratum!r}")
        strata_meta[stratum] = meta
        groups[stratum].append(row)

    # The CSV must contain exactly the declared sample allocation in each stratum.
    for h, sample in groups.items():
        N, n = strata_meta[h]
        if len(sample) != n:
            errors.append(f"stratum {h!r}: contains {len(sample)} rows but declares n_h={n}")
        if n < N and n < 2:
            errors.append(f"stratum {h!r}: n_h=1 with N_h>1 cannot estimate within-stratum variance")
    return errors, groups


def estimate(groups: dict[str, list[dict[str, str]]]) -> dict:
    population_N = sum(int(rows[0]["stratum_population_N"]) for rows in groups.values())
    output = {}
    for category in sorted(VERDICTS):
        estimated_count = 0.0
        variance_total = 0.0
        stratum_rows = {}
        for h, rows in groups.items():
            N = int(rows[0]["stratum_population_N"])
            n = int(rows[0]["stratum_sample_n"])
            y = [1 if r["manual_verdict"].strip() == category else 0 for r in rows]
            p = sum(y) / n
            estimated_count += N * p
            if n > 1 and N > n:
                sample_var = (n / (n - 1)) * p * (1 - p)
                variance_total += (N / population_N) ** 2 * (1 - n / N) * sample_var / n
            stratum_rows[h] = {"N_h": N, "n_h": n, "sample_rate": p,
                               "estimated_count": N * p}
        rate = estimated_count / population_N if population_N else 0.0
        se = math.sqrt(max(0.0, variance_total))
        output[category] = {
            "estimated_population_count": estimated_count,
            "estimated_population_rate": rate,
            "design_based_se_rate": se,
            "normal_95pct_ci_rate": [max(0.0, rate - 1.96 * se), min(1.0, rate + 1.96 * se)],
            "strata": stratum_rows,
        }
    return {"population_N": population_N,
            "variance_method": "stratified SRS without replacement; finite-population correction; normal 95% interval",
            "categories": output}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="completed stratified sample CSV")
    ap.add_argument("--out", type=Path, required=True, help="JSON report path")
    ap.add_argument("--frozen-manifest", type=Path, required=True,
                    help="pre-adjudication manifest from freeze_ens_x_review_frame.py")
    ap.add_argument("--expected-manifest-sha256", required=True,
                    help="out-of-band SHA-256 recorded before review begins")
    args = ap.parse_args()
    rows = load_rows(args.input)
    manifest_bytes = args.frozen_manifest.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    errors, groups = validate(rows)
    if manifest_sha.lower() != args.expected_manifest_sha256.lower():
        errors.append("frozen manifest SHA-256 does not match the out-of-band expected digest")
    errors.extend(frozen_frame_errors(rows, manifest))
    counts = Counter(r.get("manual_verdict", "").strip() or "pending" for r in rows)
    pending = sum(1 for r in rows if r.get("manual_verdict", "").strip() not in VERDICTS)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_manual_review_validation",
        "input_path": str(args.input),
        "input_sha256": sha256(args.input),
        "frozen_manifest_path": str(args.frozen_manifest),
        "frozen_manifest_sha256": manifest_sha,
        "frozen_manifest_sha256_verified": manifest_sha.lower() == args.expected_manifest_sha256.lower(),
        "review_rows": len(rows),
        "strata_count": len(groups),
        "verdict_counts_including_pending": dict(counts),
        "validation_errors": errors,
        "review_complete": not errors and pending == 0 and len(rows) == manifest.get("row_count") and sum(len(v) for v in groups.values()) == len(rows),
        "population_estimates": None,
        "interpretation_limits": [
            "Estimates describe this 231-pair candidate frame only, not the full ENS universe.",
            "account_confirms is not historical as-of validity; event-time ENS state must be reconstructed separately.",
            "The CI is a design-based normal approximation and may be wide or poor with sparse strata.",
            "Do not treat pending, profile existence, handle similarity, or ENS-only evidence as confirmation.",
        ],
    }
    if report["review_complete"]:
        report["population_estimates"] = estimate(groups)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "review_complete": report["review_complete"],
                      "rows": len(rows), "pending": pending, "errors": len(errors),
                      "population_estimates_emitted": report["population_estimates"] is not None}, ensure_ascii=False))
    if errors:
        raise SystemExit(2)
    if pending:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
