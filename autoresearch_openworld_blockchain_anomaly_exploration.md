# Autoresearch Phase III-Explore — Label-Free Open-World Behavioral Anomaly Discovery on Ethereum

**Targets:** NAACL / WWW  
**Repo:** `Yuming166/agent-reasoning`  
**Mode:** exploratory sprint; do not assume this direction is superior to the existing reasoning-worthiness mainline.  
**Hard constraint:** wash-trading / illicit labels may not train the primary discovery model.

## 0. Mission
Determine whether the project should pivot from exact next-counterparty forecasting toward **label-free discovery and monitoring of suspicious coordinated transaction behavior**, while preserving the temporal Ethereum substrate, graph structure, reasoning-worthiness, counterfactual intervention, and verified LLM reasoning.

Primary question:

> **Can suspicious coordinated transaction behaviors be discovered from temporal Ethereum graphs without illicit labels, interpreted as latent behavioral strategies, and verified through graph interventions and future evidence?**

Do not claim an address is laundering money. Prefer: behavioral anomaly, suspicious coordinated behavior, laundering-like/wash-like motif, open-world behavioral discovery, latent-strategy hypothesis, inferred decision state.

## 1. Research boundary
Assume these are not novel alone: GNN fraud/AML detection, temporal GNN fraud detection, graph contrastive AML, self-supervised graph anomaly detection, unsupervised community AML, motif detection, graph Transformers, or arbitrary LLM pseudo-labeling.

Potential contribution:

`Open-world temporal group discovery -> selective reasoning -> latent-strategy hypotheses -> intervention verification`

The LLM is not the primary anomaly detector.

## 2. Hypotheses
**H1 Label-free signal.** Without wash labels in training, high-anomaly groups/events significantly enrich independently held-out known wash labels.

**H2 Group > node.** Temporal subgraph/coordinated-group representations outperform isolated node anomaly scores.

**H3 Future validation.** High anomaly at cutoff t predicts future structural/behavioral change: counterparty bursts, flow redistribution, community restructuring, recurrence, or predictive surprise.

**H4 Intervention grounding.** For a hypothesis h supported by component k, `P(h|G) > P(h|G^-k)` more strongly than under irrelevant perturbations.

**H5 Verified pseudo-label > raw LLM label.** Intervention/future-filtered labels improve downstream utility.

**H6 Selective reasoning.** A reasoning-worthiness selector identifies graph episodes where expensive LLM interpretation adds more value.

## 3. Data contract
Use the leakage-audited BigQuery event stream: native transactions, token transfers, internal traces. The audited static EX-Graph gpickle is not an event stream and must not supply temporal order.

EX-Graph wash labels are **external evaluation only**, never primary training/model-selection labels.

Every artifact records cutoff, data version, event sources, lookback, horizon, and label access.

## 4. Temporal behavioral episodes
Construct episodes `C_(t,w)=G[V_C,E_C;t-w:t]` as ego networks, temporal communities, motif candidates, flow-connected components, or burst-connected groups.

Explore 1h, 6h, 24h, 3d, 7d and event-count windows. Preserve wallets, directed edges, timestamps, amounts, token/asset, edge type, inter-event time, flow and historical statistics.

## 5. Known motifs as baselines
Implement cycle, fan-in, fan-out, split/merge, rapid multi-hop forwarding, peel-chain-like flow, burst coordination, reciprocal transfer, amount-conserving chains, transient intermediaries, closed-group repetition.

These are probes/baselines, not the final ontology. Ask whether learned representations discover additional recurring temporal behaviors.

## 6. Model ladder
Tier 0: degree, activity, volume, burstiness, entropy, motif counts, flow conservation, novelty, community statistics.

Tier 1: Node2Vec/DeepWalk, GCN, GraphSAGE, GAT.

Tier 2: TGAT, TGN, temporal GraphSAGE, recurrent/time-aware graph encoders.

Tier 3: heterogeneous/flow-aware temporal graph with native/token/internal edge types plus direction, amount, timestamp, asset, inter-event time.

Tier 4: Graph Transformer only if Tier 2/3 clearly helps.

Do not invent a complicated architecture before strong baselines.

