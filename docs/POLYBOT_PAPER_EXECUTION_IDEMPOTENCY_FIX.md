# POLYBOT Paper Execution Idempotency Fix

## Status

YELLOW.

The root cause of the 4h Technical Paper Soak anomaly was found and the runtime writer path was hardened. Existing inconsistent rows remain in the database as evidence and are now reported as RED lineage truth.

## Root Cause

`MarketService.refresh()` was running two paper write paths in PAPER mode:

- legacy `RuntimePaperTradingService`, through `ExecutionAwarePaperService`
- canonical safe `PaperIntentGateService` -> `PaperExecutionService` -> `PaperExitLoopService`

The legacy path created `paper_orders` and `paper_positions` directly from ranked runtime signals. It does not write `paper_fills`, does not link positions to `paper_fill_id`, and does not write `paper_trade_ledger` OPEN rows. During the soak it created three new orders and three new open positions while `paper_intents` and `paper_fills` stayed unchanged.

## Runtime Fix

`MarketService.refresh()` no longer invokes `RuntimePaperTradingService.process_cycle()` in the runtime paper stage. The legacy service remains present for historical direct tests, but runtime paper artifact creation now flows only through safe paper execution from valid paper intents.

## Idempotency Fix

`PaperExecutionService` now:

- marks an intent `POSITION_OPENED` after a valid order/fill/position is created
- records `executed_at` and `consumed_at`
- excludes consumed intents from executable dashboard counts
- refuses to re-open a closed or already consumed intent
- checks order/fill/position lineage before creating artifacts

`PaperExitLoopService` now marks linked paper intents `CLOSED` when a safe paper position is closed.

## Dashboard Consistency Truth

The unified paper dashboard now reports lineage consistency fields:

- `duplicate_intent_orders_count`
- `duplicate_order_fills_count`
- `duplicate_fill_positions_count`
- `positions_without_fills_count`
- `fills_without_orders_count`
- `positions_without_open_ledger_count`
- `closed_positions_without_close_count`
- `closed_positions_without_close_ledger_count`
- `executed_intents_reexecuted_count`
- `paper_lineage_consistency_status`

Existing runtime DB truth after the interrupted soak:

- `paper_intents=3`
- `paper_orders=6`
- `paper_fills=3`
- `paper_positions=6`
- `open_paper_positions=3`
- `closed_paper_positions=3`
- `paper_position_closes=3`
- `paper_trade_ledger=6`
- `positions_without_fills_count=3`
- `positions_without_open_ledger_count=3`
- `paper_lineage_consistency_status=RED`

## Soak Guard Hardening

The 4h soak runner now stops and posts SYSTEM OFF when:

- paper positions increase without paper fills
- paper orders increase without new intents
- paper positions increase without ledger growth
- lineage consistency status is not OK
- fill-less positions exist
- open-ledger-less positions exist
- duplicate lineage is detected
- executed intents are re-executed

## Repair Policy

No inconsistent production rows were deleted or modified to hide the issue. They should be handled by a separate reviewed repair phase, preferably by marking legacy fill-less positions invalidated/superseded if a schema-supported audit trail is added.

## Restart Policy

Do not restart the 4h soak until:

- ChatGPT review accepts this fix
- existing inconsistent rows are either repaired with audit trail or explicitly accepted as quarantined legacy rows
- `/dashboard/api/v2/paper/soak-readiness` returns GREEN
