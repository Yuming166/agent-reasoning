# Innovative important-wallet selection for NAACL (design candidates, 2026-09-08)

Task context: next-counterparty forecasting on target_event_sequences
(11.84M directional role rows, 21,469 active targets, Mar-Aug 2022);
budgeted step-level multi-agent reasoning (finite operators OBSERVE_HISTORY,
RUN_COUNTERFACTUAL_MASK, REQUEST_NEIGHBOR_AGENT, STOP_AND_PREDICT...);
selection = which wallets receive an LLM agent / larger reasoning budget.
Hard constraints: as-of features only (no test leakage), deterministic and
auditable, claims limited to model-level counterfactuals (no social causality),
novelty requires dated related-work overlap audit.

## Candidate pillars

P1. Counterfactual occlusion influence (task-centric, matches our operators)
  I_cf(w,t) = E_{x in N(w)} [ L(pred_x | H_t \ H_w) - L(pred_x | H_t) ]
  Estimate with a cheap temporal base model (sequence/GNN embedding):
  mask w's event rows, measure neighbours' next-counterparty MRR/Recall drop.
  Wallets whose observed history most changes others' predictions get agents.
  Scaling: mini-batch occlusion + degree-biased sampling; sketch for 21k targets.
  => "importance" defined exactly as what the agent's REQUEST_NEIGHBOR_AGENT /
     RUN_COUNTERFACTUAL_MASK operators are worth; selection and reasoning share
     one semantics.

P2. Temporal triggering influence (Hawkes / on-chain Granger)
  lambda_b(t) = mu_b + sum_a sum_{ti<t, a->b} alpha_ab kappa(t-ti)
  Fit directed excitation alpha_ab on bursty event streams (as-of windows);
  I_hawk(a) = outgoing triggered mass / effective branching factor; build
  time-varying influence PageRank. Captures "leads others' activity" that static
  degree/centrality (aggregated gpickle) cannot. Fully computable in BQ.

P3. Hardness-weighted consequence ("hard AND matters")
  I_sel(w) = future_activity(w) * H(counterparty distribution over recent window)
             * new_counterparty_rate(w)
  Avoids wasting agents on trivial high-centrality CEX/router hubs (easy) and
  on obscure wallets (irrelevant). Future activity proxied only with as-of
  trend features; labels used only for router training on earlier windows.

P4. Disagreement-driven deliberation routing (core NLP/NAACL hook)
  Serialize each wallet's event history into compact "behavioral language"
  (counterparty motifs, token concentration, timing, round-trips/self-loops).
  Route wallet w to an LLM agent when a trained router predicts positive
  net gain: features = base-model uncertainty, cheap-vs-LLM-prior disagreement,
  I_cf, I_hawk, archetype. Router trained on validation window to maximise
  U = DeltaMRR / reasoning tokens (bandit/supervised on gain estimates).
  Story: learning WHERE language-based deliberation helps on structured
  financial forecasting, under an explicit, auditable operator budget.

P5. Behavioural archetypes as interpretable, prompt-conditional layer
  Motif features: burstiness, new-cp rate, token/value concentration,
  reciprocity/round-trips, self-transactions, diurnal timing, gas patterns.
  Archetypes: CEX/router hub, market maker/arb, airdrop hunter, wash trader,
  organic NFT/trader, bridge. Wash archetype supervised with released
  dune_wash_trade_tx.csv + wash labels; others unsupervised/LLM-profiled.
  Uses: (a) importance = archetype leverage x archetype rarity;
        (b) agents get archetype-conditional priors/prompts;
        (c) natural-language profiles give the NAACL language hook and
            interpretable evidence traces.

P6. Social fusion (only AFTER crosswalk / X-feature extraction)
  16-d X features join as router inputs; ablation with/without; expect gains
  concentrated in socially-anchored archetypes. No causal phrasing.

## Evaluation of selection itself (not just end metrics)
- Pareto: downstream Recall@K/MRR/NDCG vs agent-budget fraction (1%,5%,20%).
- Selective risk / coverage curves; router calibration; gain prediction R^2.
- Router baselines: random, static centrality, degree, P2 Hawkes, P1 cf-gain,
  P4 learned router, oracle (cheating upper bound, labelled as such).
- Leakage audit: every selection feature timestamped <= routing decision time;
  train router on Mar-Jun, tune Jul, report Aug; frozen protocol.

## Novelty risk (must audit before claiming)
Overlaps to check with dated title/abstract/code review:
graph node valuation via Shapley/GNN occlusion; active learning on graphs;
Hawkes/temporal point processes in crypto; LLM routing / model-routing /
deliberation allocation; LLM agents for financial time series; selective
prediction / budgeted reasoning; blockchain address role classification.
Likely defensible novelty = integration: counterfactual-gain router allocating
finite language-agent operators on a temporal dual-modality financial graph,
with selection itself under evaluation.

## v1 implementation results (2026-09-08, BigQuery, bytes billed ~3.7 GB total)

Tables created in ictdata-507912.exgraph:
- wallet_asof_features_v1 (4 monthly snapshots May-Aug 2022; ~19-20k active
  wallets each; P3 difficulty/activity + P5 motif features + fwd30 labels)
- wallet_importance_ranking_v1 (ranked, partitioned; P3 proxy + percent_rank)
- wallet_trigger_proxy_v1 (P2: June hourly lag-1 corr over directed pairs;
  14,189 outgoing wallets, 2,038 with valid score; mean 0.051, max 0.639)
- selection_eval_v1 (Aug snapshot joined with popularity-baseline MRR/headroom)

