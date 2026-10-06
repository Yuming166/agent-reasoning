# Dataset Card: FACTS (eth-actions-benchmark v1.0.0-candidate)

## Summary
- **Name**: **FACTS** (First-Attempt Counterparty Forecasting from Sequences) — presentation name. Artifact name `eth-actions-benchmark`, version 1.0.0-candidate; built 2026-10-06. All version strings, manifest keys and frozen files keep `eth-actions-benchmark-v1.0.0-candidate` unchanged.
- **Task**: given an on-chain wallet's locally visible history up to a UTC cutoff, predict the target address of the first qualifying external transaction in the following 7 days; with historical role-binding fact diagnostics attached.
- **Domain**: Ethereum mainnet, declared source window 2022-03-01 to 2022-06-08; 1,000 sampled wallets, 2,200 queries.

## Motivation and Funding
Research use: traceable evaluation of temporal-graph / language methods on real on-chain behavior forecasting. No funding body requirements; construction process in RELEASE_PROTOCOL.md and SOURCE_MANIFEST.json.

## Data Composition
- Per query: anonymized wallet id, UTC cutoff, history parent-action references, entity alias map (strictly history-prefix);
- Parent-action rows: external/token/internal rows, raw amounts (never summed across assets), timestamps, canonical order, receipt status, missing and unknown flags, source ledger row ids;
- Answers (gold) are stored separately and produced from declared external sources; independently regenerated 2200/2200 with field-level agreement;
- Grounding gold (TRAIN only): 3,755 examples, three scopes kept separate, **automatic labels**.

## Sampling and Known Biases
- Wallets are a fixed sample of addresses active in 2022 (upstream 1,000-wallet cohort), not a random sample of the network; active queries are 52.9%;
- All three history cohorts have been explored (v19–v27 development) and cannot be renamed fresh; the original 400-wallet confirmation cohort was excluded as a group after an exposure event (SPLIT_EXPOSURE_LEDGER.json);
- Shared physical parent transactions across wallets: 3,912; across splits: 1,934 — counted separately, not automatically treated as leakage;
- Target concentration: hot-hub reuse inflates apparent scores; scorer output includes target_concentration sensitivity.

## Language / Text
- The `text` field of `action_views` is **deterministic program-template rendering**, not free-form generated text; structured and text fields cover the same semantic scope.

## Sensitivity and Anonymity
- Addresses are **linkable public identifiers**; simple hashing does not achieve irreversible identity anonymization. This package contains no real-person identity mapping and no X/Twitter social features;
- No personal-information fields exist; if downstream users link off-chain identities themselves, that responsibility is theirs.

## Claim Scope (author decision, 2026-10-06)
Option (a): the paper claims the fixed_pool track **on train only**; the retrieval track is reported on train/dev/test all. Dev/test reference_pools are explicit null placeholders (`pending_no_frozen_role_pool_for_this_split`) and are not built for this submission.

## License
Code **MIT**; documentation and grounding gold **CC BY 4.0**; on-chain factual data **CC0 1.0** (author decision 2026-10-06; see LICENSE_MATRIX.md and LICENSE-CODE-MIT.txt / LICENSE-DATA-CC0.txt).

## Maintenance and Corrections
See CORRECTIONS_PROCESS.md for the correction procedure; contact channels are set with the release channel at public release (this candidate is local-only).

## Citation Constraints
Neighboring work and claimable differences follow RELATED_BENCHMARKS.md / CITATION_EVIDENCE.json; no novelty or acceptance claims may be fabricated.
