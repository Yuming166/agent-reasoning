#!/usr/bin/env python3
"""Prepare a two-pass, blinded semantic-gate worksheet from frozen hypotheses.

The script is deterministic and outcome-blind. It reads only the frozen full
hypothesis panel, selects cases by a fixed hash rule, and writes Pass A
(text-only) and Pass B (structured-consequence/evidence review) worksheets.
Pass B must not be shown to annotators until Pass A is locked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RES = ROOT / "research/decision_state/results"
PANEL = RES / "hypothesis_panel_full.jsonl"
PANEL_MANIFEST = RES / "hypothesis_panel_full.manifest.json"
TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
CLASSES = {"up", "same", "down"}
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
SAMPLE_N = 100
DOUBLE_N = 20
SAMPLE_SALT = "|semantic-gate-v1|"  # retain the already-selected exploratory sample
DOUBLE_SALT = "|semantic-gate-v2-double|"
ROW_SALT = "|semantic-gate-v2-row|"
PERM_SALT = "|semantic-gate-v2-permutation|"
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_full_panel() -> dict[str, dict]:
    records: dict[str, dict] = {}
    with PANEL.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("variant") != "full":
                continue
            case_id = str(record["case_id"])
            if case_id in records:
                raise ValueError(f"duplicate full case: {case_id}")
            parsed = record.get("parsed") if isinstance(record.get("parsed"), dict) else {}
            hypotheses = parsed.get("hypotheses", []) if isinstance(parsed.get("hypotheses"), list) else []
            valid = []
            for slot, hypothesis in enumerate(hypotheses[:3], start=1):
                if not isinstance(hypothesis, dict):
                    continue
                text = str(hypothesis.get("text", "")).strip()
                consequences = hypothesis.get("consequences")
                if not text or not isinstance(consequences, dict):
                    continue
                if any(consequences.get(target) not in CLASSES for target in TARGETS):
                    continue
                evidence = hypothesis.get("evidence_ids", [])
                if not isinstance(evidence, list):
                    evidence = []
                valid.append({
                    "slot": f"H{slot}",
                    "text": text,
                    "horizon_days": hypothesis.get("horizon_days"),
                    "evidence_labels": sorted(str(x) for x in evidence),
                    "consequences": {target: consequences[target] for target in TARGETS},
                })
            records[case_id] = {"hypotheses": valid}
    expected = int(json.loads(PANEL_MANIFEST.read_text(encoding="utf-8"))["n_cases"])
    if len(records) != expected:
        raise ValueError(f"expected {expected} full cases, found {len(records)}")
    return records


def make_rows(records: dict[str, dict]) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    ranked = sorted((sha256_text(case_id + SAMPLE_SALT), case_id) for case_id in records)
    selected = ranked[:SAMPLE_N]
    selected_hashes = [hsh for hsh, _ in selected]
    double_ranked = sorted(
        (sha256_text(case_id + DOUBLE_SALT), case_id)
        for _, case_id in selected
    )
    double_cases = {case_id for _, case_id in double_ranked[:DOUBLE_N]}

    rows = []
    internal_map = []
    for case_hash, case_id in selected:
        for hypothesis in records[case_id]["hypotheses"]:
            row_handle = "SGV2-" + sha256_text(case_hash + "|" + hypothesis["slot"] + ROW_SALT)[:32]
            row = {
                "row_handle": row_handle,
                "hypothesis_text": hypothesis["text"],
                "horizon_days": hypothesis["horizon_days"],
                "evidence_labels": ";".join(hypothesis["evidence_labels"]),
                **{f"recorded_{target}": hypothesis["consequences"][target] for target in TARGETS},
            }
            rows.append(row)
            internal_map.append({
                "row_handle": row_handle,
                "case_id": case_id,
                "case_hash": case_hash,
                "hypothesis_slot": hypothesis["slot"],
                "double_code_case": case_id in double_cases,
            })
    if len({row["row_handle"] for row in rows}) != len(rows):
        raise ValueError("row handle collision")
    order = sorted(rows, key=lambda row: sha256_text(row["row_handle"] + PERM_SALT))
    double_handles = [row["row_handle"] for row in order if next(m for m in internal_map if m["row_handle"] == row["row_handle"])["double_code_case"]]
    return order, internal_map, selected_hashes


def make_pass_a(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "row_handle": row["row_handle"],
            "hypothesis_text": row["hypothesis_text"],
            "pass_a_commitment": "",
            "pass_a_operationality": "",
            "pass_a_text_span": "",
            "pass_a_notes": "",
        }
        for row in rows
    ])


def make_pass_b(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "row_handle": row["row_handle"],
            "hypothesis_text": row["hypothesis_text"],
            "recorded_activity": row["recorded_activity"],
            "recorded_active_days": row["recorded_active_days"],
            "recorded_counterparty_breadth": row["recorded_counterparty_breadth"],
            "recorded_new_counterparties": row["recorded_new_counterparties"],
            "horizon_days": row["horizon_days"],
            "evidence_labels": row["evidence_labels"],
            "alignment_activity": "",
            "alignment_active_days": "",
            "alignment_counterparty_breadth": "",
            "alignment_new_counterparties": "",
            "alignment_span_activity": "",
            "alignment_span_active_days": "",
            "alignment_span_counterparty_breadth": "",
            "alignment_span_new_counterparties": "",
            "horizon_compatibility": "",
            **{f"evidence_relevance_{label}": "" for label in EVIDENCE_GROUPS},
            "pass_b_notes": "",
        }
        for row in rows
    ])


def audit_blinding(frame: pd.DataFrame, pass_name: str) -> dict:
    forbidden_column_tokens = [
        "case_id", "anchor_wallet", "wallet", "cutoff", "split", "activity_bin", "sample_rank",
        "probability", "confidence", "model", "loss", "log_loss", "delta", "success", "failure",
        "outcome", "future", "august", "july", "y_", "f_",
    ]
    def forbidden_column(column: str) -> bool:
        name = column.lower()
        for token in forbidden_column_tokens:
            if token in {"y_", "f_"}:
                if name.startswith(token):
                    return True
            elif token in name:
                return True
        return False

    bad_columns = [column for column in frame.columns if forbidden_column(column)]
    raw_id_hits = []
    for column in frame.columns:
        for value in frame[column].fillna("").astype(str):
            if WALLET_RE.search(value):
                raw_id_hits.append(column)
                break
    return {
        "pass": pass_name,
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "duplicate_row_handles": int(frame["row_handle"].duplicated().sum()),
        "bad_column_names": bad_columns,
        "raw_wallet_like_values": sorted(set(raw_id_hits)),
        "pass_a_hidden_until_locked": pass_name == "pass_b",
        "blinding_ok": bool(not bad_columns and not raw_id_hits and frame["row_handle"].notna().all()),
    }


def write_protocol(out: Path, manifest: dict) -> None:
    text = f"""# Semantic Gate V2 — two-pass blind human audit

