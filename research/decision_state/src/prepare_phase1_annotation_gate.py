#!/usr/bin/env python3
"""Prepare the Phase-1 NLP-object annotation gate.

This package asks only whether frozen model-produced hypotheses can be
reliably decomposed into an operational object.  It does not read future
outcomes, F, Delta, losses, split labels, or wallet identifiers into the
worksheets.  It produces a text-only Pass A and a structured Pass B that must
remain locked until Pass A is submitted and hashed.

The package is deliberately append-only: it does not modify the frozen panel,
previous semantic-gate packages, official ledgers, or experiment registries.
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
DIRECTIONS = ["up", "same", "down", "not_stated", "unclear"]
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
EVIDENCE_ALLOWLIST = set(EVIDENCE_GROUPS)
SAMPLE_N = 100
DOUBLE_N = 20
# Reuse the already-selected exploratory case sample, but create new row IDs and
# a new protocol package so the Phase-1 object is independently auditable.
SAMPLE_SALT = "|semantic-gate-v1|"
DOUBLE_SALT = "|semantic-gate-v2-double|"
ROW_SALT = "|phase1-annotation-row|"
PERM_SALT = "|phase1-annotation-permutation|"
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")

PASS_A_COLUMNS = [
    "row_handle", "hypothesis_text",
    "proposition_boundary", "proposition_span",
    "scope_status", "scope_span",
    "time_horizon_status", "time_horizon_span",
    "consequence_activity_text", "consequence_active_days_text",
    "consequence_counterparty_breadth_text", "consequence_new_counterparties_text",
    "falsifier_status", "falsifier_span",
    "qualification_status", "qualification_span",
    "pass_a_notes",
]
PASS_B_COLUMNS = [
    "row_handle", "hypothesis_text",
    "recorded_activity", "recorded_active_days",
    "recorded_counterparty_breadth", "recorded_new_counterparties",
    "recorded_horizon_days", "evidence_labels",
    "alignment_activity", "alignment_active_days",
    "alignment_counterparty_breadth", "alignment_new_counterparties",
    "alignment_span_activity", "alignment_span_active_days",
    "alignment_span_counterparty_breadth", "alignment_span_new_counterparties",
    "horizon_compatibility",
    "evidence_pointer_E_SELF", "evidence_pointer_E_MARKET",
    "evidence_pointer_E_COVERAGE", "evidence_pointer_E_PLACEBO",
    "pass_b_notes",
]


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
                if any(consequences.get(target) not in {"up", "same", "down"} for target in TARGETS):
                    continue
                evidence = hypothesis.get("evidence_ids", [])
                if not isinstance(evidence, list):
                    evidence = []
                evidence_labels = sorted({str(x) for x in evidence})
                unknown = set(evidence_labels) - EVIDENCE_ALLOWLIST
                if unknown:
                    raise ValueError(f"unknown evidence IDs in source {case_id}: {sorted(unknown)}")
                valid.append({
                    "slot": f"H{slot}",
                    "text": text,
                    "horizon_days": hypothesis.get("horizon_days"),
                    "evidence_labels": evidence_labels,
                    "consequences": {target: consequences[target] for target in TARGETS},
                })
            records[case_id] = {"hypotheses": valid}
    expected = int(json.loads(PANEL_MANIFEST.read_text(encoding="utf-8"))["n_cases"])
    if len(records) != expected:
        raise ValueError(f"expected {expected} full cases, found {len(records)}")
    if not records or sum(len(x["hypotheses"]) for x in records.values()) == 0:
        raise ValueError("no valid hypotheses found")
    return records


def make_rows(records: dict[str, dict]) -> tuple[list[dict], list[dict], list[str]]:
    ranked = sorted((sha256_text(case_id + SAMPLE_SALT), case_id) for case_id in records)
    selected = ranked[:SAMPLE_N]
    selected_hashes = [hsh for hsh, _ in selected]
    double_ranked = sorted((sha256_text(case_id + DOUBLE_SALT), case_id) for _, case_id in selected)
    double_cases = {case_id for _, case_id in double_ranked[:DOUBLE_N]}

    rows: list[dict] = []
    internal_map: list[dict] = []
    for case_hash, case_id in selected:
        for hypothesis in records[case_id]["hypotheses"]:
            row_handle = "SGP1-" + sha256_text(case_hash + "|" + hypothesis["slot"] + ROW_SALT)[:32]
            row = {
                "row_handle": row_handle,
                "hypothesis_text": hypothesis["text"],
                "recorded_horizon_days": hypothesis["horizon_days"],
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
    rows.sort(key=lambda row: sha256_text(row["row_handle"] + PERM_SALT))
    return rows, internal_map, selected_hashes


def make_pass_a(rows: list[dict]) -> pd.DataFrame:
    result = []
    for row in rows:
        item = {column: "" for column in PASS_A_COLUMNS}
        item["row_handle"] = row["row_handle"]
        item["hypothesis_text"] = row["hypothesis_text"]
        result.append(item)
    return pd.DataFrame(result, columns=PASS_A_COLUMNS)


def make_pass_b(rows: list[dict]) -> pd.DataFrame:
    result = []
    for row in rows:
        item = {column: "" for column in PASS_B_COLUMNS}
        item.update({
            "row_handle": row["row_handle"],
            "hypothesis_text": row["hypothesis_text"],
            "recorded_activity": row["recorded_activity"],
            "recorded_active_days": row["recorded_active_days"],
            "recorded_counterparty_breadth": row["recorded_counterparty_breadth"],
            "recorded_new_counterparties": row["recorded_new_counterparties"],
            "recorded_horizon_days": row["recorded_horizon_days"],
            "evidence_labels": row["evidence_labels"],
        })
        result.append(item)
    return pd.DataFrame(result, columns=PASS_B_COLUMNS)


def audit_blinding(frame: pd.DataFrame, pass_name: str) -> dict:
    forbidden_tokens = [
        "case_id", "anchor_wallet", "wallet", "cutoff", "split", "activity_bin", "sample_rank",
        "probability", "confidence", "model", "loss", "log_loss", "delta", "success", "failure",
        "outcome", "future", "august", "july", "f_", "y_",
    ]

    def forbidden_column(column: str) -> bool:
        name = column.lower()
        return any((name.startswith(token) if token in {"f_", "y_"} else token in name) for token in forbidden_tokens)

    bad_columns = [column for column in frame.columns if forbidden_column(column)]
    raw_id_hits: list[str] = []
    forbidden_terms = re.compile(r"(?i)(?:\\bdelta\\b|\\baugust\\b|\\bjuly\\b|\\bsplit\\b|\\blog[_ -]?loss\\b|\\bf\\s*=)")
    for column in frame.columns:
        for value in frame[column].fillna("").astype(str):
            if WALLET_RE.search(value) or forbidden_terms.search(value):
                raw_id_hits.append(column)
    raw_id_hits = sorted(set(raw_id_hits))
    return {
        "pass": pass_name,
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "unexpected_forbidden_columns": bad_columns,
        "raw_wallet_or_outcome_like_values": raw_id_hits,
        # This is a package-level requirement, not an assertion that a human
        # handoff has already locked Pass A.
        "pass_a_lock_required_before_pass_b_distribution": pass_name == "pass_b",
        "blinding_ok": not bad_columns and not raw_id_hits,
    }


def write_protocol(out: Path, manifest: dict) -> None:
    text = f"""# Phase 1 NLP-object annotation gate

