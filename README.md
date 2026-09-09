# EX-Graph microtransaction analysis

Reproducible data preparation and research code for **wallet-level next-transaction
forecasting** that combines temporal Ethereum events with external social
context through **counterfactual, step-level multi-agent reasoning**. The
repository targets an **ACL Rolling Review submission for the NAACL 2027 cycle**.

The repository keeps large/raw data outside Git while preserving the code,
schemas, manifests, checksums, and bounded validation results needed to
reproduce the workflow and to rerun the planned experiments.

## Research mainline

The project has been upgraded from a single next-counterparty ranker into an
**influence-adaptive, trustworthy recursive reasoning system** for temporal
wallet graphs. The central premise is that deeper reasoning is not uniformly
useful: only some wallet-events have enough market relevance or counterfactual
headroom to justify high-cost recursion.

The research pipeline is:

1. **Dynamic wallet influence** — identify wallet addresses or wallet clusters
   whose future behavior is likely to create measurable downstream spillover.
   Static degree/PageRank are priors; the main selection target must be built
   from strict pre-snapshot history and evaluated on future spillover.
2. **Adaptive reasoning depth** — choose low, medium, or high depth per
   `(wallet, event, time)` under a fixed token/latency budget. Low depth uses the
   cheap predictor; medium depth uses one counterfactual FSM; high depth performs
   a bounded shared-state recursive rollout.
3. **Step-level trustworthy reasoning** — every recursive transition records
   evidence event IDs, the intervention, belief update, confidence, temporal
   validity, candidate support, and a stop/continue decision. Invalid or
   unverifiable calls abstain and fall back to the cheap path; this is not an
   unrestricted chain-of-thought requirement.
4. **Micro-to-macro outputs** — predict the next counterparty/action at the
   micro level, a short wallet/community strategy at the meso level, and
   aggregated flow, protocol-exposure, and network-state statistics at the macro
   level. The rollout updates a shared state so agents are not simulated as
   independent isolated forecasts.

The formal mainline is documented in
[`notes/RESEARCH_MAINLINE.md`](notes/RESEARCH_MAINLINE.md). The main claim under
evaluation is:

> Under a matched reasoning budget, influence-adaptive selective recursion with
> counterfactual and step-level verification should outperform uniform shallow
> or uniform deep reasoning on multi-step wallet/action forecasting per unit of
> cost.

This claim is deliberately narrower than “LLM is better for every wallet.”
The current v2 experiment validates the one-step counterfactual component; the
adaptive depth policy, future-spillover influence label, coupled multi-step
rollout, and market aggregation are the next experiments.

## Data scope

Available and used in this repository:

- **EX-Graph official matching**: 27,613 Ethereum addresses matched to
  anonymized X/Twitter accounts (`vendor/EX-Graph-repo/twitter_matching.csv`,
  released as part of Persdre/EX-Graph). This provides the address-to-X
  match dimension, not raw tweet text.
- **Temporal Ethereum events**: Google Blockchain Analytics materializations
  for the primary 2022-03-01 (inclusive) through 2022-09-01 (exclusive) window,
  plus a separately materialized 2022-09 holdout extension through 2022-10-01.
- **External social context**: the Crypto Influencer tweet dataset is used as a
  second modality for asset- and market-level sentiment, **not** as a
  "wallet owner's tweets". We do not require influencers to own the sampled
  EX-Graph addresses; we require the tweets to be temporally aligned with the
  asset/contract context of a wallet.

Important distinction:

- EX-Graph supplies the address-to-X matching and the X follower/following
  graph, but does **not** ship a large historical tweet-text corpus.
- The Crypto Influencer dataset supplies tweet text and sentiment, but does
  **not** supply a reliable author-to-wallet crosswalk.

Consequently the first paper version treats social information as **external
social context** (asset-conditioned or global sentiment) rather than claiming to
recover a wallet owner's personal tweets or intentions.

## Validated data preparation

The development materialization covers **2022-03-01 (inclusive) through
2022-09-01 (exclusive), UTC** and uses 27,613 EX-Graph-mapped addresses.

| Event family | Rows |
|---|---:|
| Native transactions | 2,877,009 |
| Token transfers | 4,275,544 |
| Internal traces | 4,478,515 |
| **Source total** | **11,631,068** |

Derived tables in BigQuery (`ictdata-507912.exgraph`):

