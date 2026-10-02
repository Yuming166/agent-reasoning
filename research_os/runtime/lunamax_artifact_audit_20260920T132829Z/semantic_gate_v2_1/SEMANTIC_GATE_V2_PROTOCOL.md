# Semantic Gate V2 — two-pass blind human audit

**Status:** deterministic exploratory preparation only. This is not an Astra6
result, preregistration, official claim, or experiment-registry entry.

## Fixed sample

- Source: frozen `full` variant of `hypothesis_panel_full.jsonl`.
- Source cases: 3000.
- Selected cases: 100.
- Case selection: `SHA256(UTF-8(case_id + "|semantic-gate-v1|"))`, sorted by
  `(hash, case_id)`, first 100; no replacement after annotation starts.
- Double-code cases: 20, selected independently
  from the fixed sample using `SHA256(UTF-8(case_id + "|semantic-gate-v2-double|"))`.
- Worksheet rows: 300 valid hypotheses. The actual row
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

Independently double-code all rows belonging to the fixed 20-case
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

Generated at `2026-09-20T13:56:49Z`.
