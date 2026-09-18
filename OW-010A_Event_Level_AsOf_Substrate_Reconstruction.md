# OW-010A --- Event-Level As-of Substrate Reconstruction

## Codex Execution Protocol

**Project:** Open-World Behavioral Anomaly Discovery on Ethereum\
**Phase:** OW-010A\
**Mode:** substrate reconstruction only\
**Hard stop:** Do not proceed automatically to OW-010B.

## 0. Mission

Reconstruct a leakage-safe, event-level, as-of Ethereum substrate
suitable for open-world temporal behavioral discovery.

OW-009 must not be interpreted as a method-level NO-GO. Its local
artifact narrowed the intended population through primary-only events,
counterparty-present, non-self, both endpoints EX-Graph-mapped,
outgoing-only, day-level aggregation, `active_days >= 3`, and
`hist_events >= 10`, yielding only 370/282/359 candidates.

The objective is not to improve anomaly performance. Build the correct
`(wallet, cutoff_time)` discovery substrate, quantify coverage, audit
temporal semantics, and determine whether it supports a sufficiently
large leakage-safe open-world population. Do not use wash/illicit
labels.

## 1. Hard stop rules

Do not optimize anomaly detectors, build a new GNN, run latent-strategy
inference, generate pseudo-labels, inspect wash labels, evaluate wash
enrichment, select thresholds using downstream performance, tune
substrate for positive results, blanket-fill missing values with zero,
or proceed to OW-010B.

## 2. Intended population

Primary anchors are EX-Graph-mapped Ethereum wallets with valid
pre-cutoff event history.

`anchor mapped` does **not** imply `counterparty mapped`. Retain
interactions between mapped anchors and any observable Ethereum address.

Observational unit: `(wallet_i, cutoff_t)`. Discovery may use only
`G_<t`. No at/post-cutoff information may affect eligibility, features,
normalization, ranking, or cohort construction.

## 3. Cutoffs

At minimum: 2022-06-01, 2022-07-01, 2022-08-01. Preserve September only
if cleanly supported. Record timezone semantics. Use deterministic
half-open intervals: history `[start, cutoff)`, future `[cutoff, end)`.

## 4. Event families and canonical schema

Preserve separately: external/native transactions, token transfers,
internal traces/calls.

Minimum fields where available:
`event_family, block_timestamp, block_number, transaction_hash, transaction_index, event_index, trace_address/identity, from_address, to_address, native_value, token_quantity, token_contract, token_id, call_type/trace_type, status/success`.

Document unavailable fields; never fabricate identifiers.

## 5. Event identity / deduplication

Audit duplicate rows, duplicate identities, token logs, trace
identities, failed/reverted events, shared transaction hashes, and
multi-layer representations of the same economic transaction.

Keep separate counts:
`n_external_transactions, n_token_transfer_events, n_internal_trace_events, n_unique_transaction_hashes, n_all_events`.

Write an explicit semantic policy for every count/amount feature.

## 6. Anchor expansion and direction

For every mapped anchor include events where it is
`from_address OR to_address`. Define relative direction:
`incoming, outgoing, self`.

Do not silently discard self-transactions. For each anchor-event pair
define `anchor_wallet, counterparty, direction`. Document self-event
convention.

## 7. Counterparty coverage

Allow mapped and unmapped counterparties. Add
`counterparty_is_exgraph_mapped` where possible.

For each cutoff report mapped/unmapped interaction fractions and unique
mapped/unmapped counterparties. Quantify what OW-009 lost from requiring
both endpoints mapped.

## 8. Temporal ordering

Preserve sub-day ordering using block number, transaction index, and
family-specific event index/trace identity. Timestamp alone must not be
assumed to uniquely order a block.

The substrate should support inter-event gaps, burstiness, rapid
forwarding, short-horizon fan-in/out, temporal reciprocity, temporal
cycle proxies, split/merge. Mark unsupported behaviors rather than
silently approximating them.

## 9. Discovery windows

Where feasible construct `[t-1h,t)`, `[t-6h,t)`, `[t-1d,t)`, `[t-7d,t)`,
`[t-30d,t)`, `[t-30d,t-7d)`. Do not require activity in every window.

## 10. Observability sensitivity

