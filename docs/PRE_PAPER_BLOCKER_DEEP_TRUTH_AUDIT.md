# Pre-Paper Blocker Deep Truth Audit

Date: 2026-06-15

## 1. Executive Summary

This was a read-only blocker truth audit before Phase 10 Controlled Paper Certification.

Result: Phase 10 cannot start yet.

The current blocking chain is not one single blocker. It is a stack:

1. Lifecycle governance denies candidate-scoped paper actionability.
2. The lifecycle denial is currently rooted in stale capital evaluation evidence.
3. Duplicate active intent risk is reported, but the current implementation overcounts stale historical paper intents because it checks a non-existent `status` column instead of `intent_status`.
4. Open paper position conflict is reported, but the current implementation counts quarantined, excluded legacy positions as open because it only checks `closed_at IS NULL`.
5. Candidate-scoped evidence exists in some pre-paper surfaces, but candidate event correlation and candidate-scoped event surfaces still report zero candidate-scoped events after smoke. This is a consistency blocker, not permission to ignore the safety gate.
6. `ACTIONABLE_SMALL_PAPER` remains zero because all checked candidate-scoped bundles map to `BLOCKED_BY_LIFECYCLE`, and the what-if chain then exposes duplicate/open-position and final no-trade/coordinator layers.

No Paper Simulation was activated. No Full Monitor Run was started. No paper orders, paper fills, paper positions, live orders, or live positions were created.

## 2. Current Blocker Map

| Blocker | Classification | Should block Phase 10? | Should block paper execution? | Root status |
| --- | --- | --- | --- | --- |
| PAPER_SIMULATION_OFF | EXPECTED_PAPER_OFF_BLOCKER | Yes, until Phase 10 explicitly enables it | Yes | Valid safety gate |
| BLOCKED_BY_LIFECYCLE | CURRENT_REAL_BLOCKER | Yes | Yes | Rooted in stale capital evaluation |
| STALE_CAPITAL_EVALUATION | CURRENT_REAL_BLOCKER / DATA_QUALITY_BLOCKER | Yes | Yes | Capital evidence is far older than TTL |
| DUPLICATE_ACTIVE_INTENT_RISK | STALE_HISTORICAL_BLOCKER / BUG_SUSPECTED | Yes, until reconciled | Yes if truly active | Current count is overbroad |
| OPEN_PAPER_POSITION_CONFLICT | DUPLICATE_FALSE_POSITIVE / BUG_SUSPECTED | Yes, until query is fixed | Yes if truly open | Current rows are quarantined and excluded |
| NO_ACTIONABLE_SMALL_PAPER | CURRENT_REAL_BLOCKER | Yes | Yes | Derived from lifecycle and safety blockers |
| NO_PAPER_ACTIONABILITY | Derived blocker | Yes if no specific state exists | Yes | Should not be root |
| NO_CANDIDATE_SCOPED_EVENT | DATA_QUALITY_BLOCKER / BUG_SUSPECTED | Yes, until surfaces agree | Yes | Some surfaces disagree after smoke |
| MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE | CURRENT_REAL_BLOCKER | Yes for market-level events | Yes | Valid safety gate |
| MISSING_CANDIDATE_EVENT_LINK | DATA_QUALITY_BLOCKER | Yes for affected events | Yes | Valid unless candidate-scoped evidence exists elsewhere |
| WAITING_FOR_PRICE_REFRESH | CURRENT_SOFT_BLOCKER | Maybe | Yes | Cleared in candidate price path during smoke, remains in some aggregate surfaces |
| STALE_PAPER_INTENT / ONLY_STALE_PAPER_INTENTS | STALE_HISTORICAL_BLOCKER | Yes, until stale intents are not reused | Yes | Historical paper intent truth needs reconciliation |

## 3. Lifecycle Blocker Analysis

Latest lifecycle governance row inspected:

- `decision_id`: `lifecycle_governance_d7b128b829a656f0a5152fd65bbdb63d`
- `subject_id`: `eligibility_exit_risk_thesis_coord_3191a12086604b9fbe6e4b6ad2045330`
- `market_id`: `691547`
- `side`: `YES`
- `actionability_class`: `HARD_BLOCK`
- `allow_paper_intent`: false
- `allow_paper_execution`: false
- `critical_blockers_json`: `["STALE_CAPITAL_EVALUATION"]`
- Reason: paper intent blocked by critical lifecycle governance blockers.

Freshness detail:

