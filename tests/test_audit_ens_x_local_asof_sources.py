from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - dependency-specific skip
    pa = pq = None

from scripts.audit_ens_x_local_asof_sources import (
    CANONICAL_REPLAY_COLUMNS,
    DEFAULT_FILES,
    build_report,
    inspect_parquet,
)


@unittest.skipIf(pa is None, "install requirements-ens-source-audit.txt")
class LocalAsOfSourceAuditTests(unittest.TestCase):
    def test_default_inventory_includes_later_decoded_derivatives(self):
        self.assertIn("textchanged_twitter_decoded_v2.parquet", DEFAULT_FILES)
        self.assertIn("textchanged_twitter_decoded_v3.parquet", DEFAULT_FILES)

    def test_reports_schema_and_timestamp_without_claiming_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "artifacts/ens_x_crosswalk"
            source.mkdir(parents=True)
            parquet_path = source / "tiny.parquet"
            table = pa.table({
                "node": ["0x01", "0x02"],
                "block_timestamp": pa.array([
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 2, 1, tzinfo=timezone.utc),
                ], type=pa.timestamp("us", tz="UTC")),
            })
            pq.write_table(table, parquet_path)

            record = inspect_parquet(parquet_path, "tiny.parquet")
            report = build_report(root, ("tiny.parquet", "missing.parquet"))

            self.assertEqual(record["row_count"], 2)
            self.assertEqual(record["timestamp_min_utc"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(record["timestamp_max_utc"], "2026-02-01T00:00:00+00:00")
            self.assertEqual(len(record["sha256"]), 64)
            self.assertEqual(set(record["missing_canonical_replay_columns"]),
                             CANONICAL_REPLAY_COLUMNS - {"node", "block_timestamp"})
            self.assertFalse(report["schema_union_can_directly_satisfy_replay"])
            self.assertFalse(report["source_completeness_proven"])
            self.assertFalse(report["asof_replay_ready"])
            self.assertFalse(report["files"][1]["exists"])

    def test_naive_timestamps_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "naive.parquet"
            pq.write_table(pa.table({
                "block_timestamp": pa.array([datetime(2026, 1, 1)], type=pa.timestamp("us")),
            }), path)
            with self.assertRaisesRegex(ValueError, "naive timestamp"):
                inspect_parquet(path, "naive.parquet")


if __name__ == "__main__":
    unittest.main()