## 7. Self-supervised objectives
Candidate objectives:
- future-event prediction;
- masked edge/attribute reconstruction;
- temporal-order prediction;
- contrastive learning under behavior-preserving perturbations;
- flow consistency;
- motif consistency.

Candidate total:
`L = L_future + λ1 L_mask + λ2 L_contrast + λ3 L_flow + λ4 L_temporal`

Keep next-counterparty prediction as an optional auxiliary objective. Ablate every term.

## 8. Label-free anomaly scores
Compare predictive surprise, reconstruction error, representation density, contrastive inconsistency, structural novelty, and a learned hybrid calibrated without illicit labels.

## 9. Core candidate: Counterfactual Graph Anomaly Decomposition
For suspicious episode C compute A(C). Intervene with:
`remove_cycle`, `remove_burst`, `remove_amount_similarity`, `remove_rapid_forwarding`, `remove_transient_intermediary`, `remove_reciprocity`, `remove_fanout`, `remove_fanin`, `remove_community_coordination`, `shuffle_timestamps`, `shuffle_amounts`.

Measure `ΔA_k=A(C)-A(C^-k)` and form a mechanism vector over cycle/burst/flow/layering/coordination/novelty.

Random and irrelevant interventions are mandatory specificity controls.

## 10. Open-world motif discovery
Cluster episode representations with HDBSCAN, spectral clustering, k-means baseline, deep clustering/prototypes where justified.

For every cluster report size, time span, wallets, edges, asset/flow/motif statistics, anomaly distribution, future behavior, and known-label enrichment (evaluation only). Test cluster stability over time.

## 11. Validation without training labels
### A. Synthetic motif injection
Inject cycles, fan-in/out, split-merge, rapid forwarding, coordinated bursts and amount-conserving chains into held-out real backgrounds. Vary size, duration, amount noise, hops and camouflage. Report Recall@K, NDCG@K, detection delay and localization. This validates structural sensitivity, not real laundering.

### B. EX-Graph held-out enrichment
Never expose wash labels during training/model selection. Report:
`Enrichment@K = P(wash|TopK anomaly) / P(wash)`
plus Recall@K, Precision@K, NDCG, bootstrap CI and permutation null.

### C. Future consequence
At cutoff t rank anomalies, then measure future counterparty growth, flow redistribution, community change, activity bursts, recurrence and predictive surprise versus matched controls.

### D. Temporal replication
Repeat across chronological windows. A useful pattern cannot exist only in one month.

## 12. Matched controls
Match high-anomaly episodes on activity, volume, wallet age, participants, density, asset and time period. Explicitly test whether anomaly is merely volume/activity/degree.

## 13. LLM latent-strategy track
Only start after graph discovery shows non-trivial signal. Give structured evidence packets, not raw graphs. Ask for competing hypotheses such as ordinary consolidation, liquidity migration, arbitrage-like routing, distribution, accumulation, exchange-seeking, wash-like coordination, layering-like obfuscation, unknown/insufficient evidence.

Require JSON with hypothesis probability, supporting/contradicting evidence IDs, required evidence, confidence, and abstention. Never ask for “true criminal intent”.

## 14. Pseudo-label verification
Raw LLM output is not a label. For each h, remove/alter its claimed support and measure counterfactual sensitivity, evidence support, specificity versus irrelevant perturbations, temporal validity, and future consistency.

Define provisional quality:
`Q(h)=αS_evidence+βS_cf+γS_specificity+δS_future`
Tune only on development data. Accepted outputs are **verified pseudo-labels**, not ground truth.

## 15. Future-consistency
Every strategy must imply falsifiable future patterns. Examples:
- accumulation -> continued net inflow/concentration;
- distribution -> fan-out/net outflow;
- wash-like coordination -> reciprocal/cyclic synchronized closed-group activity;
- layering-like -> continued multi-hop forwarding, transient intermediaries, fragmentation.

If a label has no falsifiable implication, drop it.

## 16. Optional second-order decision-state pilot
Define `B_i(t)` as inferred decision state, not true belief. Define `B_(i→C)(t)` as a behavioral hypothesis about i's expectation of group C. Validate only through future group behavior. If no falsifiable prediction exists, DROP.

