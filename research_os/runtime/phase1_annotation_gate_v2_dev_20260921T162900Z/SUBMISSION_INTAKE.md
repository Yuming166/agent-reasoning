# Phase 1 V2 submission intake

Protocol state: `FROZEN_PRE_ANNOTATION`  
Pass B state: `LOCKED_PRE_PASS_A`

Submit exactly two completed CSV files, using the frozen assignment schemas:

- `submissions/PASS_A_CODER_A.csv`
- `submissions/PASS_A_CODER_B.csv`

Each file must contain exactly its assigned 180 rows and the exact frozen Pass-A
columns. Do not include case IDs, cutoff dates, wallet IDs, outcomes, scores,
model metadata, or any extra columns. The intake workflow will reject blank,
changed, duplicated, missing, or extra rows. It will hash and lock each file
only after independent validation succeeds.

Pass B is not present in this release directory. It can be released only by the
workflow after both Pass A submissions validate and their hashes are recorded in
`PASS_A_SUBMISSION_LOCK.json`.
