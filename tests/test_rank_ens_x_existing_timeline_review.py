import unittest

from scripts.rank_ens_x_existing_timeline_review import analyze


class ExistingTimelineReviewPriorityTests(unittest.TestCase):
    def test_bridge_and_text_review_priority_never_promotes_or_ranks_probability_arm(self):
        workbook = []
        leads = []
        for i in range(231):
            uid = str(10000 + i)
            arm = "stratified_probability_sample_60" if i < 60 else "targeted_nonprobability_complement_171"
            workbook.append({
                "x_user_id": uid, "address": f"0x{i:040x}",
                "handle_at_profile_audit": f"h{i}", "review_arm": arm,
                "manual_verdict": "pending", "candidate_events_2026": str(i),
            })
            leads.append({"x_user_id": uid, "evidence_lead_type": "profile_exact_reverse_ens_name"})
        # Production metrics cover exactly 50 IDs; preserve that input contract
        # while assigning meaningful values to the two synthetic edge sources.
        pilot_ids = [str(10060 + i) for i in range(50)]
        metrics = [{
            "x_user_id": uid,
            "crosswalk_status": "candidate_unconfirmed_not_eligible_for_shortlist",
            "authored_posts_observed_in_window": "0",
            "nonempty_authored_posts_observed_in_window": "0",
            "unique_external_interaction_neighbors_observed": "0",
            "stop_reason": "page_ceiling",
        } for uid in pilot_ids]
        metrics[0].update({
            "authored_posts_observed_in_window": "6",
            "nonempty_authored_posts_observed_in_window": "5",
            "unique_external_interaction_neighbors_observed": "4",
            "stop_reason": "page_ceiling",
        })
        metrics[1].update({
            "authored_posts_observed_in_window": "4",
            "nonempty_authored_posts_observed_in_window": "4",
            "unique_external_interaction_neighbors_observed": "3",
            "stop_reason": "cursor_exhausted",
        })
        edges = [
            {"source_x_user_id": "10060", "target_x_user_id": "10062", "event_type": "mention", "created_at_utc": "2026-03-02T00:00:00Z"},
            {"source_x_user_id": "10060", "target_x_user_id": "seed-x", "event_type": "quote", "created_at_utc": "2026-03-03T00:00:00Z"},
        ]
        pairs, priority, stats = analyze(workbook, leads, metrics, edges, [{"x_user_id": "seed-x"}], 6)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["observed_edge_event_count"], 1)
        self.assertEqual({r["x_user_id"] for r in priority}, {"10060", "10061", "10062"})
        self.assertTrue(all(r["review_arm"] == "targeted_nonprobability_complement_171" for r in priority))
        self.assertTrue(all(r["manual_verdict"] == "pending" for r in priority))
        self.assertEqual(stats["probability_arm_rows_excluded_from_targeted_ranking"], 60)
        self.assertEqual(stats["provisional_candidate_to_confirmed_seed_edge_events"], 1)
        self.assertEqual(stats["mapping_promotions"], 0)
        self.assertFalse(stats["timeline_collection_authorized"])


if __name__ == "__main__":
    unittest.main()
