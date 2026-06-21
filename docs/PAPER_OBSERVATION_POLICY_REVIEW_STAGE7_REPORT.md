# Paper Observation Policy Review Stage 7 Report

## 1. Purpose

Stage 7 adds a DATA_ONLY policy review layer for existing `PAPER_OBSERVATION` classifications. It separates observation policy eligibility from execution authority, Full Paper Certification, Shadow readiness, and Live readiness.

## 2. Money Machine Fit

The proactive stack can now produce Mesh-reviewed opportunity classifications. This stage turns those classifications into review-only observation policy truth with explicit limits, blockers, lineage checks, and ledger-readiness diagnostics.

## 3. Existing Observation Classification Audit

- Persisted `PAPER_OBSERVATION` classifications are stored in `proactive_seed_mesh_results`.
- Current reviewed classifications: 73.
- Full Paper ready classifications: 0.
- Risk states on reviewed rows: `RISK_OK`.
- Capital states on reviewed rows: `CAPITAL_WATCH`.
- Exit states on reviewed rows: `EXIT_READY`.
- Lifecycle states on reviewed rows: `DATA_ONLY_RESEARCH`.
- Hard blockers on reviewed `PAPER_OBSERVATION` rows: none.
- Soft blockers: `capital_watch_not_full_paper_ready`, `reward_evidence_weak_or_missing`.
- Orderbook state: `FRESH`.
- Token verification: `TOKENS_VERIFIED`.
- Candidate event scope: `CANDIDATE_SCOPED`.
- Lineage: complete for reviewed persisted seed Mesh rows.

## 4. Architecture

Added `PaperObservationPolicyReviewService`, a control wrapper, API routes, and a canonical review table. The service reads persisted seed Mesh `PAPER_OBSERVATION` rows, verifies lineage and safety fields, writes review records, and exposes policy state to control surfaces.

## 5. Policy States

- `OBSERVATION_POLICY_ELIGIBLE`
- `OBSERVATION_POLICY_WATCH`
- `OBSERVATION_POLICY_BLOCKED`
- `OBSERVATION_POLICY_INCOMPLETE`

## 6. Eligibility Rules

Eligibility requires a `PAPER_OBSERVATION` band, supported Edge, supported thesis, score at or above the observation threshold, active market identity, verified token/side, fresh orderbook, sufficient lineage, exit readiness, and no hard blocker. Eligibility remains review-only and does not grant paper, shadow, live, or execution permission.

## 7. Thresholds

- Observation score threshold: `60.0`.
- Edge required: `EDGE_SUPPORTED`.
- `THESIS_SUPPORTED` required for eligible.
- `THESIS_WATCH` maps to watch by default.
- `RISK_REVIEW` may be reviewed for observation, but `RISK_BLOCKED` blocks.
- `CAPITAL_WATCH` may be reviewed for observation, but `CAPITAL_BLOCK` blocks.
- Fresh orderbook and verified token/side are required.

## 8. Risk / Capital Treatment

Risk and capital states are preserved. Stage 7 does not convert `RISK_REVIEW` to `RISK_OK` or `CAPITAL_WATCH` to `CAPITAL_SUPPORT`. `CAPITAL_WATCH` remains a Full Paper blocker and a policy note for observation-only review.

## 9. Exit / Lifecycle Treatment

`EXIT_READY` is required for eligible policy review. Missing or failed exit state blocks or marks incomplete. Lifecycle hard blocks deny observation policy eligibility.

## 10. Observation Limits

- Max observation notional: `5.0`.
- Max total open observation positions: `1`.
- Max observation positions per market: `1`.
- Max observation positions per trigger family: `1`.
- Max daily observation entries: `3`.
- Time stop: `86400` seconds.
- Exit and invalidation are required.
- No averaging down.
- No pyramiding.
- Excluded from Full Paper, Shadow, and Live readiness.

## 11. Ledger / Reporting Separation Review

Current paper ledger tables do not yet expose explicit observation-mode columns, observation policy review id fields, or certification-exclusion flags. Ledger separation is therefore reported as not ready for observation execution. Future Paper Observation Execution Mode should add additive ledger tags before any paper intent creation.

## 12. API Endpoints

Added:

- `GET /dashboard/api/v2/control/paper-observation-policy`
- `POST /dashboard/api/v2/control/paper-observation-policy/refresh`
- `GET /dashboard/api/v2/control/paper-observation-policy/by-seed`
- `GET /dashboard/api/v2/control/paper-observation-policy/by-market`

Updated visibility in paper actionability, paper certification plan, pre-paper safety, trade opportunity score, proactive seed Mesh inquiry, and decision propagation trace.

## 13. Integration Surfaces

- Paper Actionability exposes policy state and keeps execution flags false.
- Paper Certification Plan separates Full Paper from observation policy counts.
- Pre-Paper Safety reports observation execution mode as not implemented and paper intent creation as not allowed.
- Decision Trace exposes policy lineage fields.
- Trade Opportunity Score exposes policy fields as visibility-only.

## 14. Tests Run

- Focused Stage 7: `11 passed`.
- Related regression: `24 passed, 3 skipped`.
- Broad policy/actionability/score selection: `86 passed, 1 skipped, 2194 deselected`.
- Stage 7 plus Stage 6 regression after multi-trigger refresh fix: `29 passed`.
- Compile: `python -m compileall app tests` passed.

## 15. DATA_ONLY Verification

Verification used DATA_ONLY refreshes, a controlled SYSTEM ON window, and SYSTEM OFF cleanup. Paper Simulation remained disabled. The runtime returned to `system_power=OFF`, `current_mode=DATA_ONLY`, and `paper_simulation.enabled=false`.

## 16. Eligible / Watch / Blocked Counts

- Reviewed `PAPER_OBSERVATION` classifications: 73.
- `OBSERVATION_POLICY_ELIGIBLE`: 73.
- `OBSERVATION_POLICY_WATCH`: 0.
- `OBSERVATION_POLICY_BLOCKED`: 0.
- `OBSERVATION_POLICY_INCOMPLETE`: 0.

## 17. Full Paper Count

Full Paper ready count remains 0.

## 18. Paper Observation Execution Readiness

Policy review produced eligible rows, but Paper Observation Execution Mode is not ready because ledger separation tags are not present and execution mode is not implemented. `paper_allowed`, `execution_allowed`, `shadow_allowed`, and `live_allowed` remain false.

## 19. Safety Result

No execution candidates were created. No paper intents, orders, fills, positions, live orders, or shadow orders were created during verification. Paper Simulation remained OFF. SYSTEM OFF cleanup completed.

## 20. Limitations

- Passive score/actionability candidates that are not linked to persisted seed Mesh review rows may show `NOT_REVIEWED`.
- Ledger separation for future observation execution requires an additive migration.
- Stage 7 does not implement Paper Observation execution.

## 21. Recommended Next Stage

If observation execution is desired, build an additive Observation Ledger Separation migration and a separate Paper Observation Execution Mode design review before any paper intent creation. Otherwise, continue policy hardening and trigger coverage expansion.
