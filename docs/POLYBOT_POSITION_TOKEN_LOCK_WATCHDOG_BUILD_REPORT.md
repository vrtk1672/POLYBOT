# POLYBOT Position Token Lock + Open Position Watchdog Build Report

Date: 2026-06-03

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Current Reality Found

- Total paper positions: 9
- Open paper positions: 0
- Closed paper positions: 6
- Quarantined legacy positions: 3
- Open positions with fill/token/condition/side: 0 because there are no open positions
- Existing position awareness rows: 1
- Existing position reactions: 5
- Existing live orderbook watchlist items: 10
- Existing live orders: 0

Paper fills do not store `token_id` directly. The deterministic token source is the entry `orderbook_snapshots.token_id` referenced by `paper_fills.orderbook_snapshot_id`.

## Implemented

- Added `position_token_locks`.
- Added `open_position_watchdog_runs`.
- Added `open_position_watchdog_traces`.
- Added Phase 4 neural event types and awareness-domain mappings.
- Added `OpenPositionWatchdogService`.
- Added dashboard/read endpoints and bounded run endpoint.
- Added source-backed brain dialogue materialization.
- Added tests proving open-position behavior with fixtures.

## Watchdog Model

The watchdog processes only active canonical paper positions. It derives the locked token from actual entry fill/orderbook truth and does not infer from stale current market identity.

If a lock exists, token drift is reported and the lock is not overwritten.

## Reaction Rules

- Valid book: `POSITION_ORDERBOOK_REFRESHED`
- PnL estimate threshold crossed: `PNL_CHANGED`
- Spread widening, liquidity drop, missing bid, unavailable book: `POSITION_EXIT_RISK`
- Unavailable locked token book: `TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION`
- Positive PnL with exit liquidity or adverse condition: `EXIT_REVIEW`
- Stable condition: `HOLD_REVIEW`

No event executes an exit.

## API / Dashboard

- `GET /dashboard/api/v2/open-position-watchdog`
- `GET /dashboard/api/v2/open-position-watchdog/{paper_position_id}`
- `POST /open-position-watchdog/run`

Internal HTTP check returned `200` and `mock_data=false`.

## Tests Run

- `tests/test_open_position_watchdog.py`: 9 passed
- `tests/test_v3_position_awareness.py tests/test_live_orderbook_watcher.py`: 24 passed, 1 warning
- `tests/test_paper_execution_service.py tests/test_paper_execution_capital_guards.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py tests/test_paper_trade_forensics.py`: 34 passed, 1 warning
- `tests/test_v3_source_to_neuron_ingestion_wiring.py`: 8 passed, 1 warning
- Python compile check: passed

## Runtime Smoke

Sequence:

1. SYSTEM OFF.
2. Captured safety baseline.
3. Verified watchdog blocked while OFF.
4. SYSTEM ON.
5. Ran bounded watchdog, limit 25, max 30 seconds.
6. SYSTEM OFF.

Results:

- OFF run: `BLOCKED`, `SYSTEM_POWER_OFF`.
- ON run: `OK`, `NO_OPEN_POSITIONS`.
- Positions checked: 0
- Token locks: 0
- Watchdog traces: 0
- Events published: 0
- No fake position was created.
- Final SYSTEM state: OFF.

## Safety Counts

Before / after runtime smoke:

- `paper_intents`: 6 / 6
- `paper_orders`: 9 / 9
- `paper_fills`: 6 / 6
- `paper_positions`: 9 / 9
- `paper_position_closes`: 6 / 6
- `paper_capital_ledger`: 1 / 1
- `live_orders`: 0 / 0
- `orders_v2`: 1 / 1
- `fills_v2`: 1 / 1
- canonical positions: 0 / 0

Operational watchdog rows changed only by smoke run records:

- `open_position_watchdog_runs`: 0 / 2
- `open_position_watchdog_traces`: 0 / 0
- `position_token_locks`: 0 / 0

## No Open Position Statement

`NO_OPEN_POSITIONS_IN_RUNTIME_SMOKE`

Production had zero active open positions, so no token lock or watchdog event was created. Fixture tests prove open-position behavior.

## Remaining Risks

- Runtime did not observe a real open position because none currently exists.
- Security governance remains accepted-risk yellow until operator rotates or formally closes prior credential exposure.
- Future Phase 5 active observation should verify behavior when a real paper position is open.

## Phase Status

YELLOW.

Reason: service and tests are green, safety is clean, but runtime smoke had no open positions and security governance remains `YELLOW_ACCEPTED_BY_OPERATOR`.

Can run 30m active observation: YES, from Phase 4 perspective, if the separate preflight remains clean.