| Table | Description |
|---|---|
| `external_transactions_20220301_20220901` | Native transactions touching a mapped address |
| `token_transfers_20220301_20220901` | Token transfers touching a mapped address |
| `internal_traces_20220301_20220901` | Internal traces touching a mapped address |
| `target_events_20220301_20220901` | `UNION ALL` unified view over the three families |
| `exgraph_x_matches_v1` | Official address-to-X match dimension with provenance |
| `target_event_sequences_20220301_20220901` | Directional target/counterparty role rows |
| `exgraph_structural_features_v1` | Per-mapped-address static-graph structural features (degree / weighted degree) |

`target_event_sequences_*` semantics:

- `target_address` is the matched endpoint; `counterparty_address` is the other
  endpoint.
- A source event with two distinct matched endpoints produces two role rows; a
  self-transaction produces one `self` row.
- `external_tx` and `token_transfer` are `sequence_role=primary`;
  `internal_trace` is retained as `sequence_role=auxiliary` for ablations.
- `target_sequence_index` is deterministic per target address. Cross-family
  ordering inside one transaction is a deterministic tie-breaker, not a
  canonical EVM event order.
- Rows without a destination address are retained with
  `counterparty_present=false` and must be excluded from next-counterparty
  labels.

Reproduction SQL and manifests:

- `src/sql/create_target_events_view_ictdata.sql`
- `src/sql/create_exgraph_sequence_tables_ictdata.sql`
- `src/create_target_events_view.py`
- `src/create_exgraph_sequence_tables.py`
- `artifacts/google_event_prep_2022-03_2022-09.json`
- `artifacts/google_trace_prep_2022-03_2022-09.json`
- `artifacts/google_target_events_view_2022-03_2022-09.json`
- `artifacts/google_sequence_tables_2022-03_2022-09.json`

### Static-graph structural features (2026-09-08)

Computed locally from the released static weighted graph without re-downloading
it. Graph nodes are integer EX-Graph node ids, so the features are emitted for
the 27,613 mapped addresses through the `twitter_matching.csv` address bridge.

- `artifacts/exgraph_structural_features.csv` (27,613 rows):
  `ethereum_address, exgraph_node_id, graph_node_present, in_degree,
  out_degree, w_in_degree, w_out_degree, degree, w_degree, pagerank`.
  `pagerank` is weighted PageRank (alpha 0.85, edge `weight` =
  transaction multiplicity), computed over the full directed graph.
- `artifacts/exgraph_structural_features_manifest.json`: provenance, hashes,
  counts, and degree summary.
- `exgraph.exgraph_structural_features_v1` in BigQuery (27,613 rows), joined to
  `exgraph_x_matches_v1` on `ethereum_address` + `exgraph_node_id` with zero
  mismatches.

Reproduce:

```bash
# extraction needs networkx (see the analysis virtualenv)
python src/extract_graph_structural_features.py \
  --graph /path/to/ethereum_graph.gpickle \
  --target-addresses data/metadata/target_addresses.csv \
  --output artifacts/exgraph_structural_features.csv \
  --manifest artifacts/exgraph_structural_features_manifest.json \
  --pagerank

# upload needs requests + gcloud Application Default Credentials
python3 src/upload_graph_structural_features.py \
  --project-id ictdata-507912 --dataset-id exgraph \
  --csv artifacts/exgraph_structural_features.csv \
  --output artifacts/exgraph_structural_features_upload.json \
  --gcloud-bin "${GCLOUD_BIN:-gcloud}"
```


### Learned candidate ranker and event gate (2026-09-09 pilot)

The next-counterparty pilot uses monthly snapshots (June train, July
gate-tuning, August frozen test) and features for `(source wallet, candidate)`:
historical global popularity rank/count, 90-day personal interaction count and
recency, and 2-hop bridge path/weight signals. BigQuery materialization and
local training/evaluation code are in:

- `src/pipeline/build_rankertables.py` -> `exgraph.nc_ranker_samples_v2`.
- `src/pipeline/train_candidate_ranker.py`.
- `src/pipeline/gate_and_budget.py` (leakage-safe event-level gate prototype).
- `src/pipeline/evaluate_supported_pool.py` (support-restricted audit).

The exported development table contained 28,472,717 compressed CSV rows
(966 MB across 30 gzip shards; the data itself is not committed). The first
naive sampled-pool result (August MRR .896) is **not** a valid full-task
result: negatives were drawn from the historical global top-2000 support while
82.2% of observed positives were outside it and received sentinel
`g_rank=99999`, making them trivially separable.

