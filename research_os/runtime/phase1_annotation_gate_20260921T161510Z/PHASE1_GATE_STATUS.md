# Phase 1 gate status

**Status:** `PREPARED_NO_ANNOTATIONS`

The project is now explicitly in **Phase 1: NLP-object validity**. The only
question being evaluated is whether independent annotators can stably decompose
a hypothesis into proposition, evidence pointer, scope, horizon, consequence,
falsifier, and assertion/qualification/abstention status.

Prediction score is out of scope. Phase 2 (text versus consequence/template
value) and Phase 3 (selective acceptance) are locked until Phase 1 passes.

## Required handoff

1. Two independent human annotators complete `PASS_A_TEXT_ONLY_BLIND.csv`.
2. Validate and hash both Pass-A files.
3. Lock Pass A before revealing `PASS_B_STRUCTURED_REVIEW_LOCKED.csv`.
4. Both annotators complete Pass B; double-code all rows listed in
   `DOUBLE_CODE_ROW_HANDLES.csv`.
5. Run the fail-closed validator and then pre-adjudication reliability scorer.
6. If any critical reliability threshold fails, mark `KILL / REDESIGN`; do not
   proceed to Phase 2.

No future outcomes, August labels, F/Delta, model losses, or prediction results
may be joined before the reliability result is locked.
