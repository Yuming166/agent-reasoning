# Research mainline: influence-adaptive trustworthy recursive reasoning

## 1. Research question

The project studies whether a temporal wallet-graph model can allocate reasoning
capacity where it has the highest expected market-relevant value. We do **not**
assume that deeper reasoning improves every wallet. Instead, the system should
identify influential wallet agents, estimate the value of a counterfactual
intervention, and choose a low, medium, or high reasoning depth under a fixed
budget.

The intended claim is:

> A selective policy that combines dynamic wallet influence, counterfactual
> sensitivity, and step-level verification can obtain better multi-step
> next-counterparty/action forecasts per unit of reasoning cost than either a
> uniformly shallow or a uniformly deep LLM policy.

The broader objective is a controlled micro-to-macro simulation: predict a
wallet's next counterparty/action, roll those predictions forward for a small
number of steps, aggregate wallet or community trajectories, and evaluate the
resulting market-relevant flow state. The first paper should treat this as a
measured hierarchy rather than claim a complete causal market simulator.

## 2. Four-layer architecture

```text
as-of temporal history H_t
        |
        v
(1) dynamic influence scorer
        |
        v
(2) adaptive depth/budget policy
        |------------------------------+
        |                              |
   low-depth path                  high-depth path
   cheap/one-step                 recursive counterfactual FSM
                                       |
                                       v
                              step-level trust checks
                                       |
                                       v
                         K-step wallet/group rollout
                                       |
                                       v
                         aggregate market-relevant state
```

### Layer 1: dynamic wallet influence

Static degree or PageRank may be used as priors, but the primary selection target
must be time-dependent and computed from pre-snapshot information. A practical
first target is **future spillover relevance**, such as weighted downstream
counterparty reach, future flow mass, protocol exposure, or change in a
market-state statistic over a fixed horizon.

A counterfactual influence proxy can be written as:

```text
I_i(t, h) = E[future spillover | H_t, wallet i retained]
           - E[future spillover | H_t, wallet i masked]
```

Until an identification strategy or natural experiment is added, this is a
predictive/counterfactual influence proxy, not a causal effect. All influence
features must be strict as-of joins; future spillover is a label only.

### Layer 2: adaptive reasoning depth

For each `(wallet, event, time)` choose `d` from a small auditable set:

- `d=0`: cheap ranker or direct structured predictor;
- `d=1`: observe history, run one counterfactual mask, update belief, predict;
- `d>=2`: recursively update a shared state for several future actions, with an
  explicit stop/continue decision.

The policy is trained against realized operational gain with failed calls treated
as cheap fallback. It is evaluated at matched token/latency budgets against
all-shallow, all-deep, random, uncertainty, repeat-only, centrality, and oracle
references.

### Layer 3: step-level trustworthy reasoning

The recursive agent must not be an unrestricted sequence of opaque LLM calls.
Every transition should emit a compact, machine-checkable state record:

- `state_before` and `state_after`;
- candidate action and counterparty;
- identifiers for supporting historical events;
- explicit counterfactual intervention;
- belief or probability update;
- confidence and stop/continue decision;
- temporal, candidate-support, and state-transition checks.

The public artifact should expose structured evidence and validation fields, not
private credentials or unrestricted hidden chain-of-thought. A failed or
unverifiable step abstains and falls back to the cheap path.

### Layer 4: hierarchical outputs

1. **Micro:** next counterparty, direction, event family, token/contract, and
   confidence.
2. **Meso:** a short wallet or community trajectory and a strategy label such as
   repeated interaction, protocol migration, splitting, or consolidation.
3. **Macro:** aggregate future flow, concentration, protocol exposure, and graph
   statistics. Price or liquidity claims require additional market-state data.

The rollout must update a shared state so that predicted actions of one wallet
can affect later predictions for other wallets. Independent per-wallet forecasts
are an ablation, not the final simulator.

## 3. Falsifiable hypotheses

### H1: counterfactual operator

