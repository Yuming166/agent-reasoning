# Draft: request to EX-Graph authors (GitHub issue / email)

Repo: https://github.com/Persdre/EX-Graph

**Title: Missing X numeric id column in twitter_matching.csv (README says X_matching.csv includes it)**

Hi, thanks for releasing EX-Graph. We are reproducing the dataset for an
academic next-counterparty forecasting study and hit a blocker:

1. README "Dataset Overview" states:
   "X_matching.csv: X accounts and the Ethereum addresses matched with
   them ... you can see the X numerical id matching with Ethereum addresses".
   But the released `twitter_matching.csv` contains only two columns:
   `node_id, ethereum_address` (27,613 rows). Its `node_id` ranges up to
   1,809,649 and matches the Ethereum graph node ids (8,820 values exceed the
   X Graph size of 1,103,509), so it cannot be the X numerical id.

2. `matching_link_prediction_graph.pkl` is homogeneous with collapsed edge
   types: the ~27.6k true match edges are indistinguishable inside the
   ~2.12M bidirectional cross-type candidate/negative pairs, and the X-side
   combined features collapse to a single PCA placeholder, so the
   eth<->X mapping cannot be recovered from the released files.

Would it be possible to additionally release either:
  (a) the full matching table with columns (ethereum_address OR eth node id,
      X numerical node id as used in `twitter_graph.pkl`), or
  (b) the raw heterogeneous DGL graph with typed match edges, or
  (c) the per-X-profile BERT vectors keyed by X numeric id mentioned in the
      paper appendix ("we provide open-source BERT-handled vectors")?

We fully understand handles must stay anonymized; numeric ids suffice.
Happy to describe our use case and cite the dataset. Thank you!
