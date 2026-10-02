import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_ens_x_provisional_timeline_metrics.py"
spec = importlib.util.spec_from_file_location("timeline_metrics", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TimelineStatusDedupTests(unittest.TestCase):
    def test_repost_does_not_suppress_original_authored_post(self):
        owner = "795684794"
        tweet = "2096170487239909809"
        repost_key = module.status_dedup_key("406298400", tweet, True)
        authored_key = module.status_dedup_key(owner, tweet, False)
        self.assertNotEqual(repost_key, authored_key)

    def test_duplicate_same_owner_same_kind_is_deduplicated(self):
        self.assertEqual(
            module.status_dedup_key("42", "100", False),
            module.status_dedup_key("42", "100", False),
        )

    def test_same_post_reposted_by_two_owners_remains_two_observations(self):
        self.assertNotEqual(
            module.status_dedup_key("41", "100", True),
            module.status_dedup_key("42", "100", True),
        )


if __name__ == "__main__":
    unittest.main()
