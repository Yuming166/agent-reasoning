# Known Limitations (must ship with any release)

1. **Exploration status**: all three cohorts (train/dev/test) went through v19–v27 development use; every result is a development screen, not independent confirmation. The original 400-wallet confirmation cohort was excluded as a group after a root exposure event (EXPOSURE_EVENT.json).
2. **Uneven semantic coverage**: under the unified schema, credible own-wallet role packets exist for TRAIN only (30,494/53,024); DEV 0/13,411, TEST 0/25,270. Cross-split performance differences of role-based methods are first of all source-coverage differences.
3. **Labels = facts within the declared source window**: inactive only means no qualifying external action inside the declared source window, not lifetime wallet inactivity; the legal domain is the declared-source first-seen domain, not all of Ethereum.
4. **Attempted semantics**: failed receipts count as qualifying actions; results are not directly comparable with "successful transactions only" protocols.
5. **Reference pools are method artifacts**: the frozen v27lean pools contain addresses invisible before the cutoff (legal under fixed_pool); numbers from the two tracks must never be mixed.
6. **Shared targets / calendar dependence**: popular targets are reused across queries; the wallet-cluster bootstrap gives nominal intervals — shared events remain dependent across wallets, and nothing is multiply-correction adjusted.
7. **Automatic labels**: grounding gold is not human-verified; machine and program text rendering must be stated as such.
8. **Address linkability**: addresses are public linkable identifiers; hashing is not anonymization.
9. **Time boundary**: all data are 2022-03 to 2022-06; no cross-cycle, cross-chain, or current-market conclusions are supported.
10. **Single-seed baselines**: released baselines are seed-0 development screens; no multi-seed stability evidence exists.
