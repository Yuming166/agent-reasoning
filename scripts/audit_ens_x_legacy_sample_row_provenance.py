#!/usr/bin/env python3
"""Audit legacy ENS-X sample row provenance without changing source data.

The audit establishes exact sample-to-frame matches and key-sequence alignment
between the frame and bidirectional-validation tables. It treats duplicate
address+handle keys as ambiguous rather than assigning validation rows by position.
It never transfers or repairs labels or treats profile auto-matches as human
adjudication.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path("artifacts/ens_x_crosswalk")
DEFAULTS = {
    "sample": BASE / "verification_sample_v2.csv",
    "filled": BASE / "verification_sample_v2_filled.csv",
    "frame": BASE / "pairs_stratified_frame.csv",
    "validation": BASE / "bidirectional_validation.csv",
    "classifier": Path("scripts/classify_verification.py"),
}
SAMPLE_MATCH_FIELDS = ("node", "address", "handle", "record_set_at", "transaction_hash")
ALIGN_FIELDS = ("address", "handle")
PRESERVED_FIELDS = (
    "pair_id", "status", "reverse_name", "recency", "activity", "multiplicity",
    "resolver_era", "address", "node", "handle", "record_set_at", "transaction_hash",
    "x_profile_url", "events_2026",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"missing CSV header: {path}")
        return list(reader)


def norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def tuple_key(row: dict[str, str], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(norm(row.get(field)) for field in fields)


def audit_rows(sample, filled, frame, validation) -> dict:
    ids = [r.get("pair_id", "") for r in sample]
    sample_id_unique = len(ids) == len(set(ids)) and all(ids)

    frame_index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, row in enumerate(frame):
        frame_index[tuple_key(row, SAMPLE_MATCH_FIELDS)].append(i)

    matches, missing, ambiguous, status_conflicts, unresolved_validation = [], [], [], [], []
    validation_pair_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    frame_pair_groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, row in enumerate(frame):
        frame_pair_groups[tuple_key(row, ALIGN_FIELDS)].append(i)
    for i, row in enumerate(validation):
        validation_pair_groups[tuple_key(row, ALIGN_FIELDS)].append(i)

    for sample_i, row in enumerate(sample):
        key = tuple_key(row, SAMPLE_MATCH_FIELDS)
        positions = frame_index.get(key, [])
        if not positions:
            missing.append(row.get("pair_id", f"row_{sample_i + 1}"))
            continue
        if len(positions) != 1:
            ambiguous.append({"pair_id": row.get("pair_id", ""), "frame_rows_1based": [p + 1 for p in positions]})
            continue
        frame_i = positions[0]
        entry = {"pair_id": row.get("pair_id", ""), "sample_row_1based": sample_i + 2, "frame_row_1based": frame_i + 2}
        matches.append(entry)

        pair_key = tuple_key(frame[frame_i], ALIGN_FIELDS)
        frame_pair_positions = frame_pair_groups[pair_key]
        validation_pair_positions = validation_pair_groups.get(pair_key, [])
        if len(frame_pair_positions) != 1 or len(validation_pair_positions) != 1:
            unresolved_validation.append({
                **entry,
                "reason": "address_handle_not_unique_in_frame_or_validation",
                "frame_group_size": len(frame_pair_positions),
                "validation_group_size": len(validation_pair_positions),
            })
            continue

        validation_i = validation_pair_positions[0]
        vrow = validation[validation_i]
        if norm(row.get("status")) != norm(vrow.get("status")):
            status_conflicts.append({
                **entry,
                "validation_row_1based": validation_i + 2,
                "sample_status": row.get("status", ""),
                "validation_status": vrow.get("status", ""),
                "join_basis": "unique_address_handle_in_both_tables",
            })

    row_alignment = len(frame) == len(validation) and all(
        all(norm(fr.get(k)) == norm(vr.get(k)) for k in ALIGN_FIELDS)
        for fr, vr in zip(frame, validation)
    )
    frame_duplicate_groups = [v for v in frame_pair_groups.values() if len(v) > 1]
    validation_duplicate_groups = [v for v in validation_pair_groups.values() if len(v) > 1]

    filled_by_id = {r.get("pair_id", ""): r for r in filled}
    sample_by_id = {r.get("pair_id", ""): r for r in sample}
    filled_alignment = len(filled) == len(sample) and set(filled_by_id) == set(sample_by_id)
    preserved_field_mismatches = []
    if filled_alignment:
        for pair_id, orig in sample_by_id.items():
            out = filled_by_id[pair_id]
            diffs = [k for k in PRESERVED_FIELDS if norm(orig.get(k)) != norm(out.get(k))]
            if diffs:
                preserved_field_mismatches.append({"pair_id": pair_id, "fields": diffs})

    return {
        "sample_rows": len(sample),
        "sample_pair_ids_unique": sample_id_unique,
        "frame_rows": len(frame),
        "validation_rows": len(validation),
        "sample_exact_frame_matches": len(matches),
        "sample_missing_from_frame": missing,
        "sample_ambiguous_in_frame": ambiguous,
        "frame_validation_ordered_address_handle_alignment": row_alignment,
        "frame_address_handle_duplicate_group_count": len(frame_duplicate_groups),
        "frame_rows_in_duplicate_address_handle_groups": sum(map(len, frame_duplicate_groups)),
        "validation_address_handle_duplicate_group_count": len(validation_duplicate_groups),
        "validation_rows_in_duplicate_address_handle_groups": sum(map(len, validation_duplicate_groups)),
        "sample_validation_linkage_unresolved_count": len(unresolved_validation),
        "sample_validation_links_unambiguous": len(unresolved_validation) == 0,
        "sample_validation_linkage_unresolved": unresolved_validation,
        "sample_status_conflict_count": len(status_conflicts),
        "sample_status_conflicts": status_conflicts,
        "filled_rows": len(filled),
        "filled_matches_sample_pair_id_set": filled_alignment,
        "filled_preserved_source_field_mismatches": preserved_field_mismatches,
        "sample_status_counts": dict(Counter(r.get("status", "") for r in sample)),
        "filled_verification_status_counts": dict(Counter(r.get("verification_status", "") for r in filled)),
        "filled_account_side_labels_are_human_adjudication": False,
        "match_fields": list(SAMPLE_MATCH_FIELDS),
        "validation_alignment_fields": list(ALIGN_FIELDS),
    }


def build_report(paths: dict[str, Path]) -> dict:
    source_rows = {name: read_csv(path) for name, path in paths.items() if name != "classifier"}
    row_audit = audit_rows(
        source_rows["sample"], source_rows["filled"], source_rows["frame"], source_rows["validation"]
    )
    hashes = {name: {"path": str(path), "sha256": sha256(path)} for name, path in paths.items()}
    checks = {
        "sample_pair_ids_unique": row_audit["sample_pair_ids_unique"],
        "every_sample_row_exactly_matches_one_frame_row": (
            row_audit["sample_exact_frame_matches"] == row_audit["sample_rows"]
            and not row_audit["sample_missing_from_frame"]
            and not row_audit["sample_ambiguous_in_frame"]
        ),
        "frame_and_validation_order_align_by_address_handle": row_audit["frame_validation_ordered_address_handle_alignment"],
        "filled_preserves_all_original_fields": (
            row_audit["filled_matches_sample_pair_id_set"]
            and not row_audit["filled_preserved_source_field_mismatches"]
        ),
        "sample_validation_links_unambiguous": row_audit["sample_validation_links_unambiguous"],
        "all_uniquely_linked_rows_are_status_consistent": row_audit["sample_status_conflict_count"] == 0,
    }
    return {
        "mode": "offline_read_only_legacy_sample_provenance_audit",
        "network_requests": 0,
        "source_hashes": hashes,
        "row_audit": row_audit,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "provenance_boundary": {
            "sample_generator_bound_to_exact_version": False,
            "filled_output_writer_execution_bound_by_run_hash": False,
            "classifier_contains_automatic_profile_text_matching": True,
            "account_confirms_labels_independently_human_reviewed": False,
            "status_conflicts_repaired_or_transferred": False,
        },
        "interpretation": (
            "Exact row matches and source-field preservation establish artifact alignment only. "
            "Status differences are called conflicts only when address+handle uniquely joins in both tables. "
            "Repeated address+handle groups remain unlinked/ambiguous; do not use row position to infer identity, "
            "overwrite labels, or infer historical link validity. Profile-derived labels are not independent human adjudication."
        ),
    }


def render_markdown(report: dict) -> str:
    rows = report["row_audit"]
    lines = [
        "# Legacy ENS–X sample row-provenance audit",
        "",
        "Offline/read-only. No source row was changed and no network or paid query was used.",
        "",
        "## Alignment",
        "",
        f"- Sample rows: {rows['sample_rows']}; unique pair IDs: {rows['sample_pair_ids_unique']}",
        f"- Exact sample-to-frame matches: {rows['sample_exact_frame_matches']}/{rows['sample_rows']}; missing: {len(rows['sample_missing_from_frame'])}; ambiguous: {len(rows['sample_ambiguous_in_frame'])}.",
        f"- Ordered address+handle key sequences align: {rows['frame_validation_ordered_address_handle_alignment']} (this does not establish unique row identity where keys repeat).",
        f"- Filled file preserves original source columns: {rows['filled_matches_sample_pair_id_set'] and not rows['filled_preserved_source_field_mismatches']}.",
        "",
        f"- Duplicate address+handle groups: frame {rows['frame_address_handle_duplicate_group_count']} groups / {rows['frame_rows_in_duplicate_address_handle_groups']} rows; validation {rows['validation_address_handle_duplicate_group_count']} groups / {rows['validation_rows_in_duplicate_address_handle_groups']} rows.",
        f"- Sample rows whose validation counterpart is ambiguous on address+handle: {rows['sample_validation_linkage_unresolved_count']}/{rows['sample_exact_frame_matches']}",
        "",
        "## Unresolved sample-vs-validation status conflicts (unique joins only)",
        "",
        "| Pair ID | Sample status | Validation status | Frame row |",
        "|---|---|---|---:|",
    ]
    for item in rows["sample_status_conflicts"]:
        lines.append(f"| {item['pair_id']} | {item['sample_status']} | {item['validation_status']} | {item['frame_row_1based']} |")
    if not rows["sample_status_conflicts"]:
        lines.append("| — | none among uniquely joined rows; this does not resolve ambiguous duplicate-key rows | — | — |")
    lines += [
        "",
        "Only unique address+handle joins are labeled conflicts. Duplicate-key rows are unresolved, not conflicts; ordered row position is insufficient to assign validation records. No labels are repaired. The filled workbook's profile-text labels are not proof of independent human review.",
        "The exact generator for the original sample and a run-hash binding for the filled output remain unverified.",
        "",
        "## Source SHA-256",
        "",
    ]
    for name, item in report["source_hashes"].items():
        lines.append(f"- `{name}` (`{item['path']}`): `{item['sha256']}`")
    unresolved = rows["sample_validation_linkage_unresolved_count"]
    conflicts = rows["sample_status_conflict_count"]
    lines += [
        "",
        f"Overall audit checks pass: **{report['all_checks_pass']}** (false here because {unresolved} sampled row(s) cannot be uniquely linked to validation records by the available key; {conflicts} uniquely linked status conflict(s) detected).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: args.project_root / path for name, path in DEFAULTS.items()}
    report = build_report(paths)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"all_checks_pass": report["all_checks_pass"], "row_audit": report["row_audit"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
