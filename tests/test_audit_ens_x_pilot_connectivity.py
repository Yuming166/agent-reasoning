import unittest

from scripts.audit_ens_x_pilot_connectivity import analyze


class PilotConnectivityAuditTests(unittest.TestCase):
    def setUp(self):
        self.seeds = [{"x_user_id": "100", "address": "0x1"}, {"x_user_id": "101", "address": "0x2"}]
        self.candidates = [{"x_user_id": "200", "address": "0x3"}, {"x_user_id": "201", "address": "0x4"}]
        self.coverage = [
            {"x_user_id": "200", "stop_reason": "page_ceiling"},
            {"x_user_id": "201", "stop_reason": "cursor_exhausted"},
        ]

    def test_only_timed_authored_posts_and_sample_internal_edges_count(self):
        report = analyze(
            self.seeds,
            [{"x_user_id": "100", "created_at_utc": "2026-01-01T00:00:00Z", "post_kind": "original"}],
            [{"source_x_user_id": "100", "target_x_user_id": "200", "event_type": "mention",
              "created_at_utc": "2026-01-02T00:00:00Z", "source_post_id": "s1"}],
            self.candidates,
            [
                {"x_user_id": "200", "created_at_utc": "2026-01-03T00:00:00Z", "post_kind": "reply"},
                {"x_user_id": "200", "created_at_utc": "2026-01-04T00:00:00Z", "post_kind": "repost"},
                {"x_user_id": "201", "created_at_utc": "2025-12-31T23:59:59Z", "post_kind": "original"},
            ],
            [{"source_x_user_id": "200", "target_x_user_id": "999", "event_type": "mention",
              "created_at_utc": "2026-01-05T00:00:00Z", "source_post_id": "c1"}],
            self.coverage,
        )
        self.assertEqual(report["observed_authored_text"]["provisional_candidate_accounts_only"]["authored_posts_observed"], 1)
        self.assertEqual(report["observed_timestamped_edges"]["sample_induced_edge_count"], 1)
        self.assertEqual(report["observed_timestamped_edges"]["sample_induced_edges_by_relation"],
                         {"candidate_seed_cross_group_provisional_wallet_link": 1})
        self.assertEqual(report["observed_timestamped_edges"]["sample_nodes_with_at_least_one_induced_edge"], 2)
        self.assertEqual(report["scope"]["provisional_wallet_x_links_promoted"], 0)

    def test_untimed_reposts_do_not_create_edges_or_authored_text(self):
        report = analyze(
            self.seeds[:1], [], [], self.candidates[:1],
            [{"x_user_id": "200", "created_at_utc": "2026-02-01T00:00:00Z", "post_kind": "repost"}],
            [{"source_x_user_id": "200", "target_x_user_id": "100", "event_type": "mention",
              "created_at_utc": "", "source_post_id": "rt1"}],
            self.coverage[:1],
        )
        self.assertEqual(report["observed_authored_text"]["provisional_candidate_accounts_only"]["authored_posts_observed"], 0)
        self.assertEqual(report["observed_timestamped_edges"]["all_observed_edge_count"], 0)
        self.assertEqual(report["observed_timestamped_edges"]["sample_induced_edge_count"], 0)

    def test_pair_persistence_requires_repeated_induced_pair_across_months(self):
        seed_edges = [
            {"source_x_user_id": "100", "target_x_user_id": "200", "event_type": "mention",
             "created_at_utc": "2026-01-02T00:00:00Z", "source_post_id": "s1"},
            {"source_x_user_id": "100", "target_x_user_id": "200", "event_type": "mention",
             "created_at_utc": "2026-02-02T00:00:00Z", "source_post_id": "s2"},
        ]
        report = analyze(self.seeds, [], seed_edges, self.candidates, [], [], self.coverage)
        self.assertEqual(report["observed_timestamped_edges"]["induced_directed_pairs_repeated_across_months"], 1)
        self.assertEqual(report["monthly_observations"]["2026-01"]["sample_induced_edges"], 1)

    def test_invalid_duplicate_or_overlapping_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            analyze(self.seeds, [], [], [{"x_user_id": "100"}], [], [], [], [])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            analyze(self.seeds, [], [], [{"x_user_id": "200"}, {"x_user_id": "200"}], [], [], [], [])


if __name__ == "__main__":
    unittest.main()
