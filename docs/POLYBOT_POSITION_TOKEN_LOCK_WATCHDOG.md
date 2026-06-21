# POLYBOT Position Token Lock + Open Position Watchdog

Phase 4 adds an observational safety layer for open canonical paper positions.

## Purpose

An open paper position must remain tied to the actual outcome token used at entry. The watchdog does not trade, does not close positions, and does not edit paper PnL or balances. It only locks deterministic token truth and publishes source-backed review events.

## Token Lock Rules

- Active positions are only `paper_positions.current_status IN ('OPEN','EXIT_PENDING')`, `closed_at IS NULL`, and not `excluded_from_active_paper_truth`.
- Closed and quarantined legacy positions are excluded.
- The lock is derived from the actual entry lineage:
  - `paper_positions.payload_json.paper_fill_id`
  - `paper_fills.paper_order_id`
  - `paper_fills.orderbook_snapshot_id`
  - `orderbook_snapshots.token_id`
- If the token cannot be determined, the position is marked `MISSING_POSITION_TOKEN`.
- Existing locks are not silently overwritten.
- If current watched identity disagrees with a locked position token, the watchdog emits `TOKEN_IDENTITY_DRIFT_REVIEW`.

## Watchdog Polling

For each active lock, the watchdog calls read-only CLOB `/book` by the locked `token_id`.

Validation:

- `asset_id` must match the locked token.
- `market` must match locked `condition_id` when known.
- Bid/ask data must be usable.

Mark price:

- For a long YES/NO paper position, the exit reference is best bid.
- Estimated unrealized PnL is `(best_bid - avg_entry) * size`.
- This estimate is written to watchdog traces only; canonical paper PnL is not mutated.

## Events

The watchdog can publish:

- `POSITION_ORDERBOOK_REFRESHED`
- `PNL_CHANGED`
- `POSITION_EXIT_RISK`
- `TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION`
- `EXIT_REVIEW`
- `HOLD_REVIEW`
- `TOKEN_IDENTITY_DRIFT_REVIEW`
- `MISSING_POSITION_TOKEN`

These events are source-backed and include position, market, condition, side, token, and snapshot references when available.

## API

- `GET /dashboard/api/v2/open-position-watchdog`
- `GET /dashboard/api/v2/open-position-watchdog/{paper_position_id}`
- `POST /open-position-watchdog/run`

The run endpoint is bounded and respects SYSTEM ON/OFF. SYSTEM OFF blocks polling and mutation.

## Safety

This phase has no authority to:

- create paper intents, orders, fills, or positions
- close positions
- create real orders
- enable live or shadow
- call order/write endpoints

Security governance remains `YELLOW_ACCEPTED_BY_OPERATOR`.
