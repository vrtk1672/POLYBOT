# POLYBOT Paper Exit Capital Release Fix Build Report

## Dispatch

- Executor: Codex
- Task mode: `CONTROLLED_RUNTIME_FIX + PAPER_EXIT_ACCOUNTING + CAPITAL_RELEASE_RECONCILIATION`
- Risk: VERY HIGH
- ChatGPT review: REQUIRED
- Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Summary

Fixed the Paper Exit accounting path so a close cannot persist unless its position-specific capital lock is released and realized PnL is applied. Added audited repair event types, close-specific reconciliation diagnostics, forensics visibility, tests, and a bounded production repair for the close created by `controlled_10m_paper_run_20260603T225755Z`.

## Current Reality Found

Before repair:

- current_balance: `996.849322`
- available_balance: `996.689322`
- locked_balance: `0.16`
- open_exposure: `0.16`
- realized_pnl: `-3.150678`
- unrealized_pnl: `-0.04`
- expected_locked_balance: `0.0`
- expected_open_exposure: `0.0`
- open positions: `0`
- locks_without_open_position: `1`
- capital_reconciliation_status: `RED`

The target close existed and was real:

- position: `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- close: `paper_close_7668d890-0fe3-5aa3-bc32-996a2f121da2`
- realized_pnl: `-0.03`
- paper_trade_ledger close row: present
- capital release row: missing
- realized PnL applied row: missing

## Root Cause

`PaperCapitalService.release_on_close()` required a `CAPITAL_LOCKED_ON_FILL` row even though active lock math already included `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL`. The target position had the latter, so capital release returned `NO_CAPITAL_LOCK_FOUND`.

The exit loop also did not fail the close on a non-released capital result. It now raises on failed release and each position close runs inside a savepoint.

## Files Created

- `app/db/migrations/0124_paper_exit_capital_release_backfill.sql`
- `docs/POLYBOT_PAPER_EXIT_CAPITAL_RELEASE_FIX.md`
- `docs/POLYBOT_PAPER_EXIT_CAPITAL_RELEASE_FIX_BUILD_REPORT.md`

## Files Changed

- `app/services/paper_capital.py`
- `app/services/paper_exit_loop.py`
- `app/services/paper_dashboard_truth.py`
- `app/services/paper_trade_forensics.py`
- `app/services/same_market_side_guard.py`
- `app/services/capital_efficiency.py`
- `app/services/brain_dialogue.py`
- `tests/test_paper_exit_capital_release.py`
- `tests/test_paper_exit_loop.py`
- `tests/test_paper_trade_forensics.py`
- `tests/test_paper_exit_safety.py`
- `tests/test_paper_pnl_ledger.py`
- `tests/test_paper_pnl_reconciliation.py`

## DB Migration

Applied:

- `0124_paper_exit_capital_release_backfill.sql`

Adds event types:

- `CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE`
- `REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE`

Adds unique indexes for audited close repair rows.

## Exit Release Accounting Model

- Close release now accepts any active source-backed lock for the position, including `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL`.
- Release idempotency checks both normal and repair release event types.
- Realized PnL idempotency checks both normal and repair realized-PnL event types.
- A close with missing active lock is blocked and rolled back.
- A duplicate close does not double-release or double-apply PnL.

## Repair / Backfill

Used audited repair for one real close.

Rows added:

- `CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE`, amount `0.16`
- `REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE`, amount `-0.03`

No order, fill, position, close, live order, or canonical position was created.

## Runtime Smoke

Sequence:

1. Confirmed SYSTEM OFF and PAPER mode.
2. Captured safety baseline.
3. Confirmed capital reconciliation RED before repair.
4. Applied migration `0124`.
5. Ran audited close-release repair.
6. Rebuilt/restarted API.
7. Verified capital dashboard and forensics.

After repair:

- current_balance: `996.819322`
- available_balance: `996.819322`
- locked_balance: `0.0`
- open_exposure: `0.0`
- realized_pnl: `-3.180678`
- unrealized_pnl: `0.0`
- expected_locked_balance: `0.0`
- expected_open_exposure: `0.0`
- closed_positions_with_active_lock: `[]`
- locks_without_open_position: `[]`
- closes_without_release: `[]`
- closes_without_realized_pnl_applied: `[]`
- duplicate_releases: `[]`
- duplicate_realized_pnl_apply_count: `0`
- capital_reconciliation_status: `OK`

Safety counts after repair:

- paper_intents: `20`
- paper_orders: `12`
- paper_fills: `9`
- paper_positions: `12`
- paper_position_closes: `9`
- paper_capital_ledger: `38`
- live_orders: `0`
- orders_v2: `1`
- fills_v2: `1`
- canonical positions: `0`

## Tests Run

- `python -m py_compile app/services/paper_capital.py app/services/paper_exit_loop.py app/services/paper_dashboard_truth.py app/services/paper_trade_forensics.py app/services/same_market_side_guard.py app/services/capital_efficiency.py app/services/brain_dialogue.py`: passed.
- `docker compose --profile test build test`: passed.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_exit_capital_release.py -q`: 6 passed.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_exit_loop.py -q`: 7 passed.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_trade_forensics.py -q`: 6 passed, 1 warning.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_capital_account.py tests/test_dashboard_paper_capital_truth.py -q`: 8 passed, 1 warning.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_execution_capital_guards.py tests/test_paper_execution_service.py -q`: 14 passed.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_lifecycle_governance.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q`: 22 passed, 1 warning.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_execution_capital_guards.py tests/test_paper_execution_service.py tests/test_lifecycle_governance.py tests/test_paper_no_live_safety.py tests/test_paper_exit_safety.py -q`: 25 passed, 1 warning.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_pnl_ledger.py tests/test_paper_pnl_reconciliation.py tests/test_active_30m_observation_runner.py -q`: 10 passed, 1 warning.
- `docker compose --profile test run --rm --no-deps -e PYTHONPATH=/app test python -m pytest tests/test_paper_runtime_regression.py tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py -q`: 8 passed.

One broad combined pytest command hit Docker `Cannot allocate memory` during collection; the same coverage was rerun in smaller shards.

## Remaining Risks

- Security governance remains `YELLOW_ACCEPTED_BY_OPERATOR`.
- Existing older closes that predate capital-managed locking are not treated as capital release blockers unless they have capital lock lineage.
- ChatGPT/operator review is still required before rerunning 10m controlled PAPER validation.

## Phase Status

GREEN pending ChatGPT review.

Can rerun 10m controlled PAPER validation: YES, after ChatGPT/operator acceptance.
