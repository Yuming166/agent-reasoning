import importlib.util
import unittest
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/select_ens_x_followup_batch.py"
spec = importlib.util.spec_from_file_location("followup", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

START = "2026-01-01T00:00:00Z"
END = "2026-09-01T00:00:00Z"
SUMMARY = {
    "review_complete": True, "review_rows": 60,
    "frozen_manifest_sha256_verified": True, "validation_errors": [],
    "population_estimates": {
        "population_N": 231,
        "categories": {v: {"estimated_population_rate": 0.25}
                       for v in ("account_confirms", "ens_only", "conflict", "unverifiable")},
    },
}


def review(i, verdict="account_confirms"):
    return {
        "address": "0x" + f"{i:040x}", "x_user_id": str(1000+i),
        "manual_verdict": verdict, "reviewer": "reviewer-a",
        "reviewed_at_utc": "2026-09-25T10:00:00Z",
        "evidence_seen_at_utc": "2026-09-25T09:00:00Z",
        "x_profile_evidence_url": f"https://x.com/i/user/{1000+i}",
        "evidence_quote_or_capture_id": "capture:sha256=abc",
        "evidence_verified_x_user_id": str(1000+i),
        "review_notes": "explicit account-side address statement",
        "review_stratum": "random|2025|wallet|1_50",
    }


def metric(i, posts, neighbors, start=START, end=END):
    return {
        "address": "0x" + f"{i:040x}", "x_user_id": str(1000+i),
        "window_start_utc": start, "window_end_utc": end,
        "authored_posts_in_window": str(posts),
        "unique_confirmed_interaction_neighbors_in_window": str(neighbors),
        "active_months_2026": "4", "chain_events_2026": "20",
    }


class FollowupSelectionTests(unittest.TestCase):
    def test_only_confirmed_with_complete_evidence_are_ranked(self):
        reviews = [review(1), review(2, "pending")]
        metrics = [metric(1, 10, 2), metric(2, 100, 10)]
        rows, summary = mod.build_shortlist(reviews, metrics, SUMMARY, set(), START, END, 10)
        self.assertEqual([r["x_user_id"] for r in rows], ["1001"])
        self.assertEqual(summary["excluded_review_rows"]["pending_or_nonconfirming"], 1)
        self.assertEqual(rows[0]["collection_authorized"], "false")

    def test_individual_confirmation_can_rank_before_probability_sample_is_complete(self):
        rows, summary = mod.build_shortlist(
            [review(1)], [metric(1, 1, 1)],
            {"review_complete": False, "review_rows": 60, "frozen_manifest_sha256_verified": False, "population_estimates": None},
            set(), START, END, 5,
        )
        self.assertEqual([row["x_user_id"] for row in rows], ["1001"])
        self.assertFalse(summary["probability_sample_complete"])
        self.assertFalse(summary["population_estimate_available"])
        self.assertEqual(summary["population_estimate_status"],
                         "unavailable_until_frozen_probability_sample_is_fully_adjudicated")
        self.assertEqual(rows[0]["collection_authorized"], "false")

    def test_weighted_estimate_is_not_required_for_individual_ranking(self):
        rows, summary = mod.build_shortlist(
            [review(1)], [metric(1, 1, 1)],
            {"review_complete": True, "review_rows": 60, "frozen_manifest_sha256_verified": True, "validation_errors": []}, set(), START, END, 5,
        )
        self.assertEqual(len(rows), 1)
        self.assertFalse(summary["population_estimate_available"])

    def test_population_estimate_flag_requires_verified_60_row_frame_and_valid_categories(self):
        malformed = dict(SUMMARY)
        malformed["review_rows"] = 59
        _, summary = mod.build_shortlist([review(1)], [metric(1, 1, 1)], malformed,
                                         set(), START, END, 5)
        self.assertFalse(summary["probability_sample_complete"])
        self.assertFalse(summary["population_estimate_available"])

        malformed = dict(SUMMARY)
        malformed["frozen_manifest_sha256_verified"] = False
        _, summary = mod.build_shortlist([review(1)], [metric(1, 1, 1)], malformed,
                                         set(), START, END, 5)
        self.assertFalse(summary["population_estimate_available"])

        malformed = dict(SUMMARY)
        malformed["population_estimates"] = {"population_N": 231}
        _, summary = mod.build_shortlist([review(1)], [metric(1, 1, 1)], malformed,
                                         set(), START, END, 5)
        self.assertFalse(summary["population_estimate_available"])

    def test_metrics_must_match_fixed_window(self):
        with self.assertRaisesRegex(ValueError, "different window"):
            mod.build_shortlist([review(1)], [metric(1, 1, 1, end="2026-08-01T00:00:00Z")], SUMMARY, set(), START, END, 5)

    def test_timestamp_without_timezone_rejected_for_confirmation(self):
        row = review(1); row["reviewed_at_utc"] = "2026-09-25T10:00:00"
        rows, summary = mod.build_shortlist([row], [metric(1, 1, 1)], SUMMARY, set(), START, END, 5)
        self.assertEqual(rows, [])
        self.assertEqual(summary["excluded_review_rows"]["incomplete_evidence"], 1)

    def test_current_v2_workbook_schema_is_accepted_and_sampling_stratum_is_preserved(self):
        row = review(1)
        row["sampling_stratum"] = row.pop("review_stratum")
        rows, _ = mod.build_shortlist([row], [metric(1, 1, 1)], SUMMARY, set(), START, END, 5)
        self.assertEqual(rows[0]["review_stratum"], "random|2025|wallet|1_50")

    def test_confirm_requires_manually_verified_x_id_to_match_frozen_id(self):
        row = review(1)
        row["evidence_verified_x_user_id"] = "999999"
        rows, summary = mod.build_shortlist([row], [metric(1, 1, 1)], SUMMARY, set(), START, END, 5)
        self.assertEqual(rows, [])
        self.assertEqual(summary["excluded_review_rows"]["evidence_x_user_id_mismatch"], 1)

    def test_missing_manual_x_id_verification_column_fails_closed(self):
        row = review(1)
        del row["evidence_verified_x_user_id"]
        with self.assertRaisesRegex(ValueError, "missing columns"):
            mod.build_shortlist([row], [metric(1, 1, 1)], SUMMARY, set(), START, END, 5)

    def test_validation_report_must_attest_exact_current_231_row_workbook(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.csv"
            path.write_text("one,two\n1,2\n", encoding="utf-8")
            report = {
                "mode": "offline_full_frame_review_workbook_validation_v1",
                "row_count": 231,
                "validation_errors": [],
                "workbook_manifest_sha256": "a" * 64,
                "workbook_sha256": mod.sha256(path),
            }
            mod.verify_workbook_validation(report, path)
            report["workbook_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "does not match"):
                mod.verify_workbook_validation(report, path)

    def test_validation_report_with_errors_or_wrong_frame_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.csv"
            path.write_text("one\n1\n", encoding="utf-8")
            base = {
                "mode": "offline_full_frame_review_workbook_validation_v1",
                "row_count": 231,
                "validation_errors": [],
                "workbook_manifest_sha256": "a" * 64,
                "workbook_sha256": mod.sha256(path),
            }
            for patch in ({"validation_errors": ["tampered"]}, {"row_count": 230}):
                with self.subTest(patch=patch), self.assertRaises(ValueError):
                    mod.verify_workbook_validation({**base, **patch}, path)

    def test_seed_ids_and_duplicate_x_ids_do_not_add_duplicate_authors(self):
        reviews = [review(1), review(2)]
        reviews[1]["x_user_id"] = reviews[0]["x_user_id"]
        metrics = [metric(1, 10, 2), metric(2, 99, 9)]
        rows, _ = mod.build_shortlist(reviews, metrics, SUMMARY, {"1001"}, START, END, 5)
        self.assertEqual(rows, [])

    def test_duplicate_x_id_uses_measured_wallet_not_lifetime_event_proxy(self):
        first, second = review(1), review(2)
        second["x_user_id"] = first["x_user_id"]
        second["evidence_verified_x_user_id"] = first["x_user_id"]
        first["events_2026"] = "999999"  # would win the old pre-metric dedupe
        second["events_2026"] = "1"
        second_metric = metric(2, 10, 3)
        second_metric["x_user_id"] = first["x_user_id"]
        rows, summary = mod.build_shortlist(
            [first, second], [second_metric], SUMMARY, set(), START, END, 5
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], second["address"])
        self.assertEqual(summary["eligible_unique_new_x_ids"], 1)
        self.assertEqual(summary["missing_metrics_for_confirmed_pairs"], 0)

    def test_duplicate_x_id_with_conflicting_timeline_metrics_fails_closed(self):
        first, second = review(1), review(2)
        second["x_user_id"] = first["x_user_id"]
        second["evidence_verified_x_user_id"] = first["x_user_id"]
        first_metric = metric(1, 10, 3)
        second_metric = metric(2, 11, 3)
        second_metric["x_user_id"] = first["x_user_id"]
        with self.assertRaisesRegex(ValueError, "conflicting fixed-window X metrics"):
            mod.build_shortlist(
                [first, second], [first_metric, second_metric],
                SUMMARY, set(), START, END, 5,
            )

    def test_empty_text_and_no_confirmed_neighbors_not_selected(self):
        rows, _ = mod.build_shortlist([review(1)], [metric(1, 0, 0)], SUMMARY, set(), START, END, 5)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
