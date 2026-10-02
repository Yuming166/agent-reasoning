import unittest
from pathlib import Path

from scripts.screen_ens_x_profile_evidence_leads_offline import exact_term, scan

ROOT = Path(__file__).resolve().parents[1]


class ProfileEvidenceLeadScreenTests(unittest.TestCase):
    def test_exact_term_requires_token_boundaries(self):
        self.assertTrue(exact_term("I use 0x" + "a" * 40 + " for ENS", "0x" + "a" * 40))
        self.assertTrue(exact_term("Name: yurin.eth", "yurin.eth"))
        self.assertFalse(exact_term("not-yurin.eth-extra", "yurin.eth"))
        self.assertFalse(exact_term("yurin.ethx", "yurin.eth"))

    def test_frozen_231_screen_is_audit_only_and_preserves_sampling_arms(self):
        rows, report = scan(ROOT)
        self.assertEqual(len(rows), 231)
        self.assertEqual(report["review_arm_counts"], {
            "stratified_probability_sample_60": 60,
            "targeted_nonprobability_complement_171": 171,
        })
        self.assertEqual(report["integrity_and_lead_counts"]["verified_capture_id_and_hash"], 231)
        self.assertEqual(report["manual_verdict_counts"], {"pending": 231})
        self.assertFalse(report["weighted_estimate_allowed"])
        self.assertTrue(all(r["adjudication"] == "not_adjudicated_manual_verdict_unchanged" for r in rows))
        self.assertEqual(sum(r["evidence_lead_type"] in {"profile_exact_full_wallet_address", "profile_exact_wallet_and_ens"} for r in rows), 27)


if __name__ == "__main__":
    unittest.main()