Do not automatically reinstate `active_days >= 3` or
`hist_events >= 10`.

Report cohort sizes for event thresholds
`>=1, >=3, >=5, >=10, >=20, >=50` and active-day thresholds
`>=1, >=2, >=3, >=5, >=10`, including useful cross-tabs. This is
coverage analysis, not performance-based threshold selection.

## 11. Physically separate discovery and evaluation

Create a pre-cutoff discovery table, suggested
`openworld_wallet_cutoff_features_v1`, keyed by
`(anchor_wallet, cutoff_time)`.

Create a post-cutoff future table, suggested
`openworld_wallet_cutoff_future_outcomes_v1`, with the same key and all
fields explicitly `evaluation_only`.

Never join future outcomes during discovery construction.

## 12. Compact feature table

Activity: all/unique/external/token/internal event counts; in/out/self;
active hours/days; inter-event gap statistics; mathematically defined
burstiness.

Counterparty: unique in/out/all; new/repeat count/rate; entropy;
mapped/unmapped counts/fraction. Define "new" only from pre-cutoff
history.

Flow: native inflow/outflow/netflow; token in/out counts; amount
summaries; concentration; flow-conservation proxy. Never aggregate
incomparable token quantities as one economic amount.

Temporal structure where faithful: reciprocity, temporal reciprocity,
rapid forwarding, fan-in/out proxies, cycle proxy, split/merge proxy,
turnover, concentration, short-horizon repeat rate. Give exact
algorithms.

Composition: external/token/internal fractions, native/token interaction
fractions, token diversity, reliable contract interaction fraction.

Network/ego: temporal degree, weighted degree, in/out degree, ego
density, bridge/local clustering proxies computed strictly pre-cutoff.

## 13. Missingness semantics

No blanket `fillna(0)`. Classify each missing value as `TRUE_ZERO`,
`UNOBSERVED`, `NOT_APPLICABLE`, `UNSUPPORTED`, or `EXTRACTION_FAILURE`.
Add indicators where useful. Produce a missingness audit.

## 14. Future outcomes

Evaluation-only windows `[t,t+7d)` and `[t,t+30d)`.

Prepare event count, active days, unique/new counterparties, meaningful
inflow/outflow, counterparty entropy, reciprocity, burstiness,
composition, turnover, and defensible pre/post change variables.

Do not choose the final OW-010B target yet.

## 15. Behavioral-change preparation

Prepare but do not optimize against a possible future vector:
`Y_future = [ΔActivity, ΔCounterparty, ΔReciprocity, ΔFlow, ΔEntropy, ΔComposition]`.

OW-010A only establishes leakage-safe computability.

## 16. BigQuery-first policy

Heavy processing stays in BigQuery. Do not export millions of raw rows
unless narrowly necessary.

Preferred outputs: wallet×cutoff feature table, wallet×cutoff future
table, coverage/candidate/missingness/event-family summaries.

For jobs record query name, SQL hash, sources, destination, row count,
bytes processed/billed, execution timestamp. Save SQL for persistent
artifacts.

## 17. Mandatory QA

Assert: - discovery `MAX(source_event_timestamp) < cutoff`; - future
events are `>= cutoff` and `< horizon end`; - every row has an allowed
mapped anchor; - unmapped counterparties are allowed; -
incoming/outgoing are retained; - all available event families
represented; - no accidental duplicate inflation; - one compact row per
`(anchor_wallet, cutoff)`; - no unjustified zero-fill; - deterministic
row counts under frozen sources.

## 18. Population funnel

Per cutoff report: all mapped anchors → observed pre-cutoff → \>=1
event/30d → \>=3 → \>=5 → \>=10 → \>=20, plus \>=1/3/5 active days, and
incoming-only/outgoing-only/both coverage.

Compare against OW-009 370/282/359.

Quantify recovery from allowing unmapped counterparties, restoring
incoming roles, restoring event families, removing day compression, and
relaxing legacy gates. Do not add overlapping recovery effects
incorrectly.

## 19. \>=2,000 restart gate

Do not modify the operational restart gate in OW-010A. Report whether
`N_discovery >= 2000` under transparent observability definitions.

The preferred substrate should support \>=2,000 per cutoff without
scientifically artificial filtering. At completion recommend
keep/amend/replace only for a later preregistration amendment.

