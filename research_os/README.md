# EX-Graph Astra6-only autoresearch runtime

This runtime follows `ASTRA6_AUTORESEARCH_CHARTER_NAACL.md`. The first autonomous cycle is deliberately discovery-first:

1. ingest frozen project artifacts and negative results;
2. run the deterministic case-level Decision-State Evidence–Validity discovery audit;
3. ask independent Astra6 roles for literature/novelty, phenomenon, NLP-centrality, design, and falsifier audits;
4. ask an Astra6 research manager to synthesize at most 2–3 surviving branches;
5. stop before any large new LLM experiment unless the first falsification gate survives.

Run state is under `runtime/`; Astra6 call logs are non-secret JSONL. No credentials are stored here.
