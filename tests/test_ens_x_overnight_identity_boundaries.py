import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

review = load('ens_x_overnight_review_under_test', ROOT / 'scripts/ens_x_overnight_review.py')
package = load('ens_x_overnight_package_under_test', ROOT / 'scripts/ens_x_overnight_package.py')
candidate_collector = load('ens_x_candidate_collector_under_test', ROOT / 'scripts/ens_x_overnight_candidate_timelines.py')


class OvernightIdentityBoundaryTests(unittest.TestCase):
    def test_ai_result_never_overwrites_human_fields(self):
        source = {
            'address': '0x' + '1' * 40, 'x_user_id': '123',
            'manual_verdict': 'pending', 'reviewer': '', 'reviewed_at_utc': '',
            'evidence_seen_at_utc': '', 'x_profile_evidence_url': '',
            'evidence_quote_or_capture_id': '', 'review_notes': '',
        }
        result = {
            'address': source['address'], 'x_user_id': '123', 'verdict': 'account_confirms',
            'review_method': 'AI', 'reviewer': 'AI:model', 'reviewed_at_utc': '2026-01-01T00:00:00Z',
            'evidence_quote': 'claimed address', 'evidence_source_field': 'bio',
            'rationale': 'model output', 'quote_verified_in_archived_content': True,
        }
        row = review.build_ai_review_rows([source], [result])[0]
        for key, value in source.items():
            self.assertEqual(row[key], value, key)
        self.assertEqual(row['ai_verdict'], 'account_confirms')
        self.assertEqual(row['eligible_as_confirmed_crosswalk'], 'false')
        lead = review.build_ai_review_leads([row])[0]
        self.assertEqual(lead['human_review_status'], 'pending')
        self.assertEqual(lead['eligible_as_confirmed_crosswalk'], 'false')

    def test_package_crosswalk_contains_only_supplied_human_seeds(self):
        seed = [{'address': '0x' + '2' * 40, 'x_user_id': '456', 'handle_at_verification': 'seed'}]
        rows = package.confirmed_seed_crosswalk(seed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['evidence_tier'], 'prior_account_side_verified')
        self.assertEqual({r['x_user_id'] for r in rows}, {'456'})

    def test_provisional_candidate_collector_fails_before_network(self):
        with patch.object(candidate_collector, 'collect_account', side_effect=AssertionError('network path reached')):
            with self.assertRaisesRegex(RuntimeError, 'collection disabled'):
                candidate_collector.main()

    def test_ai_candidate_is_lead_not_link(self):
        candidate = [{'address': '0x' + '3' * 40, 'x_user_id': '789', 'ai_verdict': 'account_confirms'}]
        lead = package.ai_review_leads(candidate)[0]
        self.assertEqual(lead['ai_verdict_lead'], 'account_confirms')
        self.assertEqual(lead['human_review_status'], 'pending')
        self.assertEqual(lead['eligible_as_confirmed_crosswalk'], 'false')
        self.assertNotIn('evidence_tier', lead)


if __name__ == '__main__':
    unittest.main()