Artifacts:
- artifacts/wallet_importance_ranking_v1.csv (60,260 rows, all snapshots)
- artifacts/important_wallets_aug_top20.csv
- artifacts/wallet_selection_baseline_eval_2022-08.json
- src/sql/create_wallet_asof_features_ictdata.sql
- src/sql/create_wallet_importance_ranking_ictdata.sql
- src/sql/create_p2_trigger_proxy_ictdata.sql
- src/sql/create_selection_baseline_metrics_ictdata.sql

Headline (Aug test window, popularity baseline): P3 at 1% budget covers
22.7% of hard events vs 14.6% raw volume / 1.3% random; at 20% budget
74.5% vs 65.8% / 19.3%. P2 trigger needs v2 (denser aggregation, longer
window). Leakage note: production router must train on May/Jun only.

Next: (1) popularity+recency candidate scoring in-sample per wallet for a
stronger baseline; (2) P1 occlusion gain via cheap sequence model;
(3) P4 learned router (features -> DeltaMRR/token) trained May/Jun,
frozen Aug; (4) X-feature fusion after GCP extraction.

## P1 v1 implementation results (2026-09-09)

Tables: p1_bridge_events_v1 (516,163 event-driven bridges, 109,895 distinct
August events = 24.0% of 457,128 outgoing events, 5,100 bridging wallets;
median 9 bridges/bridged event), p1_wallet_icf_v1 (per-wallet I_cf).
Artifacts: artifacts/p1_wallet_icf_ranking.csv,
artifacts/wallet_selection_p1_eval_2022-08.json,
src/sql/create_p1_occlusion_ictdata.sql, create_p1_icf_ictdata.sql,
src/sql/p1_p3_selection_curves_ictdata.sql, src/bq_run.py helper.

Key findings:
- Top-1% P1 and P3 sets overlap only 14/144 => complementary importance axes.
- P1 1% budget covers 47.9% of bridge information events (P3 29.2%, volume
  36.7%, random 5.5%); 10% -> 91.2%; 20% -> 97.9%.
- P3 still leads hard-event coverage; quota half-P1 half-P3 balances both,
  motivating the P4 learned router with P1+P3 (+motif, later X features) as
  inputs.
- v1 P1 = graph-path occlusion proxy; v2 = cheap sequence model with actual
  row masking and rescoring, for the paper's main counterfactual operator.

## P4 learned router v1 (2026-09-09)

Data: ictdata-507912.exgraph.router_dataset_v1 (59,137 rows across Jun/Jul/Aug
snapshots; 28 as-of features + P1/P2 scores + future-30d labels). Built by
src/build_p1_snapshots.py (p1_*_v2, 3 snapshots, ~1.8 GB billed),
src/build_router_tables.py (p2_trigger_v2, wallet_future_headroom_v1),
src/sql/create_router_dataset_ictdata.sql. Local copy: /tmp/router CSV,
exported via gs://ictdata-exgraph-artifacts/router_dataset_v1/.

Model: HistGradientBoostingRegressor (tuned on July: 100 trees lr .05),
trained June -> FROZEN August test. Target = log(1+ future popularity-headroom).

Frozen-Aug budget-utility (share of future headroom captured):
  budget      1%     5%    10%    20%
  router    .174   .390   .551   .733
  volume    .161   .394   .537   .718
  P1 static .089   .284   .416   .606
  oracle    .259   .522   .682   .845
Selection AUC above random, normalized to oracle: router .823, volume .805,
P1 .564, P2 .162. Spearman(score, realized headroom)=0.746.
Hard-event coverage at 10%: router .563 vs volume .549; at 1% .185 vs .169.

Findings / boundaries:
- Learned router beats raw volume at every budget on the headroom target it
  was optimized for; strongest as-of predictor is cp_new_30d (distinct new
  counterparties in the last 30 history days), then native-tx activity;
  motif/P1/P2 add little on THIS target (headroom mass is activity-driven).
- P1/P2 retain independent value for the bridge-information objective
  (P1: 47.9% bridge coverage at 1%), so the v2 router should be MULTI-OBJECTIVE
  or budget-conditioned mixture, not a single scalar regressor.
- v1 is selection-layer proxy utility (popularity headroom), not the actual
  LLM-agent DeltaMRR/token objective; the latter needs the candidate-scoring
  model + agent runner. No X features yet (P6 pending extraction).
Artifacts: artifacts/router_v1/{manifest, efficiency, hard_density,
router_aug_scores.csv, router_budget_curve.png}.

## Candidate scoring model v1 (2022-09-09)

Tables: nc_events_v1 (monthly outgoing events tagged repeat/new),
nc_edges_hist_v1 (1.16M Mar-Jul weighted pairs), nc_global_pop_v1 (352,623),
nc_bridge_cand_v1 (64.6M 2-hop non-neighbor candidates), nc_bridge_hits_v1,
nc_bridge_poolsize_v1. Code: src/nc/evaluate_candidates.py, evaluate_hybrid.py;
artifacts artifacts/nc_v1/*.json + RESULTS.md.
Headline: repeat events solved reasonably by personal recency (MRR .374,
R@10 .734 on history-known); NEW counterparties remain hard (global
non-neighbor MRR .024); 2-hop bridge covers only 5.9% of truths and a fixed
hybrid hurts, but oracle scorer selection on that pool yields +25% MRR,
motivating a learned per-candidate ranker / per-event scorer gate. Combined
v1 pipeline: MRR .185 / R@10 .368 over 457k August events.
