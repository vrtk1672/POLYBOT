# Final Pre-Paper Decision Run Report

Date: 2026-06-15

## Purpose

Run one final pre-paper resolution pass across SYSTEM ON, candidate-scoped evidence, fresh price/orderbook, all-five Mesh opinions, coordinator decision, Paper Actionability, and Pre-Paper Safety.

Paper Simulation was not activated. No paper/live/shadow execution action was taken.

## Corrections Made

1. Event-native lifecycle now forces a candidate lifecycle plan rebuild before governance classification.
2. The orderbook mesh consumer refreshes safe DATA_ONLY derived inputs before lifecycle governance:
   - Same-market side guard
   - Risk evidence mesh
   - Exit hold reasoning
   - Capital efficiency
3. Trusted orderbook blocked-path counts no longer crash when the DB factory is disabled; `_zero_counts()` was restored.

These are derived-truth writes only. They do not create intents, orders, fills, positions, live orders, or capital ledger mutations.

## Current State Before Run

Baseline forbidden artifact counts:

- paper_intents: 20
- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- paper_position_closes: 9
- live_orders: 0
- positions: 0

## Controlled Run

Action:

- POST `/system/power/on`
- Mode stayed `DATA_ONLY`
- Paper Simulation stayed `OFF`
- Waited through supervisor cycles
- POST `/system/power/off`

Supervisor result:

- SYSTEM ON accepted.
- Runtime Supervisor reached `RUNNING` / `ALIVE`.
- Candidate producer ran.
- Candidate-scoped orderbook events were produced.
- SYSTEM OFF cleanup completed.

## Candidate-Scoped Evidence Result

During run:

- candidate_event_scoped: 39
- market_event_only: 0
- unlinked_with_reason: 0
- ambiguous_candidate_event: 0
- token_side_mismatch: 11

Post-cleanup Paper Readiness still reported candidate_scoped_event_count: 20.

## Mesh Evidence Result

During run:

- bundles: 50
- complete: 50
- conflicted: 0
- with_liquidity_opinion: 50
- with_risk_opinion: 50
- with_exit_opinion: 50
- with_capital_opinion: 50
- with_lifecycle_opinion: 50
- with_event_native_capital: 50
- with_event_native_lifecycle: 50
- with_all_five_opinions: 50
- candidate_scoped: 39
- consensus_blocked: 50

Sample:

- candidate_id: `eligibility_exit_risk_thesis_coord_4e27dbd7013c4a18a55295e46443dcbf`
- market_id: `691547`
- side: `YES`
- token_id: `34626184950254225208692030156208941308358060420950772251072421141618169142241`
- correlation_id: `trusted_orderbook_35289011722d44f8b400a54d147d3bfa:ob_e10577d589824cb8b2fcc2b670803b21`
- candidate_event_link_state: `LINKED_TO_CANDIDATE`
- correlation_confidence: `HIGH`
- orderbook: `TRUSTED_FRESH`, age about 53s at sample capture

## Risk Result

Risk is the current hard blocker for the strongest candidate-scoped samples.

Fresh risk evidence rows created during the run classify many candidates as:

- risk_decision: `RISK_BLOCK`
- risk_blocker_subtype: `RISK_BLOCKED_LINEAGE_CRITICAL`
- critical missing: `CONDITION_ID_MISSING`, `TOKEN_MISSING`
- edge_status: `EDGE_NOT_EVALUATED`

This is not stale capital, duplicate intent, or open-position truth. It is a current data-lineage risk blocker.

## Exit Result

Event-native exit brain is present and non-blocking for the main sample.

Some fresh-seed candidates still hit lifecycle `STALE_EXIT_PLAN`; Exit Hold was refreshed, but the existing Exit Foundation plan remains stale. There is no narrow candidate-specific Exit Foundation refresh API comparable to risk evidence, exit hold, capital efficiency, or same-market guard, so this was left as a true current blocker instead of forcing a broad exit rebuild.

## Same-Market Result

Same-market revalidation now runs for candidate-scoped orderbook events.

Event-native lifecycle rows show same-market decision `ALLOW`, so the previous stale same-market guard is cleared for the sampled candidate-scoped path.

Duplicate active intent risk: 0.

Open paper position conflict: 0.

## Capital Result

Capital is fresh and event-native.

Sample:

- capital_opinion_state: `CAPITAL_OK`
- available_capital: `996.819322`
- locked_capital: `0`
- open_exposure: `0`
- open_positions: `0`

The prior stale capital blocker is cleared.

## Lifecycle Result

Lifecycle is event-native and fresh, but denies progression.

Sample lifecycle blockers:

