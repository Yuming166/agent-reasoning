# Phase 1 V2 annotation handoff

Status: `PREPARED_NO_ANNOTATIONS`

1. Release only `PASS_A_TEXT_ONLY_BLIND.csv` first.
2. Validate and hash both independent Pass A submissions against this exact V2 schema.
3. Record the two Pass A hashes before releasing Pass B.
4. Double-code all rows in `DOUBLE_CODE_ROW_HANDLES.csv`; primary uncertainty is clustered by case.
5. Run fail-closed validation and pre-adjudication reliability scoring.
6. Evaluate Gate 1A and Gate 1B separately; do not treat agreement as substantive validity.
7. Do not join August, future outcomes, F/Delta, losses, split/date, wallet identity,
   or model probabilities to annotation sheets before both gates are interpreted.
