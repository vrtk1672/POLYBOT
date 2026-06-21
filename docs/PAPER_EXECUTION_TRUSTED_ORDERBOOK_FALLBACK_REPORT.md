# PAPER Execution Trusted Orderbook / Learning Price Fallback Repair

## Purpose

Fix the PAPER execution bottleneck where Defense 20 created Paper intents but none became Paper orders/fills/positions because execution reported `MISSING_TRUSTED_ORDERBOOK`.

## Stage A Audit

`MISSING_TRUSTED_ORDERBOOK` was produced in `app/services/paper_execution.py`, inside `PaperExecutionService._validate_intents()`, when `_orderbook_for_intent()` returned `None`.

The old execution lookup only accepted the exact `paper_intents.orderbook_snapshot_id` if that snapshot was still fresh under the 180 second TTL. It did not call the last-mile orderbook refresh service, did not look up a newer matching market/token/side snapshot, and did not have a labeled PAPER learning fallback path.

Runtime audit of session `paper_session_20260620T133422Z_63eb14ef` showed execution runs with 53 checked intents, 53 blocked intents, 0 executable intents, and only `MISSING_TRUSTED_ORDERBOOK` in block reasons.

Sample intents had valid `market_id`, `side`, `intended_price`, `orderbook_snapshot_id`, quantity in evidence, and runtime decision lineage. Their referenced snapshots existed and had bid/ask/mid/spread data, but those snapshots had become stale before execution.

## Root Cause Classification

- `STALE_ORDERBOOK_NO_REFRESH`
- `EXECUTION_QUERY_TOO_STRICT_FOR_PAPER`
- `NO_PAPER_LEARNING_PRICE_FALLBACK`

## Trusted Orderbook Lookup Findings

Trusted/fresh snapshots existed during runtime decision creation, but execution used only the stored snapshot id. If that exact snapshot aged past TTL, execution treated the intent as not executable.

## Last-Mile Refresh Findings

`LastMileOrderbookRefreshService` already existed and successfully refreshed exact market/token/side snapshots. It was integrated into runtime decision creation, but not into Paper execution.

## Fallback Pricing Design

Execution now resolves price in this order:

1. Fresh stored snapshot: `TRUSTED_ORDERBOOK`.
2. Execution-time last-mile fresh snapshot: `LAST_MILE_TRUSTED_ORDERBOOK`.
3. Defense-aware bounded fresh regular snapshot: `PAPER_LEARNING_PRICE_FALLBACK`.
4. Otherwise no execution with `NO_EXECUTABLE_PAPER_PRICE` or refresh error diagnostics.

Fallback is never labeled trusted. Defense 100 does not use regular fallback. Defense 20 may use bounded fresh regular orderbook fallback for PAPER learning.

## Execution Price Source Fields

Paper order/fill/position metadata now records:

- `execution_price_source`
- `trusted_orderbook_used`
- `orderbook_snapshot_id`
- `fallback_source`
- `fallback_reason`
- `price_confidence`
- `fallback_learning_only`
- `price_age_seconds`
- `spread`
- `slippage_model`
- `orderbook_source`
- `orderbook_refresh_state`
- `orderbook_refresh_error`

## Tests Run

- `tests/test_paper_execution_trusted_orderbook.py tests/test_paper_execution_learning_fallback.py tests/test_missing_trusted_orderbook_diagnostics.py tests/test_paper_execution_price_source_reporting.py`: 6 passed.
- `tests/test_intent_queue_visibility.py tests/test_paper_session_learning_report.py tests/test_opportunity_memory.py`: 4 passed.
- `tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py tests/test_opportunity_mesh_coordinator.py tests/test_paper_execution_adapter_runtime.py tests/test_paper_session_status_report.py tests/test_opportunity_memory.py`: 12 passed.
- `tests/test_paper_session_learning_report.py`: 1 passed after report path persistence fix.
- `python -m compileall app tests`: passed.

## Runtime Verification

After rebuild/restart, a clean Defense 20 session was started:

- Session: `paper_session_20260620T204519Z_8fd1bf45`
- Starting balance: 1000
- Defense level: 20
- Current paper intents/orders/fills/positions after observation: 8/5/5/5
- Open positions: 0
- Realized PnL: -48.4858446
- Trusted executions: 2
- Last-mile trusted executions: 3
- PAPER fallback executions observed naturally: 0
- `MISSING_TRUSTED_ORDERBOOK` after fix: 0 current-session intent diagnostics
- No executable price expirations observed in the final session: 0
- Expired intents: 3, all for risk/capital blockers, not missing orderbook.

## Example Executed Trades

Intent queue showed closed positions with price sources:

- `677404 YES`: `TRUSTED_ORDERBOOK`
- `666655 NO`: `TRUSTED_ORDERBOOK`
- `2365093 NO`: `LAST_MILE_TRUSTED_ORDERBOOK`
- `598936 NO`: `LAST_MILE_TRUSTED_ORDERBOOK`
- `597967 NO`: `LAST_MILE_TRUSTED_ORDERBOOK`

## Example No-Price Expiration

Regression coverage proves an intent with no trusted snapshot, failed refresh, and no bounded fallback becomes `EXPIRED_NO_EXECUTION` with `NO_EXECUTABLE_PAPER_PRICE`.

## Remaining Risks

During observation, direct `/healthz` briefly timed out while the API was busy with runtime work and external CLOB calls, but CLI control endpoints and final health recovered. This is an API responsiveness/load concern, separate from the execution price repair.

The final natural Defense 20 run did not require `PAPER_LEARNING_PRICE_FALLBACK`; tests cover the fallback behavior.

## Status

GREEN for the execution blocker repair.

Safe to continue Defense 20 PAPER runtime: YES.
