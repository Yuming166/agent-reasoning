#!/usr/bin/env python3
"""Prepare the repaired Phase-1 annotation package.

This is an append-only V2 package.  It samples only the June/July development
pool, freezes Gate 1A reliability separately from Gate 1B substantive validity,
and distinguishes descriptive evidence support from predictive consistency.
No future outcomes or test labels are joined to the worksheets.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from collections import Counter
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
CUTOFFS = ["2022-06-01", "2022-07-01"]
EXPECTED_SPLITS = {"2022-06-01": "train", "2022-07-01": "dev"}
PER_CUTOFF_N = 50
DOUBLE_PER_CUTOFF_N = 10
SAMPLE_N = PER_CUTOFF_N * len(CUTOFFS)
DOUBLE_N = DOUBLE_PER_CUTOFF_N * len(CUTOFFS)
SAMPLE_SALT = "|phase1-v2-dev-balanced-case|"
DOUBLE_SALT = "|phase1-v2-dev-balanced-double|"
ROW_SALT = "|phase1-v2-annotation-row|"
PERM_SALT = "|phase1-v2-annotation-permutation|"
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")

# Gate 1B values are exploratory feasibility thresholds, frozen in this package
# before any formal annotation is released.  They are not prediction claims.
GATE_1B_THRESHOLDS = {
    "well_formed_proposition_min": 0.80,
    "explicit_scope_min": 0.70,
    "explicit_time_horizon_min": 0.70,
    "observable_consequence_min": 0.80,
    "executable_falsifier_min": 0.50,
    "valid_evidence_link_min": 0.70,
    "non_trivial_qualification_or_abstention_min": 0.20,
}

PASS_A_COLUMNS = [
    "row_handle", "hypothesis_text",
    "proposition_boundary", "proposition_span", "proposition_status",
    "scope_status", "scope_span",
    "time_horizon_status", "time_horizon_span",
    "consequence_activity_text", "consequence_active_days_text",
    "consequence_counterparty_breadth_text", "consequence_new_counterparties_text",
    "consequence_observability",
    "falsifier_status", "falsifier_span", "falsifier_executability",
    "qualification_status", "qualification_span", "qualification_substantive",
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
    "evidence_pointer_E_SELF", "evidence_span_E_SELF",
    "evidence_pointer_E_MARKET", "evidence_span_E_MARKET",
    "evidence_pointer_E_COVERAGE", "evidence_span_E_COVERAGE",
    "evidence_pointer_E_PLACEBO", "evidence_span_E_PLACEBO",
    "placebo_handling", "pass_b_notes",
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
            cutoff = str(record.get("cutoff_date", ""))
            split = str(record.get("split", ""))
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
            records[case_id] = {
                "cutoff_date": cutoff,
                "split": split,
                "hypotheses": valid,
            }
    expected = int(json.loads(PANEL_MANIFEST.read_text(encoding="utf-8"))["n_cases"])
    if len(records) != expected:
        raise ValueError(f"expected {expected} full cases, found {len(records)}")
    for case_id, record in records.items():
        if record["cutoff_date"] in CUTOFFS and record["split"] != EXPECTED_SPLITS[record["cutoff_date"]]:
            raise ValueError(f"unexpected split for development case {case_id}: {record}")
    return records


def make_rows(records: dict[str, dict]) -> tuple[list[dict], list[dict], list[str], dict[str, list[str]]]:
    selected_cases: list[str] = []
    selected_ranks: dict[str, list[str]] = {}
    for cutoff in CUTOFFS:
        pool = [case_id for case_id, r in records.items() if r["cutoff_date"] == cutoff]
        if len(pool) < PER_CUTOFF_N:
            raise ValueError(f"not enough cases for {cutoff}: {len(pool)}")
        ranked = sorted((sha256_text(case_id + SAMPLE_SALT), case_id) for case_id in pool)
        chosen = [case_id for _, case_id in ranked[:PER_CUTOFF_N]]
        selected_ranks[cutoff] = chosen
        selected_cases.extend(chosen)

    double_cases: set[str] = set()
    for cutoff in CUTOFFS:
        ranked = sorted((sha256_text(case_id + DOUBLE_SALT), case_id) for case_id in selected_ranks[cutoff])
        double_cases.update(case_id for _, case_id in ranked[:DOUBLE_PER_CUTOFF_N])

    rows: list[dict] = []
    internal_map: list[dict] = []
    for case_id in selected_cases:
        record = records[case_id]
        case_hash = sha256_text(case_id + SAMPLE_SALT)
        for hypothesis in record["hypotheses"]:
            row_handle = "SGP2-" + sha256_text(case_hash + "|" + hypothesis["slot"] + ROW_SALT)[:32]
            rows.append({
                "row_handle": row_handle,
                "hypothesis_text": hypothesis["text"],
                "recorded_horizon_days": hypothesis["horizon_days"],
                "evidence_labels": ";".join(hypothesis["evidence_labels"]),
                **{f"recorded_{target}": hypothesis["consequences"][target] for target in TARGETS},
            })
            internal_map.append({
                "row_handle": row_handle,
                "case_id": case_id,
                "case_hash": case_hash,
                "cutoff_date": record["cutoff_date"],
                "split": record["split"],
                "hypothesis_slot": hypothesis["slot"],
                "double_code_case": case_id in double_cases,
            })
    if len({row["row_handle"] for row in rows}) != len(rows):
        raise ValueError("row handle collision")
    if len(rows) != SAMPLE_N * 3:
        raise ValueError(f"expected 3 valid hypotheses per selected case, got {len(rows)} rows")
    rows.sort(key=lambda row: sha256_text(row["row_handle"] + PERM_SALT))
    selected_hashes = [sha256_text(case_id + SAMPLE_SALT) for case_id in selected_cases]
    return rows, internal_map, selected_hashes, selected_ranks


def make_pass_a(rows: list[dict]) -> pd.DataFrame:
    result = []
    for row in rows:
        item = {column: "" for column in PASS_A_COLUMNS}
        item.update({"row_handle": row["row_handle"], "hypothesis_text": row["hypothesis_text"]})
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
        "pass_a_lock_required_before_pass_b_distribution": pass_name == "pass_b",
        "blinding_ok": not bad_columns and not raw_id_hits,
    }


def write_protocol(out: Path, manifest: dict) -> None:
    text = f"""# Phase 1 NLP-object annotation gate — V2 development package

