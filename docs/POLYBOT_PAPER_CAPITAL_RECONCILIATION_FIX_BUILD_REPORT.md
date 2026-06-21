# POLYBOT Paper Capital Reconciliation Fix Build Report

## Dispatch

- Executor: Codex
- Task mode: `CONTROLLED_RUNTIME_FIX + PAPER_CAPITAL_ACCOUNTING + RECONCILIATION_HARDENING`
- Risk: VERY HIGH
- ChatGPT review: REQUIRED
- Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Summary

Fixed the Paper capital accounting path that allowed an open Paper position to exist without active locked capital. Added source-derived reconciliation diagnostics, per-position release accounting, audited backfill support for real fills, dashboard/forensics visibility, tests, and bounded production smoke.

## Root Cause

Root cause category: `MISSING_LOCK_ON_FILL`.

Execution inserted paper artifacts before the final lock. The final lock reran max-open/exposure guards after the new position already existed and could self-block. The execution loop caught the error inside the transaction scope, allowing already-inserted paper artifacts to commit without the lock.

## Files Created

- `app/db/migrations/0117_paper_capital_reconciliation_backfill_event.sql`
- `docs/POLYBOT_PAPER_CAPITAL_RECONCILIATION_FIX.md`
- `docs/POLYBOT_PAPER_CAPITAL_RECONCILIATION_FIX_BUILD_REPORT.md`

## Files Changed

- `app/services/paper_capital.py`
- `app/services/paper_execution.py`
- `app/services/paper_dashboard_truth.py`
- `app/services/paper_trade_forensics.py`
- `scripts/run_active_30m_observation.py`
- `tests/test_paper_capital_account.py`
- `tests/test_paper_execution_capital_guards.py`
- `tests/test_paper_exit_capital_release.py`
- `tests/test_dashboard_paper_capital_truth.py`
- `tests/test_paper_trade_forensics.py`

## DB Migration

Applied:

- `0117_paper_capital_reconciliation_backfill_event.sql`

Migration changes:

- Adds `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL` to `paper_capital_ledger.event_type` check constraint.
- Adds unique index `uq_paper_capital_backfill_lock_fill`.

## Tests Run

- `python -m py_compile app/services/paper_capital.py app/services/paper_execution.py app/services/paper_trade_forensics.py app/services/paper_dashboard_truth.py scripts/run_active_30m_observation.py`: passed.
- `docker compose --profile test build test`: passed.
- `docker compose --profile test run --rm -e PYTHONPATH=/app test python -m pytest tests/test_paper_capital_account.py -q`: 6 passed.
- `docker compose --profile test run --rm -e PYTHONPATH=/app test python -m pytest tests/test_paper_execution_capital_guards.py -q`: 6 passed.
- `docker compose --profile test run --rm -e PYTHONPATH=/app test python -m pytest tests/test_paper_exit_capital_release.py -q`: 3 passed.
- `docker compose --profile test run --rm -e PYTHONPATH=/app test python -m pytest tests/test_dashboard_paper_capital_truth.py -q`: 2 passed, 1 warning.
- `docker compose --profile test run --rm -e PYTHONPATH=/app test python -m pytest tests/test_paper_trade_forensics.py -q`: 6 passed, 1 warning.
- `docker compose --profile test run --rm -e PYTHONPATH=/app test python -m pytest tests/test_paper_execution_service.py tests/test_paper_execution_safety.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_paper_pnl_reconciliation.py tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py tests/test_paper_no_live_safety.py tests/test_paper_exit_safety.py tests/test_active_30m_observation_runner.py tests/test_overnight_observation_runner.py -q`: 46 passed, 1 warning.

An initial combined test command timed out before returning results; the same coverage was rerun in split commands.

## Runtime Smoke

Sequence:

1. Confirmed SYSTEM OFF.
2. Captured account/reconciliation/safety baseline.
3. Applied migration `0117`.
4. Ran audited repair only for real open positions with real fills.
5. Rebuilt/restarted API.
6. Verified `/healthz`, `/system/power`, `/dashboard/api/v2/paper/capital`, `/dashboard/api/v2/paper`, and open-position forensics.

## Before / After

Before repair:

- current_balance: `996.84932200`
- available_balance: `996.84932200`
- locked_balance: `0`
- open_exposure: `0`
- realized_pnl: `-3.15067800`
- unrealized_pnl: `0`
- expected_locked_balance: `0`
- expected_open_exposure: `0.16`
- open_positions: `1`
- open_positions_without_lock: `1`
- locks_without_open_position: `0`
- duplicate_releases: `0`
- paper_capital_ledger rows: `35`

After repair:

- current_balance: `996.84932200`
- available_balance: `996.68932200`
- locked_balance: `0.16000000`
- open_exposure: `0.16000000`
- realized_pnl: `-3.15067800`
- unrealized_pnl: `-0.04000000`
- expected_locked_balance: `0.16`
- expected_open_exposure: `0.16`
- open_positions: `1`
- open_positions_without_lock: `0`
- locks_without_open_position: `0`
- duplicate_releases: `0`
- paper_capital_ledger rows: `36`

Unchanged safety counts:

- paper_intents: `20`
- paper_orders: `12`
- paper_fills: `9`
- paper_positions: `12`
- paper_position_closes: `8`
- paper_trade_ledger: `17`
- live_orders: `0`
- orders_v2: `1`
- fills_v2: `1`
- canonical positions: `0`

## Sample Open Lock Trace

- position: `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- market: `598936`
- side: `YES`
- entry: `0.016`
- quantity: `10`
- notional: `0.16`
- fill: `paper_fill_6c333992b94257cf9ca77b6d4a7d72f9`
- order: `b12cfb10-8c08-51a4-a42b-d33d3fb50ccf`
- token id: `13894524895366006997415301184483786855853683638290113202814526270024185311964`
- capital ledger: `paper_capital_backfill_lock_7668d890-0fe3-5aa3-bc32-996a2f121da2`
- event: `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL`

## Sample Closed Release Trace

- `691547 YES`: released `4.99998900`, STOP_LOSS, realized PnL `-3.01369200`, release count `1`, realized application count `1`.
- `691547 NO`: released `4.99998900`, TAKE_PROFIT, realized PnL `-0.13698600`, release count `1`, realized application count `1`.

## Safety Checklist

- SYSTEM remained OFF after smoke.
- Live not enabled.
- Shadow not enabled.
- No real/live orders created.
- No paper intents/orders/fills/positions/closes created by repair.
- No fake ledger row: repair linked to real fill/order/position.
- No fake PnL.
- No closed position reopened.
- Dashboard and forensics now show expected vs actual capital truth.

## Remaining Risks

- Security governance remains `YELLOW_ACCEPTED_BY_OPERATOR`.
- API readiness is GREEN for paper capital, but operator review is still required before the next 30m dress rehearsal.
- Existing quarantined legacy paper positions remain excluded from active truth.

## Phase Status

GREEN pending ChatGPT review.

Can run 30m dress rehearsal again: YES, after ChatGPT/operator acceptance.
