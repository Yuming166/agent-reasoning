WITH norm AS (
  SELECT e.target_address, e.evt_cnt_90d, e.importance_proxy_p3,
         COALESCE(e.aug_out_events,0) AS aev,
         COALESCE(e.hard_events_pop100plus,0) AS hh,
         p.icf_score_p1
  FROM `ictdata-507912.exgraph.selection_eval_v1` e
  LEFT JOIN `ictdata-507912.exgraph.p1_wallet_icf_v1` p USING(target_address)
),
b AS (
  SELECT *,
    ROW_NUMBER() OVER (ORDER BY importance_proxy_p3 DESC) AS r_p3,
    ROW_NUMBER() OVER (ORDER BY evt_cnt_90d DESC) AS r_vol,
    ROW_NUMBER() OVER (ORDER BY icf_score_p1 DESC NULLS LAST) AS r_p1,
    ROW_NUMBER() OVER (ORDER BY RAND()) AS r_rand,
    COUNT(*) OVER () AS n_tot,
    SUM(aev) OVER () AS tot_ev, SUM(hh) OVER () AS tot_hard
  FROM norm
),
br AS (SELECT DISTINCT event_key, u, bridge_w FROM `ictdata-507912.exgraph.p1_bridge_events_v1`),
totb AS (SELECT COUNT(DISTINCT event_key) AS bridged FROM br),
pb AS (
  SELECT b.*, ks, CAST(ks*n_tot/100 AS INT64) AS k_full, CAST(ks*n_tot/200 AS INT64) AS k_half
  FROM b CROSS JOIN UNNEST([1,5,10,20]) ks
),
sel AS (
  SELECT target_address, aev, hh, ks, k_full, k_half, tot_ev, tot_hard, method,
    CASE method
      WHEN 'P3_difficulty' THEN IF(r_p3<=k_full,1,0)
      WHEN 'raw_volume' THEN IF(r_vol<=k_full,1,0)
      WHEN 'P1_occlusion' THEN IF(r_p1<=k_full,1,0)
      WHEN 'random' THEN IF(r_rand<=k_full,1,0)
      WHEN 'quota_half_P1_half_P3' THEN IF(r_p1<=k_half OR r_p3<=k_half,1,0)
    END AS is_sel
  FROM pb
  CROSS JOIN (SELECT method_name AS method FROM UNNEST(['P1_occlusion','P3_difficulty','raw_volume','random','quota_half_P1_half_P3']) AS method_name)
),
chain AS (
  SELECT ks, method,
    SUM(aev*is_sel)/MAX(tot_ev) AS event_cov,
    SUM(hh*is_sel)/MAX(tot_hard) AS hard_cov
  FROM sel GROUP BY ks, method
),
bcov AS (
  SELECT s.ks, s.method,
    COUNT(DISTINCT IF(s.is_sel=1, br1.event_key, NULL)) / ANY_VALUE((SELECT bridged FROM totb)) AS bridge_cov_as_bridge,
    COUNT(DISTINCT IF(s.is_sel=1, br2.event_key, NULL)) / ANY_VALUE((SELECT bridged FROM totb)) AS bridge_cov_as_source
  FROM sel s
  LEFT JOIN br br1 ON br1.bridge_w=s.target_address
  LEFT JOIN br br2 ON br2.u=s.target_address
  GROUP BY s.ks, s.method
)
SELECT c.ks AS k_pct, c.method,
  ROUND(c.event_cov,3) AS event_cov,
  ROUND(c.hard_cov,3) AS hard_cov,
  ROUND(COALESCE(bc.bridge_cov_as_bridge,0),3) AS bridge_cov_as_bridge,
  ROUND(COALESCE(bc.bridge_cov_as_source,0),3) AS bridge_cov_as_source
FROM chain c JOIN bcov bc USING(ks,method)
ORDER BY ks, c.method;