**Status:** `PREPARED_NO_ANNOTATIONS`  
**Protocol:** `{manifest['protocol_version']}`  
**Created:** `{manifest['created_at']}`  
**Audit conclusion that triggered this version:** `PROTOCOL_REPAIR_REQUIRED`

## Scope

This append-only version tests whether frozen model-produced hypotheses form a
measurable NLP object. It is not a prediction-score experiment. August is the
frozen test cutoff and is excluded from this development package. No future
outcomes, F, Delta, model loss, or wallet identity is exposed to annotators.
The original V1 package remains unchanged as retrospective feasibility material.

## Roster and independence

- Source: frozen `full` records in `hypothesis_panel_full.jsonl`.
- Development pool: June (`2022-06-01`, train) and July (`2022-07-01`, dev) only.
- Selection: independently sort SHA-256(case_id + `{SAMPLE_SALT}`) within each
  allowed cutoff and take 50 cases per cutoff; 100 cases total and 300 rows.
- Double coding: independently sort SHA-256(case_id + `{DOUBLE_SALT}`) within
  each selected cutoff and take 10 cases per cutoff; 20 cases and 60 rows.
- Three hypotheses from one case are clustered. The primary reliability unit is
  the case; row-level agreement is a descriptive supplement.
- Selection is outcome-blind and based only on case ID, cutoff membership, and
  the frozen full panel. The cutoff is never shown in annotation sheets.

## Gate 1A — annotation reliability

Annotators independently label Pass A. Reliability is field-level and is
computed on the fixed double-code roster. Whole-case bootstrap or another
predeclared case-clustered uncertainty procedure is primary; pooled values are
descriptive only. If a field has one observed category, Cohen kappa is reported
as `NOT_ESTIMABLE`; it is never changed to 1.0 or silently omitted.

The technical thresholds are frozen as:

