import unittest

from scripts.audit_ens_x_legacy_sample_row_provenance import audit_rows


def row(**kwargs):
    base = {"pair_id": "P1", "status": "bidirectional_ok", "node": "0x01", "address": "0xabc", "handle": "SomeUser", "record_set_at": "2025-01-01T00:00:00Z", "transaction_hash": "0xhash"}
    base.update(kwargs)
    return base


class LegacySampleProvenanceTests(unittest.TestCase):
    def test_exact_alignment_reports_conflict_without_relabeling(self):
        sample = [row()]
        frame = [row()]
        validation = [{"address": "0xabc", "handle": "SomeUser", "status": "forward_only"}]
        filled = [dict(row(), verification_status="account_confirms")]
        result = audit_rows(sample, filled, frame, validation)
        self.assertEqual(1, result["sample_exact_frame_matches"])
        self.assertTrue(result["frame_validation_ordered_address_handle_alignment"])
        self.assertEqual("bidirectional_ok", sample[0]["status"])
        self.assertEqual("forward_only", result["sample_status_conflicts"][0]["validation_status"])
        self.assertFalse(result["filled_account_side_labels_are_human_adjudication"])

    def test_no_conflict_claim_when_order_alignment_fails(self):
        sample = [row()]
        frame = [row()]
        validation = [{"address": "0xother", "handle": "Other", "status": "forward_only"}]
        filled = [dict(row(), verification_status="pending")]
        result = audit_rows(sample, filled, frame, validation)
        self.assertFalse(result["frame_validation_ordered_address_handle_alignment"])
        self.assertEqual([], result["sample_status_conflicts"])

    def test_duplicate_address_handle_is_unresolved_not_positionally_conflicted(self):
        first = row(pair_id="P1", node="node-a", transaction_hash="tx-a", status="bidirectional_ok")
        second = row(pair_id="P2", node="node-b", transaction_hash="tx-b", status="forward_only")
        sample = [first]
        frame = [first, second]
        validation = [
            {"address": "0xabc", "handle": "SomeUser", "status": "forward_only"},
            {"address": "0xabc", "handle": "SomeUser", "status": "bidirectional_ok"},
        ]
        filled = [dict(first, verification_status="pending")]
        result = audit_rows(sample, filled, frame, validation)
        self.assertEqual(0, result["sample_status_conflict_count"])
        self.assertEqual(1, result["sample_validation_linkage_unresolved_count"])
        self.assertFalse(result["sample_validation_links_unambiguous"])
        self.assertEqual("address_handle_not_unique_in_frame_or_validation", result["sample_validation_linkage_unresolved"][0]["reason"])
        self.assertEqual(2, result["sample_validation_linkage_unresolved"][0]["frame_group_size"])
        self.assertNotIn("frame_group_rows_1based", result["sample_validation_linkage_unresolved"][0])



if __name__ == "__main__":
    unittest.main()