**Status:** `PREPARED_NO_ANNOTATIONS`  
**Mode:** exploratory, outcome-blind, append-only preparation  
**Created:** `{manifest['created_at']}`

## Scientific question

Can one model-produced hypothesis be reliably decomposed by independent human
annotators into an operational object with:

- an atomic proposition boundary;
- evidence pointer(s);
- scope and time horizon;
- observable consequence direction;
- an explicit or absent falsifier;
- assertion, qualification, or abstention status?

This phase does **not** evaluate prediction score, future validity, F, Delta,
model loss, or whether the hypothesis is scientifically true. It tests whether
the proposed NLP object is operationally clear enough to study.

## Fixed sample and blinding

- Source: frozen `full` variant of `hypothesis_panel_full.jsonl`.
- Selected cases: `{manifest['sample_n_cases']}`; worksheet rows: `{manifest['worksheet_rows']}`.
- Case selection: SHA-256 of `case_id + sample salt`, first `{SAMPLE_N}`; no outcome, F,
  Delta, score, or test membership is used.
- Double-code roster: `{manifest['double_code_cases']}` cases, including every row for
  each selected case.
- Pass A contains only opaque row handle and hypothesis text plus blank annotations.
- Pass B contains recorded model consequence/horizon/evidence metadata and must not
  be distributed until both coders have submitted Pass A and the submissions have
  been hashed and locked. The package generator cannot enforce human handoff order;
  the handoff manifest must record this lock externally.

