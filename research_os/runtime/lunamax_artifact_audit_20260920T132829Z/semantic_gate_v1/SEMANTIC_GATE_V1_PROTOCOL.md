# Proposed Semantic Gate V1 — blind human audit worksheet

**Status:** exploratory preparation only; not an Astra6 result, preregistration,
official claim, or experiment-registry entry.

## Locked selection rule

- Source: the existing `full` variant in `hypothesis_panel_full.jsonl`.
- Unit: one source case, selected before inspecting semantic annotations.
- For every source `case_id`, compute `SHA-256(case_id + "|semantic-gate-v1|")`.
- Sort hashes lexicographically and select the first 100 cases.
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

Generated at `2026-09-20T13:35:13Z`.
