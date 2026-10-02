# Phase 1 Pre-Annotation Audit — V2 development package

**Audit created:** `2026-09-21T16:35:55Z`  
**Package:** `research_os/runtime/phase1_annotation_gate_v2_dev_20260921T162900Z/`  
**Conclusion:** `READY_TO_ANNOTATE`

## Meaning of this decision

`READY_TO_ANNOTATE` means that the repaired package is protocol-ready for two independent human Pass-A annotators. It does **not** mean that Gate 1A reliability or Gate 1B substantive validity has passed; both remain pending annotation.

## Audit checks

- Source full panel: `3000` full cases; cutoff distribution `{'2022-06-01': 1000, '2022-07-01': 1000, '2022-08-01': 1000}`.
- V2 roster: `100` cases / `300` hypothesis rows; cutoff distribution `{'2022-06-01': 50, '2022-07-01': 50}`.
- V2 double-code roster: `20` cases / `60` rows; cutoff distribution `{'2022-06-01': 10, '2022-07-01': 10}`.
- August (`2022-08-01`) is excluded from both the selected roster and double-code roster.
- Selection is balanced, deterministic, case-hash based, and outcome-blind.
- Case is the primary uncertainty unit; row-level agreement is descriptive only.
- Field-level reliability is primary; pooled summaries are descriptive only.
- Undefined Cohen kappa is frozen as `NOT_ESTIMABLE`; no coercion to 1.0 and no post-hoc omission.
- Gate 1A reliability and Gate 1B substantive validity are separate locked gates.
- Gate 1B includes well-formed proposition, explicit scope/horizon, observable consequence, executable falsifier, valid evidence link, and non-trivial qualification/abstention.
- `falsifier_executability` distinguishes executable conditions from `caveat_only`.
- Pass B distinguishes `direct_descriptive` from `predictive_consistent` evidence support.
- `E_PLACEBO` is a negative-control channel and cannot count as a valid evidence link.
- Pass A explicitly forbids inferring a missing horizon from task instructions or structured output.
- Pass B remains locked until both Pass-A submissions are hashed.

## Verification artifacts

- Blank schema validation: `PASS` with `0` errors.
- Blank reliability smoke: `RELIABILITY_NOT_YET_ASSESSABLE` for `20` cases / `60` rows; this is expected before annotations.
- Deliberately malformed fixture: `FAIL`, observed exit code `2`; fail-closed behavior confirmed.
- Original V1 package preservation checks: `{'PASS_A_TEXT_ONLY_BLIND.csv': True, 'PASS_B_STRUCTURED_REVIEW_LOCKED.csv': True, 'DOUBLE_CODE_ROW_HANDLES.csv': True, 'BLINDING_AUDIT.json': True}`.

## Decision

`READY_TO_ANNOTATE`. Release only `PASS_A_TEXT_ONLY_BLIND.csv` to the two independent human annotators. Do not release Pass B yet. Do not open Phase 2 or Phase 3. If Gate 1A fails, kill/redesign the schema; if Gate 1A passes but Gate 1B is substantively weak, report the object as weak and do not automatically proceed.

## Reproducibility anchors

- V2 source panel SHA-256: `047f999c1dde6b2f47d7601f3bb41fe6a457b6dbad028932e0469b95e7effe2b`.
- V2 Pass A SHA-256: `feb52a1e0d14a1242132adaa0bd4e20d48080b9ab59a2820cfb651ef36a1f93b`.
- V2 Pass B SHA-256: `877a8858961c839540fe59fd94a4186ee653ab0ac33c10167dc186681e32836c`.
- V2 double-code roster SHA-256: `c0bef4f2333fe9bde2dce760b14fc10582f5d8766930e6b4f3888733b77be635`.
- V2 blinding audit SHA-256: `969f1c3f05c9b58202890659ba56b3ec253d689c827e559180cc729043a19bd3`.
