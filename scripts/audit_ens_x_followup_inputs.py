#!/usr/bin/env python3
"""Offline audit of whether reviewed ENS/X candidates can enter a follow-up shortlist.

This script never makes network requests and never promotes candidate mappings.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


DEFAULT_ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts" / "ens_x_crosswalk"
V2_WORKBOOK_MANIFEST_SHA256 = "439fd267328d0db556cc5f4f7298c46e41be0379f7e6f34e0741609ae07ade39"


def file_info(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "sha256": None, "row_count": None, "fields": []}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return {"path": str(path), "exists": True, "sha256": digest, "row_count": len(rows), "fields": fields, "rows": rows}


def validate_authoritative_workbook(artifact_root: Path, workbook: Path, manifest: Path) -> dict[str, Any]:
    """Run the full frozen-source validator; never infer validity from CSV fields alone."""
    decision = artifact_root / "expansion_decision_20260925"
    queue_dir = decision / "targeted_review_queue_20260925"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_ens_x_full_frame_review_workbook import validate

    args = SimpleNamespace(
        workbook=workbook,
        workbook_manifest=manifest,
        expected_workbook_manifest_sha256=V2_WORKBOOK_MANIFEST_SHA256,
        candidate=decision / "candidate_review_full_231.csv",
        sample=decision / "candidate_review_stratified_sample_60.csv",
        frozen_manifest=decision / "candidate_review_stratified_sample_60.frozen_manifest.json",
        queue=queue_dir / "manual_review_queue_171.csv",
        queue_report=queue_dir / "queue_report.json",
    )
    report, _ = validate(args)
    return report


def inspect_inputs(artifact_root: Path, *, allow_legacy: bool = False) -> dict[str, Any]:
    decision = artifact_root / "expansion_decision_20260925"
    state = artifact_root / "state_audit_20260925"
    selection = decision / "followup_selection_recheck_20260925"
    paths = {
        "legacy_candidate_frame_231": decision / "candidate_review_full_231.csv",
        "manual_review_workbook_231_v2": artifact_root / "goal_audit_20260925" / "manual_review_workbook_231_v2.csv",
        "manual_review_workbook_231_v2_manifest": artifact_root / "goal_audit_20260925" / "manual_review_workbook_231_v2_manifest.json",
        "frozen_probability_sample_60": decision / "candidate_review_stratified_sample_60.csv",
        "manual_review_packet_60": state / "manual_review_packet_60.csv",
        "confirmed_seed_crosswalk": artifact_root / "two_graph_seed_20260925" / "crosswalk_confirmed_unique.csv",
        "fixed_window_timeline_metrics": decision / "followup_selection_20260925" / "timeline_metrics_unavailable.csv",
        "provisional_candidate_lower_bound_metrics_50": state / "provisional_50_timeline_lower_bound_metrics_20260925.csv",
        "legacy_fx_pilot_metrics_13": artifact_root / "fx_pilot_metrics.csv",
        "previous_shortlist": selection / "shortlist.csv",
        "previous_selection_report": selection / "selection_report.json",
    }
    data = {key: file_info(path) for key, path in paths.items() if key != "previous_selection_report"}

    workbook_info = data["manual_review_workbook_231_v2"]
    manifest_info = data["manual_review_workbook_231_v2_manifest"]
    workbook_validation: dict[str, Any] = {
        "available": False,
        "valid": False,
        "report": None,
        "error": None,
    }
    if workbook_info["exists"] and manifest_info["exists"]:
        try:
            validation = validate_authoritative_workbook(
                artifact_root,
                Path(workbook_info["path"]),
                Path(manifest_info["path"]),
            )
            workbook_validation = {
                "available": True,
                "valid": not validation.get("validation_errors")
                and validation.get("row_count") == 231
                and validation.get("workbook_manifest_sha256") == V2_WORKBOOK_MANIFEST_SHA256,
                "report": validation,
                "error": None,
            }
        except Exception as exc:  # fail closed and preserve the reason in the audit
            workbook_validation = {"available": True, "valid": False, "report": None,
                                   "error": f"{type(exc).__name__}: {exc}"}

    if workbook_info["exists"]:
        # The v2 workbook is authoritative whenever present, even when invalid.
        frame_rows = workbook_info.get("rows") or []
        frame = frame_rows if workbook_validation["valid"] else []
        sample = [r for r in frame_rows if r.get("review_arm") == "stratified_probability_sample_60"] if workbook_validation["valid"] else []
    elif allow_legacy:
        frame_info = data["legacy_candidate_frame_231"]
        frame = frame_info.get("rows") or []
        sample = data["frozen_probability_sample_60"].get("rows") or []
        workbook_validation["error"] = "explicit legacy compatibility mode; v2 workbook absent"
    else:
        frame, sample = [], []
    report_path = paths["previous_selection_report"]
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        data["previous_selection_report"] = {
            "path": str(report_path),
            "exists": True,
            "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "report": report,
        }
    else:
        data["previous_selection_report"] = {"path": str(report_path), "exists": False, "report": None}

    packet = data["manual_review_packet_60"].get("rows") or []
    seed = data["confirmed_seed_crosswalk"].get("rows") or []
    fixed_metrics = data["fixed_window_timeline_metrics"].get("rows") or []
    lower_bound = data["provisional_candidate_lower_bound_metrics_50"].get("rows") or []
    legacy = data["legacy_fx_pilot_metrics_13"].get("rows") or []
    shortlist = data["previous_shortlist"].get("rows") or []

    verdict_counts = Counter((row.get("manual_verdict") or "").strip() or "missing" for row in frame)
    sample_verdict_counts = Counter((row.get("manual_verdict") or "").strip() or "missing" for row in sample)
    lower_bound_status_counts = Counter((row.get("crosswalk_status") or "").strip() or "missing" for row in lower_bound)
    lower_bound_complete_claim_counts = Counter((row.get("window_coverage_complete_claim") or "").strip() or "missing" for row in lower_bound)
    account_confirms = [r for r in frame if (r.get("manual_verdict") or "").strip() == "account_confirms"]
    evidence_complete_confirms = [r for r in account_confirms if all((r.get(k) or "").strip() for k in (
        "x_user_id", "reviewer", "reviewed_at_utc", "x_profile_evidence_url", "evidence_quote_or_capture_id", "evidence_seen_at_utc"
    ))]
    stable_numeric_seed_ids = {str(r.get("x_user_id", "")).strip() for r in seed if str(r.get("x_user_id", "")).strip().isdigit()}
    lower_bound_ids = {str(r.get("x_user_id", "")).strip() for r in lower_bound if str(r.get("x_user_id", "")).strip().isdigit()}
    fixed_metric_ids = {str(r.get("x_user_id", "")).strip() for r in fixed_metrics if str(r.get("x_user_id", "")).strip().isdigit()}
    eligible_confirm_ids = {str(r.get("x_user_id", "")).strip() for r in evidence_complete_confirms if str(r.get("x_user_id", "")).strip().isdigit()} - stable_numeric_seed_ids
    fixed_window_join_ids = eligible_confirm_ids & fixed_metric_ids
    provisional_only_join_ids = eligible_confirm_ids & lower_bound_ids
    legacy_stable_ids = {str(r.get("x_user_id", "")).strip() for r in legacy if str(r.get("x_user_id", "")).strip().isdigit()}

    metrics_window = None
    previous_report = data["previous_selection_report"].get("report")
    if previous_report:
        metrics_window = {
            "start_utc": previous_report.get("window_start_utc"),
            "end_exclusive_utc": previous_report.get("window_end_utc"),
        }
    if workbook_info["exists"]:
        sample_complete = bool(
            workbook_validation["valid"]
            and workbook_validation["report"].get("probability_sample_complete")
        )
    else:
        sample_complete = bool(sample) and all(
            (r.get("manual_verdict") or "").strip()
            in {"account_confirms", "ens_only", "conflict", "unverifiable"}
            for r in sample
        )

    blockers = []
    if workbook_info["exists"] and not workbook_validation["valid"]:
        blockers.append("authoritative_v2_review_workbook_missing_or_validation_failed")
    elif not workbook_info["exists"] and not allow_legacy:
        blockers.append("authoritative_v2_review_workbook_missing")
    if len(frame) != 231:
        blockers.append("candidate_frame_missing_or_not_231_rows")
    if len(sample) != 60:
        blockers.append("frozen_probability_sample_missing_or_not_60_rows")
    if not sample_complete:
        blockers.append("frozen_probability_sample_not_fully_adjudicated_weighted_population_estimate_unavailable")
    if not evidence_complete_confirms:
        blockers.append("no_individually_account_confirmed_candidate_with_complete_evidence_fields")
    if not fixed_metrics:
        blockers.append("no_fixed_window_timeline_metrics_for_stable_x_user_ids")
    elif not (eligible_confirm_ids & fixed_metric_ids):
        blockers.append("no_fixed_window_metrics_join_to_an_individually_confirmed_nonseed_candidate")
    if not packet or len(packet) != len(sample):
        blockers.append("manual_review_packet_missing_or_not_aligned_to_frozen_sample")

    return {
        "audit_type": "offline_followup_shortlist_input_availability",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_requests_made": 0,
        "collection_authorized": False,
        "shortlist_generated": False,
        "artifact_root": str(artifact_root),
        "authoritative_workbook_validation": workbook_validation,
        "fixed_research_window_utc": metrics_window,
        "inputs": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in data.items()},
        "counts": {
            "candidate_frame_rows": len(frame),
            "candidate_verdict_counts": dict(verdict_counts),
            "frozen_sample_rows": len(sample),
            "frozen_sample_verdict_counts": dict(sample_verdict_counts),
            "frozen_sample_complete": sample_complete,
            "manual_packet_rows": len(packet),
            "confirmed_seed_rows": len(seed),
            "confirmed_seed_unique_numeric_x_ids": len(stable_numeric_seed_ids),
            "individually_account_confirmed_candidates": len(account_confirms),
            "evidence_complete_individually_confirmed_candidates": len(evidence_complete_confirms),
            "fixed_window_metric_rows": len(fixed_metrics),
            "fixed_window_metrics_required_schema_present": set((data["fixed_window_timeline_metrics"].get("fields") or [])) >= {"address", "x_user_id", "window_start_utc", "window_end_utc", "authored_posts_in_window", "unique_confirmed_interaction_neighbors_in_window", "active_months_2026", "chain_events_2026"},
            "confirmed_nonseed_ids_with_fixed_window_metrics": len(fixed_window_join_ids),
            "confirmed_nonseed_ids_with_only_provisional_lower_bound_metrics": len(provisional_only_join_ids),
            "provisional_candidate_lower_bound_rows": len(lower_bound),
            "provisional_lower_bound_crosswalk_status_counts": dict(lower_bound_status_counts),
            "provisional_lower_bound_coverage_claim_counts": dict(lower_bound_complete_claim_counts),
            "provisional_lower_bound_ids_overlap_with_seed": len(lower_bound_ids & stable_numeric_seed_ids),
            "legacy_fx_pilot_rows": len(legacy),
            "legacy_fx_pilot_rows_with_stable_numeric_x_id": len(legacy_stable_ids),
            "legacy_fx_pilot_has_required_fixed_window_metric_schema": set((data["legacy_fx_pilot_metrics_13"].get("fields") or [])) >= {"address", "x_user_id", "window_start_utc", "window_end_utc", "authored_posts_in_window", "unique_confirmed_interaction_neighbors_in_window", "active_months_2026", "chain_events_2026"},
            "previous_shortlist_rows": len(shortlist),
        },
        "decision": "do_not_generate_or_expand_shortlist",
        "blockers": blockers,
        "interpretation": [
            "Profile string matches and ENS-side records remain candidates until manual account-side evidence is recorded; they are not promoted by this audit.",
            "Provisional 50-row metrics are explicitly candidate_unconfirmed and observed lower bounds; even endpoint cursor exhaustion is not a history-completeness claim. They cannot supply shortlist metrics.",
            "The 13-row Fx pilot is a legacy handle-based pilot without the required stable-ID, frozen-window join and cannot substitute for fixed-window metrics.",
            "An empty prior shortlist is a correct eligibility result, not evidence that all candidates are false links.",
            "Historical event-time as-of validity is a separate unresolved requirement and is not established by this shortlist-input audit.",
        ],
        "next_required_inputs": [
            "Complete all 60 frozen probability-sample verdicts with reviewer, review timestamp, account-side evidence URL or capture ID, quoted evidence, evidence-seen timestamp, and conflict notes.",
            "Produce and hash-join the weighted 231-frame review summary only after the frozen 60 are fully adjudicated.",
            "For any individually confirmed non-seed X ID, supply observed authored-post and confirmed-neighbor metrics in the exact frozen UTC window, with page/cursor/error and coverage semantics.",
            "Keep event-level historical ENS resolver/name/address evidence and canonical event ordering as a separate gate before making as-of claims.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    c = report["counts"]
    lines = [
        "# ENS–X 后续名单输入可用性审计",
        "",
        f"生成时间（UTC）：`{report['generated_at_utc']}`",
        "",
        "## 结论",
        "",
        "**当前不生成后续名单，也不触发采集。** 此报告是离线输入审计，不是映射升级、采集授权或历史 as-of 验证。",
        "",
        f"- 候选框：{c['candidate_frame_rows']} 行；verdict：`{json.dumps(c['candidate_verdict_counts'], ensure_ascii=False)}`。",
        f"- 冻结概率样本：{c['frozen_sample_rows']} 行；已完成：`{c['frozen_sample_complete']}`；verdict：`{json.dumps(c['frozen_sample_verdict_counts'], ensure_ascii=False)}`。",
        f"- 账号侧明确确认：{c['individually_account_confirmed_candidates']}；证据字段齐全：{c['evidence_complete_individually_confirmed_candidates']}。",
        f"- 固定窗口时间线指标：{c['fixed_window_metric_rows']} 行；必需 schema 完整：`{c['fixed_window_metrics_required_schema_present']}`；确认非种子 ID 与固定窗口指标连接：{c['confirmed_nonseed_ids_with_fixed_window_metrics']}。",
        f"- 仅有 provisional 指标、无固定窗口指标的确认候选：{c['confirmed_nonseed_ids_with_only_provisional_lower_bound_metrics']}；旧 shortlist：{c['previous_shortlist_rows']} 行。",
        f"- 种子：{c['confirmed_seed_rows']} 行、{c['confirmed_seed_unique_numeric_x_ids']} 个唯一数字 X ID。",
        f"- 50 行 provisional lower-bound 指标：{c['provisional_candidate_lower_bound_rows']} 行；状态：`{json.dumps(c['provisional_lower_bound_crosswalk_status_counts'], ensure_ascii=False)}`；完整覆盖声明：`{json.dumps(c['provisional_lower_bound_coverage_claim_counts'], ensure_ascii=False)}`。",
        f"- FxEmbed 旧试点：{c['legacy_fx_pilot_rows']} 行；含稳定数字 X ID 的行：{c['legacy_fx_pilot_rows_with_stable_numeric_x_id']}；具备固定窗口所需 schema：`{c['legacy_fx_pilot_has_required_fixed_window_metric_schema']}`。",
        "",
        "## 阻塞项",
        "",
    ]
    lines.extend(f"- `{x}`" for x in report["blockers"])
    lines += ["", "## 解释边界", ""]
    lines.extend(f"- {x}" for x in report["interpretation"])
    lines += ["", "## 下一步所需输入", ""]
    lines.extend(f"{i}. {x}" for i, x in enumerate(report["next_required_inputs"], 1))
    lines += ["", "## 输入文件 SHA-256", ""]
    for key, item in report["inputs"].items():
        if item.get("exists"):
            lines.append(f"- `{key}`: `{item['sha256']}` ({item.get('row_count', 'report')}) — `{item['path']}`")
        else:
            lines.append(f"- `{key}`: **缺失** — `{item['path']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_inputs(args.artifact_root.resolve())
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(args.out_json), "markdown": str(args.out_md), "blockers": report["blockers"], "shortlist_generated": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
