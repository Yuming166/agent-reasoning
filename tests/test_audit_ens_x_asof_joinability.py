from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - environment-specific
    pa = pq = None

from scripts.audit_ens_x_asof_joinability import FILES, build_report, inspect, render_markdown


@unittest.skipIf(pa is None, "install requirements-ens-source-audit.txt")
class AsOfJoinabilityAuditTests(unittest.TestCase):
    def test_hashes_are_normalized_and_duplicate_rows_are_distinguished(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.parquet"
            pq.write_table(pa.table({
                "transaction_hash": ["0xAB", "0xab", None, " 0xCD "],
                "log_index": [0, 1, 2, 3],
            }), path)
            record, hashes, counts = inspect(path)
            self.assertEqual(hashes, {"0xab", "0xcd"})
            self.assertEqual(counts, {"0xab": 2, "0xcd": 1})
            self.assertEqual(record["transaction_hash_nonnull"], 3)
            self.assertEqual(record["transaction_hash_unique"], 2)
            self.assertEqual(record["duplicate_hash_rows"], 1)

    def test_report_computes_intersection_but_disclaims_event_level_join(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "artifacts/ens_x_crosswalk"
            base.mkdir(parents=True)
            for name in FILES:
                if name == "addrchanged_latest.parquet":
                    table = pa.table({"node": ["n1"], "address": ["a1"]})
                elif name == "reverse_evidence.parquet":
                    table = pa.table({"transaction_hash": ["0xAA", "0xAA", "0xBB"], "log_index": [1, 2, 3]})
                elif name == "textchanged_raw.parquet":
                    table = pa.table({"transaction_hash": ["0xaa", "0xaa", "0xCC"], "node": ["n1", "n2", "n3"]})
                elif name == "textchanged_raw_v2.parquet":
                    table = pa.table({"transaction_hash": ["0xaa"], "resolver": ["r1"]})
                elif name == "textchanged_twitter.parquet":
                    table = pa.table({"transaction_hash": ["0xCC"], "key": ["com.twitter"]})
                elif name == "textchanged_twitter_decoded_v2.parquet":
                    table = pa.table({"transaction_hash": ["0xCC"], "event_family": ["TextChanged"]})
                elif name == "textchanged_twitter_decoded_v3.parquet":
                    table = pa.table({"transaction_hash": ["0xCC"], "event_family": ["TextChanged"]})
                else:
                    table = pa.table({"address": ["a1"], "revnode": ["n1"]})
                pq.write_table(table, base / name)

            report = build_report(root)
            overlaps = {(row["a"], row["b"]): row["distinct_shared_transaction_hashes"]
                        for row in report["pairwise_hash_overlap"]}
            self.assertEqual(overlaps[("reverse_evidence.parquet", "textchanged_raw.parquet")], 1)
            reverse_raw = next(row for row in report["pairwise_hash_overlap"]
                               if (row["a"], row["b"]) == ("reverse_evidence.parquet", "textchanged_raw.parquet"))
            self.assertEqual(reverse_raw["shared_rows_in_a"], 2)
            self.assertEqual(reverse_raw["shared_rows_in_b"], 2)
            self.assertEqual(reverse_raw["naive_transaction_hash_join_pairs"], 4)
            self.assertIsNone(report["files"]["addrchanged_latest.parquet"]["transaction_hash_unique"])
            self.assertFalse(report["network_accessed"])
            self.assertEqual(report["paid_query_usd"], 0)
            text = render_markdown(report)
            self.assertIn("不能区分同一交易内的多个日志", text)
            self.assertIn("不证明源数据完整性", text)


if __name__ == "__main__":
    unittest.main()
