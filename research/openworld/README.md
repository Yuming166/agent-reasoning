# Phase III-Explore: Label-Free Open-World Behavioral Anomaly Discovery

This directory implements the exploratory protocol from
`autoresearch_openworld_blockchain_anomaly_exploration.md`.

## Current status

- `OW-000`: protocol freeze and data/label boundary audit — in progress.
- `OW-001`: external wash-label overlap and timestamp feasibility — first sanity check.
- No wash/illicit labels are used for training, feature selection, threshold tuning,
  or model selection. They are evaluation-only.
- No large LLM run is started before graph-only discovery shows a non-trivial signal.
  If that gate is passed, the authorized Astra6 relay may be used for structured
  hypothesis generation, with raw graphs replaced by compact evidence packets.

## Execution order

1. Literature/novelty and data protocol audit.
2. Leakage-safe episode construction.
3. Tier-0 non-neural anomaly baselines.
4. Held-out wash-label enrichment sanity check.
5. Synthetic motif injection and camouflage benchmark.
6. Static/temporal representation baselines only if the sanity check passes.
7. Astra6 latent-strategy and intervention-verification track only after Step 12.

## Claim boundary

Use `behavioral anomaly`, `suspicious coordinated behavior`,
`wash-like/laundering-like motif`, or `latent-strategy hypothesis`. Do not label an
address as laundering or illicit based on this work.

## 2026-09-18 checkpoint

- OW-001 recovered 77 external reference hashes in the six-month target-event table,
  with no August overlap; external enrichment is therefore coverage-limited.
- OW-002/003 simple transaction baselines produced no matched labels in the top 1,000
  for March--July; wider-K enrichment was sparse and non-replicating.
- OW-004/005 synthetic motif recovery is non-trivial, but matched-volume controls do not
  yet show a consistent motif-specific advantage over volume.
- OW-006 history-only active-day/breadth scores predict future activity/new counterparties;
  this is a promising association but still requires finer matching and group-level tests.
- Decision: **HOLD** before the Astra6 latent-strategy track; continue graph-only controls.

## 2026-09-18 Astra6-routed graph-only audit

A bounded structured design request was sent through the private Astra6 relay; no
hidden reasoning or raw credentials were stored. Astra6 selected one fixed
conditional structure-residual experiment and explicitly kept the LLM out of the
primary detector. The advice and the subsequent critique are recorded in
`results/ASTRA6_ADVICE_20260918.json` and `results/ASTRA6_CRITIQUE_20260918.json`.

`OW-009` ran that design as a local pilot on the existing day-level,
matched-matched primary edge extract. Because this extract has no event timestamp,
event family, native value, or token fields, rapid-forward and in/out-change
features were not claimed. The registered strict cohort had only 370/282/359
candidates at the three cutoffs; an expanded diagnostic cohort had 1059/811/898.
Both are below the preregistered 2,000-candidate / top-100 coverage gate.

The fixed residual score did not pass: strict median open-world lift was 0.536 and
mean adjacent top-5% Jaccard was 0.064; the expanded diagnostic values were 0.800
and 0.053. Some future-new-counterparty ratios were large because control means
were small, but bootstrap lower bounds, stability, and matching balance were not
reliable; several standardized mean differences exceeded 0.10. Astra6's critique
therefore selected **stop as underpowered**, not detector tuning or a latent-strategy
pivot.

The next valid restart condition is an event-level compact materialization with the
same time windows, at least 2,000 eligible candidates per cutoff, all matching
covariate absolute SMD <= 0.10, and a three-cutoff bootstrap result that beats the
volume/activity baseline. Until then, the project remains **HOLD before the Astra6
latent-strategy track**.
