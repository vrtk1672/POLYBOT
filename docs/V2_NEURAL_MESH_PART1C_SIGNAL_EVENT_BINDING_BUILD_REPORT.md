# POLYBOT V2 Neural Mesh Part 1C Signal Event Binding Build Report

## 1. Purpose

Implement V2 Neural Mesh Activation Part 1C: Signal Store Event Binding and Producer Registry Binding.

## 2. Current Reality Found

- `event_log` exists with `id`, `event_id`, `event_type`, `source_service`, non-null `correlation_id`, `payload_json`, and `metadata_json`.
- `source_status` exists with numeric `id`, `source_name`, source type/status fields, read-only safety checks, details JSON, and timestamps.
- `neuron_signals` already had `correlation_id` and `raw_payload_ref` but no explicit producer/source/event binding table.
- `neuron_registry` and `neuron_health` exist from Part 1B.
- Existing source/rules adapters created neutral Signals but did not attach explicit binding rows.
- Existing correlation helper in `app.events.correlation` provides `new_correlation_id`.
- Raw payload patterns already favor JSON payload columns or references; Part 1C uses references only.
- Rules/resolution dashboard rows have `market_id` and `rules_analysis_id` but not an event-log ID.
- Existing dashboard Signals endpoint did not expose enough producer/source binding health.

## 3. Files Created

- `app/db/migrations/0061_v2_neural_mesh_signal_event_binding.sql`
- `app/neural_mesh/lineage.py`
- `app/repositories/signal_lineage_repository.py`
- `app/services/signal_lineage.py`
- `tests/test_v2_signal_event_binding_contract.py`
- `tests/test_v2_signal_event_binding_repository.py`
- `tests/test_v2_signal_event_binding_api.py`
- `tests/test_v2_dashboard_signal_lineage.py`
- `docs/V2_NEURAL_MESH_PART1C_SIGNAL_EVENT_BINDING.md`
- `docs/V2_NEURAL_MESH_PART1C_SIGNAL_EVENT_BINDING_BUILD_REPORT.md`

## 4. Files Changed

- `app/services/neuron_signals.py`
- `app/api/signal_routes.py`
- `app/api/routes.py`
- `app/services/query/dashboard_v2_query_service.py`

## 5. DB Migration

Migration applied:

- `0061_v2_neural_mesh_signal_event_binding.sql`

Tables:

- `neuron_producers`
- `neuron_signal_bindings`

Default producers:

- `source_status_adapter`
- `clob_source_status_adapter`
- `rules_resolution_adapter`
- `future_news_adapter`
- `future_social_adapter`
- `future_whale_adapter`

## 6. API Routes

Added:

- `GET /signals/{signal_id}/lineage`
- `GET /signals/correlation/{correlation_id}`
- `GET /signals/source/{source_name}`
- `GET /signals/producer/{producer_name}`
- `GET /dashboard/api/v2/signal-lineage`

## 7. Dashboard Changes

- Added Signal Lineage dashboard endpoint.
- Added Signal Lineage dashboard page navigation.
- Added lineage summary to Dashboard V2 `signals` page.
- Added compact lineage fields to Dashboard V2 overview:
  - `signal_lineage_bound_pct_24h`
  - `unbound_signals_24h`

## 8. Tests Added

- Contract tests for lineage model and adapter correlation/raw reference behavior.
- Repository tests for create-with-lineage, missing event-log ID, correlation/source/producer queries, unbound listing, summary counts, adapter lineage, and order non-mutation.
- API tests for lineage by signal ID and query endpoints.
- Dashboard tests for `/dashboard/api/v2/signal-lineage` and Signal page lineage inclusion.

## 9. Tests Run With Exact Results

- `docker compose config` -> passed; compose rendered successfully.
- `docker compose --profile test config` -> passed; test profile rendered successfully.
- `docker compose ps` -> passed; API, Postgres, Redis, and test Postgres healthy.
- `docker compose --profile test build api migrate test test_migrate` -> passed.
- `docker compose run --rm migrate` -> applied `0061_v2_neural_mesh_signal_event_binding.sql`.
- `docker compose --profile test run --rm test_migrate` -> applied `0061_v2_neural_mesh_signal_event_binding.sql`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_signal_event_binding_contract.py -q` -> `4 passed in 0.93s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_signal_event_binding_repository.py -q` -> `7 passed in 2.87s`.
- Initial parallel `tests/test_v2_signal_event_binding_api.py` run -> `1 failed, 1 passed`; rerun showed the storage/route path was correct.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_signal_event_binding_api.py -q` -> `2 passed in 1.43s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_signal_lineage.py -q` -> `2 passed in 5.37s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_contract.py -q` -> `8 passed in 0.85s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_repository.py -q` -> `3 passed in 1.75s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_api.py -q` -> `2 passed in 2.56s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_signals.py -q` -> `3 passed in 5.25s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_contract.py -q` -> `4 passed in 0.96s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_repository.py -q` -> `6 passed in 3.02s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_api.py -q` -> `3 passed in 3.39s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_neurons.py -q` -> `3 passed in 6.15s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_21_source_status.py -q` -> `6 passed in 3.46s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_22_rules_resolution_truth.py -q` -> `9 passed in 29.70s`.

## 10. Runtime Verification

Runtime verification is performed after API restart onto the rebuilt image.

Required checks:

- `/healthz`
- `/runtime/health`
- `/dashboard/api/v2/overview`
- `/dashboard/api/v2/source-status`
- `/dashboard/api/v2/rules`
- `/signals/recent`
- `/dashboard/api/v2/signals`
- `/neurons`
- `/dashboard/api/v2/neurons`
- `/dashboard/api/v2/signal-lineage`
- one `/signals/{signal_id}/lineage` check

## 11. Safety Verification

- Lineage is observational only.
- No Brain Coordinator was implemented.
- No trading logic was modified.
- No private keys were used.
- No order/cancel/sign/live mutation path was touched.
- Tests verify lineage summary does not mutate `paper_orders`, `shadow_orders`, or `live_orders`.
- Dashboard lineage uses DB truth with `mock_data=false`.
- Runtime kill state was not changed.

## 12. What Is Complete

- Producer registry table and seed rows.
- Signal binding table.
- Create Signal with lineage in one transaction.
- Source/rules adapters attach lineage metadata.
- Lineage APIs.
- Dashboard lineage summary.
- Bound/unbound summary.
- Tests and regressions.
- Documentation.

## 13. What Is Partial

- Existing pre-Part-1C Signals remain unbound unless explicitly backfilled later.
- Event-log binding is supported but not populated unless an event ID is available.
- Correlation IDs are generated for source/rules adapters when absent.

## 14. Remaining Risks

- Runtime env kill switch and persisted runtime kill state still disagree.
- Existing legacy unbound Signals reduce lineage binding percentage until they age out of the 24h window or are backfilled by an explicit audit task.
- Event-log binding coverage is limited by current producers not passing event IDs.

## 15. Recommended Next Phase

V2 Neural Mesh Activation Part 1D: event-to-signal replay/read model or producer coverage hardening.

Do not implement Brain Coordinator yet.

## 16. Final Status

GREEN, pending final live endpoint verification after API restart.