At equal candidate support and with failure fallback:

```text
Full FSM > NoCF > Cheap
```

The Full-vs-NoCF comparison isolates the value of the counterfactual step rather
than the value of calling an LLM at all.

### H2: heterogeneous depth value

The gain from deeper reasoning is concentrated in some event strata (currently
especially difficult repeated interactions) and is small or negative in others.
A learned depth policy should therefore beat fixed-depth policies at matched
budget.

### H3: influence-aware allocation

A dynamic influence scorer should identify wallets with more future spillover
than static-only or activity-only ranking, under a chronological holdout.
Influence selection must not use the future spillover label at prediction time.

### H4: trustworthy recursion

Adding step-level evidence and transition checks should improve calibration,
selective risk, and multi-step stability, while reducing unsupported or
 temporally invalid transitions compared with unverified recursive LLM calls.

### H5: micro-to-macro aggregation

A coupled K-step rollout should predict future group/market-relevant flow
statistics better than independently forecasting each wallet, after controlling
for the same wallet coverage and compute budget.

## 4. Required comparisons

### Depth and routing policies

- all-cheap / all-shallow;
- all-FSM / all-deep;
- random equal-budget routing;
- high cheap uncertainty;
- repeat-only heuristic;
- centrality-only heuristic;
- influence-only routing;
- learned influence-adaptive depth (main method);
- oracle upper bound, reported only as an upper bound;
- unstructured recursive LLM calls at matched depth and budget.

### Reasoning ablations

- no counterfactual mask;
- no belief update;
- no verifier/constraint checks;
- fixed recursion depth;
- independent wallet rollouts instead of a shared state;
- no influence features;
- no social/context modality.

### Metrics

- micro: MRR, Recall@1/5/10, NDCG, action/event-family accuracy;
- meso: path/trajectory likelihood, top-k trajectory hit, calibration and
  consistency over steps;
- macro: future flow error, concentration/protocol exposure error, network-statistic
  distance, and interval calibration;
- trust: evidence coverage, as-of violations, invalid transition rate,
  counterfactual consistency, abstention risk/coverage;
- efficiency: token usage, latency, failure rate, fallback rate, and utility per
  budget.

All main deltas require paired bootstrap intervals and must be reported by
`new_popular`, `new_tail`, `repeat_easy`, and `repeat_hard`, as well as on the
September temporal holdout.

## 5. Current implementation boundary

The corrected v2 experiment validates the one-step counterfactual component and
measures real token/latency/failure behavior on four 1,000-event monthly panels.
It does not yet validate H2-H5: the corrected budget router, dynamic influence
label, multi-step state rollout, and market aggregation remain follow-up work.
The current v2 results are therefore a component result, not a frozen end-to-end
NAACL result.

The June run has an unusually low parse rate and must be diagnosed before its
outputs are used as clean router-training evidence. Operational fallback results
are retained for audit and must not be replaced by silently dropping failures.

## 6. Identity and causal boundaries

The primary agent is a wallet address or wallet cluster. The available EX-Graph
release does not by itself establish a reliable real-person identity or a
wallet-owner tweet corpus. Social context must therefore be described as
asset/project/market context unless a separately verified as-of crosswalk is
available. Similarly, observational or masked predictive influence must not be
reported as a causal market effect without identification.

## 7. Execution roadmap

1. Diagnose/re-run the June service/parse anomaly without changing the frozen
   July-August-September evaluation protocol.
2. Rebuild the v2 router dataset with explicit cheap fallback.
3. Freeze the event-level budget router: June train, July tune, August test,
   September temporal holdout.
4. Add dynamic future-spillover labels and compare influence scorers.
5. Upgrade the binary router to low/medium/high depth under matched budgets.
6. Implement verified K-step shared-state rollouts for selected wallets/groups.
7. Add macro aggregation and evaluate flow/network statistics.
8. Run cross-model and strong non-LLM baselines, then freeze the NAACL result
   package and complete the dated novelty audit.
