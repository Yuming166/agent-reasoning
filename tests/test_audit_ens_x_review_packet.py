import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_ens_x_review_packet import IMMUTABLE_FIELDS, audit, row_digest


class ReviewPacketAuditTests(unittest.TestCase):
    def setup_fixture(self, root: Path):
        project = root / "project"
        project.mkdir()
        raw = project / "profile.json"
        wrapper = {
            "http_status": 200,
            "data": {"user": {"id": "12345", "screen_name": "review_handle"}},
        }
        raw.write_text(json.dumps(wrapper), encoding="utf-8")
        raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
        sample_row = {
            "address": "0x" + "a" * 40,
            "x_user_id": "12345",
            "sampling_stratum": "s1",
            "stratum_population_N": "2",
            "stratum_sample_n": "1",
            "inclusion_probability": "0.5",
            "design_weight": "2",
            "sampling_seed": "seed1",
            "handle_at_profile_audit": "review_handle",
            "profile_raw_file": "profile.json",
            "profile_raw_sha256": raw_hash,
        }
        sample = root / "sample.csv"
        with sample.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(sample_row))
            w.writeheader(); w.writerow(sample_row)
        second = {**sample_row, "address": "0x" + "b" * 40, "x_user_id": "67890"}
        frame = root / "frame.csv"
        with frame.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(sample_row))
            w.writeheader(); w.writerows([sample_row, second])
        packet_row = {
            "address": sample_row["address"], "x_user_id": "12345",
            "handle_at_profile_audit": "review_handle", "captured_x_user_id": "12345",
            "captured_handle": "review_handle", "raw_profile_relative_path": "profile.json",
            "raw_profile_sha256_verified": raw_hash, "stable_id_match": "true",
            "review_state": "pending_manual_verdict",
        }
        packet = root / "packet.csv"
        with packet.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(packet_row))
            w.writeheader(); w.writerow(packet_row)
        sample_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
        manifest = root / "frozen.json"
        manifest.write_text(json.dumps({
            "immutable_fields": IMMUTABLE_FIELDS,
            "row_count": 1,
            "ordered_row_digests": [row_digest(sample_row)],
            "source_sha256_at_freeze": sample_hash,
        }), encoding="utf-8")
        return sample, manifest, frame, packet, project

    def test_valid_frozen_sample_packet_and_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample, manifest, frame, packet, project = self.setup_fixture(Path(tmp))
            report = audit(sample, manifest, frame, packet, project)
            self.assertEqual(report["sample_rows"], 1)
            self.assertEqual(report["candidate_frame_rows"], 2)
            self.assertTrue(report["frozen_ordered_design_digests_match"])
            self.assertTrue(report["packet_membership_and_order_match"])
            self.assertTrue(report["all_profile_capture_hashes_and_ids_match"])
            self.assertFalse(report["collection_authorized"])

    def test_rejects_packet_pair_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample, manifest, frame, packet, project = self.setup_fixture(Path(tmp))
            with packet.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            rows[0]["x_user_id"] = "99999"
            with packet.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader(); w.writerows(rows)
            with self.assertRaisesRegex(ValueError, "review_packet_membership_or_order_mismatch"):
                audit(sample, manifest, frame, packet, project)

    def test_rejects_capture_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample, manifest, frame, packet, project = self.setup_fixture(Path(tmp))
            raw = project / "profile.json"
            raw.write_text(json.dumps({"http_status": 200, "data": {"user": {
                "id": "99999", "screen_name": "review_handle"}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "captured_profile_bytes_or_identity_mismatch"):
                audit(sample, manifest, frame, packet, project)


if __name__ == "__main__":
    unittest.main()
