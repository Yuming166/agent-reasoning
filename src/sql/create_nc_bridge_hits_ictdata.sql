CREATE OR REPLACE TABLE `ictdata-507912.exgraph.nc_bridge_hits_v1` AS
WITH new_ev AS (
  SELECT u, v, target_sequence_index
  FROM `ictdata-507912.exgraph.nc_events_v1`
  WHERE month = DATE '2022-08-01' AND cp_type='new'
),
nn AS (
  SELECT b.u, b.v AS c, b.bridge_signal
  FROM `ictdata-507912.exgraph.nc_bridge_cand_v1` b
  LEFT JOIN `ictdata-507912.exgraph.nc_edges_hist_v1` d ON d.u=b.u AND d.v=b.v
  WHERE d.v IS NULL
),
ranked AS (
  SELECT n.u, n.target_sequence_index, n.v AS true_v, c.c, c.bridge_signal,
         ROW_NUMBER() OVER (PARTITION BY n.u, n.target_sequence_index
                            ORDER BY c.bridge_signal DESC, c.c) AS br
  FROM new_ev n JOIN nn c ON c.u=n.u
)
SELECT u, target_sequence_index, c AS candidate, br AS bridge_rank, bridge_signal AS bridge_score
FROM ranked WHERE c=true_v;
