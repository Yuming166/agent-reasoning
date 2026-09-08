-- P1 counterfactual-occlusion influence, event-driven bridge formulation.
-- History window: 2022-05-01..2022-08-01 (as-of Aug snapshot). Test events:
-- August outgoing primary events u -> v (v present, non-self).
-- A target wallet w BRIDGES an event if history contains u->w (w incoming)
-- and w->v (w outgoing). Occluding w removes that bridge's signal
-- 1/outdeg(w); I_cf(w) aggregates its share of events' total 2-hop signal.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.p1_bridge_events_v1` AS
WITH hist_in AS (
  SELECT target_address AS w, counterparty_address AS u
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-05-01')
    AND block_timestamp <  TIMESTAMP('2022-08-01')
    AND sequence_role='primary' AND direction='incoming'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
hist_out AS (
  SELECT target_address AS w, counterparty_address AS v
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-05-01')
    AND block_timestamp <  TIMESTAMP('2022-08-01')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
outdeg AS (SELECT w, COUNT(*) AS w_outdeg FROM hist_out GROUP BY 1),
aug AS (
  SELECT CONCAT(target_address,'|',counterparty_address,'|',
                CAST(target_sequence_index AS STRING)) AS event_key,
         target_address AS u, counterparty_address AS v,
         target_sequence_index
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-08-01')
    AND block_timestamp <  TIMESTAMP('2022-09-01')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
)
SELECT a.event_key, a.u, a.v, a.target_sequence_index,
       hi.w AS bridge_w, od.w_outdeg
FROM aug a
JOIN hist_in hi ON hi.u = a.u
JOIN hist_out ho ON ho.w = hi.w AND ho.v = a.v
JOIN outdeg od ON od.w = hi.w
GROUP BY 1,2,3,4,5,6;
