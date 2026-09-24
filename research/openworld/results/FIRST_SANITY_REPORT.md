# Phase III-Explore first sanity check (OW-001--OW-004)

**Run date:** 2026-09-18

## Decision

**Status: HOLD / no LLM-gate pass yet.** The current graph-only evidence is sufficient to continue
with synthetic sensitivity and matched-control work, but not sufficient to start a large
Astra6 latent-strategy run or claim a label-free anomaly signal.

## External-label coverage audit (OW-001)

The local `dune_wash_trade_tx.csv` reference contains 22,702 rows and 22,551 unique
transaction hashes. It has no timestamp. After loading it into the private BigQuery
staging table `ictdata-507912.exgraph.openworld_wash_labels_v1` and joining only against
the leakage-audited temporal sequence table:

- matched hashes: **77 / 22,551**;
- matched sequence rows: **255**;
- matched months: March 11, April 13, May 45, June 4, July 4;
- August matched hashes: **0**;
- label overlap at the endpoint level before the join: 258 rows with at least one
  mapped endpoint, only 14 with both endpoints mapped.

The 77-hash overlap is an evaluation-coverage result, not an estimate of wash prevalence.
It is too sparse and temporally incomplete to support an August/September held-out
replication claim.

## Label-free transaction baselines (OW-002/OW-003)

Scores were frozen before reading label outcomes:

- activity: `log1p(sequence_rows)`;
- counterparty breadth: `log1p(unique_counterparties)`;
- structural complexity: activity + target/counterparty breadth + event-family diversity;
- directional imbalance;
- self-transaction fraction.

The temporal table was aggregated in BigQuery and only compact metric rows were returned.
The first top-K grid found **zero matched labels in the top 1,000 for every baseline in
March--July**. At wider K, isolated month/score combinations show enrichment, but they
do not replicate across months and there is no August label support. These are diagnostic
results only; they do not justify a pivot.

## Synthetic motif sensitivity (OW-004)

A bounded benchmark injected six known directed motifs (cycle, fan-in, fan-out,
rapid-forwarding, split/merge, reciprocal) into real daily EX-Graph edge backgrounds
under four noise/camouflage stages, 10 seeds, and 8 groups per run.

The benchmark is structural sensitivity only, not a criminal simulation. Node/group
recovery is non-trivial under several camouflage stages, but volume frequently matches or
beats the simple structural composite. Because injection volume was not yet matched,
this cannot establish group > node or structural > volume. The next required benchmark is
an amount/edge-count-matched negative control.

## Current protocol decision

1. Keep the wash reference strictly external-evaluation-only.
2. Do not use Astra6 for latent strategy hypotheses yet; the protocol requires a
   non-trivial graph-only signal before Step 13.
3. Add matched-volume/edge-count synthetic controls and temporal future-consequence
   tests.
4. Re-run external enrichment only if a timestamp-complete evaluation source or a
   larger overlap window becomes available.
5. If graph-only discovery survives those controls, use Astra6 with compact structured
   evidence packets, JSON hypotheses, abstention, and intervention/future verification.

## History-only future consequence (OW-006)

Using only 30 days of history at cutoffs 2022-05-01 through 2022-08-01, activity/breadth
and active-day scores predict future 30-day activity and new-counterparty growth. For
example, at the 2022-08-01 cutoff, top-100 active-day nodes have mean future volume
298.18 and mean future new counterparties 10.91, versus 309.64 and 9.32 for top-volume
nodes. Volume-decile-matched selection remains positive for active days and breadth,
but the matching is still coarse and this is a future-consequence association, not a
causal influence result.

This is the first graph-only signal worth pursuing, but it is not yet enough to pass the
external-enrichment gate: the result may still be an activity proxy, and group-level
stability has not been established.

## Static embedding and group-episode probes (OW-007/OW-008)

- A bounded `TruncatedSVD + IsolationForest` graph-embedding score was temporally
  unstable: its top-100 future-volume association was weak/negative in July and August.
  It is retained as a baseline, not as a discovery result.
- A shallow 7-day high-weight connected-component episode detector produced 73--142
  usable groups per cutoff under a 100-participant budget. Burst/reciprocity/volume
  sometimes exceeded random groups for future new-counterparty growth, but density was
  inconsistent and the group selections remained below the strongest top-node activity
  baseline. **H2 group > node is not supported yet.**

## Astra6-routed design and OW-009 pilot (2026-09-18)

To test whether the project could move beyond activity-only association without
starting a large LLM run, a compact structured request was routed to the private
Astra6 relay. The request asked for one experiment, fixed leakage-safe windows,
matched controls, metrics, and mechanical GO/NO-GO thresholds. No hidden reasoning,
raw graph, external labels, or credentials were stored. A second bounded Astra6
critique reviewed the resulting pilot.

The resulting `OW-009` detector was a fixed residualized score over day-level
counterparty novelty, counterparty growth, reciprocity change, and score-window
burstiness, conditional on pre-cutoff volume/activity. It used cutoffs 2022-06-01,
2022-07-01, and 2022-08-01, a 30-day history, a 7-day score window, 7/30-day
future windows, and 1:5 nearest-neighbor matching. The local input was the existing
matched-matched primary edge extract, so event-level timestamp, event-family,
native-value, and token features were unavailable and were not claimed.

The registered strict cohort had 370, 282, and 359 candidates; the expanded
three-event diagnostic cohort had 1,059, 811, and 898. Both failed the pre-registered
coverage requirement of 2,000 candidates and at least 100 top-5% addresses per
cutoff. The residual detector's strict median future-new-counterparty ratio was
6.21, but its median open-world ratio was 0.536 and its mean adjacent top-5%
Jaccard was 0.064. Some ratios were inflated by small control means; bootstrap
lower bounds, stability, and matching balance did not pass. Matching diagnostics
also showed absolute standardized differences above 0.10 in several panels.

**OW-009 decision: NO-GO / underpowered.** This is not evidence that the detector
works or fails in a sufficiently covered event-level population. Astra6's critique
selected `stop_as_underpowered`: freeze the pilot, do not tune the detector or
start latent-strategy calls, and only restart after compact event-level data is
materialized with the same leakage protocol, adequate candidate coverage, and
balanced matching.