## Pass A: text-only operational clarity

Annotators must not infer owner psychology, intent, causality, social exposure, or
unobserved external context. They annotate only what the text commits to.

Allowed labels:

- `proposition_boundary`: `atomic | compound | none | unclear`
- `scope_status`: `explicit | partial | absent | unclear`
- `time_horizon_status`: `explicit | implicit | absent | unclear`
- `consequence_*_text`: `up | same | down | not_stated | unclear`
- `falsifier_status`: `explicit | implicit | absent | unclear`
- `qualification_status`: `assert | qualify | abstain | unclear`

For every non-absent/non-unclear span, copy an exact contiguous substring from
`hypothesis_text`. `proposition_span` is the smallest contiguous span that carries
the main behavioral proposition. If the text contains multiple independent
claims, mark `compound` rather than silently selecting one. `abstain` means the
text declines to make a behavioral assertion; `qualify` means it asserts a claim
but explicitly limits certainty, scope, or alternatives.

## Pass B: structured compatibility (after Pass A lock)

The recorded fields are model-produced structured outputs, not future ground
truth. For each consequence dimension, annotate:

- `alignment_*`: `entailed | unsupported | contradicted | unclear`;
- `alignment_span_*`: exact text span supporting the judgment, unless `unclear`;
- `horizon_compatibility`: `compatible | incompatible | unclear`;
- `evidence_pointer_*`: `supported | unsupported | unclear | not_applicable`.

Evidence group definitions shown to annotators:

- `E_SELF`: recent address dynamics and event composition;
- `E_MARKET`: as-of ETH market context;
- `E_COVERAGE`: observation-window or data-coverage metadata;
- `E_PLACEBO`: non-behavioral reporting sentence.

`not_applicable` is allowed only when that evidence ID is absent from the recorded
list. Pointer support means that the text's stated proposition is semantically
compatible with the claimed evidence group; it does not mean the group proves
true intent or causal provenance.

## Reliability gate (predeclared)

Reliability is computed only on the fixed double-code roster and resamples whole
cases, not rows. Missingness, unexpected labels, and invalid spans are failures.

- Pooled categorical exact agreement: `>= 0.80`.
- Pooled nominal Cohen kappa: `>= 0.60`.
- Every critical field exact agreement: `>= 0.70`.
- Every critical field kappa: `>= 0.40`.
- Span exact agreement: `>= 0.80` where a span is required; token-overlap F1 is
  reported as a diagnostic and should be `>= 0.80`.
- Technical missingness: `<= 5%` of required annotation cells.
- `unclear` rate: `<= 20%` for proposition boundary, scope, horizon,
  consequence direction, falsifier, and qualification fields.

A failure is `KILL / REDESIGN` for the current object schema. Adjudication cannot
convert a failed pre-adjudication reliability gate into a pass.

## What a pass means

