# Certificate repair round v2 — frozen before execution

This resumes the interrupted 2026-09-30 task. The old `motif_cert_smoke01` is a
13-active-case smoke, not a completed 52-active-case experiment. Its intersection
pool, conditional MRR denominator, permissive validator and unbounded residual
must not be used as full-round evidence. Existing runs are preserved.

## Data and evaluation boundaries
- Offline March–July partitions only; August data/labels remain locked. No paid
  queries, inference-service calls or endpoint/configuration changes.
- All feature and certificate events satisfy timestamp < each case cutoff.
- Use the original 2,300 cases (2,150 train; 150 dev, including 52 active).
- Freeze a per-case union of existing motif, GraphMixer and Typed-TGN retrieval
  pools, checking membership against cutoff history; never inject a target.
- Report support and R@5/50/100, MRR@5 over every active case (unsupported = 0);
  supported-only metrics are separately labeled. OPEN_WORLD is a separate head.
- Freeze seeds 0/1/2, six epochs, AdamW lr=0.001 and weight_decay=0.0001,
  batch size 32, final epoch checkpoint, no dev checkpoint selection.
- Same cases, candidate pools and update budget for learned comparisons; source
  transformations fit on train only. Report parameter counts/runtime differences.
- Certificate-control comparisons use identical architecture and dimensions.
- Bootstrap paired differences by wallet, averaging seeds before resampling.

## Repairs and required deliverables
1. Construct proofs from canonical, deduplicated physical events. Preserve hash,
   type, endpoints, chain position, log/trace information, and role annotations.
   Only strictly ordered wallet→peer→candidate events qualify as paths; shared
   asset contexts are wedges. Distinct transaction hashes define independent
   evidence, including across external/transfer/trace records.
2. Independently resolve proof event IDs against the event ledger and verify
   time, type, role, direction, connection, chain order, and distinct transactions.
3. Separate native value fingerprints, burst, failure, per-token direction/flow,
   trace depth, and as-of role/hub groups. Do not compare raw token amounts across
   assets. Missing selector/nonce/gas/decimals/protocol labels remain unavailable.
4. Compare own-frequency, direct+global, GraphMixer-style, legacy proxy motif,
   certificate-only, fixed mixture, candidate gate, bounded residual, feature
   group ablations and matched negative controls. No certificate means exactly
   zero motif correction in fusion models.
5. Save complete scores/ranks/gates, proof coverage and duplication audits,
   structured explanations, at least five traceable cases, and event-deletion
   sensitivity with recomputed history features and matched deletion controls.
6. Persist source snapshot, hashes, configuration, logs and REPORT.md in a new
   exclusive run directory. Report negative results and unresolved limitations.

This is train/dev development, not untouched-test evidence or causal inference.
Detailed extraction caps will be persisted before the extraction starts.
