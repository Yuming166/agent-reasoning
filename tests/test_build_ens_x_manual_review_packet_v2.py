import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_ens_x_manual_review_packet_v2.py"
spec = importlib.util.spec_from_file_location("review_packet_v2", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def rows(n=60):
    workbook, packet = [], []
    for i in range(n):
        uid = str(1000 + i)
        address = f"0x{i:040x}"
        handle = f"user{i}"
        keydata = {"address": address, "x_user_id": uid}
        workbook.append({
            **keydata, "review_arm": mod.PROBABILITY_ARM, "review_order": str(i + 1),
            "handle_at_profile_audit": handle, "sampling_stratum": f"stratum{i}",
            "design_weight": "2.0", "stratum_population_N": "2", "stratum_sample_n": "1",
            "inclusion_probability": "0.5", "sampling_seed": "42", "manual_verdict": "pending",
        })
        packet.append({
            **keydata, "captured_x_user_id": uid, "captured_handle": handle,
            "stable_id_match": "true", "raw_profile_sha256_expected": "abc",
            "raw_profile_sha256_verified": "abc", "sampling_stratum": f"stratum{i}",
            "design_weight": "2.0",
        })
    return workbook, packet


class ReviewPacketV2Tests(unittest.TestCase):
    def test_one_to_one_join_keeps_pending_and_marks_capture_non_verdict(self):
        workbook, packet = rows()
        out = mod.join_review_rows(workbook, packet, "authoritative.csv")
        self.assertEqual(len(out), 60)
        self.assertTrue(all(r["captured_profile_is_identity_verdict"] == "false" for r in out))
        self.assertTrue(all(r["authoritative_manual_verdict"] == "pending" for r in out))
        self.assertEqual(out[0]["authoritative_workbook_row_order"], "1")

    def test_stable_id_mismatch_fails_closed(self):
        workbook, packet = rows()
        packet[0]["captured_x_user_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "stable X ID mismatch"):
            mod.join_review_rows(workbook, packet, "authoritative.csv")

    def test_extra_targeted_row_in_packet_fails_closed(self):
        workbook, packet = rows()
        packet.append(dict(packet[0], address="0xffff"))
        with self.assertRaisesRegex(ValueError, "outside frozen probability sample"):
            mod.join_review_rows(workbook, packet, "authoritative.csv")


if __name__ == "__main__":
    unittest.main()
