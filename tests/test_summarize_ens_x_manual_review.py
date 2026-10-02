import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/summarize_ens_x_manual_review.py"
spec = importlib.util.spec_from_file_location("review_summary", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(i, stratum, N, n, verdict="pending"):
    return {
        "address": "0x" + f"{i:040x}", "x_user_id": str(1000 + i),
        "sampling_stratum": stratum, "stratum_population_N": str(N),
        "stratum_sample_n": str(n), "design_weight": str(N / n),
        "manual_verdict": verdict, "reviewer": "", "reviewed_at_utc": "",
        "evidence_seen_at_utc": "", "x_profile_evidence_url": "",
        "evidence_quote_or_capture_id": "", "review_notes": "",
    }


class ManualReviewSummaryTests(unittest.TestCase):
    def test_pending_review_validates_allocation_but_emits_no_estimate(self):
        rows = [row(1, "A", 4, 2), row(2, "A", 4, 2), row(3, "B", 1, 1)]
        errors, groups = mod.validate(rows)
        self.assertEqual(errors, [])
        self.assertEqual({k: len(v) for k, v in groups.items()}, {"A": 2, "B": 1})
        self.assertEqual(sum(len(v) for v in groups.values()), 3)

    def test_design_weighted_estimate_and_categories_sum_to_population(self):
        rows = [row(1, "A", 4, 2, "account_confirms"),
                row(2, "A", 4, 2, "ens_only"),
                row(3, "B", 1, 1, "unverifiable")]
        groups = {"A": rows[:2], "B": rows[2:]}
        result = mod.estimate(groups)
        categories = result["categories"]
        self.assertEqual(result["population_N"], 5)
        self.assertAlmostEqual(categories["account_confirms"]["estimated_population_count"], 2.0)
        self.assertAlmostEqual(categories["account_confirms"]["estimated_population_rate"], 0.4)
        self.assertAlmostEqual(sum(x["estimated_population_count"] for x in categories.values()), 5.0)
        lo, hi = categories["account_confirms"]["normal_95pct_ci_rate"]
        self.assertLessEqual(lo, 0.4)
        self.assertGreaterEqual(hi, 0.4)

    def test_frozen_frame_rejects_omitted_rows_or_changed_design_fields(self):
        import hashlib, json
        rows = [row(1, "A", 4, 2), row(2, "A", 4, 2)]
        fields = ["address", "x_user_id", "sampling_stratum", "stratum_population_N", "stratum_sample_n", "design_weight"]
        digest = lambda r: hashlib.sha256(json.dumps({k: r.get(k, "") for k in fields}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        manifest = {"immutable_fields": fields, "row_count": 2,
                    "ordered_row_digests": [digest(r) for r in rows],
                    "strata": {"A": {"N_h": 4, "n_h": 2}}}
        self.assertEqual(mod.frozen_frame_errors(rows, manifest), [])
        self.assertTrue(any("row count" in e for e in mod.frozen_frame_errors(rows[:1], manifest)))
        changed = [dict(r) for r in rows]
        changed[0]["design_weight"] = "99"
        self.assertTrue(any("immutable" in e for e in mod.frozen_frame_errors(changed, manifest)))

    def test_missing_stable_user_id_is_rejected(self):
        rows = [row(1, "A", 2, 2, "ens_only"), row(2, "A", 2, 2, "ens_only")]
        rows[0]["x_user_id"] = "handle_only"
        errors, _ = mod.validate(rows)
        self.assertTrue(any("stable numeric ID" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
