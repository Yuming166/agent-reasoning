import json
import unittest
from pathlib import Path
from scripts.audit_ens_x_review_only_forward_nodes import audit

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "artifacts/ens_x_crosswalk/current_goal_audit"

class ReviewOnlyForwardNodeTests(unittest.TestCase):
    def test_local_diagnostics_never_promote_and_expose_snapshot_disagreement(self):
        report = audit(
            PROJECT,
            BASE / "confirmed_seed_asof_query_scope_ensip15_reviewnodes_20260926.json",
            BASE / "unresolved_seed_reverse_namechanged_20260926.json",
        )
        self.assertEqual(report["candidate_node_count"], 3)
        self.assertEqual(report["network_requests"], 0)
        self.assertEqual(report["bigquery_queries"], 0)
        self.assertEqual(report["mapping_adjudications_changed"], 0)
        by_name = {r["reverse_name"]: r for r in report["candidates"]}
        self.assertEqual(by_name["hoteth.eth"]["latest_addrchanged_snapshot"]["address"],
                         "0xeeab7e7c0bff32aecba1c497ea4e7a96c4fde393")
        self.assertEqual(by_name["enschile.eth"]["latest_addrchanged_snapshot"]["address"],
                         "0x9a75ed8e1e592c2e2b0d3eddee8404dcf326a8c5")
        self.assertNotEqual(by_name["wonjae.eth"]["latest_addrchanged_snapshot"]["address"],
                            by_name["wonjae.eth"]["candidate_wallets"][0])
        self.assertTrue(all(r["historical_asof_validated"] is False for r in report["candidates"]))

if __name__ == "__main__":
    unittest.main()
