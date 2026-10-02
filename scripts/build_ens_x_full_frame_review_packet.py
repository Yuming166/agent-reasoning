#!/usr/bin/env python3
"""Build an offline, fail-closed 231-pair human-review workbook.

The frozen 60-row stratified probability sample retains its design weights. The
remaining 171 rows are included as a separate targeted, non-probability review
complement. No automatic evidence is promoted and no network/API is used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from summarize_ens_x_manual_review import frozen_frame_errors  # noqa: E402

PINNED = {
    "candidate_sha256": "8871786e9b8897b7ba36b81c8218d862eb4248b1f43ff6cac61c48132a93c71d",
    "sample_sha256": "8aedc9e24309052f7a42ce5e7712cf463aeacbfdc5012f00444674b26834e030",
    "sample_manifest_sha256": "d5bc8639a1739f66bdddf1a7394431c11b8296a01ae65060d0166d00a7f42bdc",
    "queue_sha256": "7e8a575ce51c12bdf625296e5c52cae4c4c3628a9a531b4cf684c53a6c39131e",
    "queue_report_sha256": "3729455860963df09f1f89f706010c6e2837fc8fc5e5e69e03eabf8e366af05c",
}
REVIEW_FIELDS = (
    "manual_verdict", "x_profile_evidence_url", "evidence_quote_or_capture_id",
    "evidence_verified_x_user_id", "evidence_seen_at_utc", "reviewer", "reviewed_at_utc", "review_notes",
)
OUTPUT_FIELDS = [
    "review_order", "review_arm", "targeted_review_rank", "address", "x_user_id",
    "handle_at_profile_audit", "reverse_ens_name", "candidate_selection_stratum",
    "sampling_stratum", "stratum_population_N", "stratum_sample_n",
    "inclusion_probability", "design_weight", "sampling_seed",
    "automatic_evidence_types_not_adjudication", "automatic_matched_terms_not_adjudication",
    "candidate_events_2026", "x_profile_url_from_stable_id",
    *REVIEW_FIELDS, "review_state",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pair(row: dict[str, str]) -> tuple[str, str]:
    return row.get("address", "").strip().lower(), row.get("x_user_id", "").strip()


def build(candidate_path: Path, sample_path: Path, frozen_manifest_path: Path,
          queue_path: Path, queue_report_path: Path) -> tuple[list[dict[str, str]], dict]:
    paths = {
        "candidate": candidate_path, "sample": sample_path,
        "sample_manifest": frozen_manifest_path, "queue": queue_path,
        "queue_report": queue_report_path,
    }
    for name, path in paths.items():
        expected = PINNED[f"{name}_sha256"]
        if sha(path) != expected:
            raise ValueError(f"{name} SHA-256 differs from pinned audit input")

    candidates, sample, queue = read_csv(candidate_path), read_csv(sample_path), read_csv(queue_path)
    manifest = json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
    report = json.loads(queue_report_path.read_text(encoding="utf-8"))
    if len(candidates) != 231 or len(sample) != 60 or len(queue) != 171:
        raise ValueError("expected exact 231/60/171 candidate, sample, and complement row counts")
    errors = frozen_frame_errors(sample, manifest)
    if errors:
        raise ValueError("frozen 60 sample integrity failure: " + "; ".join(errors[:8]))
    if manifest.get("source_sha256_at_freeze") != sha(sample_path):
        raise ValueError("sample bytes do not match frozen manifest source hash")
    if report.get("candidate_rows") != 231 or report.get("representative_sample_rows_excluded") != 60 or report.get("remaining_rows") != 171:
        raise ValueError("targeted queue report counts do not match frozen frame partition")
    report_sources = report.get("source_sha256", {})
    normalized_sources = {}
    for raw_path, digest in report_sources.items():
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = PROJECT_ROOT / source_path
        normalized_sources[source_path.resolve()] = digest
    if normalized_sources.get(candidate_path.resolve()) != sha(candidate_path) or normalized_sources.get(sample_path.resolve()) != sha(sample_path):
        raise ValueError("queue report source hashes do not bind the candidate/sample inputs")
    if report.get("queue_csv_sha256") != sha(queue_path):
        raise ValueError("queue report does not bind current targeted queue bytes")

    ck, sk, qk = [pair(r) for r in candidates], [pair(r) for r in sample], [pair(r) for r in queue]
    if any(not a or not x for a, x in ck + sk + qk):
        raise ValueError("blank address or stable X ID in inputs")
    if len(set(ck)) != 231 or len({r["address"].lower() for r in candidates}) != 231 or len({r["x_user_id"] for r in candidates}) != 231:
        raise ValueError("candidate frame has duplicate pairs, addresses, or stable IDs")
    if len(set(sk)) != 60 or len(set(qk)) != 171:
        raise ValueError("sample or complement contains duplicate pairs")
    if not set(sk) <= set(ck) or not set(qk) <= set(ck):
        raise ValueError("sample or targeted complement includes non-frame pairs")
    if set(sk) & set(qk) or set(sk) | set(qk) != set(ck):
        raise ValueError("60 sample and 171 complement are not a disjoint exact cover of 231")
    if any(r.get("manual_verdict", "").strip() != "pending" for r in candidates):
        raise ValueError("candidate frame already contains non-pending verdict; refusing to rebuild")

    by_pair = {pair(r): r for r in candidates}
    sampled = {pair(r): r for r in sample}
    targeted = {pair(r): r for r in queue}
    rank_by_pair = {pair(r): r.get("targeted_review_rank", "") for r in queue}
    ordered_pairs = sorted(sampled, key=lambda k: sample.index(sampled[k]))
    ordered_pairs += sorted(targeted, key=lambda k: int(rank_by_pair[k]))
    output: list[dict[str, str]] = []
    for i, key in enumerate(ordered_pairs, 1):
        c = by_pair[key]
        if key in sampled:
            s = sampled[key]
            arm = "stratified_probability_sample_60"
            vals = {
                "sampling_stratum": s.get("sampling_stratum", ""),
                "stratum_population_N": s.get("stratum_population_N", ""),
                "stratum_sample_n": s.get("stratum_sample_n", ""),
                "inclusion_probability": s.get("inclusion_probability", ""),
                "design_weight": s.get("design_weight", ""),
                "sampling_seed": s.get("sampling_seed", ""),
            }
            for field in REVIEW_FIELDS:
                if s.get(field, "").strip() and field not in {"manual_verdict"}:
                    raise ValueError(f"frozen sample already has review data in {field}; refusing to overwrite")
            if s.get("manual_verdict", "").strip() != "pending":
                raise ValueError("frozen sample contains a non-pending manual verdict")
            rank = ""
        else:
            t = targeted[key]
            arm = "targeted_nonprobability_complement_171"
            vals = {"sampling_stratum": "", "stratum_population_N": "", "stratum_sample_n": "",
                    "inclusion_probability": "", "design_weight": "", "sampling_seed": ""}
            rank = t.get("targeted_review_rank", "")
        row = {
            "review_order": str(i), "review_arm": arm, "targeted_review_rank": rank,
            "address": c["address"], "x_user_id": c["x_user_id"],
            "handle_at_profile_audit": c.get("handle_at_profile_audit", ""),
            "reverse_ens_name": c.get("reverse_ens_name", ""),
            "candidate_selection_stratum": c.get("selection_stratum", ""),
            **vals,
            "automatic_evidence_types_not_adjudication": c.get("evidence_types", ""),
            "automatic_matched_terms_not_adjudication": c.get("matched_terms", ""),
            "candidate_events_2026": c.get("events_2026", ""),
            "x_profile_url_from_stable_id": f"https://x.com/i/user/{c['x_user_id']}",
            "manual_verdict": "pending", "review_state": "not_started_account_side_evidence_required",
            **{field: "" for field in REVIEW_FIELDS if field != "manual_verdict"},
        }
        output.append(row)
    strata = manifest.get("strata", {})
    if sum(int(v["N_h"]) for v in strata.values()) != 231 or sum(int(v["n_h"]) for v in strata.values()) != 60:
        raise ValueError("frozen sample strata do not describe the full frame and 60-row sample")
    metadata = {
        "mode": "offline_full_frame_manual_review_packet_v2",
        "candidate_rows": len(candidates), "probability_sample_rows": len(sample),
        "targeted_nonprobability_complement_rows": len(queue), "output_rows": len(output),
        "sample_complement_disjoint_exact_cover": True,
        "strata_count": len(strata), "stratum_population_total": sum(int(v["N_h"]) for v in strata.values()),
        "stratum_sample_total": sum(int(v["n_h"]) for v in strata.values()),
        "verdicts_assigned": 0, "all_rows_pending": all(r["manual_verdict"] == "pending" for r in output),
        "design_weights_only_on_probability_sample": all(bool(r["design_weight"]) == (r["review_arm"] == "stratified_probability_sample_60") for r in output),
        "network_requests": 0, "paid_queries_usd": 0, "crosswalk_modified": False,
        "interpretation": "Only the frozen 60-row arm supports design-based estimates for this 231-row frame. The 171-row targeted complement has no inclusion probability or design weight; do not combine it into weighted estimates. A complete adjudicated census may be reported separately after all 231 rows have valid evidence and verdicts.",
        "source_sha256": {name: sha(path) for name, path in paths.items()},
    }
    return output, metadata


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--sample", type=Path, required=True)
    ap.add_argument("--frozen-manifest", type=Path, required=True)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--queue-report", type=Path, required=True)
    ap.add_argument("--out-csv", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    args = ap.parse_args()
    if args.out_csv.exists() or args.out_json.exists():
        ap.error("output exists; refusing to overwrite review progress")
    rows, metadata = build(args.candidate, args.sample, args.frozen_manifest, args.queue, args.queue_report)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    metadata["output_csv_sha256"] = sha(args.out_csv)
    args.out_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in metadata.items() if k not in {"source_sha256", "interpretation"}}, indent=2))


if __name__ == "__main__":
    main()
