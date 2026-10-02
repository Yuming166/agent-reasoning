import unittest
from datetime import datetime, timedelta, timezone

from scripts.run_temporal_wallet_hypotheses_v2 import (
    apply_edit,
    counterfactual_suite,
    execute,
    metrics,
    normalize,
    verify,
)


class TemporalHypothesisV2Tests(unittest.TestCase):
    def setUp(self):
        self.cut = "2022-08-01T00:00:00+00:00"
        self.events = []
        for i, (days, cp, direction) in enumerate(
            [(1, "A", "outgoing"), (2, "A", "outgoing"), (3, "B", "incoming"), (35, "C", "outgoing"), (36, "C", "incoming")]
        ):
            stamp = (datetime(2022, 8, 1, tzinfo=timezone.utc) - timedelta(days=days)).isoformat()
            self.events.append(
                {
                    "block_timestamp": stamp,
                    "counterparty_address": cp,
                    "direction": direction,
                    "event_family": "external_tx",
                    "target_sequence_index": i,
                    "transaction_hash": f"0x{i}",
                }
            )
        self.case = {
            "case_id": "case",
            "wallet": "wallet",
            "cutoff": self.cut,
            "history_event_count": 5,
            "evidence": [{"evidence_id": "E1"}],
        }

    def test_flat_dsl_is_normalized_without_certificate(self):
        proposal = normalize({"op": "threshold", "metric": "new_rate_30d", "operator": ">=", "threshold": 0.5, "claim_type": "new_exploration", "rule": "ignored natural-language echo"})
        self.assertEqual(proposal["normalization"], "flat_dsl")
        self.assertEqual(proposal["failure_class"], "none")
        self.assertEqual(proposal["rule"]["metric"], "new_rate_30d")
        self.assertNotIn("certificate", proposal)

    def test_natural_language_rule_is_schema_invalid_not_abstention(self):
        proposal = normalize({"claim_type": "repeat_concentration", "prediction": "repeat", "rule": "if top share > .5", "abstain": False})
        self.assertEqual(proposal["failure_class"], "schema_invalid")
        self.assertFalse(proposal["abstain"])

    def test_explicit_abstain_is_separate_and_alignment_is_na(self):
        proposal = normalize({"abstain": True, "prediction": "abstain", "reason": "insufficient evidence"})
        result = verify(proposal, self.case, self.events, self.cut)
        self.assertEqual(result["verification_status"], "explicit_abstain")
        self.assertIsNone(result["semantic_alignment"])

    def test_flat_dsl_executor_recomputes_certificate(self):
        proposal = normalize({"op": "threshold", "metric": "top_cp_share_30d", "operator": ">=", "threshold": 0.5, "claim_type": "repeat_concentration"})
        result = verify(proposal, self.case, self.events, self.cut)
        self.assertTrue(result["verified"])
        self.assertEqual(result["certificate"]["value"], 2 / 3)

    def test_edit_families_preserve_asof_history_and_have_multiple_eligibility_paths(self):
        edited, metadata = apply_edit("mask_recent_30d", self.events, self.cut)
        self.assertTrue(metadata["eligible"])
        self.assertEqual(len(edited), 2)
        self.assertTrue(all(e["block_timestamp"] < self.cut for e in [*edited]))
        _, no_recent = apply_edit("delete_latest_recent_30d", self.events[3:], self.cut)
        self.assertFalse(no_recent["eligible"])

    def test_counterfactual_suite_recomputes_same_rule(self):
        proposal = normalize({"op": "threshold", "metric": "top_cp_share_30d", "operator": ">=", "threshold": 0.5, "claim_type": "repeat_concentration", "witness_ids": ["E1"]})
        baseline = verify(proposal, self.case, self.events, self.cut)
        rows = counterfactual_suite(self.case, self.events, proposal, baseline)
        self.assertEqual(len(rows), 5)
        self.assertTrue(any(row["eligible"] for row in rows))
        self.assertTrue(all("revision" in row for row in rows))

    def test_zero_denominator_is_evidence_insufficient(self):
        m, _ = metrics([], self.cut)
        result = execute({"op": "threshold", "metric": "new_rate_30d", "operator": ">=", "threshold": 0.5}, m)
        self.assertEqual(result["status"], "insufficient")


if __name__ == "__main__":
    unittest.main()
