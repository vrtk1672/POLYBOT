# POLYBOT V2 Neural Mesh Part 1B Neuron Registry Build Report

## 1. Purpose

Implement V2 Neural Mesh Activation Part 1B: Neuron Registry, producer health metadata, Signal-based runtime stats, Neuron APIs, dashboard Neuron Mesh Health, tests, and documentation.

## 2. Current Reality Found

- No canonical `neuron_registry` or `neuron_health` table/code existed before this phase.
- `service_health` exists and remains separate as runtime service ledger truth.
- `source_status` can inform neuron health for source-backed neurons.
- `neuron_signals` is the canonical source for runtime stats, signal counts, last signal time, stale counts, and unprocessed counts.
- Part 1A files extended: dashboard query service, API route registration, Signal Store stats integration.
- Next migration number selected: `0060_v2_neural_mesh_neuron_registry.sql`.
- Safety nuance still exists: env `KILL=true`, persisted runtime state reports `kill_switch_active=false`; DATA_ONLY permissions still block paper/shadow/live actions.

## 3. Files Created

- `app/db/migrations/0060_v2_neural_mesh_neuron_registry.sql`
- `app/neural_mesh/registry.py`
- `app/repositories/neuron_registry_repository.py`
- `app/services/neuron_registry.py`
- `app/api/neuron_routes.py`
- `tests/test_v2_neuron_registry_contract.py`
- `tests/test_v2_neuron_registry_repository.py`
- `tests/test_v2_neuron_registry_api.py`
- `tests/test_v2_dashboard_neurons.py`
- `docs/V2_NEURAL_MESH_PART1B_NEURON_REGISTRY.md`
- `docs/V2_NEURAL_MESH_PART1B_NEURON_REGISTRY_BUILD_REPORT.md`

## 4. Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/services/query/dashboard_v2_query_service.py`
- `app/services/neuron_registry.py`

## 5. DB Migration

Migration applied:

- `0060_v2_neural_mesh_neuron_registry.sql`

Tables:

- `neuron_registry`
- `neuron_health`

Default seeded neurons:

- market
- orderbook
- liquidity
- rules
- resolution
- news
- social
- whale
- time
- fees
- ai
- risk
- capital
- position
- exit
- source
- execution
- no_trade
- opportunity
- strategy
- memory
- learning

No `neuron_runtime_stats` table was created. Runtime stats are computed live from `neuron_signals` to avoid duplicate truth.

## 6. API Routes

Created:

- `GET /neurons`
- `GET /neurons/{neuron_name}`
- `GET /dashboard/api/v2/neurons`

All are read-only and return `mock_data=false`.

## 7. Dashboard Changes

- Added dashboard V2 `neurons` page loader.
- Added `/dashboard/api/v2/neurons`.
- Added `Neurons` dashboard navigation entry.
- Added compact neuron counts to dashboard overview summary:
  - `total_neurons`
  - `active_neurons`
  - `degraded_neurons`
- Preserved existing Signal dashboard fields.

## 8. Tests Added

- Registry contract validation tests.
- Default seed coverage tests.
- Disabled/active/stale/missing status tests.
- Signal count and last signal tests.
- `/neurons` and `/neurons/{neuron_name}` API tests.
- `/dashboard/api/v2/neurons` dashboard truth tests.
- Order table non-mutation safety test.

## 9. Tests Run With Exact Results

- `docker compose config` -> passed; compose rendered successfully.
- `docker compose --profile test config` -> passed; test profile rendered successfully.
- `docker compose ps` -> passed; API, Postgres, Redis, and test Postgres healthy.
- `docker compose --profile test build api migrate test test_migrate` -> passed.
- `docker compose run --rm migrate` -> applied `0060_v2_neural_mesh_neuron_registry.sql`.
- `docker compose --profile test run --rm test_migrate` -> applied `0060_v2_neural_mesh_neuron_registry.sql`.
- `docker compose --profile test build test api migrate test_migrate` -> passed after a test-driven stats payload fix.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_contract.py -q` -> `4 passed in 0.62s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_repository.py -q` first run -> `1 failed, 5 passed`; detail payload stats were not populated.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_repository.py -q` after fix -> `6 passed in 1.67s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_registry_api.py -q` -> `3 passed in 2.27s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_neurons.py -q` -> `3 passed in 4.98s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_contract.py -q` -> `8 passed in 0.98s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_repository.py -q` -> `3 passed in 2.16s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_api.py -q` -> `2 passed in 3.20s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_signals.py -q` -> `3 passed in 5.94s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_21_source_status.py -q` -> `6 passed in 3.25s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_22_rules_resolution_truth.py -q` -> `9 passed in 31.87s`.

