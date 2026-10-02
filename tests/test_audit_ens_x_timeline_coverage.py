import importlib.util
import json
import sys
import tempfile
import unittest
import hashlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("audit_timeline", SCRIPTS / "audit_ens_x_timeline_coverage.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class TimelineIntegrityAuditTests(unittest.TestCase):
    uid = "12345"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "raw" / "user").mkdir(parents=True)
        self.coverage = {"handle": "User", "x_user_id": self.uid,
                         "stop_reason": "target_window_boundary_reached",
                         "timeline_complete": False, "pages": 1}
        self.status = {"id": "t1", "author": {"id": self.uid},
                       "created_at": "2025-12-31T23:59:59Z"}

    def write_page(self, page=1, cursor_in=None, cursor_out=None, status=None):
        payload = {"code": 200, "results": [status or self.status],
                   "cursor": {"bottom": cursor_out} if cursor_out else {}}
        body = json.dumps(payload).encode()
        path = self.root / "raw" / "user" / f"page_{page:04d}.body"
        path.write_bytes(body)
        request = {"handle": "user", "page": page, "attempt": 1,
                   "cursor_in": cursor_in, "http_status": 200, "api_code": 200,
                   "error": None, "raw_file": str(path), "raw_sha256": hashlib.sha256(body).hexdigest(),
                   "result_count": len(payload["results"])}
        return request

    def run_audit(self, requests):
        (self.root / "coverage.jsonl").write_text(json.dumps(self.coverage) + "\n")
        (self.root / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in requests))
        return mod.audit(self.root)

    def test_only_request_bound_hash_verified_page_supports_boundary(self):
        report = self.run_audit([self.write_page()])
        self.assertEqual(report["request_attempt_count_bound_to_coverage_handles"], 1)
        self.assertEqual(report["validated_successful_page_count"], 1)
        self.assertEqual(report["corrected_boundary_observed_count"], 1)
        self.assertEqual(report["integrity_issue_count"], 0)

    def test_hash_mismatch_does_not_support_boundary(self):
        row = self.write_page()
        row["raw_sha256"] = "0" * 64
        report = self.run_audit([row])
        self.assertEqual(report["corrected_boundary_observed_count"], 0)
        self.assertIn("User:page_1_raw_sha256_mismatch", report["integrity_issues"])

    def test_cursor_chain_mismatch_is_reported_and_invalidates_boundary(self):
        first = self.write_page(page=1, cursor_out="expected")
        second = self.write_page(page=2, cursor_in="wrong")
        report = self.run_audit([first, second])
        account = report["accounts"][0]
        self.assertIn("cursor_chain_mismatch_page_2", account["integrity_issues"])
        self.assertEqual(report["corrected_boundary_observed_count"], 0)

    def test_failed_http_attempt_is_counted_but_not_coverage_evidence(self):
        failed = {"handle": "user", "page": 1, "attempt": 1,
                  "http_status": 503, "api_code": None, "error": "http_error"}
        report = self.run_audit([failed])
        self.assertEqual(report["request_attempt_count_bound_to_coverage_handles"], 1)
        self.assertEqual(report["validated_successful_page_count"], 0)
        self.assertEqual(report["corrected_boundary_observed_count"], 0)


if __name__ == "__main__":
    unittest.main()