- field exact agreement >= 0.70;
- field Cohen kappa >= 0.40 when estimable;
- pooled categorical exact agreement >= 0.80 as a descriptive summary;
- required-span exact agreement >= 0.80 and token F1 >= 0.80;
- technical missingness <= 0.05;
- unclear rate <= 0.20 for critical categorical fields.

A failure of any critical field is `KILL / REDESIGN` before adjudication.

## Gate 1B — substantive object validity

Gate 1B is separate from reliability. It estimates the proportion of annotated
rows satisfying each criterion; it does not claim that a claim is true or
prospectively valid. The exploratory minimum thresholds are frozen in the
manifest before formal annotation:

```json
{json.dumps(GATE_1B_THRESHOLDS, ensure_ascii=False, indent=2)}
```

The row-level criteria are:

- **well-formed proposition:** `proposition_boundary=atomic` and
  `proposition_status=well_formed`;
- **explicit scope:** `scope_status=explicit`;
- **explicit time horizon:** `time_horizon_status=explicit`;
- **observable consequence:** `consequence_observability=observable`;
- **executable falsifier:** `falsifier_executability=executable`;
- **valid evidence link:** at least one non-placebo evidence group is present
  and judged `direct_descriptive` or `predictive_consistent` in Pass B;
- **non-trivial qualification/abstention:** `qualification_substantive=non_trivial`
  (including a substantive abstention when no assertion is made).

A Gate 1A pass does not imply a Gate 1B pass. If Gate 1B is weak, report the
object as substantively weak and do not automatically proceed to Phase 2.

## Pass A — text-only

Annotate only commitments visible in `hypothesis_text`. Do not infer owner
psychology, intent, causality, social exposure, or hidden context. Do not infer a
missing horizon from task instructions or the recorded structured output.
`absent`/`unclear` horizon means the horizon span stays blank.

Allowed labels:

- `proposition_boundary`: `atomic | compound | none | unclear`;
- `proposition_status`: `well_formed | ill_formed | absent | unclear`;
- `scope_status`: `explicit | partial | absent | unclear`;
- `time_horizon_status`: `explicit | implicit | absent | unclear`;
- each `consequence_*_text`: `up | same | down | not_stated | unclear`;
- `consequence_observability`: `observable | non_observable | unclear`;
- `falsifier_status`: `explicit | implicit | absent | unclear`;
- `falsifier_executability`: `executable | caveat_only | absent | unclear`;
- `qualification_status`: `assert | qualify | abstain | unclear`;
- `qualification_substantive`: `non_trivial | trivial_or_none | not_applicable | unclear`.

Every non-absent/non-unclear span must be an exact contiguous substring of the
hypothesis text. A compound text is not silently reduced to one proposition.
An executable falsifier must identify an observable future event or direction
and a stated/operational horizon; hedging alone is `caveat_only`.

## Pass B — structured compatibility and evidence provenance

Pass B is locked until both Pass A files are submitted, hashed, and recorded.
The recorded consequence, horizon, and evidence fields are model outputs, not
ground truth. Consequence alignment labels are:
`entailed | unsupported | contradicted | unclear`.

For each evidence group, use:

- `direct_descriptive`: directly supports a historical/descriptive proposition;
- `predictive_consistent`: compatible with a future consequence but does not entail it;
- `unsupported`;
- `contradicted`;
- `unclear`;
- `not_applicable` only when the evidence ID is absent.

An exact text span must point to the textual basis for a non-`not_applicable`
/non-`unclear` evidence judgment. `E_PLACEBO` is a negative-control channel;
it never counts as a valid evidence link. For it, use `negative_control_failure`,
`irrelevant`, `unclear`, or `not_applicable` in `evidence_pointer_E_PLACEBO`,
and record `placebo_handling` consistently. `E_MARKET` remains distinct from
pure on-chain evidence and cannot be silently treated as on-chain support.

Historical evidence supports a premise such as “recent transaction frequency
declined”; it does not entail “activity will decline over the next seven days.”

## Handoff lock

1. Release only `PASS_A_TEXT_ONLY_BLIND.csv` to the two independent coders.
2. Validate and hash both completed Pass A sheets against this exact schema.
3. Record the two hashes in a lock manifest before distributing Pass B.
4. Release `PASS_B_STRUCTURED_REVIEW_LOCKED.csv` only after that lock.
5. Double-code every handle in `DOUBLE_CODE_ROW_HANDLES.csv`.
6. Run fail-closed validation, then pre-adjudication reliability scoring.
7. Do not join outcomes or open Phase 2/3 before both Gate 1A and Gate 1B
   interpretations are recorded.
