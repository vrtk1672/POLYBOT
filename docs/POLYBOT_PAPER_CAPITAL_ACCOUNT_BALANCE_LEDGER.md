# POLYBOT Paper Capital Account + Balance Ledger

## Status

Implemented as a paper-only bankroll layer.

This feature adds a canonical default paper account and a source-backed paper capital ledger. It does not read exchange balances, does not enable live or shadow execution, and does not create real orders.

## Default Paper Account

- account_id: `paper_default`
- currency: `USD`
- initial_balance: `1000.00`
- risk_per_trade_pct: `1.0`
- max_position_size: `25.00`
- max_daily_loss_pct: `5.0`
- max_open_positions: `3`
- max_total_open_exposure_pct: `15.0`

## Capital Model

Paper fills lock capital:

- notional = `fill_price * quantity`
- available balance decreases by notional
- locked balance increases by notional
- open exposure increases by notional
- ledger event: `CAPITAL_LOCKED_ON_FILL`

Paper closes release capital:

- locked notional is released
- realized PnL is applied to current balance
- available balance increases by released notional plus realized PnL
- open exposure decreases
- ledger events: `CAPITAL_RELEASED_ON_CLOSE`, `REALIZED_PNL_APPLIED`

Unrealized PnL remains separate and is not applied to current balance.

## Guards

Paper execution asks the capital service before creating a fill or position. The capital service blocks:

- `INSUFFICIENT_PAPER_BALANCE`
- `POSITION_SIZE_LIMIT`
- `RISK_PER_TRADE_LIMIT`
- `DAILY_LOSS_LIMIT`
- `MAX_OPEN_POSITIONS`
- `MAX_EXPOSURE_LIMIT`

Blocked checks create audit ledger events where execution reaches capital validation.

## Quarantine Handling

Quarantined legacy paper positions are excluded from:

- active open position count
- open exposure
- unrealized PnL
- reconciliation checks

No legacy rows are repaired by fabricating fills or ledger entries.

## Reconciliation

Dashboard reconciliation checks:

- `current_balance = initial_balance + total REALIZED_PNL_APPLIED`
- `available_balance + locked_balance = current_balance`
- `open_exposure = active non-quarantined open position notional`
- balances are non-negative

## API

- `GET /dashboard/api/v2/paper/capital`
- `/dashboard/api/v2/paper` includes `capital_summary`, balance fields, guard status, and reconciliation status.

## Runtime Integration

Runtime order remains unchanged except:

- `PaperExecutionService` calls `PaperCapitalService.precheck_fill()` before paper fill/position creation.
- `PaperExecutionService` calls `PaperCapitalService.lock_on_fill()` after a valid fill and position are created in the same transaction.
- `PaperExitLoopService` calls `PaperCapitalService.release_on_close()` after a valid close in the same transaction.

SYSTEM OFF blocks capital mutation methods. Dashboard reads remain available.
