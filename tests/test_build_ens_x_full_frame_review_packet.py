import tempfile
import unittest
from pathlib import Path

from scripts.build_ens_x_full_frame_review_packet import build

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/ens_x_crosswalk/expansion_decision_20260925"


class FullFrameManualReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.candidate = BASE / "candidate_review_full_231.csv"
        self.sample = BASE / "candidate_review_stratified_sample_60.csv"
        self.frozen = BASE / "candidate_review_stratified_sample_60.frozen_manifest.json"
        self.queue = BASE / "targeted_review_queue_20260925/manual_review_queue_171.csv"
        self.queue_report = self.queue.with_name("queue_report.json")

    def test_verified_disjoint_cover_keeps_design_weights_only_on_sample(self):
        rows, meta = build(self.candidate, self.sample, self.frozen, self.queue, self.queue_report)
        self.assertEqual(231, len(rows))
        self.assertEqual(60, sum(r["review_arm"] == "stratified_probability_sample_60" for r in rows))
        self.assertEqual(171, sum(r["review_arm"] == "targeted_nonprobability_complement_171" for r in rows))
        self.assertTrue(meta["sample_complement_disjoint_exact_cover"])
        self.assertTrue(meta["design_weights_only_on_probability_sample"])
        self.assertTrue(meta["all_rows_pending"])
        self.assertEqual(0, meta["verdicts_assigned"])
        self.assertEqual(23, meta["strata_count"])
        self.assertEqual(231, meta["stratum_population_total"])
        self.assertEqual(60, meta["stratum_sample_total"])
        weights = [float(r["design_weight"]) for r in rows if r["design_weight"]]
        self.assertAlmostEqual(231, sum(weights))

    def test_no_automatic_candidate_evidence_is_promoted_or_review_fields_filled(self):
        rows, _ = build(self.candidate, self.sample, self.frozen, self.queue, self.queue_report)
        self.assertTrue(all(r["manual_verdict"] == "pending" for r in rows))
        self.assertTrue(any(r["automatic_evidence_types_not_adjudication"] for r in rows))
        self.assertTrue(all(r["manual_verdict"] == "pending" for r in rows))
        blank_fields = ("x_profile_evidence_url", "evidence_quote_or_capture_id", "evidence_verified_x_user_id", "evidence_seen_at_utc", "reviewer", "reviewed_at_utc", "review_notes")
        self.assertTrue(all(not r[k] for r in rows for k in blank_fields))
        targeted = [r for r in rows if r["review_arm"] == "targeted_nonprobability_complement_171"]
        self.assertTrue(all(not r["design_weight"] and not r["inclusion_probability"] for r in targeted))

    def test_pinned_input_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            altered = Path(td) / "candidate.csv"
            altered.write_bytes(self.candidate.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "candidate SHA-256"):
                build(altered, self.sample, self.frozen, self.queue, self.queue_report)


if __name__ == "__main__":
    unittest.main()