"""
    (out / "PHASE1_ANNOTATION_PROTOCOL.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_DIR if hasattr(args, "out_DIR") else args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    records = parse_full_panel()
    rows, internal_map, selected_hashes, selected_ranks = make_rows(records)
    pass_a = make_pass_a(rows)
    pass_b = make_pass_b(rows)
    pass_a.to_csv(out / "PASS_A_TEXT_ONLY_BLIND.csv", index=False)
    pass_b.to_csv(out / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", index=False)
    # Blank coder templates are validation fixtures only; they are not human annotations.
    pass_a.to_csv(out / "PASS_A_CODER_A_BLANK.csv", index=False)
    pass_a.to_csv(out / "PASS_A_CODER_B_BLANK.csv", index=False)
    pass_b.to_csv(out / "PASS_B_CODER_A_BLANK.csv", index=False)
    pass_b.to_csv(out / "PASS_B_CODER_B_BLANK.csv", index=False)

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
        "protocol_version": "phase1_annotation_gate_v2_dev",
        "source_panel": str(PANEL),
        "source_panel_sha256": sha256_file(PANEL),
        "source_panel_manifest_sha256": sha256_file(PANEL_MANIFEST),
        "source_full_cases": len(records),
        "development_cutoffs": CUTOFFS,
        "excluded_test_cutoff": "2022-08-01",
        "selected_cases_by_cutoff": {cutoff: len(selected_ranks[cutoff]) for cutoff in CUTOFFS},
        "sample_n_cases": SAMPLE_N,
        "double_code_cases_by_cutoff": {cutoff: DOUBLE_PER_CUTOFF_N for cutoff in CUTOFFS},
        "double_code_cases": DOUBLE_N,
        "worksheet_rows": len(rows),
        "double_code_rows": len(double_handles),
        "sample_salt": SAMPLE_SALT,
        "double_salt": DOUBLE_SALT,
        "row_salt": ROW_SALT,
        "permutation_salt": PERM_SALT,
        "selection_rule": f"within each allowed cutoff, sort SHA256(UTF-8(case_id + {SAMPLE_SALT!r})) by (hash, case_id), first {PER_CUTOFF_N}",
        "double_code_rule": f"within each allowed cutoff, sort SHA256(UTF-8(case_id + {DOUBLE_SALT!r})) by (hash, case_id), first {DOUBLE_PER_CUTOFF_N}",
        "case_cluster_primary_unit": True,
        "row_level_agreement_descriptive_only": True,
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
        "gate_1a": {"name": "ANNOTATION_RELIABILITY", "status": "PENDING_ANNOTATION"},
        "gate_1b": {"name": "OBJECT_SUBSTANTIVE_VALIDITY", "status": "PENDING_ANNOTATION", "thresholds": GATE_1B_THRESHOLDS},
        "evidence_pointer_labels": ["direct_descriptive", "predictive_consistent", "unsupported", "contradicted", "unclear", "not_applicable"],
        "placebo_pointer_labels": ["negative_control_failure", "irrelevant", "unclear", "not_applicable"],
        "undefined_kappa_policy": "NOT_ESTIMABLE; never coerce to 1.0 and never omit post hoc",
        "gate_1a_kappa_pooling": "field_level_primary; pooled_descriptive_only",
        "original_v1_package_preserved": str(ROOT / "research_os/runtime/phase1_annotation_gate_20260921T161510Z"),
        "pass_a_sha256": sha256_file(out / "PASS_A_TEXT_ONLY_BLIND.csv"),
        "pass_b_sha256": sha256_file(out / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv"),
        "double_code_handles_sha256": sha256_file(out / "DOUBLE_CODE_ROW_HANDLES.csv"),
        "blinding_audit_sha256": sha256_file(out / "BLINDING_AUDIT.json"),
        "selected_case_hashes": selected_hashes,
        "outputs": [
            "PASS_A_TEXT_ONLY_BLIND.csv",
            "PASS_B_STRUCTURED_REVIEW_LOCKED.csv",
            "PASS_A_CODER_A_BLANK.csv",
            "PASS_A_CODER_B_BLANK.csv",
            "PASS_B_CODER_A_BLANK.csv",
            "PASS_B_CODER_B_BLANK.csv",
            "DOUBLE_CODE_ROW_HANDLES.csv",
            "BLINDING_AUDIT.json",
            "PHASE1_ANNOTATION_PROTOCOL.md",
            "ANNOTATION_HANDOFF.md",
            "PHASE1_GATE_STATUS.json",
            "PHASE1_GATE_STATUS.md",
        ],
    }
    (out / "PHASE1_ANNOTATION_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_protocol(out, manifest)
    (out / "ANNOTATION_HANDOFF.md").write_text("""# Phase 1 V2 annotation handoff

