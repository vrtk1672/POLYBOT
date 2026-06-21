# V2.1 Build Report

## Summary

V2.1 adds a Postgres-backed Event Bus / Neural Mesh foundation with typed events, durable event store, in-process dispatch, consumer registry, delivery attempts, retry policy, DLQ, replay jobs, API routes, dashboard truth, and minimal runtime publishing.

## Files Created

- `app/events/__init__.py`
- `app/events/types.py`
- `app/events/envelope.py`
- `app/events/event_bus.py`
- `app/events/event_store.py`
- `app/events/consumer_registry.py`
- `app/events/retry_policy.py`
- `app/events/dlq.py`
- `app/events/replay.py`
- `app/events/correlation.py`
- `app/events/event_errors.py`
- `app/repositories/event_store_repository.py`
- `app/repositories/event_consumer_repository.py`
- `app/repositories/event_replay_repository.py`
- `app/api/event_routes.py`
- `app/db/migrations/0039_v2_event_bus_foundation.sql`
- `tests/test_v2_1_event_types.py`
- `tests/test_v2_1_event_store.py`
- `tests/test_v2_1_event_bus.py`
- `tests/test_v2_1_event_consumers.py`
- `tests/test_v2_1_event_retry_dlq.py`
- `tests/test_v2_1_event_replay.py`
- `tests/test_v2_1_event_api.py`
- `tests/test_v2_1_market_service_events.py`
- `docs/V2_1_EVENT_BUS_NEURAL_MESH_FOUNDATION.md`
- `docs/V2_1_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/scheduler.py`
- `app/ingestion/market_service.py`
- `app/runtime/service_registry.py`
- `app/api/runtime_routes.py`
- `app/api/routes.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration Added

- `app/db/migrations/0039_v2_event_bus_foundation.sql`

## API Routes Added

- `GET /events/recent`
- `GET /events/dlq`
- `POST /events/replay`
- `GET /events/lag`

## Tests Added

- `tests/test_v2_1_event_types.py`
- `tests/test_v2_1_event_store.py`
- `tests/test_v2_1_event_bus.py`
- `tests/test_v2_1_event_consumers.py`
- `tests/test_v2_1_event_retry_dlq.py`
- `tests/test_v2_1_event_replay.py`
- `tests/test_v2_1_event_api.py`
- `tests/test_v2_1_market_service_events.py`

## Tests Run

- `python -m uv run pytest tests/test_v2_1_event_types.py -q`: 5 passed.
- `python -m uv run pytest tests/test_v2_1_event_store.py -q`: 4 skipped without DB env.
- `python -m uv run pytest tests/test_v2_1_event_bus.py -q`: 5 skipped without DB env.
- `python -m uv run pytest tests/test_v2_1_event_consumers.py -q`: 4 skipped without DB env.
- `python -m uv run pytest tests/test_v2_1_event_retry_dlq.py -q`: 3 skipped without DB env.
- `python -m uv run pytest tests/test_v2_1_event_replay.py -q`: 6 skipped without DB env.
- `python -m uv run pytest tests/test_v2_1_event_api.py -q`: 6 skipped without DB env.
- `python -m uv run pytest tests/test_v2_1_market_service_events.py -q`: 3 skipped without DB env.
- With `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`:
  - `tests/test_v2_1_event_store.py`: 4 passed.
  - `tests/test_v2_1_event_bus.py`: 5 passed.
  - `tests/test_v2_1_event_consumers.py`: 4 passed.
  - `tests/test_v2_1_event_retry_dlq.py`: 3 passed.
  - `tests/test_v2_1_event_replay.py`: 6 passed.
  - `tests/test_v2_1_event_api.py`: 6 passed.
  - `tests/test_v2_1_market_service_events.py`: 3 passed.
  - `tests/test_state_governor.py`: 7 passed.
  - `tests/test_runtime_api.py`: 6 passed.
- `python -m uv run pytest tests/test_runtime_modes.py -q`: 8 passed.
- `python -m uv run pytest tests/test_mode_manager.py -q`: 10 passed.
- `python -m uv run pytest tests/test_state_governor.py -q`: 7 skipped without DB env.
- `python -m uv run pytest tests/test_runtime_cycle_orchestrator.py -q`: 5 skipped without DB env.
- `python -m uv run pytest tests/test_runtime_api.py -q`: 6 skipped without DB env.
- `python -m uv run pytest tests/test_runtime_integration_guards.py -q`: 4 skipped without DB env.
- `python -m uv run pytest tests/test_stage4.py -q`: 30 passed, 1 skipped.
- `python -m uv run pytest tests/test_stage4_env_isolation.py -q`: 10 passed.
- `python -m uv run pytest tests/test_env_runtime.py -q`: 1 passed.
- `python -m uv run pytest tests/test_phase2_execution_aware_paper.py -q`: 13 skipped without DB env.
- `python -m uv run pytest tests/test_phase9_dashboard_telegram.py -q`: 10 skipped without DB env.
- `python -m uv run pytest`: 94 passed, 298 skipped.

## Runtime Verification Results

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: applied `0039_v2_event_bus_foundation.sql`.
- Runtime started through `scripts/start_runtime.ps1`.
- `GET /runtime/state`: `DATA_ONLY`, kill false, live permission false.
- `GET /runtime/health`: `HEALTHY`.
- `GET /runtime/mode`: `DATA_ONLY`.
- `GET /events/recent`: list response with 8 events.
- `GET /events/dlq`: list response with 0 open items.
- `GET /events/lag`: metrics response, failed events 0.
- `POST /events/replay` with a harmless `runtime.cycle.started` event: replayed 1, failed 0.

## Fully Implemented

- Stable event type contract.
- Event envelope with correlation and redaction.
- Postgres event store.
- In-process event bus.
- Consumer registration, pause/resume, and status persistence.
- Delivery attempts.
- Retry policy and DLQ.
- Replay jobs and safe redispatch.
- Event API routes.
- Dashboard event bus truth fields.
- Minimal scheduler, MarketService, and runtime mode-change publishing.

## Partial

- Retry scheduling records `next_retry_at`, but no retry worker runs those retries yet.
- MarketService publishes foundational runtime/snapshot events only.
- No Redis or distributed worker support in this phase.

## Safety Checklist

- KILL blocks trading: preserved by V2.0 governor.
- DATA_ONLY blocks orders: preserved by V2.0 governor.
- PAPER blocks live: preserved by V2.0 governor.
- SHADOW_LIVE blocks live: preserved by V2.0 governor.
- Live disabled by default: preserved by V2.0.1.
- Event Bus sends no orders.
- Replay blocks order side-effect event types.
- Payloads are redacted in API/DLQ views.
- Dashboard uses real DB-backed data only.

## Remaining Risks

- Event retry execution worker is future work.
- Event consumers are in-process, so multi-process distributed delivery is future work.
- Event schema versioning policy is foundational only.
- DB-backed tests are slow because each test schema replays the full migration chain.

## Recommendation

Can move to V2.2 Data Foundation Complete: YES.
