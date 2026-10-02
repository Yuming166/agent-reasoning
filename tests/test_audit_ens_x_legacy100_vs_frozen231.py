import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_ens_x_legacy100_vs_frozen231 import build_report, raw_inventory

PROJECT = Path(__file__).resolve().parents[1]


class LegacyVsFrozenAuditTests(unittest.TestCase):
    def test_current_frames_remain_separate_and_unadjudicated(self):
        report = build_report(PROJECT)
        self.assertTrue(report["all_checks_pass"], report["checks"])
        self.assertEqual(100, report["legacy_100"]["rows"])
        self.assertEqual(96, report["legacy_100"]["unique_address_handle_pairs"])
        self.assertEqual(4, report["legacy_100"]["duplicate_pair_excess_rows"])
        self.assertEqual(231, report["frozen_231"]["rows"])
        self.assertEqual({"pending": 231}, report["frozen_231"]["manual_verdict_counts"])
        comparison = report["cross_frame_comparison"]
        self.assertEqual(0, comparison["exact_address_x_user_id_links_shared"])
        self.assertEqual(0, comparison["legacy_addresses_shared"])
        self.assertTrue(comparison["no_transfer_or_extrapolation_performed"])

    def test_shared_id_and_handle_are_reported_as_mismatches_not_links(self):
        report = build_report(PROJECT)
        comparison = report["cross_frame_comparison"]
        self.assertEqual(2, comparison["stable_x_user_ids_shared"])
        self.assertEqual(2, comparison["handles_shared_casefolded"])
        self.assertEqual(2, len(comparison["shared_stable_ids_with_different_address_combinations"]))
        self.assertEqual(2, len(comparison["shared_handles_with_different_link_combinations"]))

    def test_raw_inventory_detects_missing_and_bad_capture(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "alpha.json").write_text(json.dumps({"handle": "alpha", "http_status": 200}))
            (directory / "broken.json").write_text("not-json")
            report = raw_inventory(directory, {"alpha", "beta"})
        self.assertEqual(["beta"], report["filename_handle_missing"])
        self.assertEqual(["beta"], report["payload_handle_missing"])
        self.assertEqual(1, len(report["payload_errors"]))


if __name__ == "__main__":
    unittest.main()