The valid support-restricted comparison retains 30,610/171,700 August new-event
instances whose positive is in top-2000. On the comparable approximately-50-row
sampled pool, global popularity scores MRR .448 and the learned ranker .456
(+0.0083 absolute; +1.85% relative); oracle best-of-two has MRR .505. A gate
trained on July out-of-sample events is weak on August (AUROC .557; AUPRC .278
at 23.0% winner base rate), and captures only a small part of oracle headroom
at a 10% deliberation budget (+.0029 learned gate vs +.0528 oracle). The cost
axis uses fixed token-units (32 cheap / 96 deliberation), not measured LLM
tokens. See `artifacts/nc_v1/RESULTS.md` and `supported_pool_v1.json`.

## Corrected v2 LLM panel (2026-09-09)

The corrected v2 run completed four 1,000-event snapshots with `glm-5.3`:
June, July, August, and an independent September temporal holdout. Exact score
ties use average competition ranks. Parse failures are retained and fall back
to the cheap ranker for operational scoring.

| Snapshot | Full parse | NoCF parse | Cheap MRR | NoCF MRR | Full MRR | Full-Cheap |
|---|---:|---:|---:|---:|---:|---:|
| 2022-06 | 0.322 | 0.339 | 0.3281 | 0.4647 | 0.5088 | +0.1807 |
| 2022-07 | 0.959 | 0.974 | 0.2831 | 0.3579 | 0.5029 | +0.2198 |
| 2022-08 | 1.000 | 0.999 | 0.2795 | 0.3797 | 0.5605 | +0.2810 |
| 2022-09 | 1.000 | 1.000 | 0.3003 | 0.4089 | 0.5499 | +0.2496 |

The corrected results support the counterfactual component, with the largest
benefits concentrated in difficult repeated interactions and much smaller
benefits on `new_tail`. They do **not** yet establish that a learned budget
router beats simple routing policies. June also has an anomalously low parse
rate and must be diagnosed or rerun before it is treated as clean router
training evidence.

Reproducible compact artifacts are under
`artifacts/llm_panel_v2/RESULTS_CORRECTED_V2.md`. The old
`artifacts/llm_panel_v2/router_dataset_v2.csv` is intentionally not published:
it was generated before the reciprocal-rank correction and must be rebuilt.

## What is included

- EX-Graph graph and temporal-dataset audits under `src/` and `notes/`.
- The 27,613-address mapping at `data/metadata/target_addresses.csv`.
- BigQuery SQL and Python scripts for address upload, overlap validation,
  event-table materialization, quality checks, the unified view, and the
  directional sequence table.
- Small JSON execution manifests, candidate-model summaries, and budget curves under `artifacts/`.
- The corrected v2 Full/NoCF/cheap runner, tie-aware evaluator, operational
  fallback evaluator, frozen ranker utilities, and router-training utilities
  under `src/agent/`.
- v2 panel construction scripts under `src/pipeline/`, plus compact corrected
  per-event audit outputs and evaluation summaries.
- Data provenance, checksums, and third-party notices.

## What is intentionally not included

The raw 11.6 GB `ethereum_graph.gpickle`, raw Crypto Influencer files, Python
virtual environment, and BigQuery event tables are not part of this GitHub
repository. See [`DATA_ACCESS.md`](DATA_ACCESS.md) for shared-table access and
reproduction in another Google Cloud project. Raw tweet text is not published;
derived embeddings/labels and rehydration instructions are used instead.

## Planned experiments

### Main hypothesis tests

| Question | Required comparison |
|---|---|
| Does the counterfactual operator help? | Full FSM vs NoCF vs Cheap |
| Is deeper reasoning selectively useful? | learned depth vs all-low, all-high, random, uncertainty, repeat-only |
| Does dynamic influence improve selection? | future-spillover scorer vs degree/PageRank/activity-only |
| Does verification stabilize recursion? | verified vs unverified recursive rollout |
| Does micro behavior aggregate to market state? | coupled shared-state rollout vs independent wallet forecasts |

### Prediction and influence baselines

- Most-recent counterparty;
- global popularity;
- wallet-level frequency and recency-frequency;
- first-order Markov;
- temporal sequence ranker;
- degree/PageRank and transaction-volume influence;
- uncertainty-only and repeat-only selection;
- unstructured recursive LLM calls at matched depth and budget.

### Depth/routing policies

| Setting | Policy |
|---|---|
| All-cheap | No LLM / low-depth predictor for every event |
| All-FSM | Full counterfactual FSM for every event |
| Random | Random events at equal budget |
| Centrality | Route structurally influential wallets |
| Uncertainty | Route high cheap-ranker uncertainty |
| Repeat-only | Route repeated interactions first |
| Influence-only | Route high predicted future spillover |
| Learned adaptive depth | Main policy: choose low/medium/high depth from as-of features |
| Oracle | Upper bound only; uses realized gain and is never a deployable policy |

