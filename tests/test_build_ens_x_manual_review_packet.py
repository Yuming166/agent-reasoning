import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_ens_x_manual_review_packet import build_packet


class ManualReviewPacketTests(unittest.TestCase):
    def make_fixture(self, root: Path, *, expected_hash: str | None = None):
        raw = root / "profile.json"
        body = {
            "handle": "review_handle",
            "http_status": 200,
            "fetched_at_utc": "2026-09-25T00:00:00Z",
            "data": {"user": {
                "id": "12345", "screen_name": "review_handle", "url": "https://x.com/review_handle",
                "name": "sample.eth", "description": "Wallet owner text", "website": None,
            }},
        }
        raw.write_text(json.dumps(body), encoding="utf-8")
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        sample = root / "sample.csv"
        fields = ["address", "x_user_id", "handle_at_profile_audit", "reverse_ens_name",
                  "profile_raw_file", "profile_raw_sha256", "matched_terms", "evidence_types",
                  "selection_stratum", "evidence_fields", "events_2026", "sampling_stratum", "design_weight"]
        with sample.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerow({
                "address": "0xabc", "x_user_id": "12345", "handle_at_profile_audit": "review_handle",
                "reverse_ens_name": "sample.eth", "profile_raw_file": str(raw),
                "profile_raw_sha256": expected_hash or digest, "matched_terms": "sample.eth",
                "evidence_types": "exact_reverse_ens_name", "selection_stratum": "random",
                "evidence_fields": "display_name", "events_2026": "3", "sampling_stratum": "s1", "design_weight": "2",
            })
        return sample

    def test_builds_packet_without_assigning_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = self.make_fixture(Path(tmp))
            packet, manifest = build_packet(sample)
            self.assertEqual(len(packet), 1)
            self.assertEqual(packet[0]["stable_id_match"], "true")
            self.assertEqual(packet[0]["review_state"], "pending_manual_verdict")
            self.assertFalse(manifest["verdicts_assigned"])
            self.assertFalse(manifest["collection_authorized"])

    def test_rejects_tampered_capture_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = self.make_fixture(Path(tmp), expected_hash="0" * 64)
            with self.assertRaisesRegex(ValueError, "raw_profile_sha256_mismatch"):
                build_packet(sample)


if __name__ == "__main__":
    unittest.main()
