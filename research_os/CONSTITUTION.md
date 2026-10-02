# Research Constitution — Astra6-only NAACL Autoresearch

This file is an immutable operating boundary for the autonomous research runtime. It may only be changed by the human PI.

- All scientific cognition, literature reasoning, branch formulation, experiment design, interpretation, review, and writing must use the private `gpt-6-astra` relay.
- No fallback model, Codex reasoning model, local LLM, or silent provider switch is allowed.
- If Astra6 is unavailable, pause the cognitive queue and preserve state.
- Local processes may only execute deterministic data processing, statistics, training/inference explicitly selected by Astra6, plotting, file operations, and scheduling.
- Every Astra6 call must log timestamp, role, branch, task/experiment id, exact returned model, prompt/response hashes, usage, and result path.
- Existing frozen tests and negative results are immutable; no test retuning or post-hoc relabeling.
- A branch must progress through literature/logic, feasibility, discovery, freeze, untouched replication, and only then scaling.
- The system optimizes for a novel, falsifiable, NLP-central, reproducible, reviewer-robust claim, not positive results or experiment count.
- Address-level behavior is an actor-proxy. Do not claim owner identity, true psychology, causal intent, or social exposure without identification.
- Every negative result is append-only in `NEGATIVE_RESULTS.md`.

Source: `ASTRA6_AUTORESEARCH_CHARTER_NAACL.md`; the charter hash is recorded in `runtime/CHARTER_SHA256.txt`.
