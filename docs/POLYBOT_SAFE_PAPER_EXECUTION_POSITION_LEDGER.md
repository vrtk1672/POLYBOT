# POLYBOT Safe Paper Execution + Position Ledger

This package implements the safe simulated paper execution layer between Paper Intent and Paper Exit/PnL.

It converts only valid `paper_intents` into:

1. `paper_orders`
2. `paper_fills`
3. `paper_positions`
4. an `OPEN` row in `paper_trade_ledger`

It does not create real orders, live orders, `orders_v2`, `fills_v2`, or canonical real positions.

## Execution Contract

A paper intent is executable only when it has:

- `intent_status='CREATED'`
- `intent_type='PAPER_ENTRY_INTENT'`
- `paper_only=true`
- `live=false`
- `execution_allowed=false`
- `order_intent_created=false`
- non-dry-run evidence
- `paper_intent_id`
- `eligibility_id`
- `risk_decision_id`
- `exit_plan_id`
- `market_id`
- `side` of `YES` or `NO`
- `intended_price`
- quantity/size/notional in `evidence`
- trusted fresh `orderbook_snapshot_id`

If any field is missing or weak, the service records blockers in `paper_execution_runs` and does not create orders, fills, or positions.

## Fill Simulation

The first safe fill model is deterministic and conservative:

- The intent must reference a fresh non-stale orderbook snapshot.
- The simulated fill price uses `best_ask` when available, otherwise `mid_price`.
- A fill is created only if the intended price is marketable against the trusted fill price plus allowed slippage.
- No stale, missing, or arbitrary price creates a fill.

Partial fills are intentionally not implemented in this first version.

## Position Ledger

Every opened paper position is created from a valid paper fill. The position payload links back to:

- source paper intent
- eligibility
- risk decision
- exit plan
- paper order
- paper fill
- orderbook snapshot

Repeated runs use deterministic IDs and unique constraints so one intent cannot create duplicate orders, fills, or positions.

## Tables

Migration `0090_safe_paper_execution_position_ledger.sql` adds:

- `paper_fills`
- `paper_execution_runs`

Existing canonical tables reused:

- `paper_runs`
- `paper_signals`
- `paper_orders`
- `paper_positions`
- `paper_trade_ledger`

## Runtime Integration

`MarketService.refresh()` now runs:

1. Paper Intent Gate
2. Paper Execution + Position Ledger
3. Paper Exit Loop + PnL Ledger

The execution service respects SYSTEM ON/OFF and State Governor. In `DATA_ONLY`, valid executable intents are blocked by mode instead of executed. If no valid intents exist, the service records `NO_VALID_PAPER_INTENTS`.

## API and Dashboard

Added:

- `POST /paper/execution/run`
- `GET /dashboard/api/v2/paper-execution`

The dashboard reports `mock_data=false`, paper intent/order/fill/position counts, open paper positions, latest timestamps, top block reasons, real/live safety deltas, and readiness of the exit/PnL layer.

## Safety

- No live trading is enabled.
- No real orders are created.
- No live orders are created.
- No paper orders/fills/positions are created without a valid intent and trusted price.
- No runtime paper intents are fabricated.
- No duplicate execution for the same intent.
