import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_ens_x_manual_evidence_checklist import prepare, REQUIRED_BLANK_REVIEW_FIELDS


class ManualEvidenceChecklistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sample = self.root / "sample.csv"
        self.manifest = self.root / "manifest.json"
        self.rows = []
        fields = [
            "address", "x_user_id", "sampling_stratum", "stratum_population_N",
            "stratum_sample_n", "design_weight", "manual_verdict", "reviewer",
            "reviewed_at_utc", "evidence_seen_at_utc", "x_profile_evidence_url",
            "evidence_quote_or_capture_id", "review_notes", "inclusion_probability", "sampling_seed",
            "handle_at_profile_audit", "reverse_ens_name",
        ]
        for i in range(60):
            self.rows.append({
                "address": f"0x{i:040x}", "x_user_id": str(10000 + i),
                "sampling_stratum": "h1", "stratum_population_N": "60",
                "stratum_sample_n": "60", "design_weight": "1.0",
                "manual_verdict": "pending", "reviewer": "", "reviewed_at_utc": "",
                "evidence_seen_at_utc": "", "x_profile_evidence_url": "",
                "evidence_quote_or_capture_id": "", "review_notes": "",
                "inclusion_probability": "1.0", "sampling_seed": "seed1",
                "handle_at_profile_audit": f"candidate{i}", "reverse_ens_name": f"candidate{i}.eth",
            })
        with self.sample.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.rows)
        immutable = ["address", "x_user_id", "sampling_stratum", "stratum_population_N",
                     "stratum_sample_n", "inclusion_probability", "design_weight", "sampling_seed"]
        digests = [hashlib.sha256(json.dumps({k: r[k] for k in immutable}, sort_keys=True,
                     separators=(",", ":"), ensure_ascii=False).encode()).hexdigest() for r in self.rows]
        manifest_obj = {
            "source_sha256_at_freeze": hashlib.sha256(self.sample.read_bytes()).hexdigest(),
            "row_count": 60, "immutable_fields": immutable,
            "ordered_row_digests": digests,
            "strata": {"h1": {"N_h": 60, "n_h": 60}},
        }
        manifest_bytes = (json.dumps(manifest_obj, separators=(",", ":")) + "\n").encode()
        self.manifest.write_bytes(manifest_bytes)
        self.manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_prepare_keeps_all_rows_pending_and_evidence_fields_blank(self):
        rows, metadata = prepare(self.sample, self.manifest, self.manifest_sha)
        self.assertEqual(60, len(rows))
        self.assertEqual(0, metadata["verdicts_assigned"])
        self.assertTrue(metadata["all_rows_remain_pending"])
        self.assertTrue(all(row["manual_verdict"] == "pending" for row in rows))
        self.assertTrue(all(not row[field] for row in rows for field in REQUIRED_BLANK_REVIEW_FIELDS))
        self.assertTrue(all(row["review_state"] == "not_started_account_side_evidence_required" for row in rows))
        self.assertEqual("https://x.com/i/user/10000", rows[0]["x_profile_url_from_stable_id"])
        self.assertIn("not evidence", metadata["profile_url_note"])
        self.assertEqual(0, metadata["network_requests_made"])

    def test_prepare_fails_closed_if_frozen_input_changes(self):
        with self.sample.open("a", encoding="utf-8") as f:
            f.write("\n")
        with self.assertRaisesRegex(ValueError, "differs from the frozen source CSV"):
            prepare(self.sample, self.manifest, self.manifest_sha)

    def test_prepare_refuses_nonpending_verdict(self):
        rows = list(self.rows)
        rows[0] = dict(rows[0], manual_verdict="unverifiable")
        fields = list(rows[0])
        with self.sample.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest = json.loads(self.manifest.read_text())
        manifest["source_sha256_at_freeze"] = hashlib.sha256(self.sample.read_bytes()).hexdigest()
        manifest_bytes = (json.dumps(manifest, separators=(",", ":")) + "\n").encode()
        self.manifest.write_bytes(manifest_bytes)
        updated_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        with self.assertRaisesRegex(ValueError, "is not pending"):
            prepare(self.sample, self.manifest, updated_manifest_sha)


if __name__ == "__main__":
    unittest.main()
