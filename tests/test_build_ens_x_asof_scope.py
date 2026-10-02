import tempfile
import unittest
from pathlib import Path

from scripts.build_ens_x_asof_scope import build_scope


PROJECT = Path(__file__).resolve().parents[1]


class AsOfScopeBuildTests(unittest.TestCase):
    def test_current_scope_is_confirmed_seed_only_and_fails_closed_on_unresolved_nodes(self):
        report = build_scope(PROJECT)
        self.assertFalse(report["network_accessed"])
        self.assertFalse(report["query_performed"])
        self.assertFalse(report["collection_authorized"])
        self.assertEqual(len(report["links"]), 12)
        self.assertEqual(len(report["query_node_sets"]["wallet_reverse_nodes"]), 12)
        self.assertEqual(len(report["query_node_sets"]["validated_forward_ens_nodes"]), 9)
        self.assertEqual(len(report["unresolved_forward_node_evidence"]), 6)
        self.assertEqual(report["unresolved_forward_wallet_count"], 3)
        review_only = report["review_only_forward_node_candidates"]
        self.assertEqual(len(review_only), 3)
        self.assertTrue(all(x["status"] == "review_only_namehash_candidate_source_node_mismatch" for x in review_only))
        self.assertTrue(all(x["mapping_adjudication_changed"] is False for x in review_only))
        nodes = report["query_node_sets"]
        self.assertTrue(set(nodes["review_only_forward_nodes_not_eligible_for_mapping"]).issubset(
            set(nodes["bounded_investigation_query_nodes_union"])))
        self.assertTrue(set(nodes["review_only_forward_nodes_not_eligible_for_mapping"]).isdisjoint(
            set(nodes["validated_forward_ens_nodes"])))
        self.assertFalse(report["readiness"]["event_time_asof_ready"])
        self.assertFalse(report["query_gates"]["bounded_query_ready"])
        self.assertEqual(report["event_abi_review"]["status"], "not_frozen")
        required = report["required_event_families"]
        self.assertTrue(any("AddressChanged filtered to coinType=60" in x for x in required))
        self.assertTrue(any("TextChanged" in x for x in required))
        self.assertIn("missing TextChanged values", " ".join(report["event_abi_review"]["freeze_requirements"]))


if __name__ == "__main__":
    unittest.main()
