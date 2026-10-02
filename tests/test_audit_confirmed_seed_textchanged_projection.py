import unittest

from scripts.audit_confirmed_seed_textchanged_projection import resolve_account_confirm_evidence


class ConfirmedSeedEvidenceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.seed = {
            "address": "0x" + "a" * 40,
            "x_user_id": "12345",
            "source_pair_ids": "P001;P002",
        }
        self.evidence = [
            {"pair_id": "P001", "address": self.seed["address"].upper().replace("0X", "0x"),
             "x_user_id": "12345", "verification_status": "account_confirms"},
            {"pair_id": "P002", "address": self.seed["address"],
             "x_user_id": "12345", "verification_status": "account_confirms"},
        ]

    def test_resolves_every_declared_pair_exactly(self):
        result = resolve_account_confirm_evidence(self.seed, self.evidence)
        self.assertEqual([r["pair_id"] for r in result], ["P001", "P002"])

    def test_missing_pair_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "expected exactly one"):
            resolve_account_confirm_evidence(self.seed, self.evidence[:1])

    def test_duplicate_pair_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "expected exactly one"):
            resolve_account_confirm_evidence(self.seed, self.evidence + [dict(self.evidence[0])])

    def test_wrong_status_fails_closed(self):
        evidence = [dict(x) for x in self.evidence]
        evidence[1]["verification_status"] = "ens_only"
        with self.assertRaisesRegex(ValueError, "not explicitly account_confirms"):
            resolve_account_confirm_evidence(self.seed, evidence)

    def test_wrong_address_fails_closed(self):
        evidence = [dict(x) for x in self.evidence]
        evidence[0]["address"] = "0x" + "b" * 40
        with self.assertRaisesRegex(ValueError, "address does not match"):
            resolve_account_confirm_evidence(self.seed, evidence)

    def test_wrong_x_id_fails_closed(self):
        evidence = [dict(x) for x in self.evidence]
        evidence[1]["x_user_id"] = "99999"
        with self.assertRaisesRegex(ValueError, "stable X ID does not match"):
            resolve_account_confirm_evidence(self.seed, evidence)

    def test_duplicate_declared_pair_id_fails_closed(self):
        seed = dict(self.seed, source_pair_ids="P001;P001")
        with self.assertRaisesRegex(ValueError, "duplicate source pair IDs"):
            resolve_account_confirm_evidence(seed, self.evidence)


if __name__ == "__main__":
    unittest.main()
