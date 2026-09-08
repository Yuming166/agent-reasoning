# EX-Graph microtransaction analysis

Reproducible data preparation and research code for **wallet-level next-transaction
forecasting** that combines temporal Ethereum events with external social
context through **counterfactual, step-level multi-agent reasoning**. The
repository targets an **ACL Rolling Review submission for the NAACL 2027 cycle**.

The repository keeps large/raw data outside Git while preserving the code,
schemas, manifests, checksums, and bounded validation results needed to
reproduce the workflow and to rerun the planned experiments.

## Research direction

Predicting the next transaction object for every wallet is not feasible at
scale. The project therefore follows a three-stage pipeline:

1. **Influence-aware wallet selection** — select a small influential subset of
   the EX-Graph-mapped wallets using structural influence, predictive
   uncertainty, and counterfactual sensitivity rather than analyzing all
   27,613 addresses.
2. **Counterfactual step-level reasoning** — a wallet-behavior agent performs a
   finite set of auditable reasoning steps (observe history, compare behavior,
   mask a node/tweet/transaction, request neighbor evidence, update belief,
   stop-and-predict), instead of unrestricted long LLM chain-of-thought.
3. **Budget-aware multi-agent forecasting** — in a fixed compute budget, compare
   no-LLM, all-LLM, random, centrality, uncertainty, and counterfactual routing.
   The main output is `next_counterparty` (top-K) plus direction, event family,
   token/contract, confidence, evidence citations, recursion depth, and cost.

The core claim under evaluation is not "LLM reads everything better", but:

> Under the same reasoning budget, does counterfactual-driven selective
> recursive reasoning improve next-counterparty prediction while reducing
> unnecessary LLM calls?

## Data scope

Available and used in this repository:

- **EX-Graph official matching**: 27,613 Ethereum addresses matched to
  anonymized X/Twitter accounts (`vendor/EX-Graph-repo/twitter_matching.csv`,
  released as part of Persdre/EX-Graph). This provides the address-to-X
  match dimension, not raw tweet text.
- **Temporal Ethereum events**: Google Blockchain Analytics materializations
  for 2022-03-01 (inclusive) through 2022-09-01 (exclusive), UTC.
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
  --gcloud-bin /storage/gaoym/tools/google-cloud-sdk/bin/gcloud
```

## What is included

- EX-Graph graph and temporal-dataset audits under `src/` and `notes/`.
- The 27,613-address mapping at `data/metadata/target_addresses.csv`.
- BigQuery SQL and Python scripts for address upload, overlap validation,
  event-table materialization, quality checks, the unified view, and the
  directional sequence table.
- Small JSON execution manifests and audit summaries under `artifacts/`.
- Data provenance, checksums, and third-party notices.

## What is intentionally not included

The raw 11.6 GB `ethereum_graph.gpickle`, raw Crypto Influencer files, Python
virtual environment, and BigQuery event tables are not part of this GitHub
repository. See [`DATA_ACCESS.md`](DATA_ACCESS.md) for shared-table access and
reproduction in another Google Cloud project. Raw tweet text is not published;
derived embeddings/labels and rehydration instructions are used instead.

## Planned experiments

### Prediction baselines

- Most-recent counterparty.
- Global popularity.
- Wallet-level frequency.
- Recency-frequency score.
- First-order Markov.

### Ablations

| Experiment | Input / treatment |
|---|---|
| A | Ethereum native transactions only |
| B | A + token transfers |
| C | B + internal traces |
| D | C + EX-Graph static graph features |
| E | D + external social sentiment context |
| F | Counterfactual multi-agent routing (full method) |

### Reasoning routing ablations

| Setting | LLM routing policy |
|---|---|
| No-LLM | No language model |
| All-LLM | Every candidate event |
| Random | Random subset at equal coverage |
| Centrality | High structural-influence nodes |
| Uncertainty | High model-uncertainty nodes |
| Counterfactual | High counterfactual-sensitivity nodes |

### Metrics

- Next-counterparty: `Recall@1`, `Recall@5`, `Recall@10`, `MRR`, `NDCG`,
  candidate coverage.
- Auxiliary: direction accuracy, event-family accuracy.
- Selection: LLM call coverage, selective risk, accuracy-cost curve, call
  reduction at a fixed budget.
- Reasoning: evidence grounding, counterfactual consistency, prediction
  stability, step-level auditability.

## Temporal split

No random splitting; chronological split only:

- Train: `2022-03-01` to `2022-06-30`
- Validation: `2022-07-01` to `2022-07-31`
- Test: `2022-08-01` to `2022-08-31`

Node selection and social context must use only information available up to the
prediction time (`as-of` joins) to avoid future leakage.

## NAACL 2027 timeline

- **Week 1 (Sep 08-14)**: freeze task/labels, build next-counterparty labels,
  split temporally, run simple baselines and related-work/title overlap audit.
- **Week 2 (Sep 15-21)**: finish Markov/recency/frequency baselines; native-only
  and native+token ablations; confirm whether social context can be aligned.
- **Week 3 (Sep 22-28)**: counterfactual sensitivity, selective LLM routing,
  compare routing policies.
- **Week 4 (Sep 29-Oct 05)**: recursion-depth experiments, cost-performance
  curves, case studies, ethics/privacy/leakage audit.
- **Week 5 (Oct 06-12)**: freeze main results, write the paper, finalize
  appendix/manifests and the ARR submission.

## Status boundary

What is completed: data preparation, audit, verification, and publication of the
reproducible preparation pipeline.

What is **not yet** completed: next-counterparty label table, temporal
train/validation/test split, prediction baselines, counterfactual agent
mechanism, and any model result. No report should claim predictive superiority,
trading alpha, causal influencer effects, or a working end-to-end system before
those experiments are run and frozen.
