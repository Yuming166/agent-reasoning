import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/reconcile_ens_x_candidate_timeline_quarantine.py"
spec = importlib.util.spec_from_file_location("reconcile_quarantine", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class ReconcileQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        self.run.mkdir()
        (self.run / "raw").mkdir()
        # Two page slots for user 10, with a retry on page 1; user 20 is a
        # partial account with one requested page and no terminal coverage row.
        self._jsonl("attempt_budget.jsonl", [
            {"request_id": "a", "x_user_id": "10", "page": 1},
            {"request_id": "b", "x_user_id": "10", "page": 1},
            {"request_id": "c", "x_user_id": "10", "page": 2},
            {"request_id": "d", "x_user_id": "20", "page": 1},
            {"request_id": "e", "x_user_id": "30", "page": 1},
        ])
        raw = b"{}"
        (self.run / "raw/one.body").write_bytes(raw)
        self._jsonl("requests.jsonl", [
            {"request_id": rid, "x_user_id": uid, "page": page,
             "http_status": status, "raw_file": str(self.run / "raw/one.body"),
             "raw_sha256": hashlib.sha256(raw).hexdigest()}
            for rid, uid, page, status in [
                ("a", "10", 1, 200), ("b", "10", 1, 500),
                ("c", "10", 2, 200), ("d", "20", 1, 200),
            ]
        ])
        self._jsonl("coverage.jsonl", [{"x_user_id": "10", "pages": 2, "stop_reason": "boundary"}])

    def tearDown(self):
        self.tmp.cleanup()

    def _jsonl(self, name, rows):
        (self.run / name).write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")

    def test_distinguishes_attempts_slots_and_partial_accounts(self):
        result = mod.reconcile(self.run)
        counts = result["ledger_counts"]
        self.assertEqual(counts["attempt_reservation_rows"], 5)
        self.assertEqual(counts["request_log_rows"], 4)
        self.assertEqual(counts["distinct_reserved_account_page_slots"], 4)
        self.assertEqual(counts["distinct_requested_account_page_slots"], 3)
        self.assertEqual(counts["coverage_pages_sum_for_terminal_coverage_rows"], 2)
        self.assertEqual(counts["max_distinct_reserved_pages_per_account"], 2)
        self.assertEqual(counts["max_reservations_per_account_page_slot"], 2)
        self.assertEqual(counts["reservation_only_account_ids_without_coverage"], ["20", "30"])
        self.assertEqual(counts["reserved_without_request_log_ids"], ["e"])
        self.assertEqual(counts["http_status_counts"], {"200": 3, "500": 1})
        self.assertFalse(counts["raw_response_integrity_errors"])

    def test_cli_refuses_output_inside_immutable_source_run(self):
        from unittest.mock import patch
        with patch("sys.argv", ["audit", "--run-dir", str(self.run), "--output", str(self.run / "bad.json")]):
            with self.assertRaises(SystemExit) as raised:
                mod.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.run / "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