- `RISK_BLOCKED`
- `RISK_BLOCKED_LINEAGE_CRITICAL`

Warnings include missing context and exit-now details, but the hard denial source is risk lineage.

## Coordinator Result

Coordinator consumes all five opinions and produces:

- decision: `LIFECYCLE_BLOCKED`
- mesh_consensus_state: `CONSENSUS_BLOCKED`
- execution_allowed: false

## Paper Actionability Result

Post-cleanup `/dashboard/api/v2/control/paper-actionability`:

- candidate_scoped_bundles: 27
- actionable_small_paper: 0
- actionable_if_paper_enabled: 0
- blocked_by_lifecycle: 50
- blocked_by_duplicate: 0
- blocked_by_open_position: 0
- blocked_by_capital: 0
- blocked_by_risk: 0
- blocked_by_exit: 0
- blocked_by_data: 0

The generic no-actionability blocker is not the final explanation for candidate-scoped samples; the current specific blocker is `BLOCKED_BY_LIFECYCLE`, caused by risk-lineage denial.

## Pre-Paper Safety Result

Post-cleanup `/dashboard/api/v2/control/pre-paper-safety`:

- readiness_state: `PRE_PAPER_NOT_READY`
- blockers:
  - `PAPER_SIMULATION_OFF`
  - `BLOCKED_BY_LIFECYCLE`
  - `MISSING_CANDIDATE_EVENT_LINK`
- duplicate_active_intent_risk: 0
- open_paper_positions: 0

`PAPER_SIMULATION_OFF` is expected operationally. `BLOCKED_BY_LIFECYCLE` is the current candidate actionability blocker.

## What-If Analysis

1. Current state: `BLOCKED_BY_LIFECYCLE`.
2. If Paper Simulation were ON only: still `BLOCKED_BY_LIFECYCLE`; Paper ON alone is not enough.
3. If lifecycle blocker cleared: the strongest current candidates would need risk lineage to clear first; otherwise lifecycle would deny again.
4. If risk blocker cleared: fresh-seed candidates would next expose stale/missing Exit Foundation plan truth; strongest lineage-blocked candidates could move toward `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` only if exit and lifecycle then clear.
5. If exit blocker cleared only: lineage-risk candidates remain lifecycle-blocked.
6. If same-market guard refreshed: already done; same-market allows sampled candidate-scoped events.
7. If all stale blockers cleared: remaining real gate is risk lineage/edge evidence; Phase 10 still requires at least one candidate with lifecycle allowed.

## Ready For Phase 10

READY_FOR_PHASE_10 = NO

Exact minimum blocker left:

1. Current risk lineage blocker must be resolved for at least one candidate-scoped bundle:
   - `RISK_BLOCKED_LINEAGE_CRITICAL`
   - missing `condition_id` / token lineage in fresh risk evidence for sampled candidates
2. Candidate-specific Exit Foundation refresh may also be required for fresh-seed candidates that currently report `STALE_EXIT_PLAN`.

Do not start Phase 10 yet.

## Forbidden Artifact Counts

Before:

- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- live_orders: 0
- positions: 0

After:

- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- live_orders: 0
- positions: 0

Derived DATA_ONLY rows increased, as expected:

- brain_outputs: 26942 -> 28272
- coordinator_decisions: 21954 -> 22236
- event_log: 554750 -> 555114
- orderbook_snapshots: 52198 -> 52460
- lifecycle_governance_decisions: 10899 -> 11060
- risk_decisions: 20372 -> 20392
- exit_plans: 20372 -> 20392
- no_trade_log: 20372 -> 20392

## Safety Result

- Live remained disabled.
- Shadow remained disabled.
- Paper Simulation was not activated.
- Full Monitor Run was not started.
- SYSTEM ON was used only for the controlled decision run.
- SYSTEM OFF cleanup completed.
- No paper orders were created.
- No paper fills were created.
- No positions were created.
- No live orders were created.
- No shadow orders were created.
- No capital balances were mutated.
- No lifecycle approvals were loosened.
- No risk, exit, or execution gates were loosened.
- No historical intents or positions were deleted.
- No fake readiness/actionability was introduced.
- No DB destructive action was taken.

## Recommended Next Step

Build a focused Risk Lineage / Candidate Identity Correction Bundle:

1. Ensure candidate records and risk-evidence subject records carry condition_id and token_id from candidate-scoped event/orderbook truth when source-backed.
2. Add a narrow candidate-specific Exit Foundation refresh path, if needed, so stale legacy exit plans do not mask fresh candidate-scoped exit truth.
3. Re-run the same pre-paper decision run and require at least one lifecycle-allowed candidate before Phase 10.
