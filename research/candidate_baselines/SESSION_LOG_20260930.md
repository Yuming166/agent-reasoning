# Session log 2026-09-30 (candidate baselines, evening session)

## Completed
1. `candidate_openworld_temporal_baselines_full_20260930T085705Z` — full open-world
   baseline run: 300 frozen train/dev cases + 2,000 train-only expanded cases
   (5 cutoffs x 400 wallets, disjoint from frozen+explored; eligible pool ~17k senders).
   1,247 active cases. Closed-world ceiling 80.8%. Visibility classes stable across
   cutoffs (own_seen 45-62%, new_to_wallet 21-34%, open_world 17-22%).
   Address recall (all 1,247 active), K=50/100/2000:
   - typed_temporal_diffusion: 703 / 754 / 900  (best single method)
   - typed_temporal_diffusion_union: 702 / 757 / 886
   - own_frequency: 629 / 638 / 641
   - hybrid: 677 / 720 / 860
   - global / recent_popularity: ~437-483 @50
   Diffusion = truncated, hub-normalized wallet->typed-key->peer->recipient walk
   (approx PPR, NOT exact full-graph PPR). Holdout labels untouched (manifest-verified).
2. Pipeline reconciliation vs old heuristic run (fix02/retrieval_dev_full): old
   `own_frequency` support=82 == new own_seen=82; old recall@50=78 vs new 77 (tie-break
   order). NOTE: the previous handoff's "Recall@50=49/141=34.8%" was actually
   recall_at_5 mislabeled; true old recall@50 was 78/141=55.3%.
3. `graphmixer_full_v1` — GraphMixer-style MLP-mixer scorer (pure PyTorch, hash
   embeddings, last-64 event sequence, retrieve-then-rerank pool of
   own500+diff500+recent2000+global2000). Trained on 2,150 train cases (150 frozen
   train + 2,000 expanded), validated on frozen dev (52 active, pool support 40).
   - Final epoch (6): dev Recall@50 = 29/52 all-active = parity with diffusion;
     Recall@100 = 34/52 vs diffusion 32/52. Activity AUROC 0.85, OW AUROC ~0.70.
   - Best epoch (1): Recall@50 = 35/52, but epoch selection on dev = dev-tuning;
     treat as upper bound, not headline. Overfits after epoch 2 -> needs
     regularization or proper early-stopping split.
   - OPEN_WORLD ranking loss masked; open_world never counted as address hit.

## Known limitations / next steps
- Dev is small (52 active); a few cases = several pp. Do not over-read dev deltas.
- Expanded-train activity rate ~60% vs dev 35%: distribution shift; consider
  activity-stratified expansion or importance weighting.
- GraphMixer headline should use a held-out-from-train early-stop split, not dev.
- Next: Typed TGN (priority 3), then DyGFormer / TGSL / motif retriever.
- Diffusion hyperparameters (tau=90d, caps 60/25/40) untuned; sensitivity audit TODO.
