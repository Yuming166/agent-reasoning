# X (Twitter) social-data availability & seed crosswalk audit — 2026-09-08

Goal: obtain social (follow) relation features for the 27,613 EX-Graph-mapped
wallets, including follow edges to accounts *outside* the seed set.

## Files downloaded (via proxy, jump-host traffic kept small)
- X Graph: `data/raw/x_graph/twitter_graph.pkl` (60,294,015 bytes, ~57.5 MiB)
  sha256 0d9a6b11c8630c5914c52e9cf29e07cac68552348fd428e3623c80f577aab855
- Matching Link Prediction Graph:
  `data/raw/x_graph/matching_link_prediction_graph.pkl` (476,290,042 bytes, ~444 MiB)
  sha256 466faf910fe7b7476212d9e1b24896ede83cee97a0597c2ed4138294c84e77f0

Probed but NOT downloaded (size-only):
- ethereum_with_twitter_features.pkl = 37,329,036,840 bytes (~34.8 GiB)
- wash train/val = 4.46 GiB / 1.46 GiB (collapsed homogeneous task graphs)

## Verified facts
- `twitter_graph.pkl` is a DGL **homogeneous** graph (`ntypes=['_N']`):
  1,103,509 nodes, 3,768,281 directed follow edges. No node/edge features.
  This is the "1.1M X accounts / 3.77M follow" crawl; it already contains
  external (non-seed) neighbours — matches paper/README.
- `twitter_matching.csv` (27,613 unique pairs) columns are only
  `node_id, ethereum_address`. Its `node_id` is the **Ethereum-graph** node id:
  all 27,613 ids are present in `ethereum_graph.gpickle` (1,810,641 nodes),
  max seed id 1,809,649.
- X graph node ids are an **independent** numbering 0..1,103,508. Only 18,793
  seed ids happen to be < 1,103,509; the other 8,820 exceed it, so `node_id`
  is NOT an X graph node id. Direct id join is invalid.
- The Matching Link Prediction graph is a DGL **homogeneous** merged graph
  (single `_N`, 2,833,659 nodes / 18,433,366 edges) with a 16-d `features`
  matrix and NO edge-type attribute. Ethereum transact, X follow, and Match
  edges are collapsed; the positive_*.pkl task pairs and the raw cross edges
  mix real matches with negative-sampling pairs:
    - cross ETH<->X oriented edge-ends: 2,179,260; unique ordered pairs
      2,120,394 (only 58,866 appear twice). No clean 1:1 ~27.6k match subset is
      recoverable; symmetric pairs cover only 716 of the seed eth ids.
  => The collapsed small task graphs do NOT expose an authoritative
     Ethereum-node-id -> X-node-id crosswalk.

## Blocker for seed-level social features
Assigning follow edges / X structure to the 27,613 seeds requires an
authoritative `eth_node_id <-> x_node_id` mapping. It is not present in:
- twitter_matching.csv (eth ids only),
- twitter_graph.pkl (X nodes only, separate ids),
- matching_link_prediction_graph.pkl (edge types + negatives collapsed),
- wash task graphs (homogeneous, feature-only, no clean X relation).
The authoritative match relation lives in the original heterogeneous graph /
the per-eth-node X feature object, which is only shipped in the large
`ethereum_with_twitter_features.pkl` (~34.8 GiB) or was not released as a
standalone heterograph.

## Standalone X-graph statistics (valid regardless of crosswalk)
X follow edges are directed; full-graph (1.1M nodes) indegree/outdegree mean
≈ 3.4; this is the complete published external-aware crawl, so seed social
features computed AFTER obtaining the crosswalk will include outside accounts.

## Options
1. Do NOT download 34.8 GiB to the jump host (traffic). Instead inspect whether
   the EX-Graph authors can provide / or the README site (exgraph.deno.dev)
   exposes a per-eth-node X feature/mapping small artifact.
2. Re-derive match edges only from an authoritative source; do not guess from
   collapsed negative edges.
3. Until a crosswalk exists, seed-level X structural features cannot be
   computed; label Ablation E / X-centrality routing accordingly.

## Update 2026-09-08 (definitive): feature-based crosswalk does NOT work
Attempted to recover ETH->X mapping from the matching graph's 16-d `features`
(8 eth-structural + 8 X-semantic after PCA). Result:
- In the matching-link-prediction graph the X-side semantic 8-vector is
  PCA-collapsed: across 1,124,084 X nodes there is only **1 unique last-8
  vector** (all share norm 0.1709); ETH side has only 8,284 binned last-8
  values. Full-16 uniqueness: 633,557 (ETH) vs 239,897 (X).
- Therefore nearest/exact vector matching cannot identify a *specific* X
  account per wallet; it matches a shared placeholder. The near-exact count
  (~27,060) was an artifact of this collapsed placeholder, NOT identity.
- The small released files genuinely do NOT contain the raw BERT 770-d
  per-X-profile embedding nor a per-edge type label, so a bijective,
  trustworthy eth_node_id <-> x_node_id crosswalk cannot be recovered from
  X Graph (57.5 MiB) + matching graph (444 MiB) + twitter_matching.csv.

## What WOULD supply the crosswalk
- The raw ~30k match relation (eth address/handle) is NOT published beyond the
  anonymized `twitter_matching.csv` (ethereum_address, ETH node id only).
- The per-wallet X identity / feature is shipped only inside
  `ethereum_with_twitter_features.pkl` (34.8 GiB), keyed on the ETH graph, but
  it does not trivially expose the X-follow-graph node id either.
=> Action options: (a) ask EX-Graph authors (GitHub/OpenSea contact) for the
  ETH-node-id <-> X-node-id mapping or the raw heterograph; (b) if needed,
  download the 34.8 GiB file on a non-billing/non-constrained path and inspect
  whether it carries X node ids (traffic ~35GB); (c) do not claim seed-level X
  social structure in the NAACL paper until a verified crosswalk exists.
