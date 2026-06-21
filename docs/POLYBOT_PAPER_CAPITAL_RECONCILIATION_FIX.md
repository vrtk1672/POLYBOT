# POLYBOT Paper Capital Reconciliation Fix

## Status

Implemented as a controlled paper-only accounting hardening phase.

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`.

## Root Cause

Root cause category: `MISSING_LOCK_ON_FILL`.

`PaperExecutionService` could insert a paper order, fill, position, and open ledger row before the final capital lock call. `PaperCapitalService.lock_on_fill()` then ran a second full guard check after the new open position already existed. In the dress rehearsal this self-counted the just-opened position against `max_open_positions`, raised a capital guard error, and the execution loop caught the exception inside the transaction scope. The already-inserted paper artifacts committed without a matching capital lock.

The close path for the two closed `691547` positions was not the source issue: each closed position released once and applied realized PnL once.

## Accounting Model

- `current_balance = initial_balance + sum(REALIZED_PNL_APPLIED)`.
- `available_balance + locked_balance = current_balance`.
- `open_exposure = sum(avg_entry * size)` for active, non-quarantined open paper positions.
- `expected_locked_balance = active unreleased capital locks for active open positions`.
- Unrealized PnL remains separate and does not mutate `current_balance`.

## Lock and Release Rules

- Fill precheck happens before paper artifacts are created.
- Final lock uses the prechecked fill/order/position lineage and no longer self-blocks on the position row it is locking.
- Each executable intent runs inside its own transaction. If capital lock fails, the order, fill, position, and open ledger for that intent roll back together.
- Close release now releases the position-specific active locked notional, not a global inferred amount.
- Duplicate close/release and duplicate realized PnL application remain idempotent by close id.

## Repair Policy

Historical repair is allowed only when:

- the paper position is active/open and non-quarantined,
- the position has a real `paper_fill_id`,
- the fill exists,
- the fill links to the same order as the position payload,
- notional is deterministic from `avg_entry * size`,
- account available balance can support the lock.

Repair creates `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL` with `repair=true` metadata. It does not create fills, orders, positions, closes, or fake PnL.

## Dashboard and Forensics

Capital and unified Paper dashboard truth now expose:

- `expected_locked_balance`
- `actual_locked_balance`
- `expected_open_exposure`
- `actual_open_exposure`
- `open_positions_without_lock`
- `locks_without_open_position`
- `duplicate_releases`
- `realized_pnl_double_apply_count`

Trade forensics now exposes per-position capital lineage:

- capital lock row
- capital release row
- active capital lock
- expected exposure
- per-position capital reconciliation status

## Rollback Notes

Code rollback should be paired with retaining the audited repair ledger row. Do not delete the repair row unless an operator explicitly decides to reverse the historical repair with a separate audit event.
