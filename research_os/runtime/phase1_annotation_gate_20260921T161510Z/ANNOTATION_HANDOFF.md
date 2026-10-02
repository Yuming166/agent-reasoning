# Phase 1 annotation handoff

Status: `PREPARED_NO_ANNOTATIONS`

1. Give annotators only `PASS_A_TEXT_ONLY_BLIND.csv` first.
2. Collect and validate each coder's Pass A submission against the exact schema.
3. Hash and lock both Pass A submissions; record the hashes in an external lock manifest.
4. Only then distribute `PASS_B_STRUCTURED_REVIEW_LOCKED.csv`.
5. Double-code every row whose handle appears in `DOUBLE_CODE_ROW_HANDLES.csv`.
6. Run the fail-closed validator before reliability scoring.
7. Run reliability scoring on the fixed 20-case roster. Do not adjudicate before the
   pre-adjudication gate is recorded.

No future outcomes, August labels, F/Delta, losses, split/date, wallet identity,
or model probabilities may be joined to annotation sheets before the reliability
result is locked.