**Status:** deterministic exploratory preparation only. This is not an Astra6
result, preregistration, official claim, or experiment-registry entry.

## Fixed sample

- Source: frozen `full` variant of `hypothesis_panel_full.jsonl`.
- Source cases: {manifest['source_full_cases']}.
- Selected cases: {manifest['sample_n_cases']}.
- Case selection: `SHA256(UTF-8(case_id + \"|semantic-gate-v1|\"))`, sorted by
  `(hash, case_id)`, first {SAMPLE_N}; no replacement after annotation starts.
- Double-code cases: {manifest['double_code_cases']}, selected independently
  from the fixed sample using `SHA256(UTF-8(case_id + \"|semantic-gate-v2-double|\"))`.
- Worksheet rows: {manifest['worksheet_rows']} valid hypotheses. The actual row
  count is recorded from the source and is not assumed to be 3 per case.
- Row order: opaque deterministic permutation; rows are not grouped by case,
  wallet, date, split, evidence label, or outcome.

## Pass A — text-only commitment

Show only `row_handle` and `hypothesis_text`. Do not show consequence labels,
horizon, evidence labels, probabilities, ranks, confidence, model metadata,
wallets, dates, splits, outcomes, F, Delta, losses, or August membership.
Pass A must be submitted and hashed before Pass B is shown.

Allowed Pass A labels:

- `explicit`: the proposition commits to an operational behavioral claim.
- `hedged`: the proposition makes a qualified but still operational claim.
- `generic`: the text is a broad story without a checkable operational commitment.
- `none`: no behavioral commitment is present.
- `unclear`: insufficient text to decide.

`pass_a_operationality` uses `operational`, `non_operational`, or `unclear`.
The text span must be exact for non-`unclear` labels.

## Pass B — structured alignment and evidence compatibility

Only after Pass A is locked, reveal the recorded consequence categories, the
separate horizon field, and evidence labels. These are model-produced structured
outputs, not future ground truth.

For each dimension use exactly one of:

- `entailed`: the proposition operationally supports the recorded direction;
- `unsupported`: the text does not support the direction, but does not clearly
  state the opposite;
- `contradicted`: the text explicitly or operationally predicts the opposite;
- `unclear`: cannot decide from the text and supplied metadata.

Use `compatible`, `incompatible`, or `unclear` for the separate horizon field.
For each of `E_SELF`, `E_MARKET`, `E_COVERAGE`, and `E_PLACEBO`, use
`relevant`, `irrelevant`, `unclear`, or `not_applicable`; use
`not_applicable` when that label is not present in the recorded evidence list.
Record an exact text span for every non-`unclear` alignment judgment. Do not infer
owner identity, true belief, emotion, psychology, causal intent, or social
exposure.

## Reliability gate

