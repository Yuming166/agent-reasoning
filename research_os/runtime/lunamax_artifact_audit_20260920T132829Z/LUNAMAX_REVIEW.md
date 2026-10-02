## 1. VERDICT

**Artifact-level verdict:** the simple **intervention-sensitivity → B4 effectiveness** story does **not survive** this frozen artifact set.

Under the audit’s stated criterion, the near-zero F–Δ associations, their instability across splits, and the wallet-cluster confidence interval crossing zero falsify the proposed **simple monotone mapping**. This is an artifact-level falsification of that mapping—not evidence that semantic validity, faithfulness, true belief, intent, psychology, or social exposure is absent.

The result is also consistent with poor aggregate B4 performance: mean B4 macro log-loss is worse than B0 on OOS, development, and test. This does not establish why it is worse.

## 2. EVIDENCE

### Main F–Δ associations

- **Pooled OOS, n=2,000:** Pearson `r=-0.0334210751`, `p=0.1351445511`; Spearman `rho=-0.0193664155`, `p=0.3866919214`.
- **July development, n=1,000:** Pearson `r=-0.0212528790`, `p=0.5020228830`; Spearman `rho=-0.0504352035`, `p=0.1109537630`.
- **Immutable August frozen test, n=1,000:** Pearson `r=-0.0549150537`, `p=0.0826161231`; Spearman `rho=+0.0240175112`, `p=0.4480560279`.
- **Activity-bin residualized OOS:** Pearson `r=-0.0365798619`, `p=0.1019598294`; Spearman `rho=-0.0219449162`, `p=0.3266366075`.
- **Wallet-cluster bootstrap, 2,000 replicates, seed `20260920`:** Pearson 95% CI `[-0.0807196324, 0.0139759655]`; Spearman 95% CI `[-0.0631592277, 0.0245122120]`.
- **Wallet-collapsed OOS:** Pearson `r=-0.0211956788`, `p=0.3500359496`; Spearman `rho=-0.0066349508`, `p=0.7698997789`.

The intervention-specific pooled Pearson associations were similarly weak: self `-0.0203254657`, market `-0.0290254517`. The placebo association was positive: `+0.048601651997`, `p=0.0297458984`; on the test split it was `+0.0974199997`, `p=0.0020411647`, with Spearman `+0.0910910192`, `p=0.0039397799`. This is a warning that the measured sensitivity may contain generic or nuisance variation rather than a specific effectiveness signal.

### Activity/history strata

The four activity/history strata did not show a stable monotone pattern:

| Stratum | n | Mean Δ | B4 gain rate | Pearson(F,Δ) |
|---|---:|---:|---:|---:|
| 1–2 | 500 | `+0.0582579808` | `0.584` | `-0.0183694558` |
| 3–9 | 500 | `-0.0042092891` | `0.566` | `-0.1084632882` |
| 10–19 | 500 | `+0.0178006175` | `0.506` | `-0.0094353906` |
| 20+ | 500 | `+0.0221323808` | `0.490` | `-0.025982085994` |

The `3–9` stratum is the most negative, but the pattern is not replicated across the other strata and remains descriptive rather than causal.

### Model summaries

Mean macro log-loss relative to B0:

- **OOS:** B0 `0.8020518733`; B1 `0.8070411443` (`Δ=+0.0049892710`); B2 `0.7988157339` (`Δ=-0.0032361394`); B3 `0.8157491785` (`Δ=+0.0136973052`); B4 `0.8255472958` (`Δ=+0.0234954225`), gain rate `0.5365`.
- **Development:** B0 `0.7934709131`; B4 `0.8109013541` (`Δ=+0.0174304410`), gain rate `0.557`.
- **Test:** B0 `0.8106328335`; B4 `0.8401932375` (`Δ=+0.0295604040`), gain rate `0.516`.

Thus, B4’s mean loss worsened on all three scopes, despite some negative medians and gain rates above 0.5. The mean/median divergence indicates a distributional or tail issue, not verified effectiveness.

### Variant parse/text audit

All four variants had:

- `3,000` records and `3,000` unique cases;
- parse-valid rate `1.0`;
- nonempty-text rate `1.0`;
- `model_returned_nunique=1`.

Exact text/consequence summaries:

| Variant | Mean hypotheses | Mean valid consequences | Mean text chars |
|---|---:|---:|---:|
| full | `2.9996666667` | `2.9996666667` | `531.526` |
| minus_market | `2.9996666667` | `2.9996666667` | `491.8196666667` |
| minus_self | `3.0000000000` | `3.0000000000` | `471.8956666667` |
| placebo | `3.0000000000` | `3.0000000000` | `525.122` |

