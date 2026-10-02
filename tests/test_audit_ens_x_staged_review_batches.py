import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_ens_x_staged_review_batches import audit
from scripts.stage_ens_x_review_batches import REVIEW_FIELDS


class StagedBatchAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "staged"
        self.reviewer = self.root / "reviewer_handoff"
        self.coordinator = self.root / "coordinator_only"
        self.reviewer.mkdir(parents=True, mode=0o700)
        self.coordinator.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.rows = [{
            "review_token": f"t{i}", "review_sequence": str(i), "address": f"0x{i:040x}",
            "x_user_id": str(1000+i), "handle_at_profile_audit": f"u{i}",
            "x_profile_url": f"https://x.com/i/user/{1000+i}", "manual_verdict": "pending",
            "x_profile_evidence_url": "", "evidence_quote_or_capture_id": "",
            "evidence_verified_x_user_id": "", "evidence_seen_at_utc": "", "reviewer": "",
            "reviewed_at_utc": "", "review_notes": "",
        } for i in range(1, 172)]
        self.output_hashes = {}
        for name, rows in (("targeted_priority_batch_12.csv", self.rows[:12]),
                           ("targeted_remaining_batch_159.csv", self.rows[12:])):
            p = self.reviewer / name
            with p.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
                w.writeheader(); w.writerows(rows)
            p.chmod(0o600)
            self.output_hashes[name] = ""  # populated after write; audit checks values below
        for name in ("README.txt", "REVIEW_INSTRUCTIONS.md"):
            p = self.reviewer / name
            p.write_text("approved handoff instructions\n", encoding="utf-8"); p.chmod(0o600)
        from scripts.stage_ens_x_review_batches import sha256
        self.output_hashes = {p.name: sha256(p) for p in self.reviewer.iterdir()}
        manifest = {
            "schema": "ens-x-targeted-review-batch-staging-v1", "mode": "offline_restricted_staging_not_distributed",
            "source_rows": 171, "priority_batch_rows": 12, "remaining_batch_rows": 159,
            "probability_packet_included_or_modified": False, "verdicts_assigned": 0, "mappings_promoted": 0,
            "collection_authorized": False, "network_requests": 0, "paid_queries_usd": 0,
            "priority_tasking_tier_counts": {"A_candidate_frame_interaction_bridge_review": 6,
              "B_text_coverage_review_no_observed_candidate_frame_edge": 6},
            "distribution_restrictions": {"reviewer_batch_fields": REVIEW_FIELDS, "priority_reasons_in_reviewer_files": False},
            "outputs_sha256": self.output_hashes,
        }
        p = self.coordinator / "manifest.json"
        p.write_text(json.dumps(manifest), encoding="utf-8"); p.chmod(0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_partition_passes(self):
        report = audit(self.root)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["unique_tokens"], 171)
        self.assertEqual(report["reviewer_rows"]["targeted_priority_batch_12.csv"], 12)

    def test_tampered_batch_fails_hash_check(self):
        with (self.reviewer / "targeted_priority_batch_12.csv").open("a") as f:
            f.write("tamper\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit(self.root)

    def test_nonpending_verdict_fails(self):
        p = self.reviewer / "targeted_priority_batch_12.csv"
        with p.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        rows[0]["manual_verdict"] = "account_confirms"
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS); w.writeheader(); w.writerows(rows)
        from scripts.stage_ens_x_review_batches import sha256
        self.output_hashes[p.name] = sha256(p)
        m = self.coordinator / "manifest.json"
        manifest = json.loads(m.read_text()); manifest["outputs_sha256"] = self.output_hashes
        m.write_text(json.dumps(manifest)); m.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "non-pending"):
            audit(self.root)


if __name__ == "__main__":
    unittest.main()
