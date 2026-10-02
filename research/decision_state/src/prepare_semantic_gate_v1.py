#!/usr/bin/env python3
"""Prepare a blinded, outcome-independent semantic audit sample.

This only materializes a proposed human-audit worksheet from the already frozen
full-variant hypothesis panel. It does not inspect or join future outcomes,
F/Delta, split membership, wallet identifiers, or model losses when selecting
cases, and it does not change any official ledger or registry.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RES = ROOT / "research/decision_state/results"
PANEL = RES / "hypothesis_panel_full.jsonl"
MANIFEST = RES / "hypothesis_panel_full.manifest.json"
TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
CLASSES = {"up", "same", "down"}
SAMPLE_N = 100
SALT = "|semantic-gate-v1|"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def case_hash(case_id: str) -> str:
    return hashlib.sha256((case_id + SALT).encode("utf-8")).hexdigest()


def write_protocol(out: Path, sample_manifest: dict) -> None:
    text = f"""# Proposed Semantic Gate V1 — blind human audit worksheet

**Status:** exploratory preparation only; not an Astra6 result, preregistration,
official claim, or experiment-registry entry.

## Locked selection rule

- Source: the existing `full` variant in `hypothesis_panel_full.jsonl`.
- Unit: one source case, selected before inspecting semantic annotations.
- For every source `case_id`, compute `SHA-256(case_id + \"|semantic-gate-v1|\")`.
- Sort hashes lexicographically and select the first {SAMPLE_N} cases.
- No selection by wallet, date, split, activity, repeat status, F, Delta, B4 gain/loss,
  model output, or August membership.
- The blind worksheet contains no raw `case_id`, wallet, date, split, outcome, F,
  Delta, model loss, or success/failure column.

## What the annotator sees

Each worksheet row contains one existing natural-language hypothesis, its stated
horizon, evidence labels, and the four recorded consequence categories. The
worksheet does not reveal the future outcome or model performance. The recorded
consequence categories are model-produced structured outputs, not ground-truth
future labels.

## Locked rubric (suggested)

For each consequence dimension, mark:

- `supported`, `unsupported`, or `unclear`: does the text make the recorded
  consequence operationally follow from the stated proposition?
- `specific`, `generic`, or `unclear`: is the proposition sufficiently specific
  to distinguish an operational behavior from a generic story?
- `relevant`, `irrelevant`, or `unclear`: is the named evidence group relevant to
  the proposition as written?

Record a short evidence span or phrase for every non-`unclear` judgment. Do not
infer owner identity, true belief, emotion, psychology, causal intent, or social
exposure. Do not use an LLM judge.

## Reliability and stopping rule

Independently double-code 20 of the 100 case IDs before adjudication. Report raw
agreement and a predeclared reliability statistic before resolving disagreements.
A failed semantic-consequence alignment or unstable inter-annotator reliability
stops the language-centered branch. Passing this gate would not establish
forecasting effectiveness or causal validity.

## Required human inputs

This directory contains only the deterministic sample and blank worksheet.
No human annotations have been supplied yet; therefore no semantic validity or
reliability result is claimed.

## Boundary

`large_llm_experiment_allowed=false`
`promotion_to_official_ledger=false`
`official_astra_cycle_untouched=true`

