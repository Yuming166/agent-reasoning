import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_and_rebuild_ens_x_text_projection.py"
spec = importlib.util.spec_from_file_location("ens_text_projection", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def word(n):
    return int(n).to_bytes(32, "big")


def enc_string(value):
    b = value.encode()
    return "0x" + (word(32) + word(len(b)) + b + bytes((-len(b)) % 32)).hex()


def enc_string_pair(a, b):
    aa, bb = a.encode(), b.encode()
    tail_a = word(len(aa)) + aa + bytes((-len(aa)) % 32)
    tail_b = word(len(bb)) + bb + bytes((-len(bb)) % 32)
    return "0x" + (word(64) + word(64 + len(tail_a)) + tail_a + tail_b).hex()


class EnsTextProjectionTests(unittest.TestCase):
    def test_decodes_key_value_pair_strictly(self):
        self.assertEqual(mod.decode_abi_string_pair(enc_string_pair("com.twitter", "alice")),
                         ("com.twitter", "alice"))
        self.assertEqual(mod.decode_abi_string_pair(enc_string_pair("x", "https://x.com/a")),
                         ("x", "https://x.com/a"))

    def test_rejects_truncated_or_bad_offsets(self):
        with self.assertRaisesRegex(ValueError, "invalid length"):
            mod.decode_abi_string_pair("0x1234")
        raw = bytearray.fromhex(enc_string_pair("a", "b")[2:])
        raw[:32] = word(4096)
        with self.assertRaisesRegex(ValueError, "out of bounds"):
            mod.decode_abi_string_pair("0x" + raw.hex())

    def test_single_string_decoder_for_namechanged_data(self):
        self.assertEqual(mod.decode_abi_string(enc_string("alice.eth")), "alice.eth")

    def test_legacy_textchanged_one_string_is_key_only(self):
        key, value, status = mod.decode_textchanged_payload(
            "0xd8c9334b1a9c2f9da342a0a2b32629c1a229b6445dad78947f674b44444a7550",
            enc_string("com.twitter"),
        )
        self.assertEqual((key, value), ("com.twitter", None))
        self.assertEqual(status, "one_string_key_only_value_unavailable")

    def test_legacy_textchanged_two_strings_preserves_uncertain_value_shape(self):
        key, value, status = mod.decode_textchanged_payload(
            "0xd8c9334b1a9c2f9da342a0a2b32629c1a229b6445dad78947f674b44444a7550",
            enc_string_pair("com.twitter", "alice"),
        )
        self.assertEqual((key, value), ("com.twitter", "alice"))
        self.assertEqual(status, "two_strings_legacy_semantics_uncertain")

    def test_indexed_key_family_requires_two_payload_strings(self):
        topic = "0x448bc014f1536726cf8d54ff3d6481ed3cbc683c2591ca204274009afa09b1a1"
        self.assertEqual(mod.decode_textchanged_payload(topic, enc_string_pair("x", "alice"))[:2], ("x", "alice"))
        with self.assertRaises(ValueError):
            mod.decode_textchanged_payload(topic, enc_string("x"))

    def test_ascii_namehash_is_stable_and_rejects_non_ascii(self):
        self.assertEqual(mod._ascii_namehash("vitalik.eth"), mod._ascii_namehash("Vitalik.ETH"))
        self.assertEqual(mod._ascii_namehash("例子.eth"), "")


if __name__ == "__main__":
    unittest.main()
