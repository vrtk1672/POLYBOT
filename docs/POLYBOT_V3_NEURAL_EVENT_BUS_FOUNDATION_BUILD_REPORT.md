# POLYBOT V3 Neural Event Bus Foundation Build Report

## Current Reality Found

POLYBOT already had a V2 event ledger in `app/events` backed by `event_log`, `event_consumers`, delivery attempts, DLQ, and replay jobs. It was useful, but it did not satisfy the V3 nervous-system contract because it lacked the required neural fields, source-component semantics, dashboard truth shape, and source-backed dialogue wording.

Current information producers include `MarketService.refresh()`, `DataFoundationService`, `RuntimeIntelligenceService`, Brain Mesh Activation, Evidence Refresh, Deterministic Side Evidence, Trusted Orderbook, Neuron Intelligence Pack 1, Risk Core, Exit Foundation, Eligibility, Paper Intent, Paper Execution, Paper Exit/PnL, Capital Ledger, and Brain Dialogue materializers.

Current information consumers include Risk Core, Exit Foundation, Eligibility, Paper Intent, Paper Execution, dashboard query services, Brain Dialogue, and source/status/lineage panels.

Existing event-like structures include `event_log`, `event_consumers`, `event_delivery_attempts`, `event_replay_jobs`, `brain_dialogue_events`, `neuron_signals`, `neuron_signal_bindings`, `runtime_cycles_v2`, table-level paper/risk/exit/eligibility ledgers, and service health rows.

Potential duplication risk was handled by keeping V2 `event_log` intact and adding V3 `neural_events` as the nervous-system transport surface with source-table/source-record references. Truth remains in source tables.

## Files Created

- `app/db/migrations/0101_v3_neural_event_bus_foundation.sql`
- `app/neural_bus/__init__.py`
- `app/neural_bus/contracts.py`
- `app/neural_bus/errors.py`
- `app/neural_bus/repository.py`
- `app/neural_bus/service.py`
- `app/neural_bus/types.py`
- `tests/test_v3_neural_event_bus.py`
- `tests/test_dashboard_neural_bus_api.py`
- `docs/POLYBOT_V3_NEURAL_EVENT_BUS_FOUNDATION.md`
- `docs/POLYBOT_V3_NEURAL_EVENT_BUS_FOUNDATION_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Migration `0101_v3_neural_event_bus_foundation.sql` adds:

- `neural_events`
- `neural_event_consumers`
- `neural_event_delivery`
- `neural_event_replay`

## Event Model

Events are append-only rows in `neural_events`. `consumed_count` remains part of the event contract, while dashboard computes actual delivery count from `neural_event_delivery` so event rows do not need mutation to represent delivery.

## Publisher

Implemented `NeuralEventBusService.publish_event()` and source-backed runtime harvesting through `publish_source_backed_events()`.

SYSTEM OFF raises `NeuralPublishBlocked`.

## Consumer Registry

Implemented `register_consumer()` with event-type interest and optional source-component filtering.

## Replay

Implemented `replay_events()` with filters for event type, event id, id range, market id, and correlation id. Replay records `neural_event_replay` and `REPLAYED` delivery rows.

## Dashboard

Added:

- `GET /dashboard/api/v2/neural-bus`

Dashboard returns `mock_data=false`, event counts, event type counts, active consumers, lag, failed deliveries, latest events, and registry metadata.

## Dialogue

`BrainDialogueService` now materializes `neural_events` into source-backed dialogue. Runtime smoke sample:

- `Orderbook: Published ORDERBOOK_REFRESHED for market=smoke-market`

## Tests Added

- event creation and persistence
- consumer registration
- delivery tracking
- replay by event type, market, and correlation
- SYSTEM OFF publish block
- SYSTEM OFF delivery block
- SYSTEM ON publish allowed
- dashboard truth
- no live/paper impact
- dialogue visibility

## Tests Run

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v3_neural_event_bus.py tests/test_dashboard_neural_bus_api.py -q"
8 passed, 1 warning
```

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_v2_1_event_store.py tests/test_v2_1_event_bus.py tests/test_v2_1_event_replay.py tests/test_brain_dialogue_service.py tests/test_dashboard_brain_dialogue_api.py tests/test_neuron_intelligence_runtime_order.py tests/test_neuron_intelligence_pack1_service.py -q"
34 passed, 1 warning
```

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_paper_execution_safety.py tests/test_paper_no_live_safety.py tests/test_paper_execution_service.py tests/test_paper_position_ledger.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_post_side_risk_exit_readiness_service.py tests/test_candidate_eligibility_recovery_service.py tests/test_dashboard_paper_execution_truth.py tests/test_dashboard_paper_capital_truth.py -q"
43 passed, 1 warning
```

Local host commands that failed before Docker fallback:

- `python -m pytest ...`: failed because local Python had no `pytest`.
- `python -m uv run pytest ...`: failed because local Python had no `uv`.

## Runtime Smoke

Deployment:

- `docker compose build api migrate`: passed.
- `docker compose run --rm migrate`: applied `0101_v3_neural_event_bus_foundation.sql`.
- `docker compose up -d api`: passed.
- `GET /healthz`: `200`, ready.

OFF smoke:

- SYSTEM OFF set with correlation `v3-neural-smoke-off`.
- `publish_event()` blocked with `NeuralPublishBlocked`.
- `deliver_pending()` blocked with `NeuralDeliveryBlocked`.
- `neural_events` remained `0`.
- Trading counts unchanged.

ON smoke:

- SYSTEM ON set with correlation `v3-neural-smoke-on`.
- Registered consumer `smoke-risk-organ`.
- Published one `ORDERBOOK_REFRESHED` event.
- Delivery recorded one `DELIVERED` row.
- Brain Dialogue materialized source-backed neural event dialogue.
- Dashboard returned `mock_data=false`, `events_last_day=1`, `active_consumers=1`, `failed_deliveries=0`.
- SYSTEM returned to OFF with correlation `v3-neural-smoke-complete`.

## Event Counts

Runtime smoke deltas:

- `neural_events`: `0 -> 1`
- `neural_event_delivery`: `0 -> 1`
- `brain_dialogue_events`: `55172 -> 55262`
- `live_orders`: `0 -> 0`
- `paper_orders`: `9 -> 9`
- `paper_fills`: `6 -> 6`
- `paper_positions`: `9 -> 9`
- `orders_v2`: `1 -> 1`
- `fills_v2`: `1 -> 1`
- canonical `positions`: `0 -> 0`

## Safety Checklist

- SYSTEM OFF blocks publish: YES
- SYSTEM OFF blocks delivery: YES
- SYSTEM ON allows publish: YES
- SYSTEM ON allows delivery tracking: YES
- Dashboard read-only while OFF: YES
- No live orders: YES
- No real orders: YES
- No new paper orders: YES
- No new paper fills: YES
- No new paper positions: YES
- No canonical positions: YES
- No risk, exit, eligibility, paper, execution, or capital safety checks loosened: YES

## Remaining Risks

- V3 consumers currently record delivery interest only; no organ-specific business handlers are attached in this phase by design.
- Source-backed runtime harvesting is intentionally broad but conservative. If a future source table uses a nonstandard timestamp or no numeric `id`, its mapping should be adjusted before relying on that source.
- The old V2 `event_log` still exists and will coexist with V3 until a later architectural decision. This is deliberate compatibility, not a replacement.

## Phase Status

GREEN.

Can move to Mesh Sessions Foundation: YES, after ChatGPT review.
