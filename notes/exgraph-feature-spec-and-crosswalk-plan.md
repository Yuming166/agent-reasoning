# EX-Graph released artifacts: feature spec, crosswalk status, GCP extraction plan

Last verified: 2026-09-08 (code + local files + paper arXiv source; cloud tables
re-queried today via ADC).

## 1. What is in the released files (verified from task code, not README claims)

| Artifact | Size | Nodes / edges | Node features | Contains address? | Contains X node id / handle? |
|---|---|---|---|---|---|
| twitter_matching.csv | tiny | 27,613 pairs | cols: eth node_id, ethereum_address | YES (address) | NO (node_id is ETH graph id; 8,820 ids exceed X graph size) |
| twitter_graph.pkl (X Graph) | 57.5 MiB | 1,103,509 X accts / 3,768,281 directed follow edges | none | no | nodes ARE X numeric ids, but no key to ETH side; no handle |
| matching_link_prediction_graph.pkl | 444 MiB | 2,833,659 = 1,709,575 ETH + 1,103,509 X (ETH block first, X block offset EN=1,709,575) | 16-d combined | no | cross edges = 2,179,260 directed ends / 2,120,394 unordered pairs, ALL bidirectional => candidate pool incl. negatives; real ~27.6k matches not separable |
| positive/negative_*_edge_indices.pkl (matching task) | small | 1,156,183 pos + 1,156,183 neg pairs | - | no | all ends < 1,709,575 => ETH-side pairs only; NO eth-x pairs |
| ethereum_with_twitter_features.pkl (Drive 1q3KX...) | ~34.8 GiB | 1,709,575 ETH nodes / 13,170,869 edges | ethereum_features (8-d), ethereum_twitter_combined_features (24-d) | edge data: from/to address, weight, block_number (README) | NO X node id space; X info only as 16-d aggregated per ETH node |
| wash train/val/test gpickles | 4.46/1.46/~? GiB | 1,268,607 / 452,930 / 711,084 ETH-only nodes | ethereum_features, X_semantic_features, X_structure_features, ethereum_X_combined_features(24-d), wash_trading_label | edge data n.a. per README (no address strings) | NO X nodes/ids |

Feature dims proven from code: wo_twitter models = GCN(8,...); with_twitter = GCN(24,...).

## 2. What the X features actually are (paper arXiv source)

- 8 ETH structural features (per node, both ETH graph and X graph):
  degree, in-degree, out-degree, #neighbors, #in-neighbors, #out-neighbors,
  max tx count with a neighbor, average neighbor degree.
- X semantic: BERT(profile text) -> 768-d, plus log(#followers+1), log(#followings+1)
  => 770-d; PCA to 8-d.
- X structure in released graphs = the 8 statistical structural features (PCA/packaged);
  paper ALSO trained a 128-d DeepWalk embedding on the X graph (walk len 40,
  context 5, 10 walks/node) but the released task graphs expose only the 16-d
  combined features.
- Paper appendix claims "open-source BERT-handled vectors ... for X profiles"
  are provided; no such standalone file exists in the GitHub repo, and
  exgraph.deno.dev is dead (404 on /, /data, /features on 2026-09-08).
- Matching source: OpenSea public "User" endpoint -> address self-declared X
  handle; X data via X developer API Friends/Followers/User endpoints.

## 3. X Graph standalone structure (today: artifacts/x_graph_standalone_stats.json)

1,103,509 nodes / 3,768,281 directed edges; mean in/out-degree 3.41; median
indeg 1, median outdeg 0; max indeg 4,476; max outdeg 21,621; 312,106 nodes
with zero followers; 639,846 follow nobody; reciprocal edge ends 102,088
(~2.7%); 2 weakly connected components, giant CC = 1,103,430 nodes.
Per-node in/out degree saved: data/raw/x_graph/x_graph_node_degrees.npz
(ready to join onto seeds the moment an eth->x crosswalk exists).

## 4. Crosswalk decision

- No released small artifact contains eth_node_id <-> x_node_id. Do NOT
  guess from the 2.12M collapsed candidate edges.
- Routes: (a) ask authors (issue/email) for the X-id matching table or raw
  heterograph; (b) GCP-side extraction from the 34.8 GiB file yields address
  -> 16-d X features (enough for influence-aware wallet selection) but NOT
  edge-level X relations; (c) self-build identity layer via OpenSea User API
  + ENS text records (com.twitter), provenance-graded, as reproducible
  fallback.
- Until then: no seed-level X structural claims; Crypto Influencer stays
  asset/time-window context only.

## 5. Cloud tables re-verified 2026-09-08 (ADC + proxy, REST)

- ictdata-507912.exgraph.exgraph_x_matches_v1: 27,613 rows / 27,613 addresses.
- ictdata-507912.exgraph.target_event_sequences_20220301_20220901:
  11,836,196 rows, 21,469 active target addresses, 11,832,912 with
  counterparty. Partition filter on block_timestamp is REQUIRED.
