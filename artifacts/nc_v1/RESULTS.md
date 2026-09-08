# Next-counterparty candidate model v1 (frozen August 2022)

Split: all primary outgoing events with present non-self counterparty.
History strictly before test month (Mar 1 - Jul 31). August: 457,128 events
(285,428 repeat within prior 90d = 62.4%; 171,700 new = 37.6%).

## Repeat counterparty (rank among wallet's own prior neighbors)
| model | n | MRR | R@1 | R@5 | R@10 |
|---|---|---|---|---|---|
| personal frequency | 213,285* | .346 | .174 | .561 | .705 |
| personal freq x recency(90d half-life) | 213,285 | .374 | .203 | .591 | .734 |
*72,143 "repeat" events are same-month repeats (pair unseen in Mar-Jul edge
table) and are not rankable from frozen history; 213,285 repeats are history-known.

## New counterparty (rank among non-neighbors by historical global popularity)
| model | n | MRR | R@1 | R@5 | R@10 |
|---|---|---|---|---|---|
| global historical popularity (all candidates) | 171,700 | .0118 | .00002 | .0207 | .0348 |
| global over non-neighbors only | 171,700 | .0238 | .0121 | .0360 | .0498 |
| two-hop bridge pool-first hybrid | 171,700 | .0129 | .0069 | .0183 | .0243 |

Two-hop bridge: truth lies in the wallet's bridge candidate set for only
10,134/171,700 new events (5.9%). On that sub-pool:
| scorer | MRR | R@1 | R@10 |
|---|---|---|---|
| global non-neighbor popularity | .112 | .068 | .220 |
| bridge signal | .076 | .043 | .132 |
| oracle best-of-two | .141 | .089 | .257 |
Bridge wins rank on 59.8% of sub-pool events but loses badly on the rest;
a fixed pool-prepend hybrid hurts. ORACLE combiner headroom = +25% MRR,
motivating a per-event learned scorer selector / learned candidate ranker.

## Combined pipeline (repeat->personal recency, new->global non-neighbor)
All 457,128 August events: MRR .185, R@1 .097, R@5 .295, R@10 .368.

## Boundaries / next
- Popularity/personal baselines only; no embedding/GNN/LLM yet.
- Bridge signal uses undirected-flow 1/outdeg; time-decayed or learned edge
  weights are v2.
- Next: learned candidate ranker (features per (u,v): personal stats, global
  pop, bridge signal, token overlap, archetype) and per-event scorer gating
  feeding the P4 router; then budgeted agent DeltaMRR/token.

## 2026-09-09 update: learned ranker, event gate, and sampled-pool caveat

Stage B materialized `exgraph.nc_ranker_samples_v2` (28,472,717 rows for
June/July/August; 1 positive plus deterministic sampled negatives per new
event). The first learned HistGBM ranker reached a very high sampled-pool MRR
(0.896 in August), but the audit identified an important support artifact:
negatives were drawn only from the historical global top-2000 support, while
82.2% of August positives were outside that support and carried the sentinel
`g_rank=99999`. The model can therefore separate most positives trivially.
That number is retained only as a diagnostic and must not be reported as
full-candidate predictive performance.

The support-restricted audit (`evaluate_supported_pool.py`) retains only events
whose observed positive is in top-2000 (30,610/171,700 August events = 17.8%).
Within the comparable approximately-50-row sampled pool:

| scorer | MRR | R@1 | R@5 | R@10 |
|---|---:|---:|---:|---:|
| global popularity | .448 | .343 | .543 | .636 |
| learned ranker | .456 | .351 | .550 | .642 |
| oracle best scorer/event | .505 | — | — | — |

Thus the honest pilot result is a modest +0.0083 MRR (+1.85% relative) from the
learned candidate ranker on supported events, not a near-solved task. Oracle
per-event best selection has +0.0569 MRR headroom over global popularity. A
July-trained leakage-safe event gate transfers weakly to August (AUROC .557;
AUPRC .278 at 23.0% learned-winner base rate). At a 10% deliberation budget it
improves MRR by only +0.0029 versus +0.0528 oracle; therefore current
pre-event context is not sufficient to realize the per-event headroom.

The reported token number is a fixed proxy (32 cheap units; 96 deliberation
units), not a measured LLM token count. Next work should expand negatives
beyond top-2000 (bridge/tail/hybrid strata), use all negatives rather than
~1/40 sampling for event support, and add as-of wallet/token/social context to
the gate.