### Trust and recursive ablations

- remove the counterfactual mask;
- remove belief update;
- remove evidence/constraint verification;
- fixed recursion depth;
- independent rather than shared-state rollouts;
- no influence features;
- no external context;
- failure deletion versus explicit cheap fallback (the latter is the
  production protocol).

### Outputs and metrics

- Micro: next-counterparty/action `Recall@1/5/10`, `MRR`, `NDCG`, direction and
  event-family accuracy;
- Meso: K-step path likelihood, trajectory hit rate, strategy calibration, and
  error accumulation across recursion depth;
- Macro: future flow/protocol-exposure error, concentration and graph-statistic
  distance, and interval calibration;
- Influence: future-spillover Recall@K, NDCG, AUROC, and reach/flow impact;
- Trust: evidence coverage, as-of violations, invalid transition rate,
  counterfactual consistency, abstention risk/coverage;
- Efficiency: measured token usage, latency, failure/fallback rate, and utility
  per budget.

All main deltas must be paired, bootstrap-tested, reported by
`new_popular`, `new_tail`, `repeat_easy`, and `repeat_hard`, and evaluated on
both August and the September temporal holdout.

## Temporal split

No random splitting; chronological evaluation only:

- Historical feature construction: strict as-of windows before each event;
- Router training: June 2022;
- Router/treatment tuning: July 2022;
- Frozen primary test: August 2022;
- Independent temporal holdout: September 2022.

The current four-month LLM panel contains 1,000 events per snapshot. Any
future-spillover or market-impact label is computed after the prediction time
and is never used as an input feature. Static full-window graph statistics may
be used only as explicitly labelled priors, not as time-valid dynamic features.

## NAACL 2027 execution roadmap

1. **Protocol and validity freeze** — preserve the v2 candidate-support and
   tie-aware rules; diagnose the June parse anomaly; rebuild the router data with
   explicit fallback.
2. **Budget router** — train on June, tune on July, freeze on August, and test
   again on September against all routing baselines.
3. **Influence selection** — add strict as-of future-spillover labels and test
   dynamic influence against static centrality/activity baselines.
4. **Adaptive recursion** — replace binary routing with low/medium/high depth and
   matched-cost evaluation.
5. **Trustworthy rollout** — implement evidence-backed K-step shared-state
   transitions, stop/abstain checks, and failure analysis.
6. **Micro-to-macro evaluation** — aggregate selected wallet trajectories into
   group and market-relevant flow/network forecasts.
7. **Robustness and paper freeze** — add strong non-LLM baselines, cross-model
   checks, ablations, dated novelty audit, appendix, and reproducibility package.

## Status boundary

### Completed

- Leakage-audited Ethereum temporal event preparation and directional
  next-counterparty sequence construction;
- EX-Graph structural/address feature extraction and wallet-selection pilots;
- v2 candidate-pool repair with unknown-tail negatives and tie-aware ranking;
- frozen June-trained v2 cheap ranker;
- Full counterfactual FSM, one-shot NoCF ablation, strict parsing, measured
  token/latency logging, and explicit failure fallback;
- corrected v2 LLM runs for June, July, August, and September, with compact
  per-event audit outputs and paired by-stratum evaluation.

### In progress or not yet complete

- Diagnose or rerun the anomalously low June parse-rate run;
- rebuild and freeze the v2 budget router from corrected outputs;
- dynamic future-spillover influence labels and adaptive low/medium/high depth;
- strong temporal/sequence baselines and cross-model robustness;
- verified K-step shared-state wallet/group rollout;
- macro flow/network aggregation and a frozen end-to-end NAACL result.

### Claim boundaries

The earlier `.896` candidate-ranker MRR is a support artifact, not a
full-vocabulary result; the honest support-restricted gain is documented in
`artifacts/nc_v1/RESULTS.md`. The corrected v2 Full-vs-Cheap result is a
candidate-panel component result, not proof that a budget router or a complete
market simulator is superior. We do not claim causal influencer effects,
real-person identity, trading alpha, full-market coverage, or realized token
savings without the corresponding as-of, causal, coverage, and frozen-budget
evidence.

The GitHub repository contains code, manifests, compact evaluation outputs, and
research notes. Raw graph pickles, BigQuery tables, candidate shards, full
panel-scoring tables, credentials, virtual environments, and runtime logs stay
outside Git; see [`DATA_ACCESS.md`](DATA_ACCESS.md).