This supports mechanical artifact integrity and text presence. It does **not** establish semantic validity, faithfulness, or that downstream behavior was caused by narrative text.

## 3. FALSIFIERS

- **Activity/autoregression:** F may reflect activity, event-history length, temporal dependence, regression to the mean, or overlap between history and evaluation target. Activity-bin residualization removes only fixed bin means; it is not causal adjustment. The language-centered branch would be weakened or killed if the association disappears under leakage-free temporal/block/wallet controls, or if text adds no information beyond pre-outcome history features.

- **Repeat-wallet clustering:** There are `2,000` OOS rows but only `1,946` wallets. The cluster-bootstrap CI crosses zero, and the wallet-collapsed estimate is also near zero. If any apparent signal is driven by repeated observations from a small number of wallets, it is not evidence for a general language-centered mechanism. Address-level behavior remains only an actor proxy.

- **Prompt/template sensitivity:** The variants differ in text length while all parse successfully. F could respond to formatting, prompt structure, verbosity, or generic output instability rather than semantic content. A future language branch should be considered failed if semantically irrelevant template/paraphrase changes materially alter F, or if the sign is not robust under locked prompt/template controls.

- **Consequence-dimension aggregation:** F–Δ uses an aggregate B4 macro log-loss, while consequences may differ by dimension and intervention type. Opposing dimension-level effects can cancel or create an aggregate association. A global language claim would be killed if the aggregate result disappears under a pre-specified dimension-wise decomposition, or if any apparent effect is confined to one non-generalizable dimension.

- **Closed consequence distributions downstream:** The B2/B3/B4 lineage converts hypotheses into closed consequence distributions and intervention features. The artifacts do not provide a matched text-only/text-free downstream ablation that holds consequence distributions fixed. Therefore, they cannot identify narrative text as the operative cause. A matched text-removal, text-randomization, or text-preserving control producing the same downstream behavior would kill the language-centered interpretation.

- **Model and aggregation effects:** The B4 mean loss is worse while the median and gain rate sometimes suggest row-level improvements. If performance differences are driven by a small number of large degradations or calibration artifacts, they cannot be described as broad effectiveness.

## 4. NEXT GATE

**Smallest no-new-LLM gate:** conduct one blinded, fixed human semantic-alignment audit; do not run another LLM experiment.

Pre-lock the following before exposing F, Δ, success/failure, model losses, split labels, or August results:

1. **Sampling:** from the `3,000` unique source cases, use the full variant, one record per case. Compute `SHA-256(case_id || "|semantic-gate-v1|")`, sort hashes, and select the first `100` cases. No selection by wallet activity, repeat status, F, Δ, B4 gain/loss, model outcome, or August membership.
2. **Blinding:** show only the narrative, intervention label, and recorded consequence categories needed for annotation. Hide address/wallet identifiers, activity history, split/date, F, Δ, B0/B4 losses, and success/failure.
3. **Locked rubric:** for each consequence dimension, record:
   - `supported / unsupported / unclear` by the narrative;
   - `specific / generic / unclear`;
   - intervention relevance: `relevant / irrelevant / unclear`.
   
   Do not infer owner identity, true belief, intent, psychology, or social exposure. Require an evidence span for every non-unclear judgment.
4. **Reliability:** independently double-code `20` of the `100` cases, report agreement before adjudication, then adjudicate using the locked rubric.
5. **Analysis:** report the overall semantic-alignment rate and reliability first. Any F/Δ association is secondary and must use all sampled cases without outcome-based case selection.

A pre-specified failure of text–consequence alignment, or unstable coding reliability, would stop the proposed language-centered branch. This gate would not validate causal effectiveness even if it passes.

## 5. CLAIM BOUNDARY

May be said now:

- In this deterministic audit, the simple monotone relationship between existing intervention sensitivity F and aggregate B4 effectiveness is falsified or unsupported.
- The result is robustly near zero across pooled/dev/test summaries and remains non-positive after the reported activity-bin and wallet-cluster checks.
- The frozen artifacts have complete parsing and nonempty text across the audited variants.
- Address-level observations are actor proxies only.

May **not** be said now:

- That semantic validity or faithfulness is absent or present.
- That F measures true belief, owner identity, intent, psychology, or verified social exposure.
- That narrative text caused B2/B3/B4 behavior.
- That B4 is effective, improves forecasting, or provides a causal intervention effect.
- That this is an Astra6 result, official claim, preregistered result, or final scientific conclusion.
- That the August 2022 frozen test has been reopened or modified.
- That this artifact audit justifies a new LLM experiment or promotion to the official ledger.

```text
large_llm_experiment_allowed=false
promotion_to_official_ledger=false
```