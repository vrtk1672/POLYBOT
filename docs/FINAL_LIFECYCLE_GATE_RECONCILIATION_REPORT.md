# Final Lifecycle Gate Reconciliation Report

## Purpose

Close the final pre-Phase-10 lifecycle/actionability gap without loosening safety. The task was to reconcile Lifecycle and Paper Actionability with fresh Edge/Risk truth, then return a precise Phase 10 readiness decision.

## Root Cause Found

Fresh `EDGE_SUPPORTED` / `risk_usable` evidence was reaching Risk, but Paper Actionability was still anchored to mesh bundle rows that could be stale, not candidate-actionable, or not aligned with the latest Lifecycle gate decision for the same candidate/cycle.

A second safety bug was found during reconciliation: Lifecycle could emit `ACTIONABLE_SMALL_PAPER` for `PAPER_INTENT` when the current exit gate was `INSUFFICIENT_DATA`. That violates the repository safety rule: no entry without an exit plan.

## Corrections Made

1. Paper Actionability now loads the latest candidate Lifecycle gate trace and exposes:
   - `lifecycle_decision_id`
   - `risk_evidence_id`
   - `capital_evidence_id`
   - `orderbook_snapshot_id`
   - `same_market_guard_id`
   - `exit_plan_id`
   - stale/current gate status
   - exact current lifecycle blocker

2. Paper Actionability now reconciles stale bundle blockers against the latest Lifecycle gate trace. It only maps to `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` when all current gates are clear and Edge is `EDGE_SUPPORTED`, `source_backed=true`, and `risk_usable=true`.

3. Lifecycle Governance now treats `exit_status=INSUFFICIENT_DATA`, `MISSING`, `UNKNOWN`, `EXIT_UNKNOWN`, or `EXIT_NOT_READY` as current critical exit blockers for `PAPER_INTENT` / `PAPER_EXECUTION`.

4. Decision Propagation Trace now includes Lifecycle gate evidence ids from Paper Actionability.

## Safety

No Risk, Exit, Lifecycle, Capital, Same-Market, duplicate, or open-position thresholds were loosened. The change tightened the exit gate and improved read-only trace/actionability truth.

## Controlled SYSTEM ON Final Closure Run

SYSTEM ON was accepted in `DATA_ONLY`; Runtime Supervisor stayed `RUNNING`; candidate producer stayed `RUNNING`; source refresh advanced from 22 to 28 cycles during the controlled wait. Paper Simulation stayed OFF. No Full Monitor Run was started.

Final post-run source refresh state:

- `source_refresh_orchestrator_state`: `ACTIVE`
- `cycles_completed`: `29`
- `propagation_state`: `ACTIVE`
- `propagation_breakpoint`: `null`
- fresh sources: `6`
- stale sources: `0`
- candidate-linked rows: `137441`
- directional rows: `110290`

## Edge / Risk / Lifecycle Result

Final `/source-backed-edge?limit=50`:

- `EDGE_SUPPORTED`: `50`
- `risk_usable`: `50`
- `source_backed`: `50`
- `EDGE_STALE`: `0`

Representative current candidate:

- candidate_id: `eligibility_exit_risk_thesis_coord_d4ce2b6bd4724468a93a0468d7d5e8ea`
- market_id: `691547`
- side: `YES`
- edge_state: `EDGE_SUPPORTED`
- edge_score: `1.0`
- risk_decision: `RISK_BLOCK`
- risk_blocker_subtype: `RISK_BLOCKED_CAPITAL`
- risk_usable: `true`
- source_backed: `true`

Final `/paper-actionability?limit=50`:

- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`: `0`
- `BLOCKED_BY_RISK`: `44`
- `BLOCKED_BY_EXIT`: `6`
- `BLOCKED_BY_LIFECYCLE`: `0`
- `BLOCKED_BY_DUPLICATE`: `0`
- `BLOCKED_BY_OPEN_POSITION`: `0`

Representative lifecycle gate trace:

- risk_gate_state: `RISK_BLOCK`
- capital_gate_state: `CAPITAL_OK`
- orderbook_gate_state: `FRESH`
- same_market_gate_state: `CAN_AUTHORIZE`
- exit_gate_state: `INSUFFICIENT_DATA`
- exact_current_lifecycle_blocker: `EXIT_BLOCKED`
- stale_gate_selected: `false`

## Decision Propagation Trace

Final `/decision-propagation-trace?limit=5`:

- traces: `5`
- cycle_consistent: `5`
- missing_source_refresh_context: `0`
- trace includes edge, risk, lifecycle, capital, orderbook, same-market, exit, and actionability ids.

## Counts Before / After

Forbidden artifact counts:

| Table | Before | After |
| --- | ---: | ---: |
| paper_intents | 20 | 20 |
| paper_orders | 12 | 12 |
| paper_fills | 9 | 9 |
| paper_positions | 12 | 12 |
| paper_position_closes | 9 | 9 |
| live_orders | 0 | 0 |
| positions | 0 | 0 |

DATA_ONLY counts increased as expected:

| Table | Before | After |
| --- | ---: | ---: |
| source_refresh_cycles | 22 | 29 |
| risk_evidence_mesh_evaluations | 2526 | 2766 |
| lifecycle_governance_decisions | 11824 | 12064 |
| orderbook_snapshots | 54144 | 54343 |
| exit_plans | 20695 | 20724 |
| brain_outputs | 36882 | 37897 |
| coordinator_decisions | 24110 | 24329 |

## Tests Run

- Focused: `8 passed`
- Related: `30 passed, 3 skipped`
- Broad selector: `181 passed, 334 skipped, 1532 deselected`
- Post-trace patch focused: `9 passed`
- Compile: passed for `app` and `tests`

## Deployment

`docker compose build api` and `docker compose up -d --no-deps api` completed. No DB reset, no volume reset, no migrations.

## Final Decision

`LIFECYCLE_RECONCILIATION_STATE = BLOCKED_CURRENT`

`PHASE10_READINESS_STATE = NOT_READY_CURRENT_BLOCKER`

`READY_FOR_PHASE_10 = NO`

Exact current blockers:

1. `RISK_BLOCKED` / `RISK_BLOCKED_CAPITAL`
2. `EXIT_BLOCKED` / `EXIT_NOT_READY`

These are current, source-backed, non-stale gate blockers. Paper Simulation OFF remains expected operationally, but it is not the only blocker.

## Safe Next Step

Fix the current Risk/Capital and Exit readiness blockers. Specifically, determine why Risk maps current `EDGE_SUPPORTED` candidates to `RISK_BLOCKED_CAPITAL`, and make Exit Foundation produce an exit-ready plan only when existing exit rules genuinely pass.