Independently double-code all rows belonging to the fixed {manifest['double_code_cases']}-case
roster. Compute pooled and per-dimension exact agreement and nominal Cohen's
kappa, treating `unclear` as a real category. Also report Gwet AC1 as a
prevalence-sensitive diagnostic. Resample whole cases—not individual rows—for
confidence intervals. Technical missingness above 5%, pooled agreement below
0.80, pooled kappa below 0.60, or any dimension below 0.70 agreement / 0.40
kappa fails the reliability gate. A failed pre-adjudication reliability result
cannot be repaired by adjudication.

For the descriptive semantic gate, predeclare: `entailed` alignment >= 80% of
applicable dimension cells, case-clustered 95% lower bound >= 70%, and
`contradicted` <= 5%. Passing would not establish forecasting effectiveness or
causal validity.

## Unblinding rule

Keep F, Delta, model losses, split/date, wallet identity, and August membership
hidden until raw Pass A/Pass B annotations, reliability results, adjudication
status, and file hashes are locked. Any later join is exploratory and cannot
select cases, tune thresholds, reopen the August test, or update the official
claim/experiment ledgers.

`large_llm_experiment_allowed=false`
`promotion_to_official_ledger=false`
`official_astra_cycle_untouched=true`

Generated at `{manifest['created_at']}`.
"""
    (out / "SEMANTIC_GATE_V2_PROTOCOL.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    if not PANEL.exists() or not PANEL_MANIFEST.exists():
        raise FileNotFoundError("frozen panel or manifest missing")

    records = parse_full_panel()
    rows, internal_map, selected_hashes = make_rows(records)
    pass_a = make_pass_a(rows)
    pass_b = make_pass_b(rows)
    pass_a.to_csv(out / "PASS_A_TEXT_ONLY_BLIND.csv", index=False)
    pass_b.to_csv(out / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", index=False)

    # This file is not for annotators; it is needed to reconnect annotations only
    # after the blind passes are locked.
    internal = out / "internal"
    internal.mkdir()
    (internal / "SAMPLE_ROW_MAP.json").write_text(json.dumps(internal_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    double_handles = [m["row_handle"] for m in internal_map if m["double_code_case"]]
    (out / "DOUBLE_CODE_ROW_HANDLES.csv").write_text("row_handle\n" + "\n".join(sorted(double_handles)) + "\n", encoding="utf-8")

    audits = [audit_blinding(pass_a, "pass_a"), audit_blinding(pass_b, "pass_b")]
    (out / "BLINDING_AUDIT.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all(item["blinding_ok"] for item in audits):
        raise RuntimeError("blinding audit failed")

    manifest = {
        "created_at": utc_now(),
        "status": "PREPARED_NO_ANNOTATIONS",
        "mode": "OFF_CHARTER_EXPLORATORY_PREPARATION",
        "protocol_version": "semantic_gate_v2_1",
        "source_panel": str(PANEL),
        "source_panel_sha256": sha256_file(PANEL),
        "source_panel_manifest_sha256": sha256_file(PANEL_MANIFEST),
        "source_full_cases": len(records),
        "sample_n_cases": SAMPLE_N,
        "double_code_cases": DOUBLE_N,
        "worksheet_rows": len(rows),
        "sample_salt": SAMPLE_SALT,
        "double_code_salt": DOUBLE_SALT,
        "row_handle_salt": ROW_SALT,
        "permutation_salt": PERM_SALT,
        "selection_rule": "sort SHA256(UTF-8(case_id + sample_salt)) by (hash, case_id), first 100",
        "double_code_rule": "sort SHA256(UTF-8(case_id + double_code_salt)) within fixed sample, first 20 cases",
        "future_outcomes_read": False,
        "f_delta_used_for_selection": False,
        "model_losses_used_for_selection": False,
        "annotations_present": False,
        "official_astra_cycle_untouched": True,
        "claim_ledger_touched": False,
        "experiment_registry_touched": False,
        "new_llm_outputs": False,
        "large_llm_experiment_allowed": False,
        "promotion_to_official_ledger": False,
        "pass_a_sha256": sha256_file(out / "PASS_A_TEXT_ONLY_BLIND.csv"),
        "pass_b_sha256": sha256_file(out / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv"),
        "double_code_handles_sha256": sha256_file(out / "DOUBLE_CODE_ROW_HANDLES.csv"),
        "blinding_audit_sha256": sha256_file(out / "BLINDING_AUDIT.json"),
        "selected_case_hashes": selected_hashes,
        "outputs": [
            "PASS_A_TEXT_ONLY_BLIND.csv",
            "PASS_B_STRUCTURED_REVIEW_LOCKED.csv",
            "DOUBLE_CODE_ROW_HANDLES.csv",
            "BLINDING_AUDIT.json",
            "SEMANTIC_GATE_V2_PROTOCOL.md",
        ],
    }
    (out / "SEMANTIC_GATE_V2_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_protocol(out, manifest)
    print(json.dumps({"out_dir": str(out), "source_full_cases": len(records), "sample_n_cases": SAMPLE_N, "double_code_cases": DOUBLE_N, "worksheet_rows": len(rows), "status": manifest["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