A pass supports only that the proposed object can be annotated with high agreement.
It does not establish semantic truth, forecasting effectiveness, owner psychology,
causal intent, or generalization. Phase 2 (text-versus-template/consequence
ablation) is locked out until this gate passes.

`future_outcomes_read=false`  
`f_delta_used_for_selection=false`  
`large_llm_experiment_allowed=false`  
`promotion_to_official_ledger=false`  
`official_astra_cycle_untouched=true`
"""
    (out / "PHASE1_ANNOTATION_PROTOCOL.md").write_text(text, encoding="utf-8")


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

    internal = out / "internal"
    internal.mkdir()
    (internal / "SAMPLE_ROW_MAP.json").write_text(json.dumps(internal_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    double_handles = sorted(m["row_handle"] for m in internal_map if m["double_code_case"])
    (out / "DOUBLE_CODE_ROW_HANDLES.csv").write_text("row_handle\n" + "\n".join(double_handles) + "\n", encoding="utf-8")

    audits = [audit_blinding(pass_a, "pass_a"), audit_blinding(pass_b, "pass_b")]
    (out / "BLINDING_AUDIT.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all(item["blinding_ok"] for item in audits):
        raise RuntimeError("blinding audit failed")

    manifest = {
        "created_at": utc_now(),
        "status": "PREPARED_NO_ANNOTATIONS",
        "mode": "PHASE1_NLP_OBJECT_ANNOTATION_GATE",
        "protocol_version": "phase1_annotation_gate_v1",
        "source_panel": str(PANEL),
        "source_panel_sha256": sha256_file(PANEL),
        "source_panel_manifest_sha256": sha256_file(PANEL_MANIFEST),
        "source_full_cases": len(records),
        "sample_n_cases": SAMPLE_N,
        "double_code_cases": DOUBLE_N,
        "worksheet_rows": len(rows),
        "sample_salt": SAMPLE_SALT,
        "double_salt": DOUBLE_SALT,
        "row_salt": ROW_SALT,
        "permutation_salt": PERM_SALT,
        "selection_rule": f"sort SHA256(UTF-8(case_id + {SAMPLE_SALT!r})) by (hash, case_id), first {SAMPLE_N}",
        "double_code_rule": f"sort SHA256(UTF-8(case_id + {DOUBLE_SALT!r})) within fixed sample, first {DOUBLE_N}",
        "future_outcomes_read": False,
        "f_delta_used_for_selection": False,
        "model_losses_used_for_selection": False,
        "annotations_present": False,
        "pass_a_lock_required_before_pass_b_distribution": True,
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
            "PHASE1_ANNOTATION_PROTOCOL.md",
        ],
    }
    (out / "PHASE1_ANNOTATION_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_protocol(out, manifest)
    handoff = f"""# Phase 1 annotation handoff

Status: `PREPARED_NO_ANNOTATIONS`

1. Give annotators only `PASS_A_TEXT_ONLY_BLIND.csv` first.
2. Collect and validate each coder's Pass A submission against the exact schema.
3. Hash and lock both Pass A submissions; record the hashes in an external lock manifest.
4. Only then distribute `PASS_B_STRUCTURED_REVIEW_LOCKED.csv`.
5. Double-code every row whose handle appears in `DOUBLE_CODE_ROW_HANDLES.csv`.
6. Run the fail-closed validator before reliability scoring.
7. Run reliability scoring on the fixed 20-case roster. Do not adjudicate before the
   pre-adjudication gate is recorded.

No future outcomes, August labels, F/Delta, losses, split/date, wallet identity,
or model probabilities may be joined to annotation sheets before the reliability
result is locked.
"""
    (out / "ANNOTATION_HANDOFF.md").write_text(handoff, encoding="utf-8")
    print(json.dumps({
        "out_dir": str(out),
        "status": manifest["status"],
        "source_full_cases": len(records),
        "sample_n_cases": SAMPLE_N,
        "double_code_cases": DOUBLE_N,
        "worksheet_rows": len(rows),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
