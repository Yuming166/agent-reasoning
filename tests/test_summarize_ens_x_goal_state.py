import importlib.util
from unittest.mock import patch
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/summarize_ens_x_goal_state.py"
spec = importlib.util.spec_from_file_location("goal_state_summary", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GoalStateSummaryTests(unittest.TestCase):
    def test_review_only_forward_nodes_are_audited_but_never_promoted(self):
        report = mod.build()
        check = report["checks"]
        self.assertTrue(check["review_only_nodes_remain_separate_from_eligible_nodes"])
        self.assertTrue(check["review_only_diagnostic_is_offline_and_does_not_promote"])
        self.assertTrue(check["review_only_scope_hash_matches_diagnostic_input"])
        investigation = report["historical_asof"]["review_only_forward_node_investigation"]
        self.assertEqual(investigation["candidate_node_count"], 3)
        self.assertEqual(report["historical_asof"]["unresolved_seed_forward_wallets"], 4)
        no_node = report["historical_asof"]["unresolved_wallets_without_computed_review_node"]
        self.assertEqual(len(no_node), 1)
        self.assertEqual(no_node[0]["reason"], ["namehash_input_unsupported_by_local_namehash"])
        self.assertTrue(investigation["wallets_remain_unresolved"])
        self.assertEqual(investigation["mapping_adjudications_changed"], 0)
        self.assertFalse(investigation["query_authorized"])
        self.assertFalse(investigation["event_time_asof_ready"])
        self.assertEqual(
            {row["reverse_name"] for row in investigation["candidates"]},
            {"hoteth.eth", "enschile.eth", "wonjae.eth"},
        )
        self.assertTrue(report["all_consistency_checks_pass"])

    def test_addrchanged_reconciliation_is_bound_but_not_promoted_to_asof(self):
        report = mod.build()
        check = report["checks"]
        self.assertTrue(check["addrchanged_check_is_snapshot_only"])
        self.assertTrue(check["addrchanged_forward_counts_are_internally_consistent"])
        self.assertTrue(check["addrchanged_input_hashes_match_audited_sources"])
        self.assertTrue(report["historical_asof"]["ready"] is False)
        snap = report["historical_asof"]["latest_addrchanged_snapshot_crosscheck"]
        self.assertEqual(snap["links_total"], 12)
        self.assertEqual(snap["links_with_namehash_validated_forward_nodes"], 8)
        self.assertEqual(snap["validated_forward_nodes_with_expected_address"], 8)
        self.assertIs(snap["historical_asof_evidence"], False)
        self.assertTrue(report["all_consistency_checks_pass"])

    def test_latest_seed_review_and_asof_boundaries_are_included(self):
        report = mod.build()
        self.assertTrue(report["checks"]["confirmed_seed_timeline_keeps_reposts_and_interactions_separate"])
        self.assertTrue(report["checks"]["seed_node_status_uses_fail_closed_identity_join"])
        self.assertTrue(report["checks"]["asof_hash_overlap_is_not_misreported_as_event_joinability"])
        self.assertEqual(report["seed_dataset"]["timeline_rows_verified_in_window"], 1341)
        self.assertEqual(report["seed_dataset"]["confirmed_id_interaction_edges_observed"], 0)
        self.assertEqual(report["seed_node_grain_reconciliation"]["source_pair_rows_node_status_unverified"], 6)
        self.assertEqual(report["crosswalk"]["priority_targeted_review_rows"], 12)
        self.assertFalse(report["historical_asof"]["ready"])

    def test_latest_abi_and_textchanged_audits_are_included_without_overclaiming(self):
        report = mod.build()
        checks = report["checks"]
        self.assertTrue(checks["latest_abi_scope_is_bounded_and_fail_closed"])
        self.assertTrue(checks["probability_handoff_integrity_does_not_adjudicate"])
        self.assertTrue(checks["textchanged_target_scan_is_hash_bound_observation_only"])
        asof = report["historical_asof"]
        self.assertEqual(asof["latest_scope_abi_review"]["status"], "not_frozen")
        self.assertFalse(asof["latest_scope_abi_review"]["event_time_asof_ready"])
        self.assertEqual(asof["local_textchanged_observations"]["rows"], 67)
        self.assertFalse(asof["local_textchanged_observations"]["historical_completeness_proven"])
        self.assertTrue(report["all_consistency_checks_pass"])

    def test_collection_caps_and_resume_safety_are_hash_audited(self):
        report = mod.build()
        budget = report["collection_budget_and_recovery"]
        self.assertEqual(budget["new_expansion_hard_caps"], {
            "max_accounts": 10, "max_pages_per_account": 4, "max_http_attempts_total": 50,
        })
        self.assertTrue(budget["resumable_only_with_frozen_allowlist_window_budget_and_ledger"])
        self.assertEqual(budget["raw_response_missing_or_unreferenced"], 0)
        self.assertEqual(budget["raw_response_hash_mismatches"], 0)
        self.assertFalse(budget["verified_usd_cost_for_prior_bigquery_bytes"])
        self.assertEqual(len(report["code_audits"]), 6)

    def test_staged_reviewer_handoff_is_integrity_bound_and_not_authorized(self):
        report = mod.build()
        self.assertTrue(report["checks"]["staged_targeted_review_handoff_is_integrity_checked_and_pending"])
        self.assertEqual(report["crosswalk"]["staged_targeted_review_rows"], 171)
        self.assertEqual(report["crosswalk"]["staged_targeted_review_verdicts"], {"pending": 171})
        self.assertTrue(report["crosswalk"]["staged_review_is_not_collection_authorization"])

    def test_staged_reviewer_handoff_fails_closed_on_promotion_or_authorization(self):
        original = mod.read_json

        def tamper_staged_audit(rel):
            value = original(rel)
            if rel == mod.INPUTS["staged_review_batch_audit"]:
                value["mappings_promoted"] = 1
            return value

        with patch.object(mod, "read_json", side_effect=tamper_staged_audit):
            report = mod.build()
        self.assertFalse(report["checks"]["staged_targeted_review_handoff_is_integrity_checked_and_pending"])
        self.assertFalse(report["all_consistency_checks_pass"])


if __name__ == "__main__":
    unittest.main()
