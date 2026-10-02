# Phase 1 NLP-object annotation gate

**Status:** `PREPARED_NO_ANNOTATIONS`  
**Mode:** exploratory, outcome-blind, append-only preparation  
**Created:** `2026-09-21T16:15:11Z`

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
- Selected cases: `100`; worksheet rows: `300`.
- Case selection: SHA-256 of `case_id + sample salt`, first `100`; no outcome, F,
  Delta, score, or test membership is used.
- Double-code roster: `20` cases, including every row for
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
