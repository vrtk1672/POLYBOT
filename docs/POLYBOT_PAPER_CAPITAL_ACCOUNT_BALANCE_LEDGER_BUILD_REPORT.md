# POLYBOT Paper Capital Account + Balance Ledger Build Report

## Current Reality Found

- SYSTEM power was `OFF` before implementation smoke.
- No existing `paper_accounts` or `paper_capital_ledger` tables existed.
- Existing paper runtime truth before migration:
  - paper_intents: 6
  - executable_paper_intents: 3
  - paper_orders: 9
  - paper_fills: 6
  - paper_positions: 9
  - open active paper positions: 0
  - closed paper positions: 6
  - quarantined paper positions: 3
  - paper_position_closes: 6
  - paper_trade_ledger: 12
  - paper_daily_pnl: 2
  - live_orders: 0
  - orders_v2: 1
  - fills_v2: 1
  - canonical positions: 0

## Capital Model Implemented

Created a default paper account with:

- initial_balance: 1000.00 USD
- risk_per_trade_pct: 1.0
- max_position_size: 25.00
- max_daily_loss_pct: 5.0
- max_open_positions: 3
- max_total_open_exposure_pct: 15.0

Created a paper capital ledger with events:

- ACCOUNT_INITIALIZED
- CAPITAL_LOCKED_ON_FILL
- CAPITAL_RELEASED_ON_CLOSE
- REALIZED_PNL_APPLIED
- UNREALIZED_PNL_MARK
- DAILY_LOSS_GUARD_TRIGGERED
- RISK_LIMIT_BLOCK
- INSUFFICIENT_BALANCE_BLOCK
- MAX_OPEN_POSITIONS_BLOCK
- MAX_EXPOSURE_BLOCK
- RECONCILIATION_CHECK

## Files Created

- `app/db/migrations/0099_paper_capital_account_balance_ledger.sql`
- `app/services/paper_capital.py`
- `tests/test_paper_capital_account.py`
- `tests/test_paper_execution_capital_guards.py`
- `tests/test_paper_exit_capital_release.py`
- `tests/test_dashboard_paper_capital_truth.py`
- `docs/POLYBOT_PAPER_CAPITAL_ACCOUNT_BALANCE_LEDGER.md`
- `docs/POLYBOT_PAPER_CAPITAL_ACCOUNT_BALANCE_LEDGER_BUILD_REPORT.md`

## Files Changed

- `app/services/paper_execution.py`
- `app/services/paper_exit_loop.py`
- `app/services/paper_dashboard_truth.py`
- `app/services/brain_dialogue.py`
- `app/api/routes.py`

## Runtime Integration

- Paper execution now performs capital precheck before paper fill/position creation.
- Valid paper fills lock notional capital in the same transaction.
- Paper close releases capital and applies realized PnL exactly once when a capital lock exists.
- Quarantined paper positions are excluded from active capital truth.
- Capital Neuron dialogue can materialize from `paper_capital_ledger`.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/paper/capital`

Extended:

- `GET /dashboard/api/v2/paper`

Dashboard returns `mock_data=false`, capital balances, guard status, ledger events, and reconciliation status.

## Tests Run

- `docker compose --profile test build test test_migrate`: passed.
- `docker compose --profile test run --rm test python -m pytest tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_paper_exit_capital_release.py tests/test_dashboard_paper_capital_truth.py -q`: 13 passed, 1 warning.
- `docker compose --profile test run --rm test python -m pytest tests/test_paper_execution_service.py tests/test_paper_position_ledger.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_paper_pnl_reconciliation.py tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py tests/test_paper_no_live_safety.py tests/test_paper_no_orphans_duplicates.py -q`: 30 passed, 1 warning.
- `docker compose --profile test run --rm test python -m pytest tests/test_trusted_orderbook_evidence_service.py tests/test_trusted_orderbook_runtime.py tests/test_dashboard_trusted_orderbook_truth.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py -q`: 19 passed, 1 warning.

## Runtime Deployment / Smoke

- `docker compose build api migrate`: passed.
- `docker compose run --rm migrate`: applied `0099_paper_capital_account_balance_ledger.sql`.
- `docker compose up -d api`: passed.
- `GET /healthz`: 200.
- `GET /system/power`: `OFF`, runtime work blocked.
- `GET /dashboard/api/v2/paper/capital`: 200, `mock_data=false`, reconciliation `OK`.

Short smoke:

- SYSTEM ON posted with reason `paper_capital_short_smoke_on`.
- Observed short runtime window.
- SYSTEM OFF posted with reason `paper_capital_short_smoke_complete_off`.
- No new paper fills/closes occurred during the window.
- No capital movement occurred beyond account initialization.
- live_orders remained 0.
- orders_v2 remained 1.
- fills_v2 remained 1.
- canonical positions remained 0.

## Before / After Counts

Before:

- current_balance: no account existed
- available_balance: no account existed
- locked_balance: no account existed
- open_exposure: no account existed
- realized_pnl: no account existed
- unrealized_pnl: no account existed
- capital_ledger rows: no table existed
- paper_intents: 6
- paper_orders: 9
- paper_fills: 6
- paper_positions: 9
- open active positions: 0
- quarantined positions: 3
- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0

After:

- current_balance: 1000.0
- available_balance: 1000.0
- locked_balance: 0.0
- open_exposure: 0.0
- realized_pnl: 0.0
- unrealized_pnl: 0.0
- capital_ledger rows: 1
- paper_intents: 6
- executable_paper_intents: 3
- paper_orders: 9
- paper_fills: 6
- paper_positions: 9
- open active positions: 0
- quarantined positions: 3
- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0
- capital_reconciliation_status: OK

## Sample Ledger Events

- `ACCOUNT_INITIALIZED`: amount 1000.0, balance_after 1000.0, available_after 1000.0.

Fixture tests prove:

- valid paper fill locks capital
- valid paper close releases capital
- realized PnL updates current balance
- duplicate close does not double-release
- guard failures block paper execution before order/fill/position creation

## Reconciliation Result

Runtime reconciliation after migration and smoke: `OK`.

## Safety Confirmation

- SYSTEM OFF blocks capital mutation methods.
- No live orders created.
- No real orders created.
- `orders_v2`, `fills_v2`, canonical `positions` unchanged.
- Quarantined legacy positions excluded from active capital truth.
- No fake fills, fake PnL, or fake balance inserted.

## Remaining Risks

- Runtime smoke did not produce a new valid fill/close, so production capital lock/release movement was not observed. Controlled fixture tests prove the behavior.
- Existing runtime still has 3 executable-looking intents, but latest paper execution status reported `NO_VALID_PAPER_INTENTS` with `INTENT_ALREADY_EXECUTED` and `MISSING_TRUSTED_ORDERBOOK` blockers.
- Reconciliation will intentionally report RED if active pre-capital open positions appear without matching capital lock history.

## Next Recommended Step

Proceed to Neuron Intelligence Pack 1 after ChatGPT review.
