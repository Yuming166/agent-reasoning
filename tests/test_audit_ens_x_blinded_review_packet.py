import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_ens_x_blinded_review_packet import audit_issued_packet
from scripts.build_ens_x_blinded_review_packet import (
    ARMS, COORDINATOR_DIR, REVIEWER_DIR, generate,
)

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "artifacts/ens_x_crosswalk/goal_audit_20260925/manual_review_workbook_231_v2.csv"
LEGACY_PACKET = ROOT / "artifacts/ens_x_crosswalk/goal_audit_20260925/blinded_review_packet_20260925_v3"


class AccountEvidencePacketAuditTests(unittest.TestCase):
    def test_v3_packet_discloses_identity_and_separates_coordinator_key(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "packet"
            manifest = generate(WORKBOOK, out)
            report = audit_issued_packet(out, ROOT)
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(231, report["row_count"])
            self.assertEqual(60, report["arm_counts"]["stratified_probability_sample_60"])
            self.assertEqual(171, report["arm_counts"]["targeted_nonprobability_complement_171"])
            self.assertFalse(report["identity_blinded"])
            self.assertTrue(report["coordinator_key_separated_from_reviewer_handoff"])
            handoff = out / REVIEWER_DIR
            self.assertTrue((handoff / "manifest.json").is_file())
            self.assertFalse((handoff / "coordinator_key.csv").exists())
            self.assertTrue((out / COORDINATOR_DIR / "coordinator_key.csv").is_file())
            self.assertEqual("ens-x-stratified-account-evidence-review-v3", manifest["schema"])

    def test_tampered_reviewer_file_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "packet"
            generate(WORKBOOK, out)
            packet = out / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            packet.write_text(packet.read_text(encoding="utf-8").replace("pending", "ens_only", 1), encoding="utf-8")
            report = audit_issued_packet(out, ROOT)
            self.assertFalse(report["valid"])
            self.assertIn(f"packet_file_hash_mismatch:{REVIEWER_DIR}/{ARMS['stratified_probability_sample_60']}", report["errors"])

    def test_missing_coordinator_separation_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "packet"
            generate(WORKBOOK, out)
            key = out / COORDINATOR_DIR / "coordinator_key.csv"
            key.rename(out / REVIEWER_DIR / "coordinator_key.csv")
            report = audit_issued_packet(out, ROOT)
            self.assertFalse(report["valid"])
            self.assertIn("packet_file_missing:coordinator_only/coordinator_key.csv", report["errors"])

    def test_legacy_v2_packet_is_audited_with_identity_disclosure_warning(self):
        report = audit_issued_packet(LEGACY_PACKET, ROOT)
        self.assertTrue(report["valid"], report["errors"])
        self.assertFalse(report["identity_blinded"])
        self.assertTrue(any("without_explicit_identity_blinding_disclosure" in w for w in report["warnings"]))
        self.assertFalse(report["coordinator_key_separated_from_reviewer_handoff"])

    def test_v3_manifest_cannot_claim_identity_blinding(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "packet"
            generate(WORKBOOK, out)
            mp = out / "manifest.json"
            manifest = json.loads(mp.read_text(encoding="utf-8"))
            manifest["identity_blinded"] = True
            mp.write_text(json.dumps(manifest), encoding="utf-8")
            report = audit_issued_packet(out, ROOT)
            self.assertFalse(report["valid"])
            self.assertIn("identity_blinding_disclosure_missing_or_false", report["errors"])


if __name__ == "__main__":
    unittest.main()
