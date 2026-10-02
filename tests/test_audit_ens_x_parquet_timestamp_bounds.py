import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_ens_x_parquet_timestamp_bounds.py"
spec = importlib.util.spec_from_file_location("ensx_timestamp_bounds", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TimestampBoundsTests(unittest.TestCase):
    def test_cutoff_requires_timezone(self):
        with self.assertRaises(ValueError):
            mod.parse_utc("2026-09-25T20:27:17")

    def test_counts_only_strictly_later_timestamps_and_ignores_nulls(self):
        cutoff = datetime(2026, 9, 25, 20, 27, 17, tzinfo=timezone.utc)
        report = mod.summarize_timestamps([
            datetime(2026, 9, 24, tzinfo=timezone.utc),
            cutoff,
            datetime(2026, 9, 26, tzinfo=timezone.utc),
            None,
        ], cutoff)
        self.assertEqual(report["timestamp_rows_non_null"], 3)
        self.assertEqual(report["rows_after_cutoff"], 1)
        self.assertEqual(report["first_after_cutoff_utc"], "2026-09-26T00:00:00+00:00")

    def test_empty_timestamps(self):
        report = mod.summarize_timestamps([], datetime.now(timezone.utc))
        self.assertEqual(report["rows_after_cutoff"], 0)
        self.assertIsNone(report["max_utc"])


if __name__ == "__main__":
    unittest.main()
