CREATE OR REPLACE TABLE `ictdata-507912.exgraph.nc_bridge_poolsize_v1` AS
SELECT b.u AS u, COUNT(*) AS pool_size
FROM `ictdata-507912.exgraph.nc_bridge_cand_v1` b
LEFT JOIN `ictdata-507912.exgraph.nc_edges_hist_v1` d ON d.u=b.u AND d.v=b.v
WHERE d.v IS NULL
GROUP BY 1;