## 20. Wash-label firewall

Wash labels are inaccessible in this phase. Do not load, inspect, count,
enrich, tune, QA, or expose them to Astra6/another LLM.

Protocol: substrate reconstruction → substrate freeze → blind
temporal/graph experiment → detector freeze → one-shot external-label
evaluation.

## 21. Required repository outputs

Create:

`research/openworld/substrate/ow010a/` - `README.md` -
`DATA_CONTRACT.md` - `EVENT_SCHEMA.md` - `EVENT_IDENTITY_POLICY.md` -
`BIGQUERY_MATERIALIZATION.md` - `MISSINGNESS_POLICY.md` -
`POPULATION_AUDIT.md` - `QA_REPORT.md` - `OW010A_FINAL_REPORT.md` -
`sql/00_source_audit.sql` - `sql/01_anchor_events.sql` -
`sql/02_event_identity_audit.sql` - `sql/03_discovery_features.sql` -
`sql/04_future_outcomes.sql` - `sql/05_population_summary.sql` -
`results/candidate_counts_by_cutoff.csv` -
`results/observability_sensitivity.csv` -
`results/event_family_coverage.csv` -
`results/counterparty_mapping_coverage.csv` -
`results/direction_coverage.csv` - `results/missingness_audit.csv` -
`results/event_identity_audit.csv` -
`results/temporal_leakage_audit.csv` -
`results/materialization_manifest.json`

Update `research/openworld/EXPERIMENT_REGISTRY.yaml`. Do not overwrite
OW-009.

## 22. Manifest minimum

Record experiment=OW-010A, source versions, cutoffs, event families,
anchor population, counterparty policy, history/future windows,
discovery/future tables, SQL hashes, row counts, bytes processed, QA
status, and `"wash_label_accessed": false`.

## 23. Final report questions

Answer exactly: 1. What is the intended anchor population? 2. How many
leakage-safe discovery anchors exist per cutoff? 3. How many are
recovered vs OW-009? 4. Attrition from both-endpoints-mapped? 5.
Attrition from outgoing-only? 6. Attrition from active-day/event
thresholds? 7. Information lost through day aggregation? 8. Correct
semantics for native/token/internal? 9. Defensible identity/dedup rules?
10. Reliable incoming/outgoing reconstruction? 11. Reliable
unmapped-counterparty retention? 12. Sufficient temporal ordering for
inter-event/rapid-forwarding? 13. Which temporal/motif features are
faithful? 14. Which remain unsupported/ambiguous? 15. Missingness
separated from true zero? 16. Discovery/future physically and logically
separate? 17. Did all leakage QA pass? 18. Candidate counts by
observability threshold? 19. Does each cutoff plausibly support
\>=2,000? 20. Suitable for OW-010B? 21. Remaining data risks? 22. Final
status: `SUBSTRATE_REPAIR_FAILED`, `SUBSTRATE_REPAIR_PARTIAL`, or
`SUBSTRATE_READY_FOR_OW010B`.

## 24. Decision rule

Prefer the largest **scientifically defensible, leakage-safe,
event-level open-world cohort**, not simply the largest cohort.

Declare `SUBSTRATE_READY_FOR_OW010B` only if event-level semantics are
preserved; unmapped counterparties and both directions are retained;
discovery/future are separated; no material leakage exists;
deduplication is defensible; missingness is not collapsed into zero;
coverage is adequate; preferably every cutoff exceeds 2,000; and QA is
reproducible.

Otherwise stop and document failure.

## 25. Context for OW-010B --- DO NOT EXECUTE

Expected next question:
`Does pre-cutoff temporal graph structure predict future behavioral change beyond activity and volume?`

Likely ladder:
`M0 Activity/Volume → M1 Temporal statistics → M2 Structural+temporal statistics → M3 Self-supervised temporal graph representation`.

OW-010B must be designed only after reviewing OW-010A. Do not
pre-optimize this substrate for that target.

## 26. Operating principle

Treat OW-010A as scientific-instrument construction, not a search for
positive results.

Central question:

> Do we now possess a faithful event-level view of each mapped wallet's
> observable Ethereum behavior at cutoff time?

When complete, STOP and return the generated reports and concise status
summary. Do not start OW-010B without explicit authorization.
