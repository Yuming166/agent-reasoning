# Data Contract — EX-Graph NAACL Autoresearch

## Unit and interpretation

- Primary unit: one mapped Ethereum address at one UTC cutoff; interpret as address/actor-proxy behavior, never as a verified human owner.
- Historical chain window: `[2022-03-01, 2022-09-01)` UTC for the materialized target-event pipeline.
- Current Decision-State cutoffs: 2022-06-01, 2022-07-01, 2022-08-01 UTC; June train, July development, August frozen test.

## Allowed data

- Validated target event view across native transactions, token transfers, and internal traces.
- As-of feature tables and frozen Decision-State V1 panel/features/predictions.
- Static EX-Graph features only as historical/contextual selection priors, not temporal events.
- Public market context only where explicitly as-of and present in the frozen protocol.

## Leakage and identity rules

- Future outcomes are evaluation-only and may not enter prompts, sample selection, features, intervention selection, or protocol choices.
- Existing August frozen test cannot be tuned or reused as validation.
- `ethereum_graph.gpickle` is a static aggregated weighted DiGraph without event timestamps; it cannot recover transaction order.
- No reliable Ethereum-address-to-X-owner crosswalk is assumed.
- No claim of true belief, emotion, owner intent, causality, wash-trading detection, or social influence is allowed without a new identification protocol.

## Reproducibility

- Preserve raw frozen artifacts, hashes, protocol manifests, experiment ids, cutoff dates, model ids, and negative results.
- New confirmatory work requires a new protocol and untouched temporal holdout.
