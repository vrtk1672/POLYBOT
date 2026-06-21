# POLYBOT V2 Neural Mesh Part 1A Signal Contract Build Report

## 1. Purpose

Implement V2 Neural Mesh Activation Part 1A: Unified Neuron Signal Contract, Signal Store, Basic Signal API, Dashboard Truth, safe initial adapters, tests, and documentation.

## 2. Current Reality Found

- No canonical `neuron_signals` table existed before this phase.
- No `/signals/*` API existed before this phase.
- Signal-like assets existed in legacy/specialized forms, including `paper_signals`, per-neuron tables, event log surfaces, source status, and rules/resolution truth.
- `event_log` is useful audit/event truth but not a replacement for canonical neutral Signal state.
- Existing source status and rules/resolution truth can safely feed initial neutral Signals.
- Runtime compose truth keeps live disabled and kill switch true.
- New migration number selected: `0059_v2_neural_mesh_signal_contract.sql`.

## 3. Files Created

- `app/db/migrations/0059_v2_neural_mesh_signal_contract.sql`
- `app/neural_mesh/__init__.py`
- `app/neural_mesh/contracts.py`
- `app/repositories/neuron_signal_repository.py`
- `app/services/neuron_signals.py`
- `app/api/signal_routes.py`
- `tests/test_v2_neuron_signal_contract.py`
- `tests/test_v2_neuron_signal_repository.py`
- `tests/test_v2_neuron_signal_api.py`
- `tests/test_v2_dashboard_signals.py`
- `docs/V2_NEURAL_MESH_PART1A_SIGNAL_CONTRACT.md`
- `docs/V2_NEURAL_MESH_PART1A_SIGNAL_CONTRACT_BUILD_REPORT.md`

## 4. Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/services/source_status.py`
- `app/services/rules_resolution_truth.py`
- `app/services/query/dashboard_v2_query_service.py`

## 5. DB Migration

Migration applied:

- `0059_v2_neural_mesh_signal_contract.sql`

Tables:

- `neuron_signals`
- `neuron_signal_entities`
- `neuron_signal_evidence`

Indexes:

- Created-at descending
- Neuron
- Market ID
- Status
- Correlation ID
- Processed-by-brain
- Source name
- Child-table signal/entity/evidence lookups

Checks:

- Signal status values are bounded.
- Raw direction values are bounded.
- Strength, confidence, source reliability, and freshness are bounded.
- Forbidden decision/order evidence keys are rejected.

## 6. API Routes

Created:

- `GET /signals/recent`
- `GET /signals/market/{market_id}`
- `GET /signals/neuron/{neuron_name}`
- `GET /dashboard/api/v2/signals`

All return real DB truth with `mock_data=false`.

## 7. Dashboard Changes

- Added dashboard V2 signals page route.
- Added signals page to dashboard navigation.
- Added compact signal summary into dashboard overview:
  - `signals_per_minute`
  - `total_signals_24h`
  - `unprocessed_signals`
- Added full signal dashboard block:
  - `signals_by_neuron`
  - `latest_signals`
  - `stale_signals`
  - `unprocessed_signals`

## 8. Tests Added

- Contract validation tests.
- Repository persistence/query/summary tests.
- API route tests.
- Dashboard signal truth tests.
- Safety-oriented order-count non-mutation test.
- Neutral adapter tests.

## 9. Tests Run With Exact Results

- `docker compose config` -> passed; compose rendered successfully.
- `docker compose --profile test config` -> passed; test profile rendered successfully.
- `docker compose ps` -> passed; Postgres, Redis, API, and test Postgres were healthy.
- `docker compose run --rm migrate` before rebuild -> `No pending migrations.`
- `docker compose --profile test run --rm test_migrate` before rebuild -> `No pending migrations.`
- `docker compose --profile test build api migrate test test_migrate` -> passed.
- `docker compose run --rm migrate` -> applied `0059_v2_neural_mesh_signal_contract.sql`.
- `docker compose --profile test run --rm test_migrate` -> applied `0059_v2_neural_mesh_signal_contract.sql`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_neuron_signal_contract.py -q` -> `8 passed in 0.65s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_repository.py -q` -> `3 passed in 1.13s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_api.py -q` -> `2 passed in 1.37s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_signals.py -q` -> `3 passed in 3.18s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_21_source_status.py -q` -> `6 passed in 3.33s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_22_rules_resolution_truth.py -q` -> `9 passed in 29.75s`.

Note: three initial parallel test invocations hit a Docker compose container-name conflict while `test_migrate` was being recreated. The same tests were rerun sequentially and passed.

## 10. Runtime Verification

Runtime image restart:

- `docker compose up -d api` -> API recreated and started on rebuilt image.
- `docker compose ps` -> API, Postgres, Redis, and test Postgres healthy.

Endpoint checks:

- `Invoke-RestMethod http://127.0.0.1:8000/healthz` -> `status=ok`, `ready=true`.
- `Invoke-RestMethod http://127.0.0.1:8000/runtime/health` -> `overall_status=HEALTHY`, `current_mode=DATA_ONLY`, `live_started=false`, `shadow_started=false`, `paper_started=false` in active cycle.
- `Invoke-RestMethod http://127.0.0.1:8000/runtime/state` -> `current_mode=DATA_ONLY`, `state_status=ACTIVE`, live/paper/shadow permissions false.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview` -> `status=OK`, `mock_data=false`, overview includes signal summary fields.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/source-status` -> `status=OK`, `mock_data=false`; Gamma, CLOB/orderbook/prices/spreads, activity, and Ollama active; news/social disabled truthfully.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/rules` -> `status=DEGRADED`, `mock_data=false`; degraded due truthful ambiguous/missing resolution source coverage.
- `Invoke-RestMethod http://127.0.0.1:8000/signals/recent` before source/rules checks -> `status=OK`, `mock_data=false`, `count=0`.
- `Invoke-RestMethod http://127.0.0.1:8000/signals/recent` after source/rules checks -> `status=OK`, `mock_data=false`, `count=18`.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/signals` after source/rules checks -> `mock_data=false`, `signal_status=OK`, `total_signals_24h=18`, `unprocessed_signals=18`, `signals_by_neuron` includes rules, market, orderbook, ai, news, social, whale.
- `Invoke-RestMethod http://127.0.0.1:8000/signals/neuron/rules?limit=3` -> `status=OK`, `mock_data=false`, `count=3`.
- `Invoke-RestMethod http://127.0.0.1:8000/signals/market/824952?limit=3` -> `status=OK`, `mock_data=false`, `count=3`.

## 11. Safety Verification

- Signal creation does not touch execution/order services.
- Contract rejects obvious decision/order evidence keys.
- Tests verify signal creation does not mutate `paper_orders`, `shadow_orders`, or `live_orders`.
- Source/rules adapters produce neutral `raw_direction=neutral` signals.
- No private keys were used.
- No secrets were intentionally printed in docs or final reporting.
- No order/cancel/sign path was intentionally touched.
- Safety env check:
  - `MODE=PAPER`
  - `BACKEND=paper`
  - `LIVE=false`
  - `KILL=true`
- Persisted runtime state:
  - `current_mode=DATA_ONLY`
  - `kill_switch_active=false`
  - `can_open_paper_positions=false`
  - `can_create_shadow_orders=false`
  - `can_create_live_orders=false`
  - `can_run_live_engine=false`
  - `max_risk_multiplier=0.0`
- Order counts after runtime checks:
  - `paper_orders=0`
  - `shadow_orders=0`
  - `live_orders=0`
  - `neuron_signals=18`

Safety nuance: environment kill switch is true, but persisted runtime state reports `kill_switch_active=false`. DATA_ONLY mode still blocks paper/shadow/live actions and no orders exist. This phase did not change State Governor behavior.

## 12. What Is Complete

- Unified neutral signal contract.
- Signal Store migration.
- Repository/service layer.
- Basic Signal API.
- Dashboard signal truth endpoint and overview integration.
- Source status and rules/resolution neutral adapters.
- Targeted tests and regressions.
- Documentation and build report.

## 13. What Is Partial

- Signal generation is intentionally light. There is no scheduler and no Brain Coordinator.
- Existing source/rules surfaces can emit Signals, but no full News/Social/Whale connectors were added.
- `processed_by_brain` exists for future use but no brain consumption exists in Part 1A.

## 14. Remaining Risks

- Signal volume can grow if future producers call adapters too frequently; this phase does not implement retention.
- Forbidden evidence-key checks are deliberately conservative but not a full semantic classifier.
- Runtime state kill switch does not mirror the env kill-switch value, although DATA_ONLY permissions block live/paper/shadow execution.

## 15. Recommended Next Phase

V2 Neural Mesh Activation Part 1B: Neuron Registry and producer health metadata.

Keep scope narrow: register who can emit Signals and expose registry/dashboard truth. Do not implement Brain Coordinator yet.

## 16. Final Status

GREEN.

Can continue to next phase: YES.
