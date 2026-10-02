import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fx_authorized_continue.py"
spec = importlib.util.spec_from_file_location("fx_authorized_continue", SCRIPT)
fx = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fx
spec.loader.exec_module(fx)


class ContinueSafetyTests(unittest.TestCase):
    def make_parent(self, root: Path) -> Path:
        parent = root / "parent_run"
        parent.mkdir()
        (parent / "run_manifest.json").write_text(json.dumps({
            "run_id": "parent-run-test",
            "account_count": 12,
            "target_end_exclusive_utc": "2026-09-24T17:24:10Z",
        }))
        sample_fields = ["handle", "x_user_id", "pair_ids", "profile_id_preflight_match", "activity_stratum"]
        verification_fields = ["pair_id", "handle", "verification_status", "evidence_date", "evidence_note", "x_user_id"]
        samples, verifications = [], []
        for i in range(12):
            handle, uid, pair = f"test_user_{i}", str(100000 + i), f"pair_{i}"
            samples.append({"handle": handle, "x_user_id": uid, "pair_ids": pair,
                            "profile_id_preflight_match": "true", "activity_stratum": "test"})
            verifications.append({"pair_id": pair, "handle": handle, "verification_status": "account_confirms",
                                  "evidence_date": "2026-01-01", "evidence_note": "fixture evidence", "x_user_id": uid})
        with (parent / "sample_manifest.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sample_fields); writer.writeheader(); writer.writerows(samples)
        with (root / "verification_sample_v2_filled.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=verification_fields); writer.writeheader(); writer.writerows(verifications)
        return parent

    def test_audit_only_creates_or_changes_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(Path(tmp))
            before = {}
            for path in Path(tmp).rglob("*"):
                if path.is_file():
                    before[path.relative_to(tmp).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            result = subprocess.run([sys.executable, str(SCRIPT), "--parent-run", str(parent), "--audit-only"],
                                    check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            after = {}
            for path in Path(tmp).rglob("*"):
                if path.is_file():
                    after[path.relative_to(tmp).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertFalse((parent / "continuation_20260924_fixed_window").exists())
            self.assertIn('"summary"', result.stdout)
            self.assertIn("PLAN", result.stdout)

    def test_plan_requires_full_archive_order_validation_before_terminal_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = self.make_parent(root)
            raw = parent / "raw" / "test_user_0"
            raw.mkdir(parents=True)
            uid = "100000"

            def status(tweet_id, stamp):
                return {"id": tweet_id, "created_at": stamp,
                        "author": {"id": uid}}

            # Page 1 is ascending (a pagination anomaly); page 2 is fully before
            # the target boundary. Looking only at page 2 would falsely call this complete.
            pages = {
                "page_1_cursor1.body": {"code": 200, "results": [
                    status("1", "2026-02-02T00:00:00Z"),
                    status("2", "2026-02-03T00:00:00Z")], "cursor": {"bottom": "c2"}},
                "page_2_cursor2.body": {"code": 200, "results": [
                    status("3", "2025-12-31T00:00:00Z"),
                    status("4", "2025-12-30T00:00:00Z")], "cursor": {"bottom": "c3"}},
            }
            for name, payload in pages.items():
                (raw / name).write_text(json.dumps(payload))
            account = {"handle": "test_user_0", "x_user_id": uid}
            plan = fx.plan_account(parent, parent / "continuation_20260924_fixed_window", account, [])
            self.assertEqual(plan["status"], "terminal_coverage_requires_review")
            self.assertEqual(plan["terminal_integrity_issue"], "pagination_order_violation")
            self.assertIsNone(plan["next_page"])

    def test_empty_page_with_bottom_cursor_is_resumable_not_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = self.make_parent(root)
            raw = parent / "raw" / "test_user_0"
            raw.mkdir(parents=True)
            (raw / "page_1_first.body").write_text(json.dumps({
                "code": 200, "results": [], "cursor": {"bottom": "cursor-next"}
            }))
            account = {"handle": "test_user_0", "x_user_id": "100000"}
            continuation_dir = parent / "continuation_20260924_fixed_window"
            plan = fx.plan_account(parent, continuation_dir, account, [])
            self.assertEqual(plan["status"], "resume_from_cursor")
            self.assertEqual(plan["next_page"], 2)
            self.assertEqual(plan["cursor"], "cursor-next")

            sample = [{"handle": "test_user_0", "x_user_id": "100000"}]
            coverage, _tweets, _meta = fx.reconcile(
                parent, continuation_dir, sample, datetime(2026, 9, 24, 17, 24, 10, tzinfo=timezone.utc))
            self.assertFalse(coverage[0]["timeline_exhausted_no_cursor"])
            self.assertFalse(coverage[0]["pagination_to_target_boundary"])
            self.assertTrue(coverage[0]["truncated_or_uncertain"])
            self.assertEqual(coverage[0]["stop_reason"], "cursor_available_but_target_boundary_not_reached")

            # A later page can close the gap; the intermediate empty page is
            # acceptable only because it carried the cursor to that page.
            (raw / "page_2_next.body").write_text(json.dumps({
                "code": 200, "results": [{"id": "older", "created_at": "2025-12-31T00:00:00Z",
                                           "author": {"id": "100000"}}],
                "cursor": {"bottom": "cursor-older"}
            }))
            plan = fx.plan_account(parent, continuation_dir, account, [])
            self.assertEqual(plan["status"], "already_reached_start_boundary")
            coverage, _tweets, _meta = fx.reconcile(
                parent, continuation_dir, sample, datetime(2026, 9, 24, 17, 24, 10, tzinfo=timezone.utc))
            self.assertTrue(coverage[0]["reached_start_boundary"])
            self.assertTrue(coverage[0]["pagination_to_target_boundary"])

    def test_empty_page_without_cursor_is_not_proof_of_exhaustion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = self.make_parent(root)
            raw = parent / "raw" / "test_user_0"
            raw.mkdir(parents=True)
            (raw / "page_1_empty.body").write_text(json.dumps({"code": 200, "results": [], "cursor": {}}))
            account = {"handle": "test_user_0", "x_user_id": "100000"}
            plan = fx.plan_account(parent, parent / "continuation_20260924_fixed_window", account, [])
            self.assertEqual(plan["status"], "terminal_coverage_requires_review")
            self.assertEqual(plan["terminal_integrity_issue"], "empty_archived_page_without_cursor")
            coverage, _tweets, _meta = fx.reconcile(
                parent, parent / "continuation_20260924_fixed_window", [account],
                datetime(2026, 9, 24, 17, 24, 10, tzinfo=timezone.utc))
            self.assertFalse(coverage[0]["timeline_exhausted_no_cursor"])
            self.assertFalse(coverage[0]["pagination_to_target_boundary"])
            self.assertEqual(coverage[0]["stop_reason"], "empty_page_without_cursor_unverified")

    def test_collector_follows_empty_page_cursor_within_existing_page_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "continuation"
            output.mkdir()
            collector = fx.Continuation(output, datetime.now(timezone.utc))
            responses = [
                ({"results": [], "cursor": {"bottom": "cursor-2"}}, {}),
                ({"results": [{"id": "older", "created_at": "2025-12-31T00:00:00Z",
                               "author": {"id": "100000"}}], "cursor": {"bottom": "cursor-3"}}, {}),
            ]
            acct = {"handle": "test_user_0", "x_user_id": "100000"}
            plan = {"status": "resume_from_cursor", "next_page": 2, "cursor": "cursor-1"}
            with patch.object(collector, "request", side_effect=responses) as request:
                result = collector.collect_account(acct, plan, global_pages_remaining=2,
                                                   account_pages_remaining=2)
            self.assertEqual(request.call_count, 2)
            self.assertEqual([call.args[1:] for call in request.call_args_list],
                             [(2, "cursor-1"), (3, "cursor-2")])
            self.assertEqual(result["continuation_pages_attempted"], 2)
            self.assertEqual(result["stop_reason"], "reached_start_boundary")

    def test_plan_accepts_ordered_archive_at_target_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = self.make_parent(root)
            raw = parent / "raw" / "test_user_0"
            raw.mkdir(parents=True)
            payload = {"code": 200, "results": [
                {"id": "1", "created_at": "2025-12-31T00:00:00Z", "author": {"id": "100000"}},
                {"id": "2", "created_at": "2025-12-30T00:00:00Z", "author": {"id": "100000"}}],
                "cursor": {"bottom": "older"}}
            (raw / "page_1_cursor.body").write_text(json.dumps(payload))
            account = {"handle": "test_user_0", "x_user_id": "100000"}
            plan = fx.plan_account(parent, parent / "continuation_20260924_fixed_window", account, [])
            self.assertEqual(plan["status"], "already_reached_start_boundary")

    def test_load_request_log_reads_initial_and_continuation_attempt_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = {"request_id": "req_1", "kind": "statuses", "page": 1}
            continuation = {"request_id": "cont_req_1", "kind": "statuses", "page": 1}
            (root / "requests.jsonl").write_text(json.dumps(initial) + "\n")
            (root / "continuation_requests.jsonl").write_text(json.dumps(continuation) + "\n")
            loaded = fx.load_request_log(root)
            self.assertEqual([row["request_id"] for row in loaded], ["req_1", "cont_req_1"])

    def test_load_request_log_excludes_legacy_profile_rows_without_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {"request_id": "profile_1", "kind": "", "handle": "user"},
                {"request_id": "legacy_status_1", "kind": "", "handle": "user", "page": 1},
                {"request_id": "typed_status_bad", "kind": "statuses", "handle": "user"},
                {"request_id": "other_kind", "kind": "profile", "handle": "user", "page": 1},
            ]
            (root / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            loaded = fx.load_request_log(root)
            self.assertEqual([r["request_id"] for r in loaded], ["legacy_status_1", "typed_status_bad"])

    def test_legacy_request_id_backfill_uses_only_unique_frozen_sample_handle(self):
        sample = [{"handle": "Alice", "x_user_id": "123"}, {"handle": "Bob", "x_user_id": "456"}]
        rows, count = fx.bind_legacy_request_ids([
            {"request_id": "legacy", "handle": "@ALICE", "page": 1},
            {"request_id": "known", "handle": "Bob", "x_user_id": "456", "page": 1},
        ], sample)
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["x_user_id"], "123")
        self.assertTrue(rows[0]["stable_id_recovered_from_frozen_handle"])
        with self.assertRaisesRegex(ValueError, "not unique"):
            fx.bind_legacy_request_ids([{"request_id": "unknown", "handle": "Mallory", "page": 1}], sample)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            fx.bind_legacy_request_ids([{"request_id": "mismatch", "handle": "Alice", "x_user_id": "456", "page": 1}], sample)

    def test_malformed_request_jsonl_fails_closed_with_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requests.jsonl").write_text('{"request_id":"ok"}\n{broken\n')
            with self.assertRaisesRegex(ValueError, r"malformed JSONL.*requests.jsonl:2"):
                fx.load_request_log(root)

    def test_attempt_budget_unions_matching_reservations_and_counts_orphans(self):
        request = {"request_id": "req-1", "x_user_id": "123", "page": 1, "cursor_in": None}
        matched_reservation = dict(request, reservation_id="req-1")
        orphan_reservation = {"request_id": "reserved-only", "x_user_id": "123", "page": 2,
                             "cursor_in": "cursor-2"}
        audit = fx.audit_attempt_budget([request], [matched_reservation, orphan_reservation])
        self.assertEqual(audit["known_attempt_count"], 2)
        self.assertTrue(audit["within_budget"])
        mismatch = dict(matched_reservation, page=3)
        audit = fx.audit_attempt_budget([request], [mismatch])
        self.assertFalse(audit["within_budget"])
        self.assertTrue(any("mismatched attempt identity" in x for x in audit["history_issues"]))

    def test_attempt_budget_detects_page_and_global_overages(self):
        row = {"x_user_id": "123", "page": 1, "cursor_in": None}
        page_rows = [dict(row, request_id=f"req-{i}") for i in range(fx.MAX_RETRIES + 1)]
        audit = fx.audit_attempt_budget(page_rows)
        self.assertFalse(audit["within_budget"])
        self.assertEqual(audit["per_page_overages"][0]["attempts"], fx.MAX_RETRIES + 1)
        global_rows = [dict(row, request_id=f"req-{i}", page=i + 1) for i in range(3)]
        with patch.object(fx, "MAX_HTTP_ATTEMPTS_TOTAL", 2):
            audit = fx.audit_attempt_budget(global_rows)
        self.assertTrue(audit["global_overage"])
        self.assertFalse(audit["within_budget"])

    def test_resume_budget_preflight_halts_before_writes_or_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(Path(tmp))
            rows = [{"request_id": f"req-{i}", "x_user_id": "100000", "handle": "test_user_0",
                     "kind": "statuses", "page": 1, "cursor_in": None} for i in range(fx.MAX_RETRIES + 1)]
            (parent / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            output = parent / "continuation_20260924_fixed_window"
            with patch.object(sys, "argv", [str(SCRIPT), "--parent-run", str(parent), "--resume"]), \
                 patch.object(fx.requests.Session, "get", side_effect=AssertionError("HTTP must not run")) as get:
                with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                    fx.main()
            get.assert_not_called()
            self.assertFalse(output.exists())

    def test_resume_rejects_retries_split_across_parent_and_continuation(self):
        """A restart must not reset the cumulative retry cap for the same page."""
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(Path(tmp))
            output = parent / "continuation_20260924_fixed_window"
            output.mkdir()

            def attempt(request_id, attempt):
                return {
                    "request_id": request_id,
                    "handle": "test_user_0",
                    "x_user_id": "100000",
                    "kind": "statuses",
                    "page": 1,
                    "cursor_in": None,
                    "attempt": attempt,
                    "http_status": 500,
                    "error": "http_500",
                }

            parent_rows = [attempt(f"parent-{i}", i) for i in range(1, 4)]
            continuation_rows = [
                attempt(f"continuation-{i}", (i - 1) % 3 + 1) for i in range(1, 7)
            ]
            (parent / "requests.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in parent_rows)
            )
            (output / "continuation_requests.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in continuation_rows)
            )

            bound_parent, _ = fx.bind_legacy_request_ids(parent_rows, fx.load_parent(parent)[1])
            bound_cont, _ = fx.bind_legacy_request_ids(continuation_rows, fx.load_parent(parent)[1])
            audit = fx.audit_attempt_budget(bound_parent + bound_cont, [])
            self.assertFalse(audit["within_budget"])
            self.assertEqual(audit["per_page_overages"][0]["attempts"], 9)

            before = {
                p.relative_to(parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in parent.rglob("*") if p.is_file()
            }
            with patch.object(sys, "argv", [str(SCRIPT), "--parent-run", str(parent), "--resume"]), \
                 patch.object(fx.requests.Session, "get", side_effect=AssertionError("HTTP must not run")) as get:
                with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                    fx.main()
            get.assert_not_called()
            after = {
                p.relative_to(parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in parent.rglob("*") if p.is_file()
            }
            self.assertEqual(before, after)
            self.assertFalse((output / ".resume.lock").exists())
            self.assertFalse((output / "attempt_budget.jsonl").exists())

    def test_resume_inconsistent_existing_ledger_halts_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(Path(tmp))
            request = {"request_id": "req-1", "x_user_id": "100000", "handle": "test_user_0",
                       "kind": "statuses", "page": 1, "cursor_in": None}
            (parent / "requests.jsonl").write_text(json.dumps(request) + "\n")
            output = parent / "continuation_20260924_fixed_window"
            output.mkdir()
            ledger = output / "attempt_budget.jsonl"
            ledger.write_text(json.dumps({"request_id": "different-id", "x_user_id": "100000",
                                          "page": 1, "cursor_in": None}) + "\n")
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
            with patch.object(sys, "argv", [str(SCRIPT), "--parent-run", str(parent), "--resume"]), \
                 patch.object(fx.requests.Session, "get", side_effect=AssertionError("HTTP must not run")) as get:
                with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                    fx.main()
            get.assert_not_called()
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((output / ".resume.lock").exists())

    def test_failed_page_at_cumulative_retry_limit_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = self.make_parent(root)
            output = parent / "continuation_20260924_fixed_window"
            output.mkdir()
            reqs = []
            for i in range(6):
                reqs.append({"request_id": f"cont_req_{i+1:05d}", "handle": "test_user_0",
                             "x_user_id": "100000", "kind": "statuses", "page": 1,
                             "cursor_in": None, "http_status": 500, "error": "http_500"})
            (output / "continuation_requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reqs))
            acct = {"handle": "test_user_0", "x_user_id": "100000"}
            plan = fx.plan_account(parent, output, acct, reqs)
            self.assertEqual(plan["status"], "terminal_retry_budget_exhausted")
            self.assertIsNone(plan["next_page"])
            self.assertEqual(plan["cumulative_http_attempts_for_page"], 6)

    def test_attempt_reservation_is_persisted_and_enforces_cumulative_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "continuation"
            output.mkdir()
            prior = [{"request_id": f"old_{i}", "handle": "u", "x_user_id": "123",
                      "kind": "statuses", "page": 4, "cursor_in": "cursor-x"} for i in range(3)]
            continuation = fx.Continuation(output, datetime.now(timezone.utc), prior)
            ok, error, used = continuation._reserve_attempt({"handle": "u", "x_user_id": "123"}, 4, "cursor-x", "new_req")
            self.assertFalse(ok)
            self.assertEqual(error, "cumulative_page_attempt_budget_exhausted")
            self.assertEqual(used, 3)
            ledger = [json.loads(line) for line in (output / "attempt_budget.jsonl").read_text().splitlines()]
            self.assertEqual(len(ledger), 3)
            self.assertTrue(all(row["legacy_migration"] for row in ledger))

    def test_parent_or_sample_fingerprint_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_parent(Path(tmp))
            manifest, sample, cutoff = fx.load_parent(parent)
            output = parent / "continuation_20260924_fixed_window"
            output.mkdir()
            fx.continuation_manifest_for_run(output, parent, manifest, sample, cutoff, 0, persist=True)
            with (parent / "sample_manifest.csv").open("a") as f:
                f.write("# changed\n")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                fx.continuation_manifest_for_run(output, parent, manifest, sample, cutoff, 0, persist=False)


if __name__ == "__main__":
    unittest.main()
