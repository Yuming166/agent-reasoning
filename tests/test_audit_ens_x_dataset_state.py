import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/audit_ens_x_dataset_state.py"


class DatasetStateAuditTests(unittest.TestCase):
    def test_audit_keeps_scopes_separate_and_does_not_claim_asof(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "audit.json"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--project", str(PROJECT), "--out", str(out)],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(out.read_text())
        scopes = report["scopes"]
        self.assertEqual(scopes["seed_crosswalk"]["confirmed_wallet_x_pairs"], 12)
        self.assertTrue(scopes["explicit_fx_batch"]["allowlist_equals_seed_id_set"])
        self.assertFalse(scopes["explicit_fx_batch"]["automatic_candidate_pool_expansion"])
        self.assertEqual(scopes["profile_scan_separate_scope"]["candidate_rows"], 231)
        self.assertTrue(scopes["profile_scan_separate_scope"]["candidate_status"].startswith("all candidates remain unconfirmed"))
        self.assertEqual(scopes["timeline_pilot_separate_scope"]["provisional_crosswalk_rows"], 50)
        self.assertEqual(scopes["timeline_pilot_separate_scope"]["pilot_ids_overlap_explicit_fx_allowlist"], 0)
        self.assertEqual(scopes["231_candidate_manual_review"]["frozen_probability_sample_rows"], 60)
        self.assertFalse(scopes["231_candidate_manual_review"]["sample_complete"])
        self.assertEqual(scopes["event_time_asof_reconstruction"]["status"], "not_demonstrated_from_current_local_artifacts")
        self.assertTrue(scopes["heuristic_priority_artifact"]["not_a_collection_authorization"])
        self.assertTrue(report["mode"].endswith("no_network_no_bigquery_no_collection"))


if __name__ == "__main__":
    unittest.main()
