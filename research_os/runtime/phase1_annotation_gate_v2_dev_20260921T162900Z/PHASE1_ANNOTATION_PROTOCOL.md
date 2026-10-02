# Phase 1 NLP-object annotation gate — V2 development package

**Status:** `PREPARED_NO_ANNOTATIONS`  
**Protocol:** `phase1_annotation_gate_v2_dev`  
**Created:** `2026-09-21T16:33:47Z`  
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
- Selection: independently sort SHA-256(case_id + `|phase1-v2-dev-balanced-case|`) within each
  allowed cutoff and take 50 cases per cutoff; 100 cases total and 300 rows.
- Double coding: independently sort SHA-256(case_id + `|phase1-v2-dev-balanced-double|`) within
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
{
  "well_formed_proposition_min": 0.8,
  "explicit_scope_min": 0.7,
  "explicit_time_horizon_min": 0.7,
  "observable_consequence_min": 0.8,
  "executable_falsifier_min": 0.5,
  "valid_evidence_link_min": 0.7,
  "non_trivial_qualification_or_abstention_min": 0.2
}
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
