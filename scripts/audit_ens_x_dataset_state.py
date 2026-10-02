#!/usr/bin/env python3
"""Offline, bounded audit of existing ENS-X crosswalk artifacts.

Reads local CSV/JSON/JSONL files only. It never contacts FxEmbed/X/ENS, BigQuery,
or submits, refreshes, or resumes a collection job.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def row_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)


def file_record(root: Path, rel: str) -> dict:
    p = root / rel
    return {"path": rel, "exists": p.is_file(),
            "size_bytes": p.stat().st_size if p.is_file() else None,
            "sha256": sha256(p) if p.is_file() else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    project = args.project.resolve()
    base = project / "artifacts/ens_x_crosswalk"

    batch = base / "fx_authorized_batch_20260924T172410Z"
    batch_manifest = read_json(batch / "run_manifest.json")
    batch_summary = read_json(batch / "run_summary.json")
    allowlist = read_csv(batch / "sample_manifest.csv")
    continuation = batch / "continuation_20260924_fixed_window"
    continuation_manifest = read_json(continuation / "continuation_manifest.json")
    continuation_summary = read_json(continuation / "combined_summary.json")

    profile = base / "profile_expansion_20260925"
    profile_summary = read_json(profile / "profile_audit_summary.json")
    profile_results = [json.loads(line) for line in
                       (profile / "profile_audit_results.jsonl").read_text(encoding="utf-8").splitlines()
                       if line.strip()]
    exact_candidates = read_csv(profile / "account_side_exact_match_candidates.csv")

    expansion = base / "expansion_decision_20260925"
    sample60_path = expansion / "candidate_review_stratified_sample_60.csv"
    sample60 = read_csv(sample60_path)
    full231 = read_csv(expansion / "candidate_review_full_231.csv")
    legacy50_path = profile / "manual_review_50.csv"
    legacy50 = read_csv(legacy50_path)

    pilot = base / "timeline_expansion_pilot_20260925"
    pilot_summary = read_json(pilot / "summary.json")
    pilot_integrity = read_json(pilot / "pilot_integrity_check.json")
    pilot_crosswalk = read_csv(pilot / "provisional_wallet_x_crosswalk.csv")

    seed = base / "two_graph_seed_20260925"
    seed_report = read_json(seed / "seed_quality_report.json")
    confirmed = read_csv(seed / "crosswalk_confirmed_unique.csv")

    seed_ids = {r["x_user_id"].strip() for r in confirmed}
    authorized_ids = {r["x_user_id"].strip() for r in allowlist}
    profile_ids = {r.get("x_user_id", "").strip() for r in exact_candidates}
    pilot_ids = {r.get("x_user_id", "").strip() for r in pilot_crosswalk}
    verdict_counts = Counter((r.get("manual_verdict", "").strip() or "pending") for r in sample60)
    full_verdict_counts = Counter((r.get("manual_verdict", "").strip() or "pending") for r in full231)
    legacy_verdict_counts = Counter((r.get("manual_verdict", "").strip() or "pending") for r in legacy50)

    review_171 = expansion / "targeted_manual_review_priority_171.csv"
    review_171_report = expansion / "targeted_manual_review_priority_report.json"
    review_171_status = "not_for_collection_or_confirmation"
    if review_171.exists() and review_171_report.exists():
        # Preserve the old files as audit evidence, but do not treat a heuristic
        # queue that joins independent snapshots as a validated expansion roster.
        review_171_status = "quarantined_heuristic_review_order_pending_rebuild"

    ens_names = ["addrchanged_latest.parquet", "reverse_evidence.parquet",
                 "textchanged_raw.parquet", "textchanged_raw_v2.parquet",
                 "textchanged_twitter.parquet"]
    ens_inventory = [file_record(base, n) for n in ens_names]

    source_paths = [
        "artifacts/ens_x_crosswalk/fx_authorized_batch_20260924T172410Z/run_manifest.json",
        "artifacts/ens_x_crosswalk/fx_authorized_batch_20260924T172410Z/run_summary.json",
        "artifacts/ens_x_crosswalk/fx_authorized_batch_20260924T172410Z/sample_manifest.csv",
        "artifacts/ens_x_crosswalk/fx_authorized_batch_20260924T172410Z/coverage.csv",
        "artifacts/ens_x_crosswalk/fx_authorized_batch_20260924T172410Z/requests.jsonl",
        "artifacts/ens_x_crosswalk/fx_authorized_batch_20260924T172410Z/tweets_in_window.jsonl",
        "artifacts/ens_x_crosswalk/profile_expansion_20260925/profile_audit_summary.json",
        "artifacts/ens_x_crosswalk/profile_expansion_20260925/profile_audit_results.jsonl",
        "artifacts/ens_x_crosswalk/profile_expansion_20260925/account_side_exact_match_candidates.csv",
        "artifacts/ens_x_crosswalk/profile_expansion_20260925/manual_review_50.csv",
        "artifacts/ens_x_crosswalk/timeline_expansion_pilot_20260925/summary.json",
        "artifacts/ens_x_crosswalk/timeline_expansion_pilot_20260925/pilot_integrity_check.json",
        "artifacts/ens_x_crosswalk/timeline_expansion_pilot_20260925/provisional_wallet_x_crosswalk.csv",
        "artifacts/ens_x_crosswalk/expansion_decision_20260925/candidate_review_stratified_sample_60.csv",
        "artifacts/ens_x_crosswalk/expansion_decision_20260925/targeted_manual_review_priority_171.csv",
        "artifacts/ens_x_crosswalk/expansion_decision_20260925/targeted_manual_review_priority_report.json",
        "artifacts/ens_x_crosswalk/two_graph_seed_20260925/crosswalk_confirmed_unique.csv",
        "artifacts/ens_x_crosswalk/two_graph_seed_20260925/seed_quality_report.json",
    ]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_local_artifact_audit_no_network_no_bigquery_no_collection",
        "project_root": str(project),
        "background_collection_process_check": "not_performed_by_script; caller must inspect process/job handles separately",
        "scopes": {
            "seed_crosswalk": {
                "confirmed_wallet_x_pairs": len(confirmed),
                "stable_x_ids": len(seed_ids),
                "seed_quality_report": seed_report,
                "scope": "manually checked seed; distinct from profile candidates and 50-account pilot",
            },
            "explicit_fx_batch": {
                "run_id": batch_manifest.get("run_id"),
                "manifest_account_count": batch_manifest.get("account_count"),
                "allowlist_rows": len(allowlist),
                "unique_allowlist_x_ids": len(authorized_ids),
                "allowlist_equals_seed_id_set": authorized_ids == seed_ids,
                "automatic_candidate_pool_expansion": batch_manifest.get("collection_semantics", {}).get("automatic_candidate_pool_expansion"),
                "summary": batch_summary,
                "continuation_manifest": continuation_manifest,
                "continuation_summary": continuation_summary,
                "scope_note": "Continuation inherits the original 12-ID allowlist and fixed target cutoff; it is not an expansion run.",
                "scope": "12-ID allowlist batch only; manifest excludes automatic candidate-pool expansion",
            },
            "profile_scan_separate_scope": {
                "summary": profile_summary,
                "result_rows": len(profile_results),
                "candidate_rows": len(exact_candidates),
                "candidate_unique_wallets": len({r.get("address", "").lower() for r in exact_candidates}),
                "candidate_unique_stable_x_ids": len(profile_ids),
                "candidate_ids_overlap_seed_ids": len(profile_ids & seed_ids),
                "candidate_status": "all candidates remain unconfirmed pending manual evidence review",
            },
            "timeline_pilot_separate_scope": {
                "summary": pilot_summary,
                "integrity": pilot_integrity,
                "provisional_crosswalk_rows": len(pilot_crosswalk),
                "provisional_unique_x_ids": len(pilot_ids),
                "pilot_ids_overlap_explicit_fx_allowlist": len(pilot_ids & authorized_ids),
                "pilot_ids_overlap_seed_ids": len(pilot_ids & seed_ids),
                "pilot_ids_overlap_231_profile_candidate_ids": len(pilot_ids & profile_ids),
                "pilot_ids_overlap_frozen_60_sample": len(pilot_ids & {r.get("x_user_id", "").strip() for r in sample60}),
                "manual_verdict_counts_for_legacy_50": dict(legacy_verdict_counts),
                "account_side_confirmation_rows": sum(
                    r.get("manual_verdict", "").strip() == "account_confirms" for r in legacy50
                ),
                "collection_authorization_manifest_found": False,
                "crosswalk_admission_status": "provisional_only_not_confirmed_crosswalk",
                "scope": "separate 50-account provisional pilot; do not merge into confirmed crosswalk or authorized 12-ID run",
            },
            "231_candidate_manual_review": {
                "candidate_frame_rows": len(full231),
                "candidate_frame_verdict_counts": dict(full_verdict_counts),
                "frozen_probability_sample_rows": len(sample60),
                "sample_verdict_counts": dict(verdict_counts),
                "sample_complete": len(sample60) > 0 and all(r.get("manual_verdict", "").strip() in {"account_confirms", "ens_only", "conflict", "unverifiable"} for r in sample60),
                "legacy_review_rows": len(legacy50),
                "legacy_verdict_counts": dict(legacy_verdict_counts),
                "legacy_sample_is_distinct": True,
                "weighting_rule": "Only after all 60 frozen rows have valid independent verdicts; estimate applies only to the 231-candidate frame.",
            },
            "heuristic_priority_artifact": {
                "path": str(review_171.relative_to(project)),
                "status": review_171_status,
                "not_a_collection_authorization": True,
                "reason": "A review-order heuristic joining candidate snapshot metadata and seed-network observations has not been validated as a population or collection selection design.",
            },
            "event_time_asof_reconstruction": {
                "local_ens_evidence_files": ens_inventory,
                "status": "not_demonstrated_from_current_local_artifacts",
                "limitations": [
                    "addrchanged_latest.parquet is a latest-state artifact by name and is not itself a complete historical AddrChanged stream.",
                    "Reverse/text evidence files exist, but this audit does not certify complete event history, schema semantics, resolver changes, or block-time ordering.",
                    "No event-level as-of join was executed; current snapshot fields must not be represented as historically valid links.",
                    "BigQuery objects, schemas, and billed costs were not queried or dry-run in this offline audit.",
                ],
                "required_inputs_before_join": ["AddrChanged event log", "reverse-record changes", "resolver changes", "Twitter text-record changes", "block/transaction/log ordering and UTC timestamp mapping", "stable X-ID observation/effective-time evidence"],
            },
            "hard_gates_for_next_batch": {
                "scope": "No new fetch or paid query is triggered by this audit.",
                "required_before_any_collection": [
                    "Manually adjudicate the frozen 60-row probability sample; keep 231 candidates separate from confirmed mappings.",
                    "For each proposed account, require account-side identity evidence and stable X user ID; reject ENS-only or profile-existence-only links.",
                    "The existing 50-account timeline pilot matches 50/50 records in the 231-candidate frame, but has no completed account-side verdicts; preserve it as provisional and never promote its mapping rows without separate adjudication.",
                    "Freeze an explicit allowlist, target UTC interval, endpoint/source, per-account page cap, total request cap, retry cap, and stop conditions in a run manifest.",
                    "For BigQuery, require dry-run bytes, maximum_bytes_billed, project/table and cost approval before any paid job.",
                    "Archive every request/response, cursor, error, stop reason, coverage row, and content hash; resume only from an audited checkpoint.",
                    "Do not claim complete history when a page ceiling is hit; report cursor exhaustion only as endpoint exhaustion.",
                ],
                "reusable_caps_must_be_explicit_per_run": True,
            },
        },
        "source_sha256": [file_record(project, p) for p in source_paths],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(args.out),
        "sample60_complete": report["scopes"]["231_candidate_manual_review"]["sample_complete"],
        "seed_count": len(confirmed), "profile_candidates": len(exact_candidates),
        "pilot_crosswalk": len(pilot_crosswalk),
        "asof": report["scopes"]["event_time_asof_reconstruction"]["status"],
        "network_used": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
