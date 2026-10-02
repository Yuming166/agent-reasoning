#!/usr/bin/env python3
"""Create a hash-bound summary from existing offline ENS-X audit artifacts.

This script performs no network, X/FxEmbed, ENS RPC, or BigQuery requests.
It does not adjudicate mappings or authorize collection; it summarizes only
pinned local audit outputs and retains their claim boundaries.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

try:
    from scripts.audit_ens_x_staged_review_batches import audit as audit_staged_review_batches
except ModuleNotFoundError:  # direct execution from the scripts/ directory
    from audit_ens_x_staged_review_batches import audit as audit_staged_review_batches

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts/ens_x_crosswalk/current_goal_audit/consolidated_goal_state"
INPUTS = {
    "dataset_state_reaudit": "artifacts/ens_x_crosswalk/current_goal_audit/dataset_state_reaudit.json",
    "workbook_revalidation": "artifacts/ens_x_crosswalk/current_goal_audit/manual_review_validation_refresh_task_20260926.json",
    "seed_scope_recheck": "artifacts/ens_x_crosswalk/current_goal_audit/ens_seed_asof_scope_recheck_20260925.json",
    "local_asof_sources_reaudit": "artifacts/ens_x_crosswalk/current_goal_audit/local_asof_sources_reaudit_20260925.json",
    "addrchanged_forward_node_join": "artifacts/ens_x_crosswalk/current_goal_audit/addrchanged_forward_node_join_20260925.json",
    "review_only_scope": "artifacts/ens_x_crosswalk/current_goal_audit/confirmed_seed_asof_query_scope_ensip15_reviewnodes_20260926.json",
    "review_only_diagnostic": "artifacts/ens_x_crosswalk/current_goal_audit/review_only_forward_node_diagnostic_20260926.json",
    "authorized_seed_timeline_audit": "artifacts/ens_x_crosswalk/current_goal_audit/authorized_seed_timeline_20260926/audit_report.json",
    "seed_node_grain_fail_closed": "artifacts/ens_x_crosswalk/current_goal_audit/seed_node_grain_fail_closed_20260926T065022Z/seed_node_grain.json",
    "seed_node_status_correction_supplement": "artifacts/ens_x_crosswalk/current_goal_audit/seed_node_status_correction_supplement_20260926T065037Z/supplement.json",
    "asof_joinability_diagnostic": "artifacts/ens_x_crosswalk/current_goal_audit/asof_joinability_diagnostic_20260926.json",
    "review_priority_tasking_receipt": "artifacts/ens_x_crosswalk/current_goal_audit/review_tasking_priority_20260926/coordinator_only/build_receipt.json",
    "staged_review_batch_audit": "artifacts/ens_x_crosswalk/current_goal_audit/review_tasking_priority_20260926/restricted_batches_20260926/coordinator_only/live_audit_20260926.json",
    "abi_review_scope": "artifacts/ens_x_crosswalk/current_goal_audit/confirmed_seed_asof_scope_abi_review_20260926.json",
    "probability_sample_handoff": "artifacts/ens_x_crosswalk/current_goal_audit/probability_sample_handoff_audit_20260926/audit.json",
    "textchanged_target_scan": "artifacts/ens_x_crosswalk/current_goal_audit/textchanged_target_node_raw_scan_20260926/scan.json",
}
CODE_INPUTS = {
    "expansion_collector": "scripts/collect_ens_x_expansion_pilot.py",
    "expansion_collector_tests": "tests/test_collect_ens_x_expansion_pilot_coverage.py",
    "goal_state_summarizer": "scripts/summarize_ens_x_goal_state.py",
    "goal_state_summarizer_tests": "tests/test_summarize_ens_x_goal_state.py",
    "staged_review_batch_auditor": "scripts/audit_ens_x_staged_review_batches.py",
    "staged_review_batch_auditor_tests": "tests/test_audit_ens_x_staged_review_batches.py",
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))

def read_integer_constants(rel: str, names: set[str]) -> dict[str, int]:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in names:
                value = ast.literal_eval(node.value)
                if not isinstance(value, int):
                    raise ValueError(f"{rel}: {name} is not an integer constant")
                found[name] = value
    if set(found) != names:
        raise ValueError(f"{rel}: missing hard-cap constants {sorted(names - set(found))}")
    return found

def build() -> dict:
    d = {name: read_json(path) for name, path in INPUTS.items()}
    wb, seed, src, state, addr = (d["workbook_revalidation"], d["seed_scope_recheck"],
                                  d["local_asof_sources_reaudit"], d["dataset_state_reaudit"],
                                  d["addrchanged_forward_node_join"])
    review_scope = d["review_only_scope"]
    review_diag = d["review_only_diagnostic"]
    timeline = d["authorized_seed_timeline_audit"]
    seed_grain = d["seed_node_grain_fail_closed"]
    seed_correction = d["seed_node_status_correction_supplement"]
    asof_diag = d["asof_joinability_diagnostic"]
    priority_receipt = d["review_priority_tasking_receipt"]
    staged_review_receipt = d["staged_review_batch_audit"]
    abi_scope = d["abi_review_scope"]
    probability_handoff = d["probability_sample_handoff"]
    textchanged_scan = d["textchanged_target_scan"]
    staged_review_root = ROOT / "artifacts/ens_x_crosswalk/current_goal_audit/review_tasking_priority_20260926/restricted_batches_20260926"
    # Re-run the offline audit so a stale receipt cannot conceal edits to the
    # reviewer handoff after its hash-bound snapshot was produced.
    staged_review_live = audit_staged_review_batches(staged_review_root)
    staged_review = staged_review_live
    manual = state["scopes"]["231_candidate_manual_review"]
    seed_quality = state["scopes"]["seed_crosswalk"]["seed_quality_report"]
    fx = state["scopes"]["explicit_fx_batch"]["continuation_summary"]
    audit_inputs = []
    for name, rel in INPUTS.items():
        path = ROOT / rel
        audit_inputs.append({"name": name, "path": rel, "sha256": sha256(path)})
    code_audits = [
        {"name": name, "path": rel, "sha256": sha256(ROOT / rel)}
        for name, rel in CODE_INPUTS.items()
    ]
    collector_caps = read_integer_constants(
        CODE_INPUTS["expansion_collector"],
        {"HARD_MAX_ACCOUNTS", "HARD_MAX_PAGES_PER_ACCOUNT", "HARD_MAX_HTTP_ATTEMPTS_TOTAL"},
    )
    addr_hashes_by_basename = {Path(path).name: digest for path, digest in addr["input_sha256"].items()}
    source_hashes_by_basename = {Path(item["path"]).name: item["sha256"] for item in src["files"]}
    seed_scope_sha256 = sha256(ROOT / INPUTS["seed_scope_recheck"])
    review_scope_sha256 = sha256(ROOT / INPUTS["review_only_scope"])
    review_nodes = set(review_scope["query_node_sets"]["review_only_forward_nodes_not_eligible_for_mapping"])
    investigation_nodes = set(review_scope["query_node_sets"]["bounded_investigation_query_nodes_union"])
    eligible_nodes = set(review_scope["query_node_sets"]["all_eligible_nodes_union"])
    diagnostic_inputs = review_diag["inputs"]
    candidate_wallets = {wallet for item in review_diag["candidates"] for wallet in item["candidate_wallets"]}
    unresolved_evidence = seed["unresolved_forward_node_evidence"]
    all_unresolved_wallets = {item["address"] for item in unresolved_evidence}
    unresolved_wallets_without_candidate_node = all_unresolved_wallets - candidate_wallets
    no_node_evidence = [
        {"address": address,
         "reverse_name": next(item["reverse_name"] for item in unresolved_evidence if item["address"] == address),
         "reason": sorted({item["reason"] for item in unresolved_evidence if item["address"] == address})}
        for address in sorted(unresolved_wallets_without_candidate_node)
    ]
    checks = {
        "workbook_and_dataset_state_agree_on_231_frame": wb["row_count"] == manual["candidate_frame_rows"] == 231,
        "probability_sample_is_60_and_pending": wb["review_arm_counts"].get("stratified_probability_sample_60") == 60 and not wb["probability_sample_complete"],
        "targeted_complement_is_separate_171": wb["review_arm_counts"].get("targeted_nonprobability_complement_171") == 171 and wb["targeted_complement_weighted_estimate_allowed"] is False,
        "workbook_has_no_validation_errors": not wb["validation_errors"],
        "latest_workbook_revalidation_is_still_all_pending": (
            wb["verdict_counts_by_arm"].get("stratified_probability_sample_60") == {"pending": 60}
            and wb["verdict_counts_by_arm"].get("targeted_nonprobability_complement_171") == {"pending": 171}
            and wb["probability_sample_complete"] is False
            and wb["weighted_estimate_allowed"] is False
        ),
        "confirmed_seed_timeline_keeps_reposts_and_interactions_separate": (
            timeline["network_requests"] == 0
            and timeline["paid_queries_usd"] == 0
            and timeline["candidate_ids_read_or_promoted"] is False
            and timeline["recomputed_timeline"]["deduplicated_verified_in_window_rows"] == 1341
            and timeline["recomputed_timeline"]["authored_posts"] == 267
            and timeline["confirmed_id_interactions_observed"]["edge_events"] == 0
            and timeline["pagination"]["accounts_marked_truncated_or_uncertain"] == 8
        ),
        "seed_node_status_uses_fail_closed_identity_join": (
            seed_grain["seed_counts"]["source_pair_rows_reconciled"] == 9
            and seed_grain["seed_counts"]["source_pair_rows_node_status_unverified"] == 6
            and seed_grain["seed_counts"]["source_pair_node_statuses"] == {"bidirectional_ok": 8, "forward_only": 1}
            and seed_grain["seed_counts"]["seed_summary_mismatches"] == 3
            and seed_correction["authoritative_node_status"] == "unverified_for_all_listed_pair_ids"
            and seed_correction["account_side_boundary"]["account_side_verdicts_changed"] is False
            and seed_correction["mapping_promotions"] == 0
        ),
        "asof_hash_overlap_is_not_misreported_as_event_joinability": (
            asof_diag["network_accessed"] is False
            and asof_diag["paid_query_usd"] == 0
            and "block_number or transaction_index" in " ".join(asof_diag["interpretation"])
        ),
        "review_priority_rows_are_pending_tasking_not_mapping_or_collection_authority": (
            priority_receipt["rows"] == 12
            and priority_receipt["network_requests"] == 0
            and priority_receipt["collection_authorized"] is False
            and priority_receipt["reviewer_distribution_allowed"] is False
        ),
        "staged_targeted_review_handoff_is_integrity_checked_and_pending": (
            staged_review_receipt == staged_review_live
            and
            staged_review.get("schema") == "ens-x-staged-review-batch-audit-v1"
            and staged_review.get("status") == "pass"
            and staged_review.get("reviewer_rows") == {
                "targeted_priority_batch_12.csv": 12,
                "targeted_remaining_batch_159.csv": 159,
            }
            and staged_review.get("unique_tokens") == 171
            and staged_review.get("sequence_coverage") == [1, 171]
            and staged_review.get("verdicts") == {"pending": 171}
            and staged_review.get("probability_packet_included_or_modified") is False
            and staged_review.get("mappings_promoted") == 0
            and staged_review.get("collection_authorized") is False
            and staged_review.get("network_requests") == 0
            and staged_review.get("paid_queries_usd") == 0
        ),
        "seed_scope_is_offline_and_not_queried": seed["network_accessed"] is False and seed["query_performed"] is False,
        "historical_asof_replay_not_ready": src["asof_replay_ready"] is False and src["source_completeness_proven"] is False,
        "latest_abi_scope_is_bounded_and_fail_closed": (
            abi_scope["network_accessed"] is False
            and abi_scope["query_performed"] is False
            and abi_scope["collection_authorized"] is False
            and abi_scope["event_abi_review"]["status"] == "not_frozen"
            and abi_scope["readiness"]["event_time_asof_ready"] is False
            and abi_scope["query_gates"]["bounded_query_ready"] is False
            and abi_scope["inputs"]["seed_crosswalk"]["rows"] == 12
        ),
        "probability_handoff_integrity_does_not_adjudicate": (
            probability_handoff["network_requests"] == 0
            and probability_handoff["paid_queries_usd"] == 0
            and probability_handoff["collection_started"] is False
            and probability_handoff["scope"]["probability_sample_rows"] == 60
            and probability_handoff["scope"]["full_review_frame_rows"] == 231
            and probability_handoff["checks"]["formal_verdicts_assigned"] == 0
            and probability_handoff["checks"]["weighted_estimate_allowed"] is False
        ),
        "textchanged_target_scan_is_hash_bound_observation_only": (
            textchanged_scan["network_requests"] == 0
            and textchanged_scan["paid_queries_usd"] == 0
            and textchanged_scan["matches"]["row_count"] == 67
            and textchanged_scan["source"]["sha256"] == source_hashes_by_basename.get(
                Path(textchanged_scan["source"]["path"]).name
            )
            and textchanged_scan["scope"]["sha256"] == sha256(ROOT / INPUTS["abi_review_scope"])
            and "does not establish log completeness" in textchanged_scan["interpretation"].casefold()
        ),
        "addrchanged_check_is_snapshot_only": "Latest local AddrChanged extraction" in addr["interpretation"] and "does not prove historical validity" in addr["interpretation"],
        "addrchanged_input_hashes_match_audited_sources": (
            addr_hashes_by_basename.get("addrchanged_latest.parquet") == source_hashes_by_basename.get("addrchanged_latest.parquet")
            and addr_hashes_by_basename.get("ens_seed_asof_scope_recheck_20260925.json") == seed_scope_sha256
        ),
        "review_only_nodes_remain_separate_from_eligible_nodes": (
            len(review_nodes) == 3
            and review_nodes.isdisjoint(eligible_nodes)
            and review_nodes.issubset(investigation_nodes)
            and review_scope["readiness"]["event_time_asof_ready"] is False
            and review_scope["collection_authorized"] is False
        ),
        "review_only_diagnostic_is_offline_and_does_not_promote": (
            review_diag["candidate_node_count"] == 3
            and review_diag["scope_candidate_wallets_remain_unresolved"] is True
            and review_diag["mapping_adjudications_changed"] == 0
            and review_diag["network_requests"] == 0
            and review_diag["ens_rpc_requests"] == 0
            and review_diag["bigquery_queries"] == 0
            and review_diag["x_or_fxembed_requests"] == 0
            and candidate_wallets.issubset(all_unresolved_wallets)
            and len(all_unresolved_wallets) == 4
            and len(unresolved_wallets_without_candidate_node) == 1
        ),
        "review_only_scope_hash_matches_diagnostic_input": (
            diagnostic_inputs.get(INPUTS["review_only_scope"], {}).get("sha256") == review_scope_sha256
        ),
        "addrchanged_forward_counts_are_internally_consistent": (
            addr["input_metadata"]["links_with_namehash_validated_forward_nodes"] == 8
            and addr["input_metadata"]["forward_nodes_with_expected_address"] == 8
            and addr["input_metadata"]["link_count"] == 12
            and addr["input_metadata"]["wallet_reverse_nodes_with_any_addrchanged_row"] == 0
        ),
    }
    evidence_times = [x.get("generated_at_utc") or x.get("created_utc") for x in
                      (state, seed, src, review_scope, timeline, asof_diag, seed_correction)
                      if x.get("generated_at_utc") or x.get("created_utc")]
    result = {
        "mode": "hash_bound_offline_goal_state_summary_v2",
        "evidence_snapshot_latest_input_utc": max(evidence_times) if evidence_times else None,
        "network_requests_by_this_script": 0,
        "paid_queries_by_this_script_usd": 0,
        "input_audits": audit_inputs,
        "code_audits": code_audits,
        "checks": checks,
        "all_consistency_checks_pass": all(checks.values()),
        "crosswalk": {
            "account_confirmed_seed_wallet_x_pairs": seed["inputs"]["seed_crosswalk"]["rows"],
            "stable_seed_x_ids": seed_quality["unique_seed_x_user_ids"],
            "candidate_account_confirms_adjudicated_so_far": manual["candidate_frame_verdict_counts"].get("account_confirms", 0),
            "candidate_rows_still_pending": manual["candidate_frame_verdict_counts"].get("pending", 0),
            "candidate_frame_rows": manual["candidate_frame_rows"],
            "probability_sample": manual["frozen_probability_sample_rows"],
            "probability_sample_verdicts": manual["sample_verdict_counts"],
            "probability_sample_complete": manual["sample_complete"],
            "targeted_complement_rows": wb["review_arm_counts"]["targeted_nonprobability_complement_171"],
            "targeted_complement_verdicts": wb["verdict_counts_by_arm"]["targeted_nonprobability_complement_171"],
            "weighted_population_estimate_available": wb["weighted_estimate_allowed"],
            "weighted_estimate_allowed": wb["weighted_estimate_allowed"],
            "current_review_verdicts_by_arm": wb["verdict_counts_by_arm"],
            "priority_targeted_review_rows": priority_receipt["rows"],
            "staged_targeted_review_rows": staged_review.get("unique_tokens"),
            "staged_targeted_review_verdicts": staged_review.get("verdicts"),
            "staged_targeted_review_integrity_status": staged_review.get("status"),
            "staged_review_is_not_collection_authorization": staged_review.get("collection_authorized") is False,
        },
        "seed_dataset": {
            "tweet_records": seed_quality["tweet_records"],
            "authored_posts": seed_quality["authored_posts"],
            "timestamped_social_edges": seed_quality["timestamped_social_edges"],
            "confirmed_seed_to_seed_edges": seed_quality["confirmed_seed_to_seed_edges"],
            "chain_nodes": seed_quality["chain_graph"]["nodes"],
            "chain_event_edges": seed_quality["chain_graph"]["event_edges"],
            "timeline_accounts_with_pagination_to_target_boundary": fx["accounts_with_pagination_to_target_boundary"],
            "timeline_accounts_truncated_or_uncertain": fx["accounts_truncated_or_uncertain"],
            "unique_owner_verified_tweets_in_window": fx["unique_owner_verified_tweets_in_window"],
            "continuation_http_requests": fx["continuation_http_requests"],
            "timeline_rows_verified_in_window": timeline["recomputed_timeline"]["deduplicated_verified_in_window_rows"],
            "original_posts": timeline["recomputed_timeline"]["post_kind_counts"]["original"],
            "replies": timeline["recomputed_timeline"]["post_kind_counts"]["reply"],
            "quotes": timeline["recomputed_timeline"]["post_kind_counts"]["quote"],
            "reposts_reported_separately": timeline["recomputed_timeline"]["post_kind_counts"]["repost"],
            "accounts_with_truncated_or_uncertain_history": timeline["pagination"]["accounts_marked_truncated_or_uncertain"],
            "confirmed_id_interaction_edges_observed": timeline["confirmed_id_interactions_observed"]["edge_events"],
            "timeline_history_completeness_claimed": False,
        },
        "seed_node_grain_reconciliation": {
            "source_pair_rows_reconciled": seed_grain["seed_counts"]["source_pair_rows_reconciled"],
            "source_pair_rows_node_status_unverified": seed_grain["seed_counts"]["source_pair_rows_node_status_unverified"],
            "reconciled_status_counts": seed_grain["seed_counts"]["source_pair_node_statuses"],
            "seed_summary_mismatches": seed_grain["seed_counts"]["seed_summary_mismatches"],
            "unresolved_pair_ids": seed_correction["affected_seed_source_pair_ids"],
            "account_side_verdicts_changed": seed_correction["account_side_boundary"]["account_side_verdicts_changed"],
            "mapping_promotions": seed_correction["mapping_promotions"],
        },
        "collection_budget_and_recovery": {
            "previous_authorized_seed_continuation_http_requests": timeline["reported_collector_summary"]["continuation_http_requests"],
            "previous_request_ledger_rows": timeline["request_ledger_audit"]["ledger_rows"],
            "previous_request_ledger_errors": timeline["request_ledger_audit"]["error_rows"],
            "raw_response_missing_or_unreferenced": timeline["request_ledger_audit"]["raw_body_missing_or_unreferenced_count"],
            "raw_response_hash_mismatches": timeline["request_ledger_audit"]["raw_body_hash_mismatch_count"],
            "cursor_chain_breaks": timeline["request_ledger_audit"]["cursor_chain_break_count"],
            "page_number_gaps": timeline["request_ledger_audit"]["page_number_gap_count"],
            "new_expansion_hard_caps": {
                "max_accounts": collector_caps["HARD_MAX_ACCOUNTS"],
                "max_pages_per_account": collector_caps["HARD_MAX_PAGES_PER_ACCOUNT"],
                "max_http_attempts_total": collector_caps["HARD_MAX_HTTP_ATTEMPTS_TOTAL"],
            },
            "resumable_only_with_frozen_allowlist_window_budget_and_ledger": True,
            "new_requests_by_this_summary": 0,
            "new_paid_queries_usd_by_this_summary": 0,
            "verified_usd_cost_for_prior_bigquery_bytes": False,
        },
        "historical_asof": {
            "ready": src["asof_replay_ready"],
            "missing_canonical_columns": src["union_schema_missing_canonical_columns"],
            "source_completeness_proven": src["source_completeness_proven"],
            "transaction_hash_only_join_is_event_level": False,
            "hash_joinability_pairs_are_potential_fanout_not_matches": True,
            "joinability_diagnostic_files": len(asof_diag["files"]),
            "unresolved_seed_forward_wallets": seed["unresolved_forward_wallet_count"],
            "unresolved_wallets_without_computed_review_node": no_node_evidence,
            "required_event_families": abi_scope["required_event_families"],
            "latest_scope_abi_review": {
                "status": abi_scope["event_abi_review"]["status"],
                "required_chain_order_fields": abi_scope["required_chain_order_fields"],
                "query_gates": abi_scope["query_gates"],
                "bounded_scope_links": abi_scope["inputs"]["seed_crosswalk"]["rows"],
                "validated_forward_nodes": sum(bool(row["forward_ens_nodes_namehash_validated"]) for row in abi_scope["links"]),
                "unresolved_forward_wallets": abi_scope["unresolved_forward_wallet_count"],
                "event_time_asof_ready": abi_scope["readiness"]["event_time_asof_ready"],
            },
            "local_textchanged_observations": {
                "rows": textchanged_scan["matches"]["row_count"],
                "matched_validated_nodes": textchanged_scan["scope"]["matched_node_count"],
                "timestamp_min_utc": textchanged_scan["matches"]["timestamp_min_utc"],
                "timestamp_max_utc": textchanged_scan["matches"]["timestamp_max_utc"],
                "historical_completeness_proven": False,
                "interpretation": textchanged_scan["interpretation"],
            },
            "latest_addrchanged_snapshot_crosscheck": {
                "links_total": addr["input_metadata"]["link_count"],
                "links_with_namehash_validated_forward_nodes": addr["input_metadata"]["links_with_namehash_validated_forward_nodes"],
                "validated_forward_nodes_with_expected_address": addr["input_metadata"]["forward_nodes_with_expected_address"],
                "wallet_reverse_nodes_with_any_addrchanged_row": addr["input_metadata"]["wallet_reverse_nodes_with_any_addrchanged_row"],
                "rows_timestamp_min_utc": addr["input_metadata"]["rows_timestamp_min_utc"],
                "rows_timestamp_max_utc": addr["input_metadata"]["rows_timestamp_max_utc"],
                "historical_asof_evidence": False,
                "interpretation": addr["interpretation"],
            },
            "review_only_forward_node_investigation": {
                "candidate_node_count": review_diag["candidate_node_count"],
                "wallets_remain_unresolved": review_diag["scope_candidate_wallets_remain_unresolved"],
                "mapping_adjudications_changed": review_diag["mapping_adjudications_changed"],
                "query_authorized": review_scope["collection_authorized"],
                "event_time_asof_ready": review_scope["readiness"]["event_time_asof_ready"],
                "candidates": [
                    {
                        "reverse_name": item["reverse_name"],
                        "candidate_wallets": item["candidate_wallets"],
                        "status": item["status"],
                        "latest_addrchanged_address_matches_candidate": (
                            item.get("latest_addrchanged_snapshot", {}).get("address", "").lower()
                            in {address.lower() for address in item["candidate_wallets"]}
                        ),
                        "twitter_text_observation_count": len(item.get("twitter_text_observations", [])),
                    }
                    for item in review_diag["candidates"]
                ],
                "interpretation": review_diag["interpretation"],
            },
        },
        "collection_boundary": {
            "this_script_performs_no_collection": True,
            "this_report_is_not_collection_authorization": True,
            "candidate_timeline_evidence_must_remain_quarantined_until_independent_account_side_review": True,
            "priority_tasking_is_not_mapping_promotion_or_collection_authorization": True,
        },
        "next_evidence_needed": [
            "完成并留存60行分层概率样本的核验；171行定向补充样本单独报告。",
            "仅将3个 namehash 候选节点用于有界调查；先取得完整 ENS 历史并解决节点、正向地址、反向记录与 resolver 状态差异，期间保持对应钱包 unresolved。",
            "在历史 as-of 关联前，取得并验证完整的 ENS resolver、反向记录、地址和文本事件历史，以及规范区块/交易/日志顺序。",
            "任何新增采集或付费查询前，冻结白名单、UTC 时间窗、数据源、页数/请求/成本上限、停止条件和可恢复检查点语义。",
        ],
    }
    return result

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT,
                    help="output path prefix; writes .json and .md (refuses overwrite)")
    args = ap.parse_args()
    report = build()
    out = args.out_prefix
    out.parent.mkdir(parents=True, exist_ok=True)
    jp, mp = out.with_suffix(".json"), out.with_suffix(".md")
    if jp.exists() or mp.exists():
        raise SystemExit(f"refusing to overwrite existing output: {jp} or {mp}")
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# ENS–X 双图目标状态（离线审计汇总）", "",
        f"证据输入中最新审计时间（UTC）：`{report['evidence_snapshot_latest_input_utc']}`", "",
        "> 本汇总只绑定已有本地审计文件的哈希，不产生新映射、不做网络采集，也不是采集授权。候选时间线材料不得据此升级为已确认关联。", "",
        "## 状态", "",
        f"- 确认种子：{report['crosswalk']['account_confirmed_seed_wallet_x_pairs']} 个钱包–稳定 X ID 链接。",
        f"- 231 候选框：60 个概率样本全部待核；171 个定向补充样本全部待核；加权估计可用：{report['crosswalk']['weighted_population_estimate_available']}。",
        f"- 种子双图：{report['seed_dataset']['chain_nodes']} 个链上节点、{report['seed_dataset']['chain_event_edges']} 条链上事件边；{report['seed_dataset']['timestamped_social_edges']} 条带时间社交边；种子内部社交边 {report['seed_dataset']['confirmed_seed_to_seed_edges']} 条。",
        f"- 历史 as-of：未就绪；缺少规范字段：{', '.join(report['historical_asof']['missing_canonical_columns'])}。",
        f"- AddrChanged 最新快照核对：8/8 个已 namehash 校验的前向节点命中预期地址；12 个钱包 reverse 节点均无记录；此项不是历史 as-of 证明。",
        f"- 12 个种子中有 {report['historical_asof']['unresolved_seed_forward_wallets']} 个正向 ENS 钱包仍 unresolved：其中 3 个有 review-only namehash 节点（仅进入有界调查，不是 eligible 节点），另 1 个因本地 namehash 实现无法处理该名称而没有计算候选节点。未改变映射裁决，也未授权查询。",
        f"- 一致性检查全部通过：{report['all_consistency_checks_pass']}。", "",
        "## 输入审计 SHA-256", "",
    ]
    lines += [f"- `{x['path']}` — `{x['sha256']}`" for x in report["input_audits"]]
    lines += ["", "## 种子时间线、节点核对与复核任务", "",
              f"- 确认种子时间线：{report['seed_dataset']['original_posts']} 原创、{report['seed_dataset']['replies']} 回复、{report['seed_dataset']['quotes']} 引用、{report['seed_dataset']['reposts_reported_separately']} 转发（转发单独报告，不作主动互动边）；{report['seed_dataset']['confirmed_id_interaction_edges_observed']} 条确认 ID 诱导子图内部互动边。",
              f"- 12 个已确认种子账号中，{report['seed_dataset']['accounts_with_truncated_or_uncertain_history']} 个时间线覆盖不确定；数据是可见下界，不是完整历史。",
              f"- 节点级 ENS 状态：{report['seed_node_grain_reconciliation']['source_pair_rows_reconciled']} 条来源记录可唯一关联，{report['seed_node_grain_reconciliation']['source_pair_rows_node_status_unverified']} 条仍未核实；{report['seed_node_grain_reconciliation']['seed_summary_mismatches']} 个种子汇总差异保留待解决。",
              f"- 账号侧复核：60 条概率样本与 171 条定向样本目前均待核；171 条定向复核交接包完整性审计 `{report['crosswalk']['staged_targeted_review_integrity_status']}`，未晋升映射、未授权采集。另列 12 条优先工作单，仅用于排队，不用于总体估计。", "",
              f"- 本地 TextChanged 扫描仅观察到 {report['historical_asof']['local_textchanged_observations']['rows']} 条 / {report['historical_asof']['local_textchanged_observations']['matched_validated_nodes']} 个节点的记录；未证明日志完整、部署 ABI 或事件时 resolver 状态。", "",
              "## 采集与恢复边界", "",
              f"- 后续扩展采集器硬上限：{report['collection_budget_and_recovery']['new_expansion_hard_caps']['max_accounts']} 个账号、每账号 {report['collection_budget_and_recovery']['new_expansion_hard_caps']['max_pages_per_account']} 页、总计 {report['collection_budget_and_recovery']['new_expansion_hard_caps']['max_http_attempts_total']} 次 HTTP 尝试。",
              f"- 已有授权种子续采请求 {report['collection_budget_and_recovery']['previous_authorized_seed_continuation_http_requests']} 次；账本 {report['collection_budget_and_recovery']['previous_request_ledger_rows']} 行，错误 {report['collection_budget_and_recovery']['previous_request_ledger_errors']} 行；原始响应缺失/未引用 {report['collection_budget_and_recovery']['raw_response_missing_or_unreferenced']}、哈希不匹配 {report['collection_budget_and_recovery']['raw_response_hash_mismatches']}。",
              "- 续跑必须匹配冻结白名单、UTC 窗口、预算和账本；本次汇总无新请求/付费查询。先前 BigQuery 字节量没有经价格记录核验，故不报告美元成本。", "",
              "## 代码与安全测试 SHA-256", ""]
    lines += [f"- `{x['path']}` — `{x['sha256']}`" for x in report["code_audits"]]
    lines += ["", "## 下一步证据门槛", ""]
    lines += [f"{i}. {x}" for i, x in enumerate(report["next_evidence_needed"], 1)]
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(jp), "markdown": str(mp), "checks_pass": report["all_consistency_checks_pass"]}, ensure_ascii=False))
    if not report["all_consistency_checks_pass"]:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
