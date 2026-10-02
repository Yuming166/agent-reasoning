# OW-009 substrate repair plan

## Diagnosis

OW-009 is not a valid test of the intended full wallet×cutoff discovery
population.  The local input is a day-level, matched-matched, primary-only
projection of the 11,836,196-row sequence substrate.  It contains 13,020 unique
mapped endpoint nodes across the whole extract, and the OW-009 code then keeps
only `direction=outgoing` rows.  The strict 30-day cohort is only
370/282/359 at the three cutoffs.

The same project's existing compact all-primary 90-day as-of table contains
roughly 19--20k wallets per cutoff and, with `active_days>=3` and
`events>=10`, contains 16,326 / 15,554 / 14,557 wallets at June/July/August.
This is evidence that the current failure is primarily substrate/cohort
construction, not evidence that the structural hypothesis works.

## Required changes before a rerun

1. **Materialize the compact event-level/as-of table in BigQuery.** Use
   `BIGQUERY_FEATURE_SPEC.md`; preserve incoming and outgoing roles, all three
   event families, event timestamps, amounts, token identity, and unmapped
   counterparties for wallet-level counts.
2. **Keep discovery eligibility separate from evaluation.** Outer-join all mapped
   wallets to pre-cutoff feature rows. A wallet with no future event remains in
   discovery and receives a missing/zero outcome only in the evaluation table.
3. **Remove the silent outgoing-only population change.** Canonicalize events by
   source/destination for edge features, but compute wallet-level features from
   both roles. If source-only analysis is desired, register it as a separate
   estimand.
4. **Do not use `both endpoints mapped` as a discovery requirement.** Retain an
   unmapped counterparty token for activity/novelty. Restrict only network columns
   to mapped-counterparty coverage and report that coverage separately.
5. **Keep `active_days>=3` and `events>=10` as preregistered sensitivity strata,
   not as an implicit definition of all observable wallets.** Do not choose a
   new threshold by future or label results.
6. **Freeze matching diagnostics before any outcome analysis.** Report before and
   after SMD by covariate. The current procedure has no caliper and can report a
   match as successful even when post-match SMD exceeds 0.10; do not claim a
   matched comparison until the protocol specifies how imbalance is handled.
7. **Run substrate-only QA first.** Check row counts, wallet counts, event-family
   coverage, interval coverage, and as-of leakage. Do not run an anomaly ranking
   or external-label evaluation in the repair step.

## Restart gate (not a threshold amendment)

A later rerun should require, before detector results are inspected:

- at least 2,000 discovery wallets per cutoff under the declared population;
- at least 100 Top-5% wallets per cutoff if Top-5% remains the analysis budget;
- all matching covariates reported with absolute SMD <= 0.10 for the declared
  matched estimand, or a pre-registered alternative estimand;
- complete feature-side windows and a separate, explicit future-evaluation table;
- no use of wash labels or future outcomes for cohort selection.

## Interpretation

The present OW-009 result should be frozen as **SUBSTRATE_UNDERPOWERED /
DESIGN_REVISION_NEEDED**.  It is not a method-level NO-GO because the intended
wallet×cutoff population was never represented by the local input.  It is not
READY_FOR_RERUN until the event-level/as-of materialization and discovery-vs-
evaluation separation are implemented.

The `>=2,000` requirement is retained for now as a conservative, operational
restart gate.  The evidence below supports a later amendment discussion, not a
silent change:

- with 2,000 candidates and a 5% top cohort, treated n≈100;
- at outcome rate p=0.10, a single treated proportion has an approximate 95%
  margin of ±5.9 percentage points; a 1:5 treated-control difference has a
  rough 95% margin of ±6.4 percentage points under independent-binomial
  approximation;
- at p=0.50, the corresponding difference margin is about ±10.9 points;
- the ratio metric is unstable when the control rate is near zero, so future
  reports should include absolute rates and risk differences.

These are planning approximations, not a powered superiority claim.
