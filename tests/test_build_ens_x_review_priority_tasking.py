import unittest

from scripts.build_ens_x_review_priority_tasking import build_tasking


class ReviewPriorityTaskingTests(unittest.TestCase):
    def setUp(self):
        self.key = [
            {"review_token": "tok-a", "address": "0xAa", "x_user_id": "101",
             "review_arm": "targeted_nonprobability_complement_171"},
            {"review_token": "tok-b", "address": "0xBb", "x_user_id": "102",
             "review_arm": "targeted_nonprobability_complement_171"},
            {"review_token": "tok-p", "address": "0xCc", "x_user_id": "103",
             "review_arm": "stratified_probability_sample_60"},
        ]
        self.priority = [
            {"priority_rank": "2", "address": "0xbb", "x_user_id": "102",
             "review_arm": "targeted_nonprobability_complement_171", "manual_verdict": "pending",
             "priority_tier": "B_text", "review_only_not_collection_authorization": "true"},
            {"priority_rank": "1", "address": "0xaa", "x_user_id": "101",
             "review_arm": "targeted_nonprobability_complement_171", "manual_verdict": "pending",
             "priority_tier": "A_bridge", "review_only_not_collection_authorization": "true"},
        ]

    def test_exact_identity_join_and_token_only_output(self):
        rows = build_tasking(self.priority, self.key)
        self.assertEqual(rows, [
            {"review_token": "tok-a", "priority_rank": "1", "tasking_tier": "A_bridge"},
            {"review_token": "tok-b", "priority_rank": "2", "tasking_tier": "B_text"},
        ])
        self.assertNotIn("address", rows[0])
        self.assertNotIn("x_user_id", rows[0])

    def test_rejects_probability_row(self):
        bad = [dict(self.priority[0], review_arm="stratified_probability_sample_60"), self.priority[1]]
        with self.assertRaises(ValueError):
            build_tasking(bad, self.key)

    def test_rejects_identity_mismatch(self):
        bad = [dict(self.priority[0], x_user_id="999"), self.priority[1]]
        with self.assertRaises(ValueError):
            build_tasking(bad, self.key)

    def test_rejects_nonpending_or_collection_marker(self):
        bad = [dict(self.priority[0], manual_verdict="account_confirms"), self.priority[1]]
        with self.assertRaises(ValueError):
            build_tasking(bad, self.key)


if __name__ == "__main__":
    unittest.main()
