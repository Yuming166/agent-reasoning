# Semantic Audit V2.1 frozen-input checkpoint

- Checkpoint created: `2026-09-20T14:45:47Z` (UTC).
- This checkpoint records references and SHA-256 hashes; it does not copy or overwrite original Decision-State files.
- Frozen V1 split: June 2022 train, July 2022 development, August 2022 frozen test.
- Primary frozen estimand: B4 versus B0 macro multiclass log loss over four address-level consequence dimensions.
- Future outcomes are evaluation-only and are not exposed to any semantic annotator.
- Current B4 predictions, probabilities, intervention outputs, prompts, and split are read-only for this audit.

## Frozen B0-B4 and outcome artifacts
- `research/decision_state/results/deterministic_baseline_predictions.csv` — `50050ee4452b93215f433fe2ef4b5e17f82610bfc8e12e2d2bff702c36c8ed4c`
- `research/decision_state/results/decision_state_meta_predictions.csv` — `bdba1b317ad1bcc2a09297f138ff3153668ff756f188cf50d2a215b60b396765`
- `research/decision_state/results/decision_state_eval_cases.csv` — `6fc4d84748df69ecdd6ad5ca0f790c0d54b078d39030a4d80ab4af85bcfec03f`
- `research/decision_state/results/decision_state_llm_features.csv` — `df2cc26ae26ca5b3f704d79da64fbc3a8becbf594fea643bdf3ca3048c7e8e45`
- `research/decision_state/results/decision_state_intervention_case_metrics.csv` — `2aae34c7b62945af29aaaa006a0db55df33f11323efb534075ea77e88f9eae68`
- `research/decision_state/results/decision_state_intervention_summary.csv` — `8a747bd816f35c25ef8bced793318003ae6dc28d8ecdb72773da6bb08ad5ffe6`
- `research/decision_state/results/decision_state_loss_delta_long.csv` — `bacd06b82e36c554be35d7eee083eb54cdb0f2056167dd014ff56da7e9e451b7`
- `research/decision_state/results/decision_state_metrics.csv` — `c65c97c5dbb829bb2ff7902d3e2601c41ea12a0645dbbb1c27d36b2e57861a03`
- `research/decision_state/results/decision_state_bootstrap.csv` — `7af2319622d8caa257e5d7f9676a9c989ebe691f05d16f7a1b7b611763925113`
- `research/decision_state/results/decision_state_stratum_metrics.csv` — `cb4221174e7b6ea448d8d04c042e16b28125755a06c07dddc2bc974c5321c85e`

## Protocol, prompts, and reports
- `research/decision_state/protocol/DECISION_STATE_PROTOCOL_V1.md` — `2a03aaf9d726c756e6b62b6683ac2b7862f1d1a8d89c6576cf063432b8b13b94`
- `research/decision_state/protocol/PROTOCOL_V1_AMENDMENT_META_HEADS_20260919.md` — `6d3b126b517b8426345f20fc19c7b508dc86c9fe7e631728bbb7184a9f4f1ea6`
- `research/decision_state/src/run_hypothesis_panel.py` — `97b263768383d635d0f03e261d9914f879ec9c9e01bbceedf47d9a71279e44d9`
- `research/decision_state/results/decision_state_prompt_cases.csv` — `664c0118dfba37d52f6c39127b98607565fad14cc8861d72554a16f9500f322a`
- `research/decision_state/results/hypothesis_panel_full.manifest.json` — `2ccda847b7409003b535c3cd8025c8fd481d412227a77c612336ed0be9fd9970`
- `research/decision_state/protocol/DECISION_STATE_PROTOCOL_V1.md` — `2a03aaf9d726c756e6b62b6683ac2b7862f1d1a8d89c6576cf063432b8b13b94`
- `research/decision_state/DECISION_STATE_DECISION_20260919.md` — `afb47bc7ee54e92927cb1f2505a57be858bc2397268828f20125e41b14883ae9`
- `research/decision_state/DECISION_STATE_RESULT_REPORT_20260919.md` — `adeb2ecb838927c2e6c9d7c3e74e4803344cfdfb94ca0a5642c43bee772f55bb`
- `research/decision_state/DECISION_STATE_DEGRADATION_ANALYSIS_20260919.md` — `a86ef7fbb522fb76cb293d2d7ed3687fd58d3ba01a0ab055ca9a93feab85f677`
- `research/decision_state/DECISION_STATE_RED_TEAM_REPORT_20260919.md` — `d143c6fbc0fd015e6d609303d763933e2217ca6e49ea07c7750760a57640c469`
- `research_os/NEGATIVE_RESULTS.md` — `7aab1bc8bbfd6c344fc93bf184c7f6189b2983b8069166c7bae525c5aba68e06`
- `research_os/CLAIM_LEDGER.yaml` — `534a58802321ab6a54b1503200d54f4c849ee5220c57101b3eb150509374fe6d`
- `research_os/EXPERIMENT_REGISTRY.yaml` — `0c7872a4f606ab58ccd021c96ab18c74bb11e47de975b5dd34dd11d2d5c5496f`

## Semantic Gate V2.1 code and package
- `research/decision_state/src/prepare_semantic_gate_v2.py` — `4b07d2cb88bb216d5e56bc1ce57e3dea71e58985fb3d4fe92bc5348bcde76c22`
- `research/decision_state/src/validate_semantic_gate_annotations.py` — `a7aceae0bf3ecc8211c0caf7c759bf4fad8ffa33ecc1928fc57b50e626a8f70d`
- `research/decision_state/src/score_semantic_gate_reliability.py` — `fecda111cdb880d5d99609f023ba27ad9ab5cbc9b76f8ec1fff4772cd826c209`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/PASS_A_TEXT_ONLY_BLIND.csv` — `ba50d7bc667ca23d8cb81bc18c18dc9617b414f5cf6f214935c0302957e9f57c`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/PASS_B_STRUCTURED_REVIEW_LOCKED.csv` — `fe381a6005025787c5d4080d5acb6f5ba4ba1d2ce1ca62aacb75b81f5f99b3aa`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/DOUBLE_CODE_ROW_HANDLES.csv` — `c3103ac36b5a03c1c3cf2eb05b8aa504063fd0f47f4e6f8e573779e36c1435d2`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/SEMANTIC_GATE_V2_PROTOCOL.md` — `d0b5eef1279ed3eec6b96ea808773d2231662fe74c28eceee82051fc70163385`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/SEMANTIC_GATE_V2_MANIFEST.json` — `cafc85bc79a64871a5758b72b04382398b1fc665998424f967382136eac9bc2e`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/BLINDING_AUDIT.json` — `34372f50112bf44e30dd1c27480e53d134657c2ff5d76b39a40db73379514952`
- `research_os/runtime/lunamax_artifact_audit_20260920T132829Z/semantic_gate_v2_1/internal/SAMPLE_ROW_MAP.json` — `17cf9029e1314263b69e1c65f721efd6c7e296467fef07dfce667d44a5d81eaf`

## Non-negotiable boundary
- Do not change B4 predictions, probabilities, prompt text, intervention rule, consequence schema, frozen split, or August labels.
- Do not use August outcomes for model selection, threshold tuning, or prompt revision.
- Address-level outputs remain actor-proxy behavior, not owner belief, intent, psychology, or emotion.
