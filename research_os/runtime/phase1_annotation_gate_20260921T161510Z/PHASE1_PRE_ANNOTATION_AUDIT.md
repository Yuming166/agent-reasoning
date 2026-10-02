# Phase 1 Pre-Annotation Audit

**Audit created:** `2026-09-21T16:27:59Z`  
**Audited package:** `research_os/runtime/phase1_annotation_gate_20260921T161510Z/`  
**Conclusion:** `PROTOCOL_REPAIR_REQUIRED`

## Scope and preservation

This audit is a pre-annotation check only. It reads the frozen panel metadata and the existing package roster; it does not read or join future outcomes, F, Delta, model losses, or outcome labels into annotation worksheets. The existing package is preserved byte-for-byte and is not silently overwritten.

The current package is retained as **retrospective feasibility material**. Because its sampled hypothesis texts include August frozen-test cases, it must not be used as the primary V2 development evidence or for designing a new representation before a clean development-only package is frozen.

## 1. Roster independence: FAIL

- Frozen source full cases: `3000` records / `3000` unique cases.
- Source cutoff distribution: `{'2022-06-01': 1000, '2022-07-01': 1000, '2022-08-01': 1000}`.
- Source cutoff-to-split mapping: `{('2022-06-01', 'train'): 1000, ('2022-07-01', 'dev'): 1000, ('2022-08-01', 'test'): 1000}`.
- Existing package sample: `100` cases / `300` hypothesis rows.
- Existing package sample by cutoff: `{'2022-06-01': 40, '2022-07-01': 38, '2022-08-01': 22}`.
- Existing double-code cases by cutoff: `{'2022-06-01': 30, '2022-07-01': 21, '2022-08-01': 9}`; double-coded rows observed: `60`.

The existing sample contains **22 August cases and 66 August hypothesis rows**; the double-code roster contains **3 August cases**. August is the frozen test cutoff, and the hypothesis text itself is a model output that could influence V2 schema or representation design even without future outcomes. Therefore outcome blindness does not establish test-set independence.

**Required repair:** freeze a new, deterministic, outcome-blind roster using only June and July development cases. The recommended design is 50 June + 50 July cases, with a balanced 10 June + 10 July double-code roster. Keep the old package and its hashes unchanged.

## 2. Double coding and clustering: REPAIR REQUIRED

The current package has `20` double-coded cases and `300` total rows, with `60` double-coded rows. The three hypotheses within a case share the same case-level context and are not 60 independent sampling units. The primary uncertainty unit must therefore be the 20 cases; row-level agreement can be reported as a descriptive supplement.

The repaired protocol must report both row-level agreement and case-clustered uncertainty, with the case-clustered result governing interpretation.

## 3. Reliability estimands and undefined kappa: REPAIR REQUIRED

Field-level reliability is primary. A pooled Cohen kappa may be reported only as a descriptive summary after an explicit pooling rule is frozen; it cannot replace field-level results. If a field has one observed category in the double-coded data, Cohen kappa is not estimable. The preregistered output must be `NOT_ESTIMABLE`, never 1.0 and never silently omitted after seeing the labels. A non-estimable critical field cannot be declared a reliability pass by substitution.

## 4. Gate separation: REPAIR REQUIRED

The current package operationalizes a reliability gate but does not freeze a separate substantive-object gate. The repaired protocol must separate:

- **Gate 1A — Annotation Reliability:** whether independent annotators can identify the fields consistently.
- **Gate 1B — Object Substantive Validity:** what fraction of rows contain a well-formed, operational, observable, evidence-linked, and falsifiable claim.

Passing Gate 1A must not be interpreted as evidence that the generated hypothesis object is substantively useful.

## 5. Gate 1B fields and thresholds: REPAIR REQUIRED

Before any formal annotations are viewed, the repaired protocol must freeze row-level estimands for:

1. well-formed proposition;
2. explicit scope;
3. explicit time horizon;
4. observable consequence;
5. executable falsifier;
6. valid evidence link;
7. non-trivial qualification/abstention.

Thresholds must be recorded before annotation and must not be selected after inspecting the annotations. If the thresholds are exploratory rather than confirmatory, the package must label them as such and keep them separate from any later holdout claim.

## 6. Executable falsifier: REPAIR REQUIRED

The current `falsifier_status` field does not distinguish an executable falsifier from a verbal caveat. The repaired schema must distinguish at least:

- `executable`: tied to an observable future event or direction and a stated/operational horizon;
- `caveat_only`: hedging or uncertainty language without a checkable disconfirming condition;
- `absent`;
- `unclear`.

An `explicit` falsifier label alone is not sufficient for Gate 1B.

## 7. Evidence support semantics: REPAIR REQUIRED

Pass B must distinguish evidence that directly supports a historical/descriptive premise from evidence that is merely consistent with a future prediction. The revised evidence judgment must include separate labels for:

- direct descriptive support;
- evidence-consistent predictive claim;
- unsupported;
- contradicted;
- unclear;
- not applicable.

Historical evidence that transaction frequency declined can directly support the descriptive premise that frequency declined; it does not entail that activity will decline over the next seven days.

## 8. Negative control and horizon discipline: REPAIR REQUIRED

- `E_PLACEBO` must be explicitly defined as a negative-control evidence channel. It must not automatically count as claim support; reaction to it is coded as negative-control/provenance failure or irrelevant under the frozen rubric.
- Pass A must not infer a missing horizon from task instructions or the recorded structured output. If the text does not state a horizon, annotate `absent` or `unclear` and leave the horizon span blank.
- `E_MARKET` must remain visibly distinguished from the pure on-chain evidence condition if the formal task is restricted to on-chain input.

## 9. Current decision and next action

`PROTOCOL_REPAIR_REQUIRED` is the only valid conclusion for this package. Do not release its Pass A sheet as the primary V2 annotation sample. The next append-only package should be a new protocol version restricted to June/July, with the Gate 1A/1B split, executable-falsifier field, revised evidence labels, explicit E_PLACEBO negative-control rule, and case-clustered reliability plan frozen before human annotation.

## Reproducibility anchors

- Source panel SHA-256: `047f999c1dde6b2f47d7601f3bb41fe6a457b6dbad028932e0469b95e7effe2b`.
- Source manifest SHA-256: `2ccda847b7409003b535c3cd8025c8fd481d412227a77c612336ed0be9fd9970`.
- Existing Pass A SHA-256: `5cf9d120719518348471a52e254859f20a1ef1d106a2424e29595229dbcc9404`.
- Existing Pass B SHA-256: `805248a24904d6a8db6fbb6d7081e781e96875d33c0c34f5380687ef959c097a`.
- Existing double-code roster SHA-256: `5585e3471a0fd9faf799dc0d8edd180a12de30bfce4d55fd6b0f4935275e36c3`.
- Existing blinding audit SHA-256: `7e6286d7994d472b0ba8868ade88c5f5734a5a62279a40f17cf348811b3c3829`.

The audit itself does not alter the official Astra6 cycle, claim ledger, experiment registry, August frozen test, or any model output.
