-- P1 per-wallet counterfactual influence: sum over events the wallet bridges
-- of its signal share (1/outdeg_w) / total bridge signal on that event.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.p1_wallet_icf_v1` AS
WITH weighted AS (
  SELECT event_key, bridge_w, 1.0/MAX(w_outdeg) AS wsig
  FROM `ictdata-507912.exgraph.p1_bridge_events_v1`
  GROUP BY event_key, bridge_w
),
evt_tot AS (
  SELECT event_key, SUM(wsig) AS evt_sig FROM weighted GROUP BY 1
)
SELECT bridge_w AS target_address,
       COUNT(*) AS bridges_events,
       SUM(w.wsig / e.evt_sig) AS icf_score_p1,
       SUM(w.wsig) AS icf_raw_signal
FROM weighted w JOIN evt_tot e USING(event_key)
GROUP BY 1;
