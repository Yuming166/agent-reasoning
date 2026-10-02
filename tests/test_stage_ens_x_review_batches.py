import unittest

from scripts.stage_ens_x_review_batches import REVIEW_FIELDS, validate_and_split


class StageReviewBatchesTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{
            "review_token": f"t{i}", "review_sequence": str(i), "address": f"0x{i:040x}",
            "x_user_id": str(1000+i), "handle_at_profile_audit": f"u{i}",
            "x_profile_url": f"https://x.com/i/user/{1000+i}", "manual_verdict": "pending",
            "x_profile_evidence_url": "", "evidence_quote_or_capture_id": "",
            "evidence_verified_x_user_id": "", "evidence_seen_at_utc": "",
            "reviewer": "", "reviewed_at_utc": "", "review_notes": "",
        } for i in range(1, 172)]
        self.tasking = [{"review_token": f"t{i}", "priority_rank": str(i),
                         "tasking_tier": "A_candidate_frame_interaction_bridge_review" if i <= 6 else
                         "B_text_coverage_review_no_observed_candidate_frame_edge"}
                        for i in range(1, 13)]

    def test_partition_is_12_plus_159_and_keeps_random_sequence(self):
        first, remaining, tiers = validate_and_split(self.rows, self.tasking)
        self.assertEqual(len(first), 12)
        self.assertEqual(len(remaining), 159)
        self.assertEqual([int(r["review_sequence"]) for r in first], list(range(1, 13)))
        self.assertEqual([int(r["review_sequence"]) for r in remaining], list(range(13, 172)))
        self.assertEqual(tiers, {
            "A_candidate_frame_interaction_bridge_review": 6,
            "B_text_coverage_review_no_observed_candidate_frame_edge": 6,
        })
        self.assertEqual(list(first[0]), REVIEW_FIELDS)

    def test_rejects_bad_tier_counts(self):
        bad = [dict(r) for r in self.tasking]
        bad[0]["tasking_tier"] = bad[6]["tasking_tier"]
        with self.assertRaises(ValueError):
            validate_and_split(self.rows, bad)

    def test_rejects_identity_or_sequence_corruption(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["review_sequence"] = "2"
        with self.assertRaises(ValueError):
            validate_and_split(rows, self.tasking)

    def test_rejects_pending_verdict_change(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["manual_verdict"] = "account_confirms"
        with self.assertRaises(ValueError):
            validate_and_split(rows, self.tasking)


if __name__ == "__main__":
    unittest.main()
