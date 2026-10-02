import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "build_ens_x_expansion_pilot_graph.py"
spec = importlib.util.spec_from_file_location("build_confirmed_pilot_graph", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FrozenRunInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.account = {"x_user_id": "12345", "handle_at_profile_audit": "alice",
                        "verification_status": "account_confirms", "pair_id": "pair-1",
                        "wallet_address": "0x" + "1" * 40,
                        "evidence_date": "2026-09-20", "evidence_url": "https://x.com/alice/status/1",
                        "evidence_note": "account profile explicitly lists ENS"}
        self.write_manifest([self.account])
        self.write_coverage([{"x_user_id": "12345", "stop_reason": "page_ceiling"}])

    def write_manifest(self, accounts):
        (self.out / "run_manifest.json").write_text(json.dumps({
            "schema": "ens-x-confirmed-timeline-pilot-v1", "accounts": accounts
        }))

    def write_coverage(self, rows):
        (self.out / "coverage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_accepts_exact_confirmed_manifest_coverage(self):
        queue, coverage = mod.load_run_inputs(self.out)
        self.assertEqual([row["x_user_id"] for row in queue], ["12345"])
        self.assertEqual(len(coverage), 1)

    def test_rejects_pending_candidate_in_manifest(self):
        pending = {**self.account, "verification_status": "pending"}
        self.write_manifest([pending])
        with self.assertRaisesRegex(ValueError, "non-confirmed"):
            mod.load_run_inputs(self.out)

    def test_rejects_incomplete_or_extra_coverage(self):
        self.write_coverage([])
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            mod.load_run_inputs(self.out)
        self.write_coverage([{"x_user_id": "12345"}, {"x_user_id": "99999"}])
        with self.assertRaisesRegex(RuntimeError, "incomplete or out-of-scope"):
            mod.load_run_inputs(self.out)

    def test_rejects_duplicate_manifest_or_coverage_ids(self):
        self.write_manifest([self.account, self.account])
        with self.assertRaisesRegex(ValueError, "duplicate X IDs"):
            mod.load_run_inputs(self.out)
        self.write_manifest([self.account])
        self.write_coverage([{"x_user_id": "12345"}, {"x_user_id": "12345"}])
        with self.assertRaisesRegex(ValueError, "duplicate accounts"):
            mod.load_run_inputs(self.out)


if __name__ == "__main__":
    unittest.main()
