# POLYBOT Paper Exit Capital Release Fix

## Status

Implemented as a controlled paper-only accounting fix.

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`.

## Root Cause

Root cause category: `CAPITAL_RELEASE_FAILED_AND_WAS_SWALLOWED` plus `LEDGER_IDEMPOTENCY_BUG`.

`PaperCapitalService.release_on_close()` calculated active locked notional from both normal lock rows and audited backfill lock rows, but its prerequisite check only accepted `CAPITAL_LOCKED_ON_FILL`. The position closed during the controlled 10m run had a legitimate `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL` lock, so the release path returned `NO_CAPITAL_LOCK_FOUND`.

`PaperExitLoopService` also caught per-position exceptions inside a broader transaction. If close accounting failed after close rows were inserted, the close artifacts could still commit. The exit loop now uses a per-position savepoint and treats failed capital release as a close failure, so close artifacts roll back with the accounting failure.

## Accounting Model

For every capital-managed Paper close:

1. Insert close only through the official Paper Exit path.
2. Release the active position-specific lock.
3. Apply realized PnL exactly once.
4. Update account balances atomically.
5. Write source-linked capital ledger rows.
6. Reconcile actual locked/exposure with active open positions.

Normal future closes use:

- `CAPITAL_RELEASED_ON_CLOSE`
- `REALIZED_PNL_APPLIED`

Historical repair from a real close uses:

- `CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE`
- `REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE`

## Repair Policy

The repair method only processes closed positions that have:

- a real `paper_position_closes` row,
- a real `paper_positions` row,
- a real `paper_fills` row,
- an active unreleased capital lock,
- deterministic realized PnL from the close row.

It does not create orders, fills, positions, closes, fake PnL, or fake ledger lineage.

## Runtime Repair Applied

The controlled 10m run-created close was repaired:

- position: `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- close: `paper_close_7668d890-0fe3-5aa3-bc32-996a2f121da2`
- market: `598936`
- side: `YES`
- entry: `0.016`
- exit: `0.013`
- quantity: `10`
- released lock: `0.16`
- realized PnL applied: `-0.03`

Ledger rows added:

- `paper_capital_backfill_release_paper_close_7668d890-0fe3-5aa3-bc32-996a2f121da2`
- `paper_capital_backfill_realized_paper_close_7668d890-0fe3-5aa3-bc32-996a2f121da2`

## Dashboard And Forensics

Capital and Paper dashboard truth now expose:

- `closed_positions_with_active_lock`
- `locks_without_open_position`
- `closes_without_release`
- `closes_without_realized_pnl_applied`
- `duplicate_releases`
- `duplicate_realized_pnl_apply_count`
- expected vs actual locked balance
- expected vs actual open exposure

Paper trade forensics recognizes both normal and audited release rows as close-release lineage.

## Safety Notes

- SYSTEM remained OFF during repair.
- Live remained disabled.
- Shadow remained disabled.
- No real orders were created.
- No Paper orders/fills/positions were created.
- No closed position was reopened.
- Capital reconciliation is OK after repair.