## 17. Reasoning-worthiness integration
For episode C:
`RW(C,t)=E[U_(LLM+verify)-U_graph-only | X_(C,t)]`

Compare graph-only, reason-all, random, anomaly routing, uncertainty routing, existing selector, group-level selector and oracle. Fixed budget is mandatory.

## 18. Multi-agent tournament
A Literature/novelty audit.
B Data/temporal audit.
C Classical anomaly baselines.
D Temporal GNN.
E Self-supervised representation.
F Group/motif discovery.
G Counterfactual decomposition.
H External validation (must not train discovery model).
I LLM hypotheses.
J Pseudo-label verification.
K Reasoning-worthiness.
L Red Team for leakage/confounds.

Round 1 independent; Round 2 cross-review/reproduction; Round 3 combine only independently surviving modules.

## 19. Benchmark ladder
`Random -> Volume -> Activity -> Degree -> PageRank -> Motif counts -> temporal statistical anomaly -> Isolation Forest/LOF -> Node2Vec anomaly -> graph autoencoder -> Temporal GNN -> self-supervised Temporal GNN -> group discovery -> + counterfactual decomposition -> + selective LLM -> + verified pseudo-labels`

Every sophisticated method must beat relevant simpler baselines.

## 20. Metrics
Discovery: Recall/Precision/NDCG/Enrichment@K, AUPRC only for external evaluation, cluster stability, localization.

Temporal: lead time, future-surprise prediction, recurrence, temporal stability.

Explanation: intervention sensitivity/specificity, evidence coverage, hypothesis stability, abstention calibration.

Pseudo-labels: future consistency, external agreement where appropriate, downstream utility, calibration.

Efficiency: GPU time, tokens, latency, utility/token, fraction routed to LLM.

## 21. Mandatory ablations
No temporal info; no graph; no direction; no amount; no edge type; no flow objective; no contrastive objective; no future objective; node-only vs group; no verification; random/irrelevant intervention; raw vs verified pseudo-label; reason-all vs selective; no next-counterparty auxiliary loss.

## 22. Statistical protocol
Use paired bootstrap, group/wallet resampling, temporal-block bootstrap where appropriate, permutation tests for enrichment, and multiple-comparison correction for large sweeps. Report point estimate, 95% CI, effect size, N and base rate.

## 23. FIRST SANITY CHECK
Before new architecture/LLM work, answer:

> **Can any label-free temporal/graph anomaly score trained without wash labels significantly enrich EX-Graph wash-trading labels?**

Run volume/activity, motif statistics, temporal statistical anomaly, graph embedding anomaly, simple graph autoencoder, and one temporal/self-supervised baseline.

GO signal: a non-trivial method beats activity/volume, shows significant enrichment, replicates temporally, and is not explained by graph size.

NO-GO: only volume/activity retrieves labels or gains vanish under matched controls.

## 24. Synthetic benchmark
Create `research/openworld/benchmark/synthetic_motif_injection/`. Inject motifs at S1 obvious, S2 moderate noise, S3 camouflage, S4 high camouflage. Preserve realistic background distributions. Never call this realistic criminal simulation.

## 25. Benchmark candidate
If results are strong, formalize **Open-World Temporal Behavioral Discovery**:
Input `G_≤t`; output suspicious episode/group, anomaly score, motif representation, optional strategy distribution, evidence/intervention explanation. No illicit training labels. Evaluate with injected recovery, held-out label enrichment, future consequence and temporal replication.

## 26. Paper-story candidates
WWW: **Open-World Behavioral Anomaly Discovery in Temporal Blockchain Networks**.

NAACL: **Reasoning over Behavioral Anomalies with Intervention-Verified Latent Strategy Hypotheses**.

Combined only if all stages add measurable value: **Discover, Reason, Verify: Selective LLM Reasoning for Open-World Behavioral Anomalies in Blockchain Transaction Networks**.

## 27. GO / HYBRID / NO-GO
GO pivot requires label-free discovery beating volume/activity, significant held-out enrichment, group > node, temporal replication, specific interventions, and measurable LLM/verification utility.

HYBRID if behavioral discovery is the stronger final task but next-counterparty prediction helps representation learning and reasoning-worthiness transfers.

