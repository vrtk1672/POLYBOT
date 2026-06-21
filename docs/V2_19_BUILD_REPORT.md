# V2.19 Build Report - Feedback / Learning Loop

## Summary

V2.19 is implemented as an evidence-backed learning layer. It creates internal review and learning records, emits typed learning events, exposes `/learning/*` APIs, and adds Dashboard V2 learning truth.

No trading, order intent, live exit, external send, balance mutation, or automatic model-change path was added.

## Files Created

- `app/db/migrations/0056_v2_19_feedback_learning_loop.sql`
- `app/learning/*`
- `app/api/learning_routes.py`
- `app/repositories/*learning*_repository.py`
- `app/repositories/trade_review_repository.py`
- `app/repositories/signal_performance_repository.py`
- `app/repositories/model_adjustment_repository.py`
- `tests/test_v2_19_*.py`
- `docs/V2_19_FEEDBACK_LEARNING_LOOP.md`
- `docs/V2_19_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `app/services/query/dashboard_v2_query_service.py`
- `tests/test_v2_18_dashboard_v2_api.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

Applied successfully:

- `0056_v2_19_feedback_learning_loop.sql`

Tables:

- `trade_reviews`
- `signal_performance`
- `engine_learning`
- `source_learning`
- `whale_learning`
- `ai_learning`
- `no_trade_learning`
- `model_adjustments`

## API Routes

- `GET /learning/health`
- `GET /learning/trade-reviews/recent`
- `GET /learning/signals`
- `GET /learning/engines`
- `GET /learning/sources`
- `GET /learning/whales`
- `GET /learning/ai`
- `GET /learning/no-trade`
- `GET /learning/model-adjustments`
- `GET /learning/snapshot`
- `POST /learning/review/trade`
- `POST /learning/review/no-trade`
- `POST /learning/rebuild`
- `GET /dashboard/api/v2/learning`

## Dashboard Changes

Dashboard V2 now includes a learning page and overview/memory learning indicators. Operator dashboard truth includes learning summaries, pending reviews, model adjustment counts, insufficient data counts, latest review, and recent learning events.

## Events Published

- `learning.trade_review.created`
- `learning.signal_performance.updated`
- `learning.engine.updated`
- `learning.source.updated`
- `learning.whale.updated`
- `learning.ai.updated`
- `learning.no_trade.updated`
- `learning.model_adjustment.recommended`
- `learning.memory_update.applied`
- `learning.insufficient_data`

## Tests Added

- Trade reviewer tests
- Signal performance tests
- Engine/source/whale/AI/no-trade learning tests
- Model adjustment recommendation tests
- Memory update coordinator tests
- Learning service persistence and dedupe tests
- Learning API tests
- Learning safety guard tests

## Tests Run

- Targeted V2.19 after final health-query cleanup: `21 passed, 8 skipped in 39.96s`
- V2.18 regression: `5 passed, 3 skipped in 13.00s`
- V2.17 regression: `20 passed in 29.03s`
- V2.16 regression: `23 passed, 1 skipped in 33.58s`
- V2.15 regression: `19 passed, 1 skipped in 65.14s`
- V2.14 regression: `17 passed, 4 skipped in 21.66s`
- Runtime regression: `8 passed, 19 skipped in 34.91s`
- Full suite after final fix: `383 passed, 406 skipped in 104.23s`

## Runtime Verification

Migration command:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- Result: applied `0056_v2_19_feedback_learning_loop.sql`

Canonical runtime start:

- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`
- Result: command timed out while server stayed attached.

Fallback startup:

- Direct Python startup with `from app.main import run; run()`
- Result: runtime started on `127.0.0.1:8000`

Endpoint verification:

- `/healthz`: 200
- `/runtime/state`: 200, current mode `DATA_ONLY`, live/order permissions false
- `/runtime/health`: 200
- `/events/lag`: 200
- `/data/coverage`: 200
- `/dashboard/api/v2/overview`: 200
- `/learning/health`: 200
- `/learning/trade-reviews/recent`: 200
- `/learning/signals`: 200
- `/learning/engines`: 200
- `/learning/sources`: 200
- `/learning/whales`: 200
- `/learning/ai`: 200
- `/learning/no-trade`: 200
- `/learning/model-adjustments`: 200
- `/learning/snapshot`: 200
- `/dashboard/api/v2/learning`: 200

## Manual Smoke

Manual smoke used market `2169995` with explicit completed trade, incomplete trade, no-trade, and regret payloads.

Confirmed:

- `POST /learning/review/trade dry_run=true`: wrote no rows.
- `POST /learning/review/trade dry_run=false`: created trade review and learning records.
- Incomplete trade payload produced `PENDING`.
- `POST /learning/review/no-trade`: created no-trade learning from V2.17 regret evidence.
- `POST /learning/rebuild dry_run=true`: wrote no rows.
- `POST /learning/rebuild dry_run=false`: deduped no-trade learning backfill.
- Model adjustments were recommendation-only.

## DB Row Verification

After manual smoke:

- `trade_reviews`: 2
- `signal_performance`: 2
- `engine_learning`: 2
- `source_learning`: 2
- `whale_learning`: 2
- `ai_learning`: 2
- `no_trade_learning`: 4
- `model_adjustments`: 5
- learning events in `event_log`: 21

Safety counts unchanged during smoke:

- `paper_orders`: 3 before / 3 after
- `live_orders`: 3 before / 3 after
- `orders_v2`: 5 before / 5 after
- `exit_intents`: 7 before / 7 after

## Safety Checklist

- Learning cannot create orders: YES
- Learning cannot create order intents: YES
- Learning cannot create live exits: YES
- Learning cannot mutate external balances: YES
- Model adjustments recommendation-only: YES
- No fake learning from missing outcomes: YES
- Closed trade review requires completed outcome: YES
- No-trade review requires evidence: YES
- Memory updates require confidence: YES
- Dry-run writes nothing: YES
- Bad engine penalized: YES
- Good source rewarded: YES
- AI bad call penalized: YES
- No-trade regret stored: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

Completed paper/shadow trade history is still sparse outside manual smoke. The learning layer handles this honestly through `PENDING`, `NO_DATA`, and `INSUFFICIENT_DATA`.

## Phase Status

GREEN.

## Next Phase

Can move to V2.20 Paper Full System Run: YES.
