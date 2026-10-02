import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_ens_x_followup_inputs import inspect_inputs


class FollowupInputAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "ens_x_crosswalk"
        self.decision = self.root / "expansion_decision_20260925"
        self.state = self.root / "state_audit_20260925"
        self.selection = self.decision / "followup_selection_recheck_20260925"
        self.metrics = self.decision / "followup_selection_20260925"
        for path in (self.decision, self.state, self.selection, self.metrics,
                     self.root / "two_graph_seed_20260925"):
            path.mkdir(parents=True, exist_ok=True)

        self.write_csv(self.decision / "candidate_review_full_231.csv", [
            {"address": f"0x{i:040x}", "x_user_id": str(1000 + i),
             "manual_verdict": "pending", "reviewer": "", "reviewed_at_utc": "",
             "evidence_seen_at_utc": "", "x_profile_evidence_url": "",
             "evidence_quote_or_capture_id": "", "review_notes": ""}
            for i in range(231)
        ])
        self.write_csv(self.decision / "candidate_review_stratified_sample_60.csv", [
            {"address": f"0x{i:040x}", "x_user_id": str(1000 + i), "manual_verdict": "pending"}
            for i in range(60)
        ])
        self.write_csv(self.state / "manual_review_packet_60.csv", [{"x_user_id": str(1000 + i)} for i in range(60)])
        self.write_csv(self.root / "two_graph_seed_20260925" / "crosswalk_confirmed_unique.csv",
                       [{"address": f"0x{i:040x}", "x_user_id": str(500 + i)} for i in range(12)])
        self.write_csv(self.metrics / "timeline_metrics_unavailable.csv", [], ["address", "x_user_id"])
        self.write_csv(self.state / "provisional_50_timeline_lower_bound_metrics_20260925.csv", [
            {"address": "0x" + "a" * 40, "x_user_id": "9999",
             "crosswalk_status": "candidate_unconfirmed_not_eligible_for_shortlist",
             "window_coverage_complete_claim": "no"}
        ])
        self.write_csv(self.root / "fx_pilot_metrics.csv", [{"handle": f"user{i}"} for i in range(13)])
        self.write_csv(self.selection / "shortlist.csv", [], ["address", "x_user_id"])
        (self.selection / "selection_report.json").write_text(json.dumps({
            "window_start_utc": "2026-01-01T00:00:00Z",
            "window_end_utc": "2026-09-24T17:24:10Z",
        }))

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write_csv(path, rows, fields=None):
        if fields is None:
            fields = list(rows[0]) if rows else []
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_pending_candidates_and_unconfirmed_metrics_never_make_shortlist(self):
        report = inspect_inputs(self.root, allow_legacy=True)
        self.assertFalse(report["shortlist_generated"])
        self.assertEqual(231, report["counts"]["candidate_frame_rows"])
        self.assertEqual({"pending": 231}, report["counts"]["candidate_verdict_counts"])
        self.assertEqual(0, report["counts"]["fixed_window_metric_rows"])
        self.assertEqual(1, report["counts"]["provisional_candidate_lower_bound_rows"])
        self.assertEqual(0, report["counts"]["previous_shortlist_rows"])
        self.assertIn("no_individually_account_confirmed_candidate_with_complete_evidence_fields", report["blockers"])

    def test_confirmation_with_only_provisional_metric_does_not_qualify_for_shortlist(self):
        frame_path = self.decision / "candidate_review_full_231.csv"
        with frame_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        rows[0].update({
            "manual_verdict": "account_confirms", "reviewer": "reviewer-1",
            "reviewed_at_utc": "2026-09-25T12:00:00Z", "evidence_seen_at_utc": "2026-09-25T11:59:00Z",
            "x_profile_evidence_url": "https://example.invalid/post/1",
            "evidence_quote_or_capture_id": "synthetic-test-capture",
            "review_notes": "synthetic fixture only",
        })
        self.write_csv(frame_path, rows)
        lower_path = self.state / "provisional_50_timeline_lower_bound_metrics_20260925.csv"
        self.write_csv(lower_path, [{
            "address": rows[0]["address"], "x_user_id": rows[0]["x_user_id"],
            "crosswalk_status": "candidate_unconfirmed_not_eligible_for_shortlist",
            "window_coverage_complete_claim": "no",
        }])
        report = inspect_inputs(self.root, allow_legacy=True)
        self.assertEqual(1, report["counts"]["evidence_complete_individually_confirmed_candidates"])
        self.assertEqual(0, report["counts"]["confirmed_nonseed_ids_with_fixed_window_metrics"])
        self.assertEqual(1, report["counts"]["confirmed_nonseed_ids_with_only_provisional_lower_bound_metrics"])
        self.assertFalse(report["shortlist_generated"])
        self.assertIn("no_fixed_window_timeline_metrics_for_stable_x_user_ids", report["blockers"])
        self.assertEqual(0, report["counts"]["legacy_fx_pilot_rows_with_stable_numeric_x_id"])

    def test_confirmation_without_required_account_side_evidence_is_not_eligible(self):
        with (self.decision / "candidate_review_full_231.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        rows[0]["manual_verdict"] = "account_confirms"
        self.write_csv(self.decision / "candidate_review_full_231.csv", rows)
        report = inspect_inputs(self.root, allow_legacy=True)
        self.assertEqual(1, report["counts"]["individually_account_confirmed_candidates"])
        self.assertEqual(0, report["counts"]["evidence_complete_individually_confirmed_candidates"])
        self.assertFalse(report["shortlist_generated"])
        self.assertIn("no_individually_account_confirmed_candidate_with_complete_evidence_fields", report["blockers"])

    def _write_v2_workbook(self):
        goal = self.root / "goal_audit_20260925"
        goal.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(231):
            rows.append({
                "address": f"0x{i:040x}", "x_user_id": str(9000 + i),
                "review_arm": "stratified_probability_sample_60" if i < 60 else "targeted_nonprobability_complement_171",
                "manual_verdict": "pending", "reviewer": "", "reviewed_at_utc": "",
                "evidence_seen_at_utc": "", "x_profile_evidence_url": "",
                "evidence_quote_or_capture_id": "", "evidence_verified_x_user_id": "",
                "review_notes": "",
            })
        rows[0].update({
            "manual_verdict": "account_confirms", "reviewer": "reviewer-1",
            "reviewed_at_utc": "2026-09-25T12:00:00Z", "evidence_seen_at_utc": "2026-09-25T11:59:00Z",
            "x_profile_evidence_url": "https://example.invalid/post/1",
            "evidence_quote_or_capture_id": "capture-1", "evidence_verified_x_user_id": "9000",
            "review_notes": "synthetic test only",
        })
        path = goal / "manual_review_workbook_231_v2.csv"
        self.write_csv(path, rows)
        (goal / "manual_review_workbook_231_v2_manifest.json").write_text("{}", encoding="utf-8")

    def test_v2_workbook_is_authoritative_and_validation_is_called(self):
        self._write_v2_workbook()
        valid_report = {
            "row_count": 231, "workbook_manifest_sha256": "439fd267328d0db556cc5f4f7298c46e41be0379f7e6f34e0741609ae07ade39",
            "validation_errors": [], "probability_sample_complete": False,
        }
        with patch("scripts.audit_ens_x_followup_inputs.validate_authoritative_workbook", return_value=valid_report) as validate:
            report = inspect_inputs(self.root)
        validate.assert_called_once()
        self.assertEqual(231, report["counts"]["candidate_frame_rows"])
        self.assertEqual(1, report["counts"]["individually_account_confirmed_candidates"])
        self.assertEqual({"pending": 59, "account_confirms": 1}, report["counts"]["frozen_sample_verdict_counts"])
        self.assertTrue(report["authoritative_workbook_validation"]["valid"])

    def test_invalid_v2_workbook_fails_closed_even_if_legacy_frame_has_confirmations(self):
        self._write_v2_workbook()
        invalid_report = {
            "row_count": 231, "workbook_manifest_sha256": "439fd267328d0db556cc5f4f7298c46e41be0379f7e6f34e0741609ae07ade39",
            "validation_errors": ["synthetic mismatch"], "probability_sample_complete": False,
        }
        with patch("scripts.audit_ens_x_followup_inputs.validate_authoritative_workbook", return_value=invalid_report):
            report = inspect_inputs(self.root, allow_legacy=True)
        self.assertEqual(0, report["counts"]["candidate_frame_rows"])
        self.assertEqual(0, report["counts"]["individually_account_confirmed_candidates"])
        self.assertIn("authoritative_v2_review_workbook_missing_or_validation_failed", report["blockers"])


if __name__ == "__main__":
    unittest.main()