NO-GO if anomaly reduces to activity/volume, enrichment is weak, groups unstable, LLM adds no validated utility, or pseudo-labels are not intervention-sensitive.

## 28. Experiment registry
Create `research/openworld/EXPERIMENT_REGISTRY.yaml` with:
`experiment_id, group, hypothesis, commit, data_version, cutoff, lookback, horizon, label_access, graph_construction, model, objective, anomaly_score, seed, compute, metrics, CI, leakage_audit, result, decision`.

No unregistered result enters synthesis.

## 29. Outputs
```text
research/openworld/
├── README.md
├── EXPERIMENT_REGISTRY.yaml
├── DATA_PROTOCOL.md
├── literature/NOVELTY_MAP.md
├── benchmark/synthetic_motif_injection/
├── benchmark/external_validation/
├── baselines/
├── temporal_gnn/
├── self_supervised/
├── motif_discovery/
├── interventions/
├── llm_hypotheses/
├── pseudo_label_verification/
├── reasoning_worthiness/
├── red_team/
├── figures/
├── FINAL_SYNTHESIS.md
└── NEXT_STAGE_DECISION.md
```

## 30. Required figures
1. Discover -> Select -> Reason -> Verify overview.
2. Anomaly enrichment vs Top-K.
3. Node vs group anomaly.
4. Synthetic recovery vs camouflage.
5. Counterfactual anomaly decomposition.
6. Raw vs verified pseudo-label future consistency.
7. Utility vs LLM budget.
8. Temporal replication.

## 31. Final synthesis questions
1. Can suspicious behavioral signal be discovered without illicit labels?
2. Does it beat volume/activity?
3. Does group modeling beat node anomaly?
4. Which graph representation is necessary?
5. Do discoveries enrich held-out EX-Graph wash labels?
6. Do anomaly scores predict future behavioral change?
7. Are interventions specific?
8. Do LLM hypotheses add beyond graph features?
9. Are verified pseudo-labels better than raw pseudo-labels?
10. Does selective reasoning beat reason-all/random at matched budget?
11. Does next-counterparty help as auxiliary learning?
12. Is second-order inferred-state reasoning falsifiable?
13. Which direction is stronger for NAACL?
14. Which is stronger for WWW?
15. PIVOT, HYBRID, or CURRENT MAINLINE?

## 32. Execution order
```text
0 Freeze current repo
1 Literature + novelty audit
2 Episode construction + leakage audit
3 Non-neural baselines
4 Held-out wash-label enrichment sanity check
5 Synthetic motif benchmark
6 Static graph baselines
7 Temporal GNN baselines
8 Self-supervised temporal representation
9 Group/motif discovery
10 Matched-control confound audit
11 Counterfactual anomaly decomposition
12 Temporal replication
13 IF positive: LLM strategy hypotheses
14 Intervention verification
15 Future-consistency validation
16 Verified pseudo-label experiment
17 Reasoning-worthiness integration
18 Optional second-order pilot
19 Red-team audit
20 Compare to current next-counterparty mainline
21 Chief Scientist GO/HYBRID/NO-GO
```
Do not spend large LLM budgets before Step 13.

## 33. Red-team checklist
Is it just volume/activity/degree? Exchange/service hubs? Future leakage? Identity leakage across splits? Label-informed model selection? Rare-token activity? Can motif counts match it? Does it replicate temporally? Do irrelevant interventions change scores equally? Does the LLM retain hypotheses after evidence removal? Does future behavior support the pseudo-label? Does it survive hiding raw wallet IDs?

## 34. Success criterion
A strong result supports:

> **Without illicit labels for training, a temporal graph model discovers coordinated Ethereum behavioral episodes enriched for independently known suspicious activity and predictive of future behavioral change. Selective LLM reasoning interprets only a subset of episodes, while graph/evidence interventions filter explanations insensitive to their claimed support.**

The decisive question is:

> **Does label-free group-level temporal structure contain a robust signal worth reasoning about?**

If yes: proceed toward `Discover -> Reason -> Verify`.
If partial: hybridize and retain next-counterparty as auxiliary.
If no: return to the existing reasoning-worthiness mainline and document the negative result.
