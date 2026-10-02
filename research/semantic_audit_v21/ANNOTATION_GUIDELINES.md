# Semantic Gate V2.1 human annotation guidelines

**Status:** HUMAN-READY TEMPLATE; no human annotations have been fabricated.
**Scope:** observable semantic content only. Do not infer owner belief, intent,
psychology, emotion, social exposure, or whether the hypothesis is true.

## Unit and visibility

Each row contains an opaque `sample_id`, a cutoff time, an as-of input summary,
the natural-language hypothesis, the structured state emitted with that
hypothesis, and evidence labels. The input summary contains only information
available at or before the cutoff. It contains no future labels, loss, B4/B0
performance, F, Delta, August membership, or wallet identity.

The structured consequence value `same` is recorded using the annotation label
`unchanged` when annotating language. Do not use the future outcome to decide
any field.

## Annotation fields

- `activity_direction`: `up`, `down`, `unchanged`, or `unspecified`.
- `active_days_direction`: same label set.
- `counterparty_breadth_direction`: same label set.
- `new_counterparty_direction`: same label set.
- `temporal_horizon`: `explicit`, `implicit`, or `absent`.
- `evidence_reference`: `explicit`, `implicit`, or `absent`.
- `evidence_consistency`: `consistent`, `inconsistent`, or `unclear`.
- `structured_text_consistency`: `consistent`, `inconsistent`, or `unclear`.
- `falsifiable_future_implication`: `yes`, `no`, or `unclear`.

## Operational rules

1. Assign a direction only when the text commits to an observable increase,
   decrease, or stable/unchanged behavior. A generic story is `unspecified`.
2. A direction must refer to one of the four observable consequence dimensions;
   do not map psychological language to a direction.
3. `explicit` horizon requires a stated period or window. `implicit` is allowed
   only when a temporal phrase clearly implies a window without naming a number.
4. `evidence_reference=explicit` requires the text to name or clearly point to
   the supplied evidence. `implicit` is a weaker, literal reference; do not
   infer an evidence source from plausibility.
5. `evidence_consistency` asks whether the text's stated evidence reference is
   compatible with the listed evidence label. It does not ask whether the
   evidence is causally sufficient.
6. `structured_text_consistency` compares the text's observable commitments to
   the supplied structured state. It does not ask whether the structured state
   is correct in the world.
7. `falsifiable_future_implication=yes` requires a future-observable direction
   or condition that could be checked at the stated/implicit horizon.
8. When the text is genuinely ambiguous, use `unspecified` or `unclear` rather
   than guessing.

## Examples

### Positive examples

- Text: `The address will reduce activity over the next 7 days.`
  - `activity_direction=down`, `temporal_horizon=explicit`,
    `falsifiable_future_implication=yes`.
- Text: `The address will expand its set of counterparties.`
  - `counterparty_breadth_direction=up` if no contrary qualifier appears.
- Text: `Given recent self-history, activity should remain unchanged.`
  - `activity_direction=unchanged`, `evidence_reference=explicit` for the
    self-history evidence group.

### Negative examples

- Text: `The actor is unusual and may be associated with a protocol.`
  - All four directions are `unspecified`; no checkable future direction is
    stated.
- Text: `The owner feels uncertain about the market.`
  - Do not label a direction; owner emotion/psychology is out of scope.
- Text: `The address has a complex history.`
  - This is not an operational future implication by itself.

### Ambiguous examples

- Text: `The actor is consolidating.`
  - Do not automatically map this to lower activity or fewer counterparties;
    use `unspecified` or `unclear` unless the surrounding text makes a literal
    observable direction explicit.
- Text: `The address may continue its current pattern.`
  - Horizon may be `implicit`, but a direction is `unspecified` unless the
    pattern itself is explicitly described.
- Text: `This is driven by the market.`
  - Evidence reference may be `explicit` only if the supplied market group is
    clearly the intended referent; otherwise use `unclear`.

## Independence and disagreement

Two annotators must work independently. Do not discuss rows before submitting
and hashing raw files. Lock Pass A/text-only decisions before exposing any
structured fields if the two-pass protocol is used. Compute agreement before
adjudication. After reliability is recorded, resolve disagreements using a
written rationale and retain both raw labels and adjudicated labels. A failed
pre-adjudication reliability result cannot be repaired by silently replacing
raw labels.

No human annotations are included in this package yet.
