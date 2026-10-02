import argparse
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_ens_x_full_frame_review_workbook import validate as validate_workbook
from scripts.build_ens_x_blinded_review_packet import (
    ARMS, COORDINATOR_DIR, PACKET_FIELDS, REVIEWER_DIR, generate, import_reviewed,
)

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "artifacts/ens_x_crosswalk/goal_audit_20260925/manual_review_workbook_231_v2.csv"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


class BlindedReviewPacketTests(unittest.TestCase):
    def test_packet_hides_candidate_and_sampling_metadata_and_keeps_arms_separate(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "packet"
            manifest = generate(WORKBOOK, out)
            self.assertEqual(231, manifest["rows"])
            self.assertEqual(60, manifest["arm_counts"]["stratified_probability_sample_60"])
            self.assertEqual(171, manifest["arm_counts"]["targeted_nonprobability_complement_171"])
            forbidden = {"review_arm", "sampling_stratum", "design_weight", "reverse_ens_name",
                         "automatic_matched_terms_not_adjudication", "candidate_events_2026"}
            all_rows = []
            for arm, filename in ARMS.items():
                fields, packet = rows(out / REVIEWER_DIR / filename)
                self.assertEqual(PACKET_FIELDS, fields)
                self.assertFalse(forbidden & set(fields))
                self.assertEqual(len(packet), 60 if arm == "stratified_probability_sample_60" else 171)
                all_rows.extend(packet)
            self.assertEqual(231, len({r["review_token"] for r in all_rows}))
            self.assertTrue((out / COORDINATOR_DIR / "coordinator_key.csv").exists())
            self.assertTrue((out / "DATA_MANAGER_IMPORT_GUIDE.md").is_file())
            self.assertEqual(manifest["files_sha256"]["DATA_MANAGER_IMPORT_GUIDE.md"],
                             hashlib.sha256((out / "DATA_MANAGER_IMPORT_GUIDE.md").read_bytes()).hexdigest())
            self.assertEqual(0, manifest["network_requests"])
            self.assertEqual(0, manifest["paid_queries_usd"])

    def test_reviewed_probability_row_round_trips_without_touching_candidate_fields(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "packet"
            manifest = generate(WORKBOOK, outdir)
            prob = outdir / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            fields, packet = rows(prob)
            packet[0].update({
                "manual_verdict": "account_confirms",
                "x_profile_evidence_url": "https://x.com/example/status/123",
                "evidence_quote_or_capture_id": "Synthetic test evidence excerpt",
                "evidence_verified_x_user_id": packet[0]["x_user_id"],
                "evidence_seen_at_utc": "2026-09-25T10:00:00Z",
                "reviewer": "unit-test", "reviewed_at_utc": "2026-09-25T10:01:00Z",
                "review_notes": "synthetic round-trip test",
            })
            with prob.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(packet)
            outbook = Path(td) / "reviewed.csv"
            result = import_reviewed(
                WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv", outdir / "manifest.json", [prob], outbook,
            )
            self.assertEqual(60, result["packets_imported"])
            _, merged = rows(outbook)
            token = packet[0]["review_token"]
            _, key = rows(outdir / COORDINATOR_DIR / "coordinator_key.csv")
            matched = next(k for k in key if k["review_token"] == token)
            target = next(r for r in merged if r["address"].lower() == matched["address"].lower())
            self.assertEqual("account_confirms", target["manual_verdict"])
            self.assertEqual("Synthetic test evidence excerpt", target["evidence_quote_or_capture_id"])
            self.assertEqual(packet[0]["x_user_id"], target["evidence_verified_x_user_id"])
            self.assertEqual(matched["candidate_events_2026"], target["candidate_events_2026"])
            self.assertEqual(0, result["paid_queries_usd"])

    def test_probability_then_targeted_import_resumes_from_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "packet"
            generate(WORKBOOK, outdir)
            prob = outdir / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            target = outdir / REVIEWER_DIR / ARMS["targeted_nonprobability_complement_171"]
            fields, packet = rows(prob)
            for row in packet:
                row.update({
                    "manual_verdict": "unverifiable", "reviewer": "synthetic-test",
                    "reviewed_at_utc": "2026-09-26T00:00:00Z", "review_notes": "synthetic fixture only",
                })
            with prob.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(packet)

            interim = Path(td) / "probability-reviewed.csv"
            import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv",
                            outdir / "manifest.json", [prob], interim)
            self.assertTrue(Path(str(interim) + ".receipt.json").exists())

            final = Path(td) / "both-arms-reviewed.csv"
            result = import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv",
                                     outdir / "manifest.json", [target], final,
                                     existing_workbook=interim)
            self.assertEqual(171, result["packets_imported"])
            _, merged = rows(final)
            self.assertEqual(60, sum(r["manual_verdict"] == "unverifiable" for r in merged))
            self.assertEqual(171, sum(r["manual_verdict"] == "pending" for r in merged))
            self.assertEqual(0, result["network_requests"])

    def test_resumed_probability_review_passes_frozen_workbook_validator(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "packet"
            generate(WORKBOOK, outdir)
            prob = outdir / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            target = outdir / REVIEWER_DIR / ARMS["targeted_nonprobability_complement_171"]
            fields, packet = rows(prob)
            for row in packet:
                row.update({"manual_verdict": "unverifiable", "reviewer": "synthetic-test",
                            "reviewed_at_utc": "2026-09-26T00:00:00Z", "review_notes": "fixture only"})
            with prob.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(packet)
            interim = Path(td) / "reviewed.csv"
            import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv",
                            outdir / "manifest.json", [prob], interim)
            root = ROOT / "artifacts/ens_x_crosswalk"
            audit = root / "goal_audit_20260925"
            decision = root / "expansion_decision_20260925"
            args = argparse.Namespace(
                workbook=interim,
                workbook_manifest=audit / "manual_review_workbook_231_v2_manifest.json",
                expected_workbook_manifest_sha256=hashlib.sha256(
                    (audit / "manual_review_workbook_231_v2_manifest.json").read_bytes()).hexdigest(),
                candidate=decision / "candidate_review_full_231.csv",
                sample=decision / "candidate_review_stratified_sample_60.csv",
                frozen_manifest=decision / "candidate_review_stratified_sample_60.frozen_manifest.json",
                queue=decision / "targeted_review_queue_20260925/manual_review_queue_171.csv",
                queue_report=decision / "targeted_review_queue_20260925/queue_report.json",
                out_json=Path(td) / "validation.json", sample_out=None,
            )
            report, _ = validate_workbook(args)
            self.assertTrue(report["probability_sample_complete"])
            self.assertTrue(report["weighted_estimate_allowed"])
            self.assertFalse(report["validation_errors"])
            final = Path(td) / "after-targeted.csv"
            import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv",
                            outdir / "manifest.json", [target], final, existing_workbook=interim)
            args.workbook = final
            report, _ = validate_workbook(args)
            self.assertTrue(report["probability_sample_complete"])
            self.assertEqual(171, report["verdict_counts_by_arm"]["targeted_nonprobability_complement_171"]["pending"])
            self.assertFalse(report["validation_errors"])

    def test_resume_rejects_tampered_interim_output(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "packet"
            generate(WORKBOOK, outdir)
            prob = outdir / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            first = Path(td) / "first.csv"
            import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv",
                            outdir / "manifest.json", [prob], first)
            first.write_text(first.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            target = outdir / REVIEWER_DIR / ARMS["targeted_nonprobability_complement_171"]
            with self.assertRaisesRegex(ValueError, "hash differs from import receipt"):
                import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv",
                                outdir / "manifest.json", [target], Path(td) / "second.csv",
                                existing_workbook=first)

    def test_manifest_or_identity_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "packet"
            generate(WORKBOOK, outdir)
            prob = outdir / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            fields, packet = rows(prob)
            packet[0]["address"] = "0x" + "f" * 40
            with prob.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(packet)
            with self.assertRaisesRegex(ValueError, "identity fields changed"):
                import_reviewed(WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv", outdir / "manifest.json",
                               [prob], Path(td) / "out.csv")

    def test_affirmative_verdict_with_unmatched_evidence_x_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "packet"
            generate(WORKBOOK, outdir)
            prob = outdir / REVIEWER_DIR / ARMS["stratified_probability_sample_60"]
            fields, packet = rows(prob)
            packet[0].update({
                "manual_verdict": "account_confirms",
                "x_profile_evidence_url": "https://x.com/example/status/123",
                "evidence_quote_or_capture_id": "Synthetic evidence",
                "evidence_verified_x_user_id": "999999",
            })
            with prob.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(packet)
            with self.assertRaisesRegex(ValueError, "evidence_verified_x_user_id"):
                import_reviewed(
                    WORKBOOK, outdir / COORDINATOR_DIR / "coordinator_key.csv", outdir / "manifest.json", [prob],
                    Path(td) / "rejected.csv",
                )


if __name__ == "__main__":
    unittest.main()
