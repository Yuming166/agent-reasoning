# June LLM panel parse anomaly audit

> Generated at `2026-09-10T09:04:39+00:00`. This audit is read-only with respect to all input panels and does not call an LLM endpoint.

## Decision

- **June v2 float-fix is not eligible for router training as-is.** It has a large combined parser/response-validity failure: full `32.2%` and no-CF `33.9%` (rates shown as percentages below).
- The evidence is consistent with a June-specific runtime/service failure signature, not candidate-support failure: all observed June v2 float-fix rows have `truth_in_pool=1`, while `636` rows have zero total usage, `678` rows have fewer than the expected four calls, and `636` rows jointly show short calls, zero usage, and the observed >=45-second latency plateau.
- Exact invalid-JSON, missing-field, and transport-timeout counts are **unavailable** because the historical CSVs did not persist raw responses or per-call status/error payloads. The flags are combined parser/schema/candidate-ID outcomes.
- The pre-float-fix v2 June file is not usable training evidence because its `full_rr` and `nocf_rr` columns are boolean-like rather than numeric. v1 June is retained as a historical diagnostic, not silently substituted for corrected v2 data.

## Authorized rerun result

- The June-only rerun used the authorized `Qwen3.5-4B` service and the same frozen panel, snapshot, temperature, and 700-token cap. The optional `reasoning_effort` field was omitted because this Qwen/vLLM deployment otherwise spent the 700-token completion budget on hidden reasoning and returned no JSON content.
- The corrected rerun is evaluated separately from the historical GLM/v2 files; it does not overwrite them and it is not evidence of cross-model superiority.

| rerun | rows | full parse | no-CF parse | per-step non-ok | client errors | response model | median latency | median total tokens | decision |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| v2 June authorized Qwen/vLLM rerun 1 | 1000 | 100.0% | 100.0% | 2 | 0 | Qwen3.5-4B | 11.782s | 8975.0 | eligible_with_audited_stage3_candidate_fallback |

For the rerun, all 1,000 full/no-CF outputs parsed, all events had four calls and nonzero usage, all candidate truths were supported, event keys were unique, RR columns were numeric, and the response model was `Qwen3.5-4B`. Two step-3 fusion responses were classified as unknown candidate IDs; both retained a valid final rank equal to the mask-stage rank, so the audit labels this as an explicit stage-3 candidate fallback rather than silently calling it a clean run.

## June run summary

| run | rows | full parse | no-CF parse | obs/mask/full/no-CF rank present | zero total tokens | calls <4 | median latency | numeric RR issue | decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| v1 historical June | 1000 | 99.9% (1 fail) | 100.0% (0 fail) | 1000/999/1000/1000 | 0 | 1 | 21.1695s | 0/0 | diagnostic_only_until_protocol_review |
| v2 June pre-float-fix | 1000 | 100.0% (0 fail) | 100.0% (0 fail) | 1000/1000/1000/1000 | 0 | 0 | 13.191500000000001s | 1000/1000 | not_eligible_buggy_numeric_schema |
| v2 June unsuffixed | — | — | — | — | — | — | — | — | missing |
| v2 June float-fix | 1000 | 32.2% (678 fail) | 33.9% (661 fail) | 341/333/352/339 | 636 | 678 | 45.096s | 0/0 | not_eligible_parse_anomaly |
| v2 June authorized Qwen/vLLM rerun 1 | 1000 | 100.0% (0 fail) | 100.0% (0 fail) | 1000/1000/1000/1000 | 0 | 0 | 11.782s | 0/0 | eligible_with_audited_stage3_candidate_fallback |

`obs/mask/full/no-CF rank present` is a count of positive numeric ranks, not a claim that the corresponding raw response was valid. For the v2 float-fix June run, the exact counts are shown in the JSON manifest; the missing ranks are a proxy for stage parse/schema/ID failure.

## What is and is not observed

| quantity | status | interpretation |
|---|---|---|
| event rows, unique event keys, duplicate keys | exact | recomputed from CSV |
| candidate support (`truth_in_pool`) | exact | recomputed from CSV; support is not the June failure |
| full/no-CF parse flags | exact as recorded | `1` means the run-level output path produced a valid usable result according to the old writer |
| invalid JSON count | unavailable | raw completion text was not persisted |
| missing required response field count | unavailable | raw parsed objects were not persisted |
| exact timeout/transport-error count | unavailable | no per-call error/status column was persisted |
| operational fallback count | derived | every parse flag failure treated as cheap fallback for router-data eligibility |
| rerun per-step status/model/error/finish fields | exact for the instrumented rerun | persisted as aggregate fields without response text; two known step-3 candidate-ID fallbacks are visible |

## Grouped diagnostics

For June v2 float-fix, failure is not uniform across panel strata. The manifest records exact aggregate counts by stratum/activity; this is a diagnostic signal only because the CSV has no per-call timestamps or raw errors.

| stratum | activity | n | full parse | no-CF parse | zero total tokens | short calls | median latency |
|---|---|---:|---:|---:|---:|---:|---:|
| new_popular | high | 125 | 25/125 | 27/125 | 95 | 100 | 45.141s |
| new_popular | low | 125 | 8/125 | 9/125 | 116 | 117 | 45.11s |
| new_tail | high | 125 | 21/125 | 19/125 | 95 | 104 | 45.157s |
| new_tail | low | 125 | 3/125 | 5/125 | 120 | 122 | 45.104s |
| repeat_easy | high | 125 | 19/125 | 25/125 | 99 | 106 | 45.096s |
| repeat_easy | low | 125 | 10/125 | 14/125 | 111 | 115 | 45.097s |
| repeat_hard | high | 125 | 119/125 | 118/125 | 0 | 6 | 17.048s |
| repeat_hard | low | 125 | 117/125 | 122/125 | 0 | 8 | 20.285s |

The local-weight preflight remains separate from the authorized shared-service run: the rerun manifest records `endpoint_scope=authorized_shared_qwen`, model `Qwen3.5-4B`, and no local model path. No prohibited endpoint, raw response text, bearer token, or another user's model weights were used.
The runner's opt-in `--audit-details` mode was used for the real rerun and records per-step status/error class, response model, finish reason, token usage, reasoning presence, and latency without response text.

## Cross-run and month comparison

- The JSON manifest includes pairwise June event-key overlap and exact field-match counts. v1 and v2 candidate pools are intentionally different, so rank equality across versions is diagnostic only.
- July/August reference summaries are included to test whether the anomaly is month-specific. They retain parse, RR schema, latency, and token summaries without copying response text.
- Eval JSONL summaries are checked against recomputed row counts and parse rates. A matching summary does not repair the underlying lack of raw error observability.

## Next action

1. Keep the historical June v2 float-fix file quarantined; do not train the router on its raw gains, and do not silently substitute v1 June.
2. The authorized Qwen rerun is structurally usable as corrected June training evidence only under the documented fallback policy: 1,000/1,000 full and no-CF parse, zero transport errors, and two explicit step-3 candidate-ID fallbacks to the mask-stage rank.
3. If a strictly clean no-fallback label is required, rerun or separately review those two event keys before freezing the router dataset; otherwise carry the two-event exception into the router manifest and sensitivity check.

## Reproducibility

- Audit script: `src/agent/audit_june_parse_anomaly.py`
- JSON manifest: `artifacts/llm_panel_v2/june_parse_audit.json`
- Source root: `/storage/gaoym/ex-graph-microtransaction-analysis`
- No raw response text, bearer token, endpoint credential, or prompt body is written by this audit.
