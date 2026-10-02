from __future__ import annotations
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    pa = pq = None

from scripts.audit_ens_x_addrchanged_forward_nodes import build_report


@unittest.skipIf(pa is None, "install requirements-ens-source-audit.txt")
class AddrChangedForwardNodeAuditTests(unittest.TestCase):
    def test_forward_node_address_match_is_separate_from_reverse_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet = Path(tmp) / "addrchanged.parquet"
            pq.write_table(pa.table({
                "node": ["0xforward1", "0xforward2", "0xreverse1"],
                "address": ["0xaaa", "0xwrong", "0xbbb"],
                "block_timestamp": pa.array([
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 2, 1, tzinfo=timezone.utc),
                    datetime(2025, 3, 1, tzinfo=timezone.utc),
                ], type=pa.timestamp("us", tz="UTC")),
            }), parquet)
            audit = {"links": [
                {"address": "0xAAA", "x_user_id": "11", "source_pair_ids": ["P1"],
                 "forward_node_status": "namehash_validated",
                 "forward_ens_nodes_namehash_validated": ["0xForward1"], "reverse_node": "0xreverse1"},
                {"address": "0xBBB", "x_user_id": "22", "source_pair_ids": ["P2"],
                 "forward_node_status": "namehash_validated",
                 "forward_ens_nodes_namehash_validated": ["0xforward2"], "reverse_node": "0xreverse2"},
                {"address": "0xCCC", "x_user_id": "33", "source_pair_ids": ["P3"],
                 "forward_node_status": "unresolved",
                 "forward_ens_nodes_namehash_validated": [], "reverse_node": "0xreverse3"},
            ]}
            report = build_report(audit, parquet)
            meta = report["input_metadata"]
            self.assertEqual(meta["links_with_namehash_validated_forward_nodes"], 2)
            self.assertEqual(meta["forward_nodes_with_expected_address"], 1)
            self.assertEqual(meta["wallet_reverse_nodes_with_any_addrchanged_row"], 1)
            self.assertTrue(report["links"][0]["forward_snapshot_has_expected_address"])
            self.assertFalse(report["links"][1]["forward_snapshot_has_expected_address"])
            self.assertFalse(report["links"][2]["forward_snapshot_has_expected_address"])
            self.assertEqual(report["links"][0]["reverse_addrchanged_rows"][0]["node"], "0xreverse1")
            self.assertIn("does not prove historical validity", report["interpretation"])

    def test_empty_links_returns_empty_audit_not_all_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet = Path(tmp) / "empty.parquet"
            pq.write_table(pa.table({
                "node": pa.array([], type=pa.string()),
                "address": pa.array([], type=pa.string()),
                "block_timestamp": pa.array([], type=pa.timestamp("us", tz="UTC")),
            }), parquet)
            report = build_report({"links": []}, parquet)
            self.assertEqual(report["input_metadata"]["queried_node_union"], 0)
            self.assertEqual(report["input_metadata"]["addrchanged_rows_on_queried_nodes"], 0)
            self.assertEqual(report["links"], [])


if __name__ == "__main__":
    unittest.main()
