import importlib.util
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/replay_ens_x_asof.py"
spec = importlib.util.spec_from_file_location("asof", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ADDR = "0x" + "1" * 40
RESOLVER = "0x" + "2" * 40
NODE = "0x787192fc5378cc32aa956ddfdedbf26b24e8d78e40109add0eea2c1a012c3dec"  # namehash(alice.eth)
REVERSE_NODE = "0x19e798729483c8dd1c93223c8c568fac7f64fc6d6ed33b20f51cae2fbbb65f4d"


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def source_provenance(audit_path="coverage_audit.json", audit_sha=None):
    return {
        "provider": "test-provider", "dataset": "test-chain", "table": "test.logs",
        "extraction_job_id": "job-test",
        "query_sha256": "1" * 64, "source_schema_sha256": "2" * 64,
        "scope_sha256": "3" * 64,
        "independent_coverage_audit": {
            "path": audit_path, "sha256": audit_sha or "4" * 64,
        },
    }


def complete_manifest():
    return {
        "complete": True, "total_ordering_complete": True, "decoding_validated": True,
        "event_types_complete": sorted(mod.REQUIRED_EVENT_TYPES), "source_sha256": "a" * 64,
        "coverage_start_utc": "2020-01-01T00:00:00Z", "coverage_end_utc": "2026-12-31T00:00:00Z",
        "source_provenance": source_provenance(),
    }


def ev(i, typ, ts, **kwargs):
    base = {
        "order": (1, 0, i), "timestamp": mod.parse_utc(ts, "test"),
        "type": typ, "subject": NODE, "address": "", "resolver": "",
        "key": "", "value": "", "emitter": "", "coin_type": "",
    }
    base.update(kwargs)
    return base


def link(**kwargs):
    row = {
        "address": ADDR, "ens_node": NODE, "handle": "alice",
        "x_user_id": "123456", "account_evidence_valid_from_utc": "2025-01-01T00:00:00Z",
        "account_evidence_valid_to_utc": "", "account_evidence_uri": "https://x.com/i/status/1",
        "account_evidence_type": "authored_statement",
    }
    row.update(kwargs)
    return row


class AsOfReplayTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            ev(1, "resolver_changed", "2025-01-01T00:00:00Z", subject=NODE, resolver=RESOLVER),
            ev(2, "resolver_changed", "2025-01-01T00:00:00Z", subject=REVERSE_NODE, resolver=RESOLVER),
            ev(3, "addr_changed", "2025-01-01T00:00:01Z", subject=NODE, address=ADDR, emitter=RESOLVER),
            ev(4, "reverse_name_changed", "2025-01-01T00:00:02Z", subject=REVERSE_NODE,
               value="alice.eth", emitter=RESOLVER),
            ev(5, "text_changed", "2025-01-01T00:00:03Z", subject=NODE,
               key="com.twitter", value="alice", emitter=RESOLVER),
        ]

    def test_bidirectional_state_and_account_evidence_before_cutoff_validate(self):
        out = mod.replay(self.events, [link()], [datetime(2025, 2, 1, tzinfo=timezone.utc)])
        self.assertEqual(out[0]["historical_asof_status"], "valid")
        self.assertEqual(out[0]["failure_reasons"], "")
        self.assertEqual(out[0]["reverse_node"], REVERSE_NODE)
        self.assertEqual(out[0]["reverse_name_at_cutoff"], "alice.eth")

    def test_same_timestamp_event_is_excluded_by_strict_cutoff(self):
        out = mod.replay(self.events, [link()], [datetime(2025, 1, 1, 0, 0, 3, tzinfo=timezone.utc)])
        self.assertEqual(out[0]["historical_asof_status"], "not_validated")
        self.assertIn("twitter_text_record_mismatch", out[0]["failure_reasons"])

    def test_future_account_evidence_cannot_validate_earlier_cutoff(self):
        out = mod.replay(self.events, [link(account_evidence_valid_from_utc="2025-03-01T00:00:00Z")],
                         [datetime(2025, 2, 1, tzinfo=timezone.utc)])
        self.assertIn("account_evidence_not_valid_before_cutoff", out[0]["failure_reasons"])

    def test_mismatched_reverse_name_or_forward_state_is_not_valid(self):
        bad_events = [dict(e) for e in self.events]
        bad_events[3]["value"] = "bob.eth"
        out = mod.replay(bad_events, [link(address="0x" + "3" * 40)],
                         [datetime(2025, 2, 1, tzinfo=timezone.utc)])
        self.assertIn("forward_address_mismatch", out[0]["failure_reasons"])
        self.assertIn("reverse_record_mismatch", out[0]["failure_reasons"])

    def test_name_changed_under_wrong_reverse_node_does_not_validate(self):
        bad_events = [dict(e) for e in self.events]
        wrong_reverse_node = "0x" + "a" * 64
        bad_events[1]["subject"] = wrong_reverse_node
        bad_events[3]["subject"] = wrong_reverse_node
        out = mod.replay(bad_events, [link()], [datetime(2025, 2, 1, tzinfo=timezone.utc)])
        self.assertIn("reverse_record_mismatch", out[0]["failure_reasons"])
        self.assertIn("reverse_resolver_not_set", out[0]["failure_reasons"])

    def test_reverse_name_event_from_inactive_resolver_fails_closed(self):
        bad_events = [dict(e) for e in self.events]
        bad_events[3]["emitter"] = "0x" + "4" * 40
        with self.assertRaisesRegex(ValueError, "NameChanged emitter is not active resolver"):
            mod.replay(bad_events, [link()], [datetime(2025, 2, 1, tzinfo=timezone.utc)])

    def test_text_event_from_inactive_resolver_fails_closed(self):
        bad_events = [dict(e) for e in self.events]
        bad_events[-1]["emitter"] = "0x" + "4" * 40
        with self.assertRaisesRegex(ValueError, "TextChanged emitter is not active resolver"):
            mod.replay(bad_events, [link()], [datetime(2025, 2, 1, tzinfo=timezone.utc)])

    def test_addr_event_from_inactive_resolver_fails_closed(self):
        bad_events = [dict(e) for e in self.events]
        bad_events[2]["emitter"] = "0x" + "4" * 40
        with self.assertRaisesRegex(ValueError, "AddrChanged emitter is not active resolver"):
            mod.replay(bad_events, [link()], [datetime(2025, 2, 1, tzinfo=timezone.utc)])

    def test_namehash_known_vector_uses_ensip15_and_rejects_invalid_names(self):
        self.assertEqual(mod.ens_namehash("eth"),
                         "0x93cdeb708b7545dc668eb9280176169d1c33cfd8ed6f04690a0bcc88a93fc4ae")
        self.assertEqual(mod.reverse_node_for_address(ADDR), REVERSE_NODE)
        self.assertEqual(mod.normalize_ens_name("Vitalik.ETH"), "vitalik.eth")
        self.assertEqual(mod.ens_namehash("2⃣2⃣.eth"),
                         "0x82a6569593d5440f75f35bbbc137bbff0ad406820621d82a7a2a2b1af3b68db4")
        with self.assertRaisesRegex(ValueError, "ENSIP-15 rejected"):
            mod.ens_namehash("bad..eth")

    def test_manifest_requires_all_complete_event_families_and_order(self):
        cutoff = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        manifest = complete_manifest()
        mod.validate_manifest(manifest, cutoff)
        manifest["event_types_complete"].remove("reverse_name_changed")
        with self.assertRaisesRegex(ValueError, "missing complete event types"):
            mod.validate_manifest(manifest, cutoff)

    def test_manifest_requires_multicoin_address_changed_coverage(self):
        cutoff = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        manifest = complete_manifest()
        manifest["event_types_complete"].remove("address_changed")
        with self.assertRaisesRegex(ValueError, "missing complete event types"):
            mod.validate_manifest(manifest, cutoff)

    def test_address_changed_requires_coin_type_60_and_normalized_address(self):
        base = {"block_number": "1", "transaction_index": "0", "log_index": "1",
                "block_timestamp_utc": "2025-01-01T00:00:00Z", "event_type": "address_changed",
                "node": NODE, "address": ADDR, "resolver": "", "key": "", "value": "",
                "emitter": RESOLVER, "coin_type": "60"}
        normalized = mod.normalize_events([base], {"event_count": 1})
        self.assertEqual(normalized[0]["coin_type"], "60")
        self.assertEqual(normalized[0]["address"], ADDR)
        for invalid in ("", "0", "61", "not-an-int"):
            bad = dict(base, coin_type=invalid)
            with self.assertRaisesRegex(ValueError, "coin_type"):
                mod.normalize_events([bad], {"event_count": 1})
        bad = dict(base, address="0x1234")
        with self.assertRaisesRegex(ValueError, "invalid 20-byte address"):
            mod.normalize_events([bad], {"event_count": 1})

    def test_address_changed_applies_only_from_active_resolver(self):
        state = {"resolver": {NODE: RESOLVER}, "address": {}}
        event = {"type": "address_changed", "subject": NODE, "order": (1, 0, 1),
                 "address": ADDR, "emitter": RESOLVER, "coin_type": "60"}
        mod._apply_event(event, state)
        self.assertEqual(state["address"][NODE], ADDR)
        event["emitter"] = "0x" + "4" * 40
        with self.assertRaisesRegex(ValueError, "AddressChanged emitter is not active resolver"):
            mod._apply_event(event, state)

    def test_manifest_requires_traceable_source_and_independent_audit_reference(self):
        cutoff = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        manifest = complete_manifest()
        del manifest["source_provenance"]
        with self.assertRaisesRegex(ValueError, "missing source_provenance"):
            mod.validate_manifest(manifest, cutoff)
        manifest = complete_manifest()
        manifest["source_provenance"]["query_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "invalid query_sha256"):
            mod.validate_manifest(manifest, cutoff)

    def test_independent_coverage_audit_is_hash_bound_and_checks_all_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            events.write_text("event bytes\n", encoding="utf-8")
            audit = {
                "schema": "ens_asof_independent_coverage_audit_v1", "result": "pass",
                "event_csv_sha256": mod.sha256(events), "scope_sha256": "3" * 64,
                "coverage_start_utc": "2020-01-01T00:00:00Z",
                "coverage_end_utc": "2026-12-31T00:00:00Z",
                "event_types_verified": sorted(mod.REQUIRED_EVENT_TYPES),
                "checks": {name: True for name in (
                    "scope_complete", "canonical_order", "decoding",
                    "resolver_emitter_consistency", "independent_source_sample",
                )},
                "independent_source_comparison": {
                    "method": "fixture comparison", "sample_n": 2, "mismatch_n": 0,
                },
            }
            audit_path = root / "coverage_audit.json"
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            manifest_path = root / "event_manifest.json"
            manifest = complete_manifest()
            manifest["source_sha256"] = mod.sha256(events)
            manifest["source_provenance"] = source_provenance(
                audit_path.name, mod.sha256(audit_path)
            )
            cutoff = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
            mod.validate_manifest(manifest, cutoff)
            verified = mod.validate_independent_coverage_audit(manifest, manifest_path, events)
            self.assertEqual(verified["sha256"], mod.sha256(audit_path))

            audit["event_types_verified"].remove("text_changed")
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            manifest["source_provenance"]["independent_coverage_audit"]["sha256"] = mod.sha256(audit_path)
            with self.assertRaisesRegex(ValueError, "does not verify every required"):
                mod.validate_independent_coverage_audit(manifest, manifest_path, events)

    def test_complete_candidate_extract_may_have_zero_rows_for_a_family(self):
        # A complete, candidate-scoped query can legitimately return no
        # TextChanged rows. Completeness comes from the manifest/query
        # contract, not from requiring at least one observed event per family.
        cutoff = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        manifest = {
            "complete": True, "total_ordering_complete": True,
            "decoding_validated": True,
            "event_types_complete": sorted(mod.REQUIRED_EVENT_TYPES),
            "source_sha256": "abc",
            "coverage_start_utc": "2020-01-01T00:00:00Z",
            "coverage_end_utc": "2026-12-31T00:00:00Z",
            "source_provenance": source_provenance(),
            "event_count": 3,
        }
        mod.validate_manifest(manifest, cutoff)
        rows = [
            {"block_number": "1", "transaction_index": "0", "log_index": str(i),
             "block_timestamp_utc": f"2025-01-01T00:00:0{i}Z", "event_type": typ,
             "node": NODE, "address": ADDR if typ == "addr_changed" else "",
             "resolver": RESOLVER if typ == "resolver_changed" else "",
             "key": "", "value": "alice.eth" if typ == "reverse_name_changed" else "",
             "emitter": RESOLVER if typ == "reverse_name_changed" else "", "coin_type": ""}
            for i, typ in enumerate(
                ("resolver_changed", "addr_changed", "reverse_name_changed"), start=1
            )
        ]
        normalized = mod.normalize_events(rows, manifest)
        self.assertEqual(len(normalized), 3)
        self.assertNotIn("text_changed", {event["type"] for event in normalized})

    def test_zero_row_event_csv_still_requires_canonical_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            path.write_text("wrong_header\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CSV missing columns"):
                mod.read_csv(path, required_columns=mod.REQUIRED_EVENT_COLUMNS)

            with path.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle).writerow(sorted(mod.REQUIRED_EVENT_COLUMNS))
            self.assertEqual(
                mod.read_csv(path, required_columns=mod.REQUIRED_EVENT_COLUMNS), []
            )

    def test_events_require_strict_chain_order_and_nondecreasing_time(self):
        rows = []
        for i, typ in [(2, "resolver_changed"), (1, "addr_changed"), (3, "reverse_name_changed"), (4, "text_changed")]:
            rows.append({"block_number": "1", "transaction_index": "0", "log_index": str(i),
                         "block_timestamp_utc": "2025-01-01T00:00:00Z", "event_type": typ,
                         "node": NODE, "address": ADDR if typ == "addr_changed" else "",
                         "resolver": RESOLVER if typ == "resolver_changed" else "",
                         "key": "com.twitter" if typ == "text_changed" else "",
                         "value": "alice.eth" if typ == "reverse_name_changed" else ("alice" if typ == "text_changed" else ""),
                         "emitter": RESOLVER if typ in {"text_changed", "reverse_name_changed"} else "",
                         "coin_type": ""})
        manifest = {"event_count": 4}
        with self.assertRaisesRegex(ValueError, "not strictly ordered"):
            mod.normalize_events(rows, manifest)

        # Restore ordering but make chain-ordered timestamps run backwards.
        rows.reverse()
        for i, row in enumerate(rows):
            row["log_index"] = str(i + 1)
            row["block_timestamp_utc"] = f"2025-01-01T00:00:0{3-i}Z"
        with self.assertRaisesRegex(ValueError, "timestamps decrease"):
            mod.normalize_events(rows, manifest)

    def test_legacy_address_to_node_reverse_event_is_rejected(self):
        row = {"block_number": "1", "transaction_index": "0", "log_index": "1",
               "block_timestamp_utc": "2025-01-01T00:00:00Z", "event_type": "reverse_changed",
               "node": NODE, "address": ADDR, "resolver": "", "key": "", "value": NODE, "emitter": "", "coin_type": ""}
        with self.assertRaisesRegex(ValueError, "unsupported event_type"):
            mod.normalize_events([row], {"event_count": 1})


if __name__ == "__main__":
    unittest.main()
