import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "collect_ens_x_expansion_pilot.py"
spec = importlib.util.spec_from_file_location("collect_pilot", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class RunLockTests(unittest.TestCase):
    def test_second_writer_is_rejected_for_same_run_directory(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "pilot"
            first = mod.exclusive_run_lock(out)
            first.__enter__()
            try:
                with self.assertRaisesRegex(RuntimeError, "another collector holds run lock"):
                    with mod.exclusive_run_lock(out):
                        self.fail("second collector entered locked run")
            finally:
                first.__exit__(None, None, None)
            with mod.exclusive_run_lock(out):
                pass


class AtomicLedgerTests(unittest.TestCase):
    def test_jsonl_append_rejects_torn_tail_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "events.jsonl"
            ledger.write_bytes(b'{"ok":true}')
            with self.assertRaisesRegex(ValueError, "truncated JSONL"):
                mod.append_jsonl(ledger, {"next": True})
            self.assertEqual(ledger.read_bytes(), b'{"ok":true}')

    def test_failed_atomic_replace_preserves_previous_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "events.jsonl"
            original = b'{"ok":true}\n'
            ledger.write_bytes(original)
            with patch.object(mod.os, "replace", side_effect=OSError("simulated crash boundary")):
                with self.assertRaisesRegex(OSError, "simulated crash boundary"):
                    mod.append_jsonl(ledger, {"next": True})
            self.assertEqual(ledger.read_bytes(), original)
            self.assertEqual(list(Path(d).glob("*.tmp")), [])


class CoverageSemanticsTests(unittest.TestCase):
    uid = "12345"
    acct = {"handle_at_profile_audit": "reviewed_user", "x_user_id": uid}

    def status(self, timestamp):
        return {"id": "1", "author": {"id": self.uid}, "created_at": timestamp}

    def run_pages(self, responses, max_pages=4):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        response_iter = iter(responses)
        def fake_request(_session, _handle, cursor, page, _raw_dir, _log, *_budget_args):
            return next(response_iter), f"fixture-{page}"
        with patch.object(mod, "request_page", side_effect=fake_request), patch.object(mod.time, "sleep"):
            return mod.collect_account(object(), self.acct, Path(tmp.name), max_pages, 0)

    def test_cursor_exhaustion_is_not_completeness(self):
        row = self.run_pages([{"code": 200, "results": [self.status("2026-04-01T00:00:00Z")]}])
        self.assertEqual(row["stop_reason"], "cursor_exhausted")
        self.assertFalse(row["timeline_complete"])
        self.assertFalse(row["window_boundary_reached"])
        self.assertEqual(row["coverage_status"], "endpoint_exhausted_before_boundary")

    def test_observed_pre_window_status_reaches_boundary_but_not_source_completeness(self):
        row = self.run_pages([{"code": 200, "results": [self.status("2025-12-31T23:59:59Z")], "cursor": {"bottom": "next"}}])
        self.assertEqual(row["stop_reason"], "target_window_boundary_reached")
        self.assertTrue(row["window_boundary_reached"])
        self.assertFalse(row["timeline_complete"])
        self.assertEqual(row["coverage_status"], "boundary_observed_source_completeness_unverified")

    def test_old_repost_source_timestamp_does_not_trigger_boundary(self):
        repost = self.status("2020-01-01T00:00:00Z")
        repost["reposted_by"] = {"id": self.uid}
        page = {"code": 200, "results": [repost], "cursor": {"bottom": "next"}}
        row = self.run_pages([page], max_pages=1)
        self.assertFalse(row["window_boundary_reached"])
        self.assertEqual(row["stop_reason"], "page_ceiling")

    def test_page_ceiling_is_explicitly_incomplete(self):
        page = {"code": 200, "results": [self.status("2026-04-01T00:00:00Z")], "cursor": {"bottom": "next"}}
        row = self.run_pages([page], max_pages=1)
        self.assertTrue(row["page_ceiling_reached"])
        self.assertFalse(row["timeline_complete"])
        self.assertEqual(row["coverage_status"], "incomplete_page_ceiling_before_boundary")

    def test_request_failure_is_incomplete_not_complete(self):
        row = self.run_pages([None])
        self.assertFalse(row["timeline_complete"])
        self.assertEqual(row["coverage_status"], "incomplete_request_or_payload_failure")


class DurableResumeTests(unittest.TestCase):
    uid = "12345"
    acct = {"handle_at_profile_audit": "reviewed_user", "x_user_id": uid}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.raw_dir = self.out / "raw" / "reviewed_user"
        self.raw_dir.mkdir(parents=True)

    def persist_page(self, page, cursor_in, cursor_out, statuses):
        import hashlib, json
        payload = {"code": 200, "results": statuses,
                   "cursor": {"bottom": cursor_out} if cursor_out else {}}
        path = self.raw_dir / f"page_{page:04d}_attempt_fixture.body"
        body = json.dumps(payload).encode()
        path.write_bytes(body)
        row = {"request_id": f"req-{page}-{cursor_in}", "x_user_id": self.uid,
               "page": page, "cursor_in": cursor_in, "cursor_out": cursor_out,
               "http_status": 200, "api_code": 200, "raw_file": str(path),
               "raw_sha256": hashlib.sha256(body).hexdigest(), "error": None}
        with (self.out / "requests.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        return payload, str(path)

    def status(self, tweet_id, timestamp):
        return {"id": tweet_id, "author": {"id": self.uid}, "created_at": timestamp}

    def test_resume_replays_contiguous_cursor_chain_after_crash(self):
        calls = []
        page2 = {"code": 200, "results": [self.status("2", "2025-12-31T00:00:00Z")], "cursor": {}}

        def interrupted(_session, _handle, cursor, page, *_args):
            calls.append((page, cursor))
            if page == 1:
                return self.persist_page(page, cursor, "cursor-1", [self.status("1", "2026-04-01T00:00:00Z")])
            raise RuntimeError("simulated process interruption")

        with patch.object(mod, "request_page", side_effect=interrupted), patch.object(mod.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                mod.collect_account(object(), self.acct, self.out, 3, 0, 10)

        def resume(_session, _handle, cursor, page, *_args):
            calls.append((page, cursor))
            self.assertEqual((page, cursor), (2, "cursor-1"))
            return self.persist_page(page, cursor, None, page2["results"])

        with patch.object(mod, "request_page", side_effect=resume), patch.object(mod.time, "sleep"):
            result = mod.collect_account(object(), self.acct, self.out, 3, 0, 10)
        self.assertEqual(calls, [(1, None), (2, "cursor-1"), (2, "cursor-1")])
        self.assertEqual(result["stop_reason"], "target_window_boundary_reached")

    def test_archived_page_bound_to_wrong_cursor_fails_before_request(self):
        self.persist_page(1, "unexpected", "cursor-1", [self.status("1", "2026-04-01T00:00:00Z")])
        with patch.object(mod, "request_page") as fetch:
            with self.assertRaisesRegex(RuntimeError, "unexpected cursor"):
                mod.collect_account(object(), self.acct, self.out, 2, 0, 10)
            fetch.assert_not_called()

    def test_archived_page_hash_mismatch_fails_closed(self):
        _payload, path = self.persist_page(1, None, "cursor-1", [self.status("1", "2026-04-01T00:00:00Z")])
        Path(path).write_text('{"code":200,"results":[]}')
        with patch.object(mod, "request_page") as fetch:
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                mod.collect_account(object(), self.acct, self.out, 2, 0, 10)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class AllowlistPreflightTests(unittest.TestCase):
    fields = ["handle_at_profile_audit", "x_user_id", "verification_status", "pair_id",
              "evidence_date", "evidence_url", "evidence_note", "wallet_address"]

    def write_allowlist(self, path, status="account_confirms"):
        import csv
        row = {"handle_at_profile_audit": "confirmed_fixture", "x_user_id": "12345",
               "verification_status": status, "pair_id": "pair-fixture",
               "evidence_date": "2026-09-25", "evidence_url": "https://example.invalid/evidence",
               "evidence_note": "synthetic test evidence", "wallet_address": "0x" + "1"*40}
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.fields); writer.writeheader(); writer.writerow(row)

    def test_synthetic_confirmed_allowlist_freezes_inputs_and_resumes_exactly(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "allow.csv"; out = root / "run"
            self.write_allowlist(source)
            queue = mod.prepare_run(out, source, 2, 4, 12, False)
            self.assertEqual(queue[0]["x_user_id"], "12345")
            self.assertEqual(mod.prepare_run(out, source, 2, 4, 12, True), queue)
            with self.assertRaisesRegex(ValueError, "frozen manifest"):
                mod.prepare_run(out, source, 2, 3, 12, True)

    def test_unconfirmed_rows_and_legacy_candidate_resume_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "allow.csv"; out = root / "run"
            self.write_allowlist(source, "candidate")
            with self.assertRaisesRegex(ValueError, "not account_confirms"):
                mod.prepare_run(out, source, 2, 4, 12, False)
            out.mkdir(); (out / "pilot_queue.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "legacy auto-candidate"):
                mod.prepare_run(out, source, 2, 4, 12, True)

    def test_hard_budget_caps_and_over_budget_resume_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "allow.csv"; out = root / "run"
            self.write_allowlist(source)
            with self.assertRaisesRegex(ValueError, "hard caps"):
                mod.prepare_run(out, source, 13, 8, 192, False)
            mod.prepare_run(out, source, 2, 4, 2, False)
            budget = out / "attempt_budget.jsonl"
            mod.append_jsonl(budget, {"request_id": "a", "x_user_id": "12345", "page": 1})
            mod.append_jsonl(budget, {"request_id": "b", "x_user_id": "12345", "page": 2})
            mod.append_jsonl(budget, {"request_id": "c", "x_user_id": "12345", "page": 3})
            with self.assertRaisesRegex(ValueError, "exceeds frozen global budget"):
                mod.prepare_run(out, source, 2, 4, 2, True)

    def test_deployment_hard_caps_are_10_accounts_4_pages_50_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / "allow.csv"
            self.write_allowlist(source)
            for accounts, pages, attempts in ((11, 4, 50), (10, 5, 50), (10, 4, 51)):
                with self.subTest(accounts=accounts, pages=pages, attempts=attempts):
                    with self.assertRaisesRegex(ValueError, "10 accounts, 4 pages/account, 50 HTTP attempts"):
                        mod.prepare_run(root / f"run-{accounts}-{pages}-{attempts}", source,
                                        accounts, pages, attempts, False)

    def test_global_http_reservations_enforce_persisted_one_second_spacing(self):
        from datetime import datetime as RealDateTime, timedelta, timezone
        import json

        class FakeDateTime:
            now_value = RealDateTime(2026, 9, 25, 22, 0, tzinfo=timezone.utc)

            @classmethod
            def now(cls, tz=None):
                return cls.now_value if tz is None else cls.now_value.astimezone(tz)

            @staticmethod
            def fromisoformat(value):
                return RealDateTime.fromisoformat(value)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "attempt_budget.jsonl"
            with patch.object(mod, "datetime", FakeDateTime):
                first = mod.reserve_http_attempt(path, "12345", 1, None, 5, 1.0)
                waits = []

                def advance_clock(seconds):
                    waits.append(seconds)
                    FakeDateTime.now_value += timedelta(seconds=seconds)

                with patch.object(mod.time, "sleep", side_effect=advance_clock):
                    second = mod.reserve_http_attempt(path, "12345", 2, "cursor-1", 5, 1.0)

            self.assertEqual(len(waits), 1)
            self.assertAlmostEqual(waits[0], 1.0, places=6)
            first_at = RealDateTime.fromisoformat(first["reserved_at_utc"])
            second_at = RealDateTime.fromisoformat(second["reserved_at_utc"])
            self.assertGreaterEqual((second_at - first_at).total_seconds(), 1.0)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertGreaterEqual(
                (RealDateTime.fromisoformat(rows[1]["reserved_at_utc"])
                 - RealDateTime.fromisoformat(rows[0]["reserved_at_utc"])).total_seconds(),
                1.0,
            )

    def test_attempt_reservations_enforce_global_and_per_page_caps(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "attempt_budget.jsonl"
            mod.reserve_http_attempt(path, "12345", 1, None, 3)
            mod.reserve_http_attempt(path, "12345", 1, None, 3)
            with self.assertRaisesRegex(RuntimeError, "per-page"):
                mod.reserve_http_attempt(path, "12345", 1, None, 3)
            mod.reserve_http_attempt(path, "12345", 2, "cursor-1", 3)
            with self.assertRaisesRegex(RuntimeError, "global"):
                mod.reserve_http_attempt(path, "12345", 3, "cursor-2", 3)