Generated at `{sample_manifest['created_at']}`.
"""
    (out / "SEMANTIC_GATE_V1_PROTOCOL.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)

    if not PANEL.exists() or not MANIFEST.exists():
        raise FileNotFoundError("frozen hypothesis panel or manifest missing")
    records: dict[str, dict] = {}
    with PANEL.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("variant") != "full":
                continue
            case_id = str(rec["case_id"])
            if case_id in records:
                raise ValueError(f"duplicate full case: {case_id}")
            records[case_id] = rec
    if len(records) != int(json.loads(MANIFEST.read_text())["n_cases"]):
        raise ValueError(f"unexpected full-case count: {len(records)}")

    ranked = sorted((case_hash(case_id), case_id) for case_id in records)
    selected = ranked[:SAMPLE_N]
    selected_hashes = {h for h, _ in selected}
    rows = []
    for ordinal, (hsh, case_id) in enumerate(selected, start=1):
        rec = records[case_id]
        parsed = rec.get("parsed") if isinstance(rec.get("parsed"), dict) else {}
        hypotheses = parsed.get("hypotheses", []) if isinstance(parsed.get("hypotheses"), list) else []
        sample_id = f"SGV1-{ordinal:04d}"
        for slot, hypothesis in enumerate(hypotheses[:3], start=1):
            if not isinstance(hypothesis, dict):
                continue
            consequences = hypothesis.get("consequences") if isinstance(hypothesis.get("consequences"), dict) else {}
            if any(consequences.get(t) not in CLASSES for t in TARGETS):
                continue
            evidence = hypothesis.get("evidence_ids", [])
            if not isinstance(evidence, list):
                evidence = []
            rows.append({
                "sample_id": sample_id,
                "hypothesis_slot": f"H{slot}",
                "hypothesis_text": str(hypothesis.get("text", "")),
                "horizon_days": hypothesis.get("horizon_days"),
                "evidence_labels": ";".join(sorted(str(x) for x in evidence)),
                "recorded_activity": consequences["activity"],
                "recorded_active_days": consequences["active_days"],
                "recorded_counterparty_breadth": consequences["counterparty_breadth"],
                "recorded_new_counterparties": consequences["new_counterparties"],
                # Blank fields for a human coder; no outcome or model columns.
                "activity_support": "",
                "active_days_support": "",
                "counterparty_breadth_support": "",
                "new_counterparties_support": "",
                "specificity": "",
                "evidence_relevance": "",
                "evidence_span_or_phrase": "",
                "annotator_notes": "",
            })

    worksheet = pd.DataFrame(rows)
    if worksheet["sample_id"].nunique() != SAMPLE_N:
        raise ValueError("worksheet does not contain all selected sample IDs")
    forbidden = {"case_id", "anchor_wallet", "cutoff_date", "split", "activity_bin", "sample_rank", "F", "Delta", "success", "failure", "y"}
    if forbidden.intersection(worksheet.columns):
        raise ValueError("blind worksheet contains forbidden linkage/outcome columns")
    worksheet.to_csv(out / "SEMANTIC_GATE_V1_BLIND_WORKSHEET.csv", index=False)

    sample_manifest = {
        "created_at": utc_now(),
        "status": "PREPARED_NO_ANNOTATIONS",
        "mode": "OFF_CHARTER_EXPLORATORY_FALLBACK_PREPARATION",
        "source_panel": str(PANEL),
        "source_panel_sha256": sha256_file(PANEL),
        "source_manifest_sha256": sha256_file(MANIFEST),
        "source_full_cases": len(records),
        "sample_n_cases": SAMPLE_N,
        "worksheet_rows": int(len(worksheet)),
        "salt_rule": SALT,
        "selection_rule": "sort SHA256(case_id + salt), select first 100; no outcomes/F/Delta/model fields used",
        "selected_sample_hashes": [h for h, _ in selected],
        "sample_ids": [f"SGV1-{i:04d}" for i in range(1, SAMPLE_N + 1)],
        "official_astra_cycle_untouched": True,
        "claim_ledger_touched": False,
        "experiment_registry_touched": False,
        "future_outcomes_read": False,
        "new_llm_outputs": False,
        "annotations_present": False,
        "large_llm_experiment_allowed": False,
        "promotion_to_official_ledger": False,
        "worksheet_sha256": sha256_file(out / "SEMANTIC_GATE_V1_BLIND_WORKSHEET.csv"),
    }
    (out / "SEMANTIC_GATE_V1_SAMPLE_MANIFEST.json").write_text(json.dumps(sample_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_protocol(out, sample_manifest)
    print(json.dumps({"out_dir": str(out), "sample_n_cases": SAMPLE_N, "worksheet_rows": len(worksheet), "status": sample_manifest["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
