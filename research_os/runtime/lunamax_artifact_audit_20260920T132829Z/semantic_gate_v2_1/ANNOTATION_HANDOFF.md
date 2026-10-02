# Semantic Gate V2.1 annotation handoff

This package is exploratory and off-charter. It is not an Astra6 result or an official claim.

## Order

1. Give only `annotator_templates/coder_a/PASS_A.csv` to coder A and the corresponding coder B copy to coder B.
2. Do not distribute Pass B until both Pass A files are submitted, hashed, and validated.
3. The double-code roster is `DOUBLE_CODE_ROW_HANDLES.csv`; it identifies 60 opaque rows from 20 fixed cases.
4. After Pass A is locked, distribute the corresponding Pass B copies.
5. Validate each file with `validate_semantic_gate_annotations.py`.
6. Score reliability with `score_semantic_gate_reliability.py` before adjudication.

Do not expose wallet IDs, dates, splits, F, Delta, model losses, outcomes, or August membership during annotation.