- Lifecycle plan: fresh.
- Orderbook: fresh, age about 110 seconds against 180 second TTL.
- Risk decision: fresh.
- Exit plan: fresh.
- Same-market guard: fresh.
- Paper candidate: fresh.
- Capital evaluation: stale, about 984,519 seconds old against 600 second TTL.

Conclusion: `BLOCKED_BY_LIFECYCLE` is a valid current blocker. The root cause is stale capital evaluation feeding lifecycle governance, not Paper Simulation OFF and not stale orderbook for the sampled candidate.

## 4. Duplicate Intent Risk Analysis

The reported duplicate risk centers on:

- `market_id`: `824952`
- `side`: `YES`
- Count: 6 paper intents.
- Status shape: 3 `CREATED`, 3 `CLOSED`.
- Age: created around 2026-05-30 to 2026-05-31.
- Each intent in the duplicate group has order/fill/position lineage by payload or source intent.

Code issue found:

- `PaperActionabilityService._safety_counts()` checks for column `paper_intents.status`.
- `PrePaperSafetyService._counts()` also checks for `paper_intents.status`.
- The table uses `intent_status`, not `status`.
- Because `status` does not exist, the duplicate query falls back to counting all rows by market/side and does not filter terminal or consumed states.

Conclusion: duplicate active intent risk is not trustworthy as currently computed. It should still block Phase 10 until reconciled, but the likely root is stale historical/lineage state plus read-side schema mismatch, not a fresh duplicate intent created by current DATA_ONLY smoke.

## 5. Open Position Conflict Analysis

Pre-paper safety reports:

- `open_paper_positions`: 3
- `OPEN_PAPER_POSITION_CONFLICT`

Rows with `closed_at IS NULL` are:

- `0d423170...`, market `678937`, side `NO`
- `a0a5a06b...`, market `678929`, side `YES`
- `f929eb8a...`, market `629035`, side `YES`

All three have:

- `current_status`: `QUARANTINED`
- `excluded_from_active_paper_truth`: true
- `quarantine_reason`: `LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER`
- no `paper_intent_id`

Paper readiness correctly reports `open_positions=0` because it counts active truth with `current_status IN ('OPEN','EXIT_PENDING')` and `excluded_from_active_paper_truth=false`.

Conclusion: the open position conflict is a false-positive safety count in pre-paper/actionability surfaces. The safety gate should stay, but the query must exclude quarantined/excluded legacy rows before Phase 10.

## 6. Why ACTIONABLE_SMALL_PAPER Is Zero

During controlled SYSTEM ON smoke:

- Candidate price path became fresh and ready for 50 checked candidates.
- Trusted candidate-specific orderbooks were fresh for 50 checked candidates.
- Mesh evidence bundles had all five opinions.
- Paper actionability checked 50 items.
- `candidate_scoped_bundles`: 9
- `actionable_small_paper`: 0
- `actionable_if_paper_enabled`: 0
- `blocked_by_lifecycle`: 50

The direct reason is lifecycle denial. The next visible blockers are duplicate active intent risk and open paper position conflict. Paper Simulation OFF is an expected operational blocker, but it is not the reason candidate actionability is zero.

## 7. What-If Analysis

Read-only what-if classification was applied to top candidate-scoped samples. No DB state was mutated.

| Scenario | Expected actionability | Notes |
| --- | --- | --- |
| A. Current state | BLOCKED_BY_LIFECYCLE | Blockers include lifecycle, duplicate, open position |
| B. Assume lifecycle allowed | BLOCKED_BY_DUPLICATE | Duplicate/open-position surface appears next |
| C. Assume duplicate cleared | BLOCKED_BY_LIFECYCLE | Lifecycle remains primary |
| D. Assume open position cleared | BLOCKED_BY_LIFECYCLE | Lifecycle remains primary |
| E. Assume lifecycle + duplicate + open cleared | NO_TRADE | A second-layer coordinator/no-trade state remains |

Interpretation: fixing lifecycle alone is not enough. Duplicate/open-position classification must be repaired together, and coordinator/no-trade state must be regenerated or re-evaluated after fresh lifecycle/capital truth.

## 8. Future Blocker Forecast

