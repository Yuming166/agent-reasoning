import unittest

from scripts.audit_ens_x_seed_node_grain import align_validation_to_frame, build_audit


class SeedNodeGrainAuditTests(unittest.TestCase):
    def test_unique_keys_are_joined_by_identity_not_row_position(self):
        frame = [
            {"address": "0xA", "handle": "alice", "node": "node-a", "transaction_hash": "tx-a"},
            {"address": "0xB", "handle": "bob", "node": "node-b", "transaction_hash": "tx-b"},
        ]
        validation = [
            {"address": "0xB", "handle": "bob", "status": "forward_only"},
            {"address": "0xA", "handle": "alice", "status": "bidirectional_ok"},
        ]
        aligned = align_validation_to_frame(frame, validation)
        self.assertEqual([row["status"] for row in aligned], ["bidirectional_ok", "forward_only"])
        self.assertTrue(all(row["validation_linkage_status"] == "unique_address_handle_match" for row in aligned))

    def test_duplicate_identity_is_unresolved_even_when_projection_matches(self):
        frame = [
            {"address": "0xA", "handle": "alice", "node": "node-a", "transaction_hash": "tx-a"},
            {"address": "0xA", "handle": "alice", "node": "node-b", "transaction_hash": "tx-b"},
        ]
        validation = [
            {"address": "0xA", "handle": "alice", "status": "bidirectional_ok"},
            {"address": "0xA", "handle": "alice", "status": "forward_only"},
        ]
        sample = [
            {"pair_id": "P1", **frame[0], "verification_status": "account_confirms"},
            {"pair_id": "P2", **frame[1], "verification_status": "account_confirms"},
        ]
        seed = [{
            "address": "0xA", "x_user_id": "123", "handle_at_verification": "alice",
            "source_pair_ids": "P1;P2", "ens_evidence_statuses": "bidirectional_ok;forward_only",
        }]
        result = build_audit(frame, validation, sample, seed)
        link = result["seed_links"][0]
        self.assertEqual(result["seed_counts"]["source_pair_rows_node_status_unverified"], 2)
        self.assertEqual(link["exact_source_node_ens_statuses"], [])
        self.assertFalse(link["seed_summary_matches_exact_source_nodes"])
        self.assertEqual(link["account_side_source_verdicts"], ["account_confirms"])
        for pair in link["source_pairs"]:
            self.assertEqual(pair["node_level_ens_status"], "unverified")
            self.assertEqual(pair["resolution"], "paired_row_position_unverified")

    def test_duplicate_identity_projection_mismatch_uses_ambiguous_class(self):
        frame = [
            {"address": "0xA", "handle": "alice", "node": "node-a", "transaction_hash": "tx-a"},
            {"address": "0xA", "handle": "alice", "node": "node-b", "transaction_hash": "tx-b"},
            {"address": "0xB", "handle": "bob", "node": "node-c", "transaction_hash": "tx-c"},
        ]
        validation = [
            {"address": "0xA", "handle": "alice", "status": "bidirectional_ok"},
            {"address": "0xB", "handle": "bob", "status": "forward_only"},
            {"address": "0xA", "handle": "alice", "status": "forward_only"},
        ]
        sample = [{"pair_id": "P1", **frame[0], "verification_status": "account_confirms"}]
        seed = [{"address": "0xA", "x_user_id": "123", "handle_at_verification": "alice", "source_pair_ids": "P1"}]
        result = build_audit(frame, validation, sample, seed)
        pair = result["seed_links"][0]["source_pairs"][0]
        self.assertFalse(result["row_alignment"]["ordered_address_handle_projection_matches"])
        self.assertEqual(pair["resolution"], "unverified_ambiguous_source_rows")
        self.assertEqual(pair["node_level_ens_status"], "unverified")

    def test_unique_candidate_node_status_is_reconciled(self):
        frame = [{
            "address": "0xA", "handle": "alice", "node": "node-a",
            "transaction_hash": "tx-a", "record_set_at": "t1",
        }]
        validation = [{
            "address": "0xA", "handle": "alice", "status": "forward_only",
            "reverse_name": "alice.eth", "reverse_claimed": "False",
            "namehash_matches_node": "False", "addr_record_matches": "True",
        }]
        sample = [{
            "pair_id": "P1", "address": "0xA", "handle": "alice", "node": "node-a",
            "transaction_hash": "tx-a", "verification_status": "account_confirms",
        }]
        seed = [{
            "address": "0xA", "x_user_id": "123", "handle_at_verification": "alice",
            "source_pair_ids": "P1", "ens_evidence_statuses": "bidirectional_ok",
        }]
        result = build_audit(frame, validation, sample, seed)
        link = result["seed_links"][0]
        self.assertEqual(link["exact_source_node_ens_statuses"], ["forward_only"])
        self.assertFalse(link["seed_summary_matches_exact_source_nodes"])
        self.assertFalse(link["all_source_nodes_bidirectional_ok"])


if __name__ == "__main__":
    unittest.main()
