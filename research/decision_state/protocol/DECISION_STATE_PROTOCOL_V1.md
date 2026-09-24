# Decision-State Experimental Protocol V1

**Freeze date:** 2026-09-19
**Scope:** Level-1 address-level operational behavioral hypotheses
**Status:** frozen before new LLM responses
**Level-2 relational expectation:** deferred until Level 1 passes

## Research question

Can structured, competing LLM-generated behavioral hypotheses for an external Ethereum address improve out-of-sample prediction of future address behavior beyond the leakage-safe recent-dynamics baseline M1, and do evidence interventions detect unsupported provenance?

## Unit and data boundary

- Unit: one mapped Ethereum address at one cutoff.
- Interpretation: address-level or actor-proxy behavior; never a claimed human owner's true emotion, belief, or intent.
- Cutoffs: June 1, July 1, and August 1, 2022 UTC.
- Train: June; development/tuning: July; frozen test: August.
- Source features: `research/openworld/ow010b/data/ow010b_discovery_features.csv`.
- Source outcomes: `research/openworld/ow010b/data/ow010b_future_outcomes_evaluation_only.csv`.
- LLM evaluation population: fixed 1,000 active observed addresses per cutoff, stratified by prior 30-day event count bins and selected by SHA-256 address/cutoff hash. No outcome-conditioned sampling.
- All prompts contain only information available at or before the cutoff. Future outcomes are joined only after response files are frozen.

## Outcome consequence schema

For each address, produce four future consequence dimensions over `[t,t+7d)`:

1. `activity`: compare future event count with prior 7-day event count;
2. `active_days`: compare future active days with prior 7-day active days;
3. `counterparty_breadth`: compare future unique counterparties with prior 7-day unique counterparties;
4. `new_counterparties`: compare future new counterparties with prior 7-day new counterparties.

Each dimension has three fixed values: `up`, `same`, `down`.
The semantic hypothesis is open-ended; the consequence measurement schema is closed.

## Structured LLM output

```json
{
  "hypotheses": [
    {
      "id": "H1",
      "text": "...",
      "probability": 0.0,
      "horizon_days": 7,
      "evidence_ids": ["E_SELF", "E_MARKET"],
      "consequences": {
        "activity": "up|same|down",
        "active_days": "up|same|down",
        "counterparty_breadth": "up|same|down",
        "new_counterparties": "up|same|down"
      },
      "alternative_to": null
    }
  ],
  "abstain_probability": 0.0
}
```

- Full response: exactly three competing hypotheses when possible.
- Probabilities are normalized in post-processing if the model output is valid.
- Invalid/missing outputs are retained as invalid, never silently imputed.
- B2 uses the top-probability hypothesis only.
- B3 uses the probability-weighted mixture of all valid hypotheses.
- B4 uses the intervention gate below before forming the mixture.

## Evidence packet and interventions

Full packet evidence groups:

- `E_SELF`: recent address dynamics and event composition;
- `E_MARKET`: as-of ETH market return, volatility, and drawdown context;
- `E_COVERAGE`: observation-window and data-coverage metadata;
- `E_PLACEBO`: a non-behavioral UTC reporting sentence.

Run four frozen prompt variants per sampled address:

1. `full`: all evidence groups;
2. `minus_self`: remove `E_SELF` only;
3. `minus_market`: remove `E_MARKET` only;
4. `placebo`: replace the non-behavioral UTC sentence while holding behavioral evidence fixed.

For each consequence dimension, compute a probability vector from the hypothesis mixture and Jensen-Shannon distances:

```text
R_self    = JS(full, minus_self)
R_market  = JS(full, minus_market)
R_placebo = JS(full, placebo)
```

A hypothesis passes the intervention gate for its claimed evidence group only when the relevant response is strictly greater than `R_placebo`. If all hypotheses fail the gate, B4 abstains and uses the uniform consequence distribution.

This is an evidence-responsiveness test, not causal identification of a true belief.

## Baselines

- `B0_M1`: fixed HistGradientBoostingClassifier per consequence dimension using the preregistered M1 recent-dynamics feature set.
- `B1_DETERMINISTIC`: fixed rule-based consequence proxy from recent 7-day versus prior 23-day activity/breadth/active-day trends.
- `B2_SINGLE_LLM`: top hypothesis only from the full prompt.
- `B3_MULTI_LLM`: probability-weighted mixture of the three full-prompt hypotheses.
- `B4_VERIFIED_LLM`: B3 after the relevant-evidence intervention gate.

B0 is the primary strong baseline. B1 is an interpretable no-LLM proxy. B2/B3/B4 are evaluated on exactly the same sampled rows.

## Primary estimand and gates

Primary metric: macro-average multiclass log loss across the four consequence dimensions on the frozen August test set. Secondary metrics: macro F1, balanced accuracy, Brier score, per-dimension log loss, abstention rate, and intervention alignment.

Required gates:

1. `B4 < B0` primary test log loss with paired address bootstrap 95% CI for `B0 - B4` entirely above zero; otherwise no effectiveness pass.
2. `B4 < B2` on the same paired test rows, or a preregistered calibration/abstention improvement with no predictive deterioration; otherwise intervention value is not supported.
3. `median relevant intervention response > median placebo response` and relevant-minus-placebo paired CI above zero for at least two of `E_SELF` and `E_MARKET` on development data; do not tune this threshold on August.
4. No evidence of future leakage, outcome-conditioned sampling, or test-time response selection.
5. Report active and low-activity strata separately. A gain only in the highest-activity stratum is not a general pass.

No monotonicity claim `B4>B3>B2>B1>B0` is assumed.

## Tuning and freeze rules

- Prompt text, consequence vocabulary, JSON schema, intervention rule, B4 gate, model hyperparameters, feature lists, and sample hash are frozen before August responses are used.
- June is used for deterministic model fitting; July is used only for threshold/calibration checks that are explicitly recorded; August is read once for final evaluation.
- Future outcomes never enter prompts, model features, sample selection, or intervention selection.
- Invalid LLM responses are reported and do not receive silent replacement.
- If the endpoint or parse yield fails the predeclared minimum, record an operational no-go rather than changing the protocol after seeing outcomes.

## Interpretation boundary

A pass supports only:

> structured address-level behavioral hypotheses, with evidence intervention checks, add bounded future predictive value beyond M1 in this temporal window.

It does not support true emotion, human-owner belief, causal intention, or Level-2 relational expectation.