Status: `PREPARED_NO_ANNOTATIONS`

1. Release only `PASS_A_TEXT_ONLY_BLIND.csv` first.
2. Validate and hash both independent Pass A submissions against this exact V2 schema.
3. Record the two Pass A hashes before releasing Pass B.
4. Double-code all rows in `DOUBLE_CODE_ROW_HANDLES.csv`; primary uncertainty is clustered by case.
5. Run fail-closed validation and pre-adjudication reliability scoring.
6. Evaluate Gate 1A and Gate 1B separately; do not treat agreement as substantive validity.
7. Do not join August, future outcomes, F/Delta, losses, split/date, wallet identity,
   or model probabilities to annotation sheets before both gates are interpreted.
""", encoding="utf-8")
    status = {
        "phase": "PHASE_1_NLP_OBJECT_VALIDITY",
        "status": "PREPARED_NO_ANNOTATIONS",
        "decision_target": "Gate_1A_reliability_then_Gate_1B_substantive_validity",
        "prediction_score_in_scope": False,
        "phase_2_text_value_gate": "LOCKED_PENDING_PHASE_1A_AND_PHASE_1B",
        "phase_3_selective_acceptance": "LOCKED_PENDING_PHASE_1A_PHASE_1B_AND_PHASE_2",
        "sample_n_cases": SAMPLE_N,
        "worksheet_rows": len(rows),
        "double_code_cases": DOUBLE_N,
        "double_code_rows": len(double_handles),
        "source_full_cases": len(records),
        "development_cutoffs": CUTOFFS,
        "excluded_test_cutoff": "2022-08-01",
        "future_outcomes_read": False,
        "official_astra_cycle_touched": False,
        "official_claim_ledger_touched": False,
        "official_experiment_registry_touched": False,
        "large_llm_experiment_allowed": False,
        "next_required_action": "Obtain two independent human Pass-A annotations; hash and lock both before releasing Pass-B.",
        "gate_1a_pass_condition": "Predeclared field-level reliability, case-clustered uncertainty, missingness, span, and kappa rules pass.",
        "gate_1b_pass_condition": "Predeclared substantive-validity proportions meet frozen exploratory thresholds; report separately from Gate 1A.",
        "fail_condition": "KILL_OR_REDESIGN_IF_GATE_1A_FAILS_OR_GATE_1B_OBJECT_IS_SUBSTANTIVELY_WEAK.",
        "created_at": utc_now(),
    }
    (out / "PHASE1_GATE_STATUS.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "PHASE1_GATE_STATUS.md").write_text("""# Phase 1 V2 gate status

**Status:** `PREPARED_NO_ANNOTATIONS`

- Gate 1A reliability: `PENDING_ANNOTATION`
- Gate 1B substantive object validity: `PENDING_ANNOTATION`
- August test cutoff: excluded
- Pass B: locked until both Pass A sheets are hashed
- Phase 2 and Phase 3: locked

No conclusion about agreement, well-formedness, evidence support, falsifiability,
or prospective validity has been made.
""", encoding="utf-8")
    print(json.dumps({
        "out_dir": str(out), "status": manifest["status"], "sample_n_cases": SAMPLE_N,
        "selected_cases_by_cutoff": manifest["selected_cases_by_cutoff"],
        "double_code_cases_by_cutoff": manifest["double_code_cases_by_cutoff"],
        "worksheet_rows": len(rows), "double_code_rows": len(double_handles),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