## 10. Runtime Verification

Runtime image restart:

- `docker compose up -d api` -> API recreated and started on rebuilt image.
- `docker compose ps` -> API, Postgres, Redis, and test Postgres healthy.

Endpoint checks:

- `Invoke-RestMethod http://127.0.0.1:8000/healthz` -> `status=ok`, `ready=true`.
- `Invoke-RestMethod http://127.0.0.1:8000/runtime/health` -> `overall_status=HEALTHY`, `current_mode=DATA_ONLY`, active cycle has `paper_started=false`, `shadow_started=false`, `live_started=false`.
- `Invoke-RestMethod http://127.0.0.1:8000/runtime/state` -> `mode=DATA_ONLY`, persisted `kill=false`, paper/shadow/live permissions false.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview` -> `mock_data=false`, overview includes `total_neurons=22`, `active_neurons=0` at first overview check, and `degraded_neurons=1`.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/source-status` -> `status=OK`, `mock_data=false`, `stale=false`.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/rules` -> `status=DEGRADED`, `mock_data=false`, `stale=false`.
- `Invoke-RestMethod http://127.0.0.1:8000/signals/recent` -> `status=OK`, `mock_data=false`, `count=18` before later source/rules checks emitted more neutral Signals.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/signals` -> `mock_data=false`, `total_signals_24h=26` during check.
- `Invoke-RestMethod http://127.0.0.1:8000/neurons` -> `status=OK`, `mock_data=false`, `count=22`.
- `Invoke-RestMethod http://127.0.0.1:8000/neurons/rules` -> `status=OK`, `mock_data=false`, `health=DEGRADED`, `signals_24h=20`.
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/neurons` -> `status=DEGRADED`, `mock_data=false`, `total_neurons=22`, `active_neurons=4`, `partial_neurons=11`, `disabled_neurons=2`, `missing_neurons=4`, `degraded_neurons=1`, `stale_neurons=0`.

## 11. Safety Verification

- Registry is observational only.
- No Brain Coordinator was implemented.
- No trading logic was modified.
- No private keys were used.
- No orders were created in tests.
- No cancel/sign/live mutation path was touched.
- Test coverage verifies registry reads do not mutate `paper_orders`, `shadow_orders`, or `live_orders`.
- Dashboard data uses real DB/runtime truth and `mock_data=false`.
- KILL/runtime state behavior was not changed.
- Safety env check:
  - `MODE=PAPER`
  - `BACKEND=paper`
  - `LIVE=false`
  - `KILL=true`
- Persisted runtime state:
  - `mode=DATA_ONLY`
  - `kill=false`
  - paper/shadow/live permissions false
- Order and registry counts:
  - `paper_orders=0`
  - `shadow_orders=0`
  - `live_orders=0`
  - `neuron_registry=22`
  - `neuron_health=22`
  - `neuron_signals=36` after endpoint checks emitted additional neutral source/rules Signals

## 12. What Is Complete

- Canonical registry contract.
- Registry and health tables.
- Default neuron seed rows.
- Signal-based runtime stats.
- Source-status-aware health calculation.
- Registry APIs.
- Dashboard Neuron Mesh Health.
- Tests and regressions.
- Documentation and build report.

## 13. What Is Partial

- Status calculation is intentionally simple and explainable.
- No producer registration hooks beyond metadata and source/status correlation.
- No retention policy for Signal Store or health history.
- No Brain Coordinator or interpretation layer.

## 14. Remaining Risks

- Runtime env kill switch and persisted runtime kill state still disagree.
- Source-backed status can mark source-disabled neurons as disabled via registry, but future connector configuration will need explicit operator review.
- Stats are computed live from `neuron_signals`; this is fine at current scale but may need caching/materialization if Signal volume becomes high.

## 15. Recommended Next Phase

V2 Neural Mesh Activation Part 1C: producer registration hooks and explicit producer-to-registry metadata wiring.

Do not implement Brain Coordinator yet.

## 16. Final Status

GREEN.

Can continue to next phase: YES.
