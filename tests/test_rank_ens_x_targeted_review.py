import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/rank_ens_x_targeted_review.py"
spec = importlib.util.spec_from_file_location("targeted_review", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TargetedReviewTests(unittest.TestCase):
    def test_uses_confirmed_id_edges_and_excludes_probability_sample(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profile = root / "profile.json"
            profile.write_text(json.dumps({"data": {"user": {"tweets": 900}}}))
            import hashlib
            digest = hashlib.sha256(profile.read_bytes()).hexdigest()
            candidates = [
                {"address": "0x" + "1" * 40, "x_user_id": "101", "handle_at_profile_audit": "a",
                 "reverse_ens_name": "a.eth", "review_stratum": "s", "manual_verdict": "pending",
                 "evidence_types": "exact_reverse_ens_name", "events_2026": "10",
                 "profile_raw_file": "profile.json", "profile_raw_sha256": digest},
                {"address": "0x" + "2" * 40, "x_user_id": "102", "handle_at_profile_audit": "b",
                 "reverse_ens_name": "b.eth", "review_stratum": "s", "manual_verdict": "pending",
                 "evidence_types": "full_wallet_address", "events_2026": "2",
                 "profile_raw_file": "missing.json", "profile_raw_sha256": ""},
            ]
            sampled = [{"address": candidates[0]["address"], "x_user_id": "101"}]
            confirmed = [{"x_user_id": "900"}]
            edges = [
                {"source_x_user_id": "900", "target_x_user_id": "102", "event_type": "mention", "created_at_utc": "2026-01-01T00:00:00Z"},
                {"source_x_user_id": "unconfirmed", "target_x_user_id": "102", "event_type": "mention", "created_at_utc": "2026-02-01T00:00:00Z"},
            ]
            rows, top, stats = mod.build_queue(candidates, sampled, confirmed, edges, root, 10)
            self.assertEqual(len(top), 1)
            self.assertEqual(top[0]["x_user_id"], "102")
            self.assertEqual(top[0]["distinct_confirmed_seed_sources"], 1)
            self.assertEqual(top[0]["confirmed_seed_inbound_edge_count"], 1)
            self.assertEqual(stats["representative_sample_rows_excluded"], 1)
            self.assertEqual(top[0]["timeline_collection_authorized"], "false")

    def test_existing_confirmed_id_is_not_ranked_as_new_text_account(self):
        row = {"address": "0x" + "3" * 40, "x_user_id": "900", "handle_at_profile_audit": "c",
               "reverse_ens_name": "c.eth", "review_stratum": "s", "manual_verdict": "pending",
               "evidence_types": "", "events_2026": "4", "profile_raw_file": "", "profile_raw_sha256": ""}
        rows, top, stats = mod.build_queue([row], [], [{"x_user_id": "900"}], [], Path("."), 5)
        self.assertEqual(top, [])
        self.assertEqual(rows[0]["queue_partition"], "existing_confirmed_x_id_multi_wallet_check_not_new_text")
        self.assertEqual(stats["remaining_already_confirmed_x_ids"], 1)


if __name__ == "__main__":
    unittest.main()
