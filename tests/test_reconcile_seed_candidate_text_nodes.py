import unittest

from scripts.reconcile_seed_candidate_text_nodes import (
    NO_ASOF, classify_reverse_namehash, reconcile_pair_rows,
)


class CandidateNodeReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "pair_id": "P031", "verification_status": "account_confirms",
            "node": "0x" + "a" * 64, "transaction_hash": "0x" + "b" * 64,
            "address": "0x" + "c" * 40, "handle": "hoteths", "x_user_id": "123",
            "reverse_name": "hoteth.eth",
        }
        self.text = [{
            "node": self.evidence["node"], "transaction_hash": self.evidence["transaction_hash"],
            "key": "com.twitter", "value": "hoteths", "block_timestamp": "2025-05-05T15:06:47+00:00",
            "resolver": "0x" + "d" * 40, "event_family": "text_changed_indexed_key",
            "decode_status": "two_strings_key_value_by_family",
        }]
        self.addr = [{"node": self.evidence["node"], "address": self.evidence["address"],
                      "block_timestamp": "2025-05-05T14:16:59+00:00"}]

    def test_unsupported_unicode_name_is_not_claimed_as_hash_mismatch(self):
        def ascii_only(name):
            if not name.isascii():
                raise ValueError("unsupported unicode")
            return "0x" + "e" * 64
        result = classify_reverse_namehash("0x" + "a" * 64, "2⃣2⃣.eth", ascii_only)
        self.assertEqual(result, (None, "unsupported_non_ascii_or_noncanonical"))

    def test_supported_name_must_really_mismatch(self):
        node = "0x" + "a" * 64
        with self.assertRaisesRegex(ValueError, "matches the candidate node"):
            classify_reverse_namehash(node, "known.eth", lambda _: node)
        self.assertEqual(classify_reverse_namehash(node, "known.eth", lambda _: "0x" + "b" * 64)[1],
                         "computed_node_mismatch")

    def test_exact_pair_reconciles_as_observation_only(self):
        result = reconcile_pair_rows(self.evidence, self.text, self.addr)
        self.assertEqual(result["textchanged_match"]["count"], 1)
        self.assertEqual(result["same_node_address_observation"]["row_count"], 1)
        self.assertEqual(result["link_status"], NO_ASOF)
        self.assertNotEqual(result["link_status"], "asof_valid")

    def test_scope_cannot_expand_to_other_pair(self):
        evidence = dict(self.evidence, pair_id="P999")
        with self.assertRaisesRegex(ValueError, "outside frozen candidate-node scope"):
            reconcile_pair_rows(evidence, self.text, self.addr)

    def test_mismatch_does_not_silently_match(self):
        with self.assertRaisesRegex(ValueError, "expected one exact TextChanged row"):
            reconcile_pair_rows(self.evidence, self.text + [dict(self.text[0])], self.addr)

    def test_non_account_confirm_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, "not account_confirms"):
            reconcile_pair_rows(dict(self.evidence, verification_status="ens_only"), self.text, self.addr)

    def test_same_second_is_still_not_canonical_order(self):
        same = [dict(self.addr[0], block_timestamp="2025-05-05T15:06:47+00:00")]
        result = reconcile_pair_rows(self.evidence, self.text, same)
        self.assertEqual(result["same_node_address_observation"]["text_minus_latest_addrchanged_seconds_timestamp_only"], 0)
        self.assertIn("no block/transaction/log ordering", result["same_node_address_observation"]["timestamp_precision_warning"])
        self.assertEqual(result["link_status"], NO_ASOF)


if __name__ == "__main__":
    unittest.main()