| Future blocker | Probability | Why likely | Prevention |
| --- | --- | --- | --- |
| PAPER_SIMULATION_OFF | HIGH | Expected until Phase 10 explicitly enables paper | Keep as valid operational gate |
| Governor denied paper | HIGH | Current mode remains DATA_ONLY outside certification | Phase 10 must use official paper-on path only after pre-checks |
| Stale capital evaluation | HIGH | Current lifecycle root blocker | Add/repair event-native capital evaluation refresh feeding lifecycle |
| Duplicate stale intents | HIGH | Existing stale `CREATED` intents with execution lineage | Reconcile active intent definition and stale lineage |
| Quarantined positions counted as open | HIGH | Current pre-paper safety query overcounts | Use active paper truth status and exclusion flags |
| Candidate-scoped event surface mismatch | MEDIUM | Paper actionability sees candidate-scoped bundles, correlation endpoints do not | Align window/classifier/source rules |
| Coordinator NO_TRADE after visible blockers clear | MEDIUM | What-if scenario E exposes NO_TRADE | Recompute coordinator decision after fresh lifecycle/capital truth |
| Orderbook TTL expiry after Paper ON delay | MEDIUM | Execution TTL is short | Refresh immediately before certification actions |
| Risk/exit stale on other candidates | MEDIUM | Historical lifecycle rows include risk/exit stale blockers | Refresh/recompute per candidate in certification pre-check |
| No fresh paper intent path | MEDIUM | Current readiness has fresh_intents=0 and stale_intents=14 | Phase 10 must only create intents when all gates pass |

## 9. Stale vs Current Classification

Current real blockers:

- `BLOCKED_BY_LIFECYCLE`
- `STALE_CAPITAL_EVALUATION`
- `NO_ACTIONABLE_SMALL_PAPER`
- `PAPER_SIMULATION_OFF`
- `MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE` for market-level events

Stale or historical artifacts:

- stale `paper_intents` from late May 2026
- `STALE_PAPER_INTENT`
- `ONLY_STALE_PAPER_INTENTS`
- historical lifecycle blockers unrelated to latest candidate-scoped samples, including older `RISK_BLOCKED` and stale risk/exit rows

False positives or bug-suspected:

- `DUPLICATE_ACTIVE_INTENT_RISK`, because active intent counting uses the wrong column and ignores lineage/terminal state.
- `OPEN_PAPER_POSITION_CONFLICT`, because quarantined excluded positions are counted as open.
- `NO_CANDIDATE_SCOPED_EVENT`, because pre-paper safety and correlation surfaces can disagree with paper actionability candidate-scoped bundles after smoke.

## 10. Real vs False-Positive Blockers

Real blockers that should stay:

- Paper Simulation OFF blocks execution until Phase 10.
- Lifecycle denial blocks paper intent/execution.
- Capital evidence staleness blocks lifecycle.
- Market-level events are not candidate-actionable.
- Candidate/event mismatches and token/side mismatches must block candidate actionability.
- True duplicate active intents must block.
- True open paper positions must block opposing or conflicting paper action.

Blockers that should be fixed:

- Duplicate active intent risk should use `intent_status`, age, terminal status, and execution lineage.
- Open position conflict should use canonical active position truth and exclude quarantined rows.
- Candidate-scoped evidence counts should be consistent across candidate-scoped events, candidate-event correlation, mesh bundles, pre-paper safety, and paper actionability.
- Lifecycle should consume fresh event-native capital evaluation before Phase 10.

## 11. Required Correction Bundle

The next correction should be one focused pre-paper blocker correction bundle:

1. Capital/lifecycle freshness repair:
   - Produce or refresh event-native capital evaluation for candidate-scoped bundles.
   - Feed that evidence into lifecycle governance.
   - Regenerate lifecycle/coordinator decisions without loosening lifecycle gates.

2. Duplicate intent reconciliation:
   - Replace `status` checks with `intent_status`.
   - Treat terminal/closed/consumed/executed historical intents correctly.
   - Preserve true duplicate active intent protection.

3. Open position active truth correction:
   - Count only active, non-excluded paper positions.
   - Keep quarantined legacy rows visible but non-blocking for active position conflicts.

4. Candidate-scoped surface consistency:
   - Align candidate-scoped event, candidate-event correlation, mesh bundle, pre-paper safety, and paper actionability windows and classifiers.

5. Coordinator/no-trade second-layer audit:
   - After fresh lifecycle/capital and safety counts are fixed, re-evaluate why scenario E still maps to `NO_TRADE`.

## 12. Blockers That Must Be Fixed Together

The minimum set to fix together before Phase 10:

- `STALE_CAPITAL_EVALUATION` and lifecycle regeneration.
- Duplicate active intent count semantics.
- Open paper position conflict count semantics.
- Candidate-scoped evidence surface consistency.
- Coordinator/no-trade re-evaluation after the above corrections.

