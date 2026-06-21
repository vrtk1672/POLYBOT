# POLYBOT Paper Exit Loop + PnL Ledger

Package 4C-U/V adds the safe paper exit and PnL accounting layer. It closes only existing open paper positions when a real exit condition is met, derives realized and unrealized PnL from position and market evidence, and exposes dashboard truth without enabling paper execution, shadow, live, or real orders.

## Contract

The paper exit loop is read/write only for paper position close state and paper accounting ledgers. It does not create paper orders, paper fills, live orders, real orders, or canonical positions.

The loop may close a paper position only when all of these are true:

- SYSTEM power is ON.
- The State Governor allows `CLOSE_POSITION`.
- The paper position already exists and is open.
- A trusted fresh mark price exists from orderbook evidence.
- A deterministic exit condition is met: take profit, stop loss, max hold time, or a supported exit plan trigger.
- The position has valid side, entry price, quantity, opened time, and market id.
- A close for the same position does not already exist.

If no open paper positions exist, the runtime result is `NO_OPEN_PAPER_POSITIONS`. The service must not create fake closes or fake PnL.

## PnL Rules

For the current long prediction-market paper position contract:

- Realized PnL = `(exit_price - entry_price) * quantity`.
- Unrealized PnL = `(mark_price - entry_price) * open_quantity`.
- If no trusted fresh mark price exists, unrealized PnL is unavailable or stale; it is not fabricated.

The daily PnL ledger is derived from paper close rows and open positions.

## Tables

Migration `0089_paper_exit_loop_pnl_ledger.sql` creates:

- `paper_position_closes`
- `paper_trade_ledger`
- `paper_daily_pnl`
- `paper_exit_loop_runs`

The schema enforces one close per position and one close ledger row per position.

## API and Dashboard

Endpoints:

- `POST /paper/exits/run`
- `GET /dashboard/api/v2/paper-exits`
- `GET /dashboard/api/v2/paper-pnl`

Dashboard responses include open positions, closed trades, realized/unrealized PnL, daily PnL, orphan checks, stale price counts, latest run truth, and safety deltas. Historical `orders_v2` totals remain visible, while created/delta fields show whether the exit loop created any new execution artifacts.

## Runtime Integration

`MarketService.refresh()` invokes `PaperExitLoopService` after the existing paper runtime stage. The service respects SYSTEM ON/OFF and State Governor. In the current DATA_ONLY runtime with no open paper positions, it records `NO_OPEN_PAPER_POSITIONS` and exits safely.

## Safety

This package does not enable paper execution, shadow, or live trading. It does not create paper positions, orders, fills, or real positions. No PnL is reported for a closed trade unless an actual open paper position was closed.
