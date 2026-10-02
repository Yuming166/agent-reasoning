import argparse
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_ens_x_full_frame_review_workbook import evidence_errors, validate

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/ens_x_crosswalk"
CANDIDATE = BASE / "expansion_decision_20260925/candidate_review_full_231.csv"
SAMPLE = BASE / "expansion_decision_20260925/candidate_review_stratified_sample_60.csv"
FROZEN = BASE / "expansion_decision_20260925/candidate_review_stratified_sample_60.frozen_manifest.json"
QUEUE = BASE / "expansion_decision_20260925/targeted_review_queue_20260925/manual_review_queue_171.csv"
QUEUE_REPORT = BASE / "expansion_decision_20260925/targeted_review_queue_20260925/queue_report.json"
WORKBOOK = BASE / "goal_audit_20260925/manual_review_workbook_231_v2.csv"
WORKBOOK_MANIFEST = BASE / "goal_audit_20260925/manual_review_workbook_231_v2_manifest.json"
EXPECTED_MANIFEST_SHA = "439fd267328d0db556cc5f4f7298c46e41be0379f7e6f34e0741609ae07ade39"


def args_for(workbook):
    return argparse.Namespace(
        workbook=workbook, workbook_manifest=WORKBOOK_MANIFEST,
        expected_workbook_manifest_sha256=EXPECTED_MANIFEST_SHA,
        candidate=CANDIDATE, sample=SAMPLE, frozen_manifest=FROZEN,
        queue=QUEUE, queue_report=QUEUE_REPORT,
    )


class FullFrameWorkbookValidationTests(unittest.TestCase):
    def test_current_workbook_is_valid_but_unreviewed(self):
        report, projected = validate(args_for(WORKBOOK))
        self.assertEqual(report["row_count"], 231)
        self.assertFalse(report["validation_errors"])
        self.assertFalse(report["probability_sample_complete"])
        self.assertIsNone(projected)
        self.assertFalse(report["targeted_complement_weighted_estimate_allowed"])
        self.assertEqual(report["review_arm_counts"]["stratified_probability_sample_60"], 60)
        self.assertEqual(report["review_arm_counts"]["targeted_nonprobability_complement_171"], 171)

    def test_immutable_workbook_cell_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            altered = Path(td) / "altered.csv"
            with WORKBOOK.open(encoding="utf-8-sig", newline="") as src:
                reader = csv.DictReader(src)
                rows = list(reader); fields = reader.fieldnames
            rows[0]["candidate_events_2026"] = "999999"
            with altered.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            report, _ = validate(args_for(altered))
            self.assertTrue(any("immutable field candidate_events_2026 changed" in e
                                for e in report["validation_errors"]))

    def test_only_complete_probability_sample_is_projected_for_weighted_summary(self):
        with tempfile.TemporaryDirectory() as td:
            completed = Path(td) / "completed.csv"
            with WORKBOOK.open(encoding="utf-8-sig", newline="") as src:
                reader = csv.DictReader(src)
                rows = list(reader); fields = reader.fieldnames
            for row in rows:
                if row["review_arm"] == "stratified_probability_sample_60":
                    row.update({
                        "manual_verdict": "unverifiable", "reviewer": "test-reviewer",
                        "reviewed_at_utc": "2026-09-25T10:00:00Z",
                        "review_notes": "synthetic test only",
                        "review_state": "completed",
                    })
            with completed.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            report, projection = validate(args_for(completed))
            self.assertFalse(report["validation_errors"])
            self.assertTrue(report["probability_sample_complete"])
            self.assertEqual(60, len(projection))
            self.assertTrue(all(r["manual_verdict"] == "unverifiable" for r in projection))
            self.assertFalse(report["targeted_complement_weighted_estimate_allowed"])

    def test_confirm_requires_account_side_evidence_and_timestamps(self):
        row = {
            "address": "0x" + "1" * 40, "x_user_id": "12345",
            "manual_verdict": "account_confirms", "reviewer": "reviewer",
            "reviewed_at_utc": "2026-09-25T10:00:00Z", "review_notes": "checked",
            "x_profile_evidence_url": "", "evidence_quote_or_capture_id": "",
            "evidence_verified_x_user_id": "",
            "evidence_seen_at_utc": "",
        }
        errors = evidence_errors(row, 2)
        self.assertTrue(any("requires evidence URL or durable capture ID" in e for e in errors))
        self.assertTrue(any("requires evidence_seen_at_utc" in e for e in errors))
        self.assertTrue(any("requires evidence_verified_x_user_id" in e for e in errors))

    def test_confirm_requires_evidence_id_to_match_frozen_stable_id(self):
        row = {
            "address": "0x" + "1" * 40, "x_user_id": "12345",
            "manual_verdict": "account_confirms", "reviewer": "reviewer",
            "reviewed_at_utc": "2026-09-25T10:00:00Z", "review_notes": "checked by stable ID",
            "x_profile_evidence_url": "https://x.com/i/user/12345",
            "evidence_quote_or_capture_id": "Synthetic capture id",
            "evidence_verified_x_user_id": "99999",
            "evidence_seen_at_utc": "2026-09-25T09:00:00Z",
        }
        errors = evidence_errors(row, 2)
        self.assertTrue(any("must equal the frozen target x_user_id" in e for e in errors))
        row["evidence_verified_x_user_id"] = "12345"
        self.assertEqual(evidence_errors(row, 2), [])

    def test_pending_rows_may_not_be_treated_as_decisions(self):
        row = {"address": "0x" + "1" * 40, "x_user_id": "12345", "manual_verdict": "pending"}
        self.assertEqual(evidence_errors(row, 2), [])


if __name__ == "__main__":
    unittest.main()
