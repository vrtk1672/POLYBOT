# POLYBOT Active Truth & Historical Memory Layer Build Report

Generated: 2026-06-04

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Summary

Implemented the Active Truth & Historical Memory layer so stale decision records cannot masquerade as current Paper authorization truth. The main 30m run blocker artifact was old same-market guard evidence being reused as current opposing exposure. That path now requires fresh guard truth and emits `STALE_SAME_MARKET_GUARD` instead of treating old guard rows as active same-market exposure.

No live/shadow was enabled. No Paper orders, fills, positions, closes, or capital ledger rows were created by this phase.

## Files Created

* `app/db/migrations/0126_active_truth_historical_memory_layer.sql`
* `app/services/truth_state.py`
* `tests/test_truth_state_service.py`
* `docs/POLYBOT_ACTIVE_TRUTH_HISTORICAL_MEMORY_LAYER.md`
* `docs/POLYBOT_ACTIVE_TRUTH_HISTORICAL_MEMORY_LAYER_BUILD_REPORT.md`

## Files Changed

* `app/services/freshness_governance.py`
* `app/services/lifecycle_governance.py`
* `app/services/paper_trade_forensics.py`
* `app/services/brain_dialogue.py`
* `app/api/routes.py`
* `tests/test_lifecycle_governance.py`

## Migration

`0126_active_truth_historical_memory_layer.sql`

Tables:

* `truth_state_policy`
* `truth_state_registry`
* `truth_state_transitions`
* `truth_state_decision_links`

Seeded source policies for critical, contextual, and historical sources.

## Current Reality Found

The latest controlled 30m run completed safely but produced no trades. Forensics showed:

* `RISK_BLOCKED` remained a real critical blocker.
* Old same-market guard records were repeatedly reused as current blocker evidence.
* Stale payout/odds and capital-efficiency context was too visible in hard-block aggregates.
* Existing old Paper intents required fresh governance before execution.

## Truth-State Audit Results

Bounded audit after implementation:

* `truth_state_registry`: 1180
* `ACTIVE_FRESH`: 3
* `LAST_KNOWN`: 300
* `HISTORICAL_ONLY`: 47
* `REFRESH_REQUIRED`: 830
* `CAN_AUTHORIZE`: 3
* `CAN_INFORM_ONLY`: 300
* `CAN_TEACH_ONLY`: 47
* `MUST_REFRESH`: 830
* stale same-market guard sources: 110
* old intents requiring refresh: 20
* historical closed positions: 12

Source examples:

* same-market guard rows: `REFRESH_REQUIRED / MUST_REFRESH`
* payout/odds rows: `LAST_KNOWN / CAN_INFORM_ONLY`
* exit/hold rows: `LAST_KNOWN / CAN_INFORM_ONLY`
* capital-efficiency rows: `LAST_KNOWN / CAN_INFORM_ONLY`
* closed positions: `HISTORICAL_ONLY / CAN_TEACH_ONLY`
* true capital lock rows: `ACTIVE_FRESH / CAN_AUTHORIZE`

## Governance Smoke Results

`POST /truth-state/audit` with `limit=100`:

* records checked: 1070
* trading mutation: false
* paper/live/capital counts unchanged

`POST /lifecycle-governance/evaluate` with `limit=100`:

* plans checked: 100
* trading mutation: false
* latest outcomes used `STALE_SAME_MARKET_GUARD`
* stale payout/odds and capital-efficiency checks were informational

Historical lifecycle governance rows still remain in the database and still preserve their old blockers. Aggregate historical counts therefore still include old `SAME_MARKET_OPPOSING_SIDE_BLOCK` rows. Current bounded re-evaluation records the stale guard status separately.

## Safety Counts

Before and after smoke:

| Item | Before | After |
| --- | ---: | ---: |
| `paper_intents` | 20 | 20 |
| `paper_orders` | 12 | 12 |
| `paper_fills` | 9 | 9 |
| `paper_positions` | 12 | 12 |
| `paper_position_closes` | 9 | 9 |
| `paper_capital_ledger` | 38 | 38 |
| `live_orders` | 0 | 0 |
| `orders_v2` | 1 | 1 |
| `fills_v2` | 1 | 1 |
| canonical `positions` | 0 | 0 |

Capital before and after:

* `current_balance`: 996.81932200
* `available_balance`: 996.81932200
* `locked_balance`: 0.00000000
* `open_exposure`: 0.00000000
* `realized_pnl`: -3.18067800
* `unrealized_pnl`: 0.00000000

System remained `OFF`.

## Tests

Passed:

* `python -m py_compile app\services\truth_state.py app\services\freshness_governance.py app\services\lifecycle_governance.py app\services\paper_trade_forensics.py app\services\brain_dialogue.py app\api\routes.py tests\test_truth_state_service.py tests\test_lifecycle_governance.py`
* `pytest -q tests/test_truth_state_service.py` -> 6 passed, 1 warning
* `pytest -q tests/test_lifecycle_governance.py` -> 12 passed, 1 warning

Previously passed in this phase before the final dialogue/capital-account refinement:

* `pytest -q tests/test_same_market_side_guard.py` -> 16 passed
* `pytest -q tests/test_paper_execution_service.py` -> 9 passed
* `pytest -q tests/test_paper_execution_capital_guards.py tests/test_paper_execution_safety.py` -> 7 passed
* `pytest -q tests/test_trade_lifecycle.py tests/test_paper_trade_forensics.py` -> 16 passed, 1 warning

A later parallel rerun of those regression groups was aborted by wrapper timeout and left temporary test containers running; they were stopped. That timeout is treated as environment/test-profile cleanup pressure, not as a passing result.

## API / Dashboard

Added truth-state dashboard endpoints:

* `GET /dashboard/api/v2/truth-state`
* `GET /dashboard/api/v2/truth-state/{truth_id}`
* `GET /dashboard/api/v2/truth-state/subject/{subject_id}`
* `POST /truth-state/audit`

All return `mock_data=false`.

## Forensics And Dialogue

Paper forensics now includes:

* truth-state records linked by position/source id
* truth-state summary counts

Brain dialogue now includes:

* `Truth State: ... is ACTIVE_FRESH and can authorize ...`
* `Truth State: ... is REFRESH_REQUIRED and must refresh ...`
* `Truth State: ... is historical memory and cannot authorize ...`

## Remaining Risks

* Historical lifecycle governance rows still contain old blockers in aggregate history. Dashboards should distinguish raw historical blocker counts from current re-evaluated blocker counts.
* The next controlled run is still expected to require fresh risk, exit, capital, orderbook, lifecycle, and same-market guard cycles before Paper can become actionable.
* `RISK_BLOCKED` remains a legitimate high-volume blocker and still needs precision in the next calibration phase.

## Phase Status

GREEN for the Active Truth layer:

* stale same-market guard rows cannot authorize Paper
* old intents require refresh
* contextual economic records inform only when stale
* historical records cannot authorize
* dashboard/forensics/dialogue expose truth state
* no trading mutation occurred
* targeted tests passed

Can run 10m controlled PAPER validation: YES.