Fixing lifecycle alone would expose duplicate/open-position blockers. Fixing duplicate/open-position alone would still leave lifecycle. Fixing all three without coordinator re-evaluation may still leave `NO_TRADE`.

## 13. Blockers That Should Remain Valid Safety Gates

- Paper Simulation OFF until explicit Phase 10 activation.
- State Governor denial outside approved modes.
- Lifecycle denial.
- Risk blocked.
- Exit blocked.
- Capital blocked or missing.
- True duplicate active intent.
- True open paper position conflict.
- Market-level event not candidate-actionable.
- Token/side mismatch.
- Stale orderbook before execution.

## 14. Expected Paper-Off Blockers

These are expected today and should not be treated as defects:

- `PAPER_SIMULATION_OFF`
- `SYSTEM_POWER_OFF` after cleanup
- `RUNTIME_STOPPED` after cleanup
- `GOVERNOR_DENIED_PAPER` while not in Paper mode
- `EXECUTION_DISABLED_PAPER_OFF`

They should block execution, but should not hide candidate-level actionability analysis.

## 15. Before/After Smoke Counts

Baseline before controlled smoke:

```json
{
  "brain_outputs": 23092,
  "coordinator_decisions": 21128,
  "lifecycle_governance_decisions": 10753,
  "live_orders": 0,
  "no_trade_log": 20302,
  "paper_fills": 9,
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_position_closes": 9,
  "paper_positions": 12,
  "positions": 0
}
```

After SYSTEM ON smoke, before cleanup:

```json
{
  "brain_outputs": 24277,
  "coordinator_decisions": 21381,
  "lifecycle_governance_decisions": 10753,
  "live_orders": 0,
  "no_trade_log": 20322,
  "paper_fills": 9,
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_position_closes": 9,
  "paper_positions": 12,
  "positions": 0
}
```

Final after SYSTEM OFF cleanup:

```json
{
  "brain_outputs": 24377,
  "coordinator_decisions": 21401,
  "lifecycle_governance_decisions": 10753,
  "live_orders": 0,
  "no_trade_log": 20322,
  "paper_fills": 9,
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_position_closes": 9,
  "paper_positions": 12,
  "positions": 0
}
```

Forbidden artifact counts did not increase:

- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `live_orders`: 0 -> 0
- `positions`: 0 -> 0

Expected DATA_ONLY evidence counts increased:

- `brain_outputs`
- `coordinator_decisions`
- `no_trade_log`

## 16. Safety Result

Controlled smoke was safe.

- SYSTEM ON was activated only for the audit smoke.
- Paper Simulation remained OFF.
- Full Monitor Run was not started.
- Shadow and Live remained disabled.
- SYSTEM OFF cleanup completed.
- Runtime health after cleanup reported `SAFE_STOPPED`.
- No forbidden paper/live artifacts were created.

## 17. Recommended Next Implementation Prompt Outline

Title: POLYBOT Pre-Paper Blocker Correction Bundle

Scope:

1. Refresh event-native capital evaluation for candidate-scoped bundles.
2. Recompute lifecycle governance from fresh capital/risk/exit/orderbook evidence.
3. Fix duplicate active intent detection to use `intent_status`, terminal states, age, and execution lineage.
4. Fix open paper position conflict detection to use canonical active non-excluded position truth.
5. Align candidate-scoped event counts across pre-paper safety, candidate-scoped events, candidate-event correlation, mesh bundles, and paper actionability.
6. Re-run read-only what-if after corrections and verify whether candidate state reaches `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`.

Strict safety:

- Do not activate Paper Simulation.
- Do not create paper orders, fills, or positions.
- Do not loosen lifecycle, capital, risk, exit, or execution gates.
- Preserve true duplicate/open-position safety gates.

## 18. Can Phase 10 Start Now

No.

Minimum blockers to fix first:

1. `STALE_CAPITAL_EVALUATION` causing lifecycle denial.
2. Duplicate active intent false/stale counting.
3. Open paper position false-positive counting.
4. Candidate-scoped evidence surface mismatch.
5. Second-layer coordinator/no-trade state after those corrections.

## 19. Audit Status

Status: GREEN for audit completion.

Reason:

- Current blockers were classified.
- Lifecycle, duplicate intent, and open position roots were identified.
- What-if analysis was completed.
- Future blockers were forecasted.
- A minimum correction bundle was identified.
- No forbidden artifacts were created.

Phase 10 readiness: NO.
