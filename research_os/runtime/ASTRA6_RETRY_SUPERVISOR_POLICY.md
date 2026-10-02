
## 2026-09-21 15:02 CST policy extension

The user requested persistent retry rather than stopping on transient upstream instability. A hard-deadline timeout from `EXPERIMENT_DESIGNER_resume1` is now treated like a transient upstream failure: retry with a fresh task id and preserved parent history. Non-transient HTTP/auth/model/parse failures remain fail-closed; no fallback provider is allowed.
