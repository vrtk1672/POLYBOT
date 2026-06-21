# POLYBOT V2 Neural Mesh Part 2A Brain Output Contract Build Report

## 1. Purpose

Implement V2 Neural Mesh Activation Part 2A: Brain Output Contract, Brain Output Store, basic Brain Output APIs, and Dashboard Brain Output truth.

## 2. Current Reality Found

- `neuron_signals` exists and contains live/runtime Signals.
- `neuron_signal_bindings` exists from Part 1C.
- `neuron_registry` and `neuron_health` exist from Part 1B.
- Part 1C source code had lineage routes wired, but the live API initially returned 404 because the running API image was stale.
- Rebuilding/restarting the API restored:
  - `/dashboard/api/v2/signal-lineage`
  - `/signals/{signal_id}/lineage`
- Existing sampled lineage after restart returned `mock_data=false`.
- Newer signals carry producer lineage such as `rules_resolution_adapter`.
- Existing context/capital brain-specific tables exist, but no canonical cross-brain output store existed before this phase.
- Runtime persisted state is `DATA_ONLY`.
- Runtime env still reports `POLYBOT_RUNTIME_MODE=PAPER`.
- `LIVE_TRADING_ENABLED=false`.
- `LIVE_KILL_SWITCH=true`.
- Persisted runtime `kill_switch_active=false`.
- DATA_ONLY permissions block paper, shadow, live, new positions, closes, and attack engines.
- `paper_orders=0`, `shadow_orders=0`, `live_orders=0`.

## 3. Files Created

- `app/db/migrations/0062_v2_neural_mesh_brain_output_contract.sql`
- `app/neural_mesh/brain_outputs.py`
- `app/repositories/brain_output_repository.py`
- `app/services/brain_outputs.py`
- `app/api/brain_output_routes.py`
- `tests/test_v2_brain_output_contract.py`
- `tests/test_v2_brain_output_repository.py`
- `tests/test_v2_brain_output_api.py`
- `tests/test_v2_dashboard_brain_outputs.py`
- `docs/V2_NEURAL_MESH_PART2A_BRAIN_OUTPUT_CONTRACT.md`
- `docs/V2_NEURAL_MESH_PART2A_BRAIN_OUTPUT_CONTRACT_BUILD_REPORT.md`

## 4. Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/services/query/dashboard_v2_query_service.py`
- `tests/test_v2_dashboard_brain_outputs.py`

## 5. DB Migration

Migration applied:

- `0062_v2_neural_mesh_brain_output_contract.sql`

Tables:

- `brain_outputs`
- `brain_output_dependencies`
- `brain_output_conflicts`

Constraints:

- `confidence` is `0..1` when present.
- `urgency` is `0..1` when present.
- `conflict_severity` is `0..1` when present.
- `brain`, `output_type`, `recommendation`, and `status` must be non-empty.
- Dependencies and conflicts use constrained type values.

## 6. API Routes

Added:

- `GET /brain-outputs/recent`
- `GET /brain-outputs/{brain_output_id}`
- `GET /brain-outputs/market/{market_id}`
- `GET /brain-outputs/brain/{brain_name}`
- `GET /brain-outputs/signal/{signal_id}`
- `GET /brain-outputs/conflicts/recent`
- `GET /dashboard/api/v2/brain-outputs`

## 7. Dashboard Changes

- Added Dashboard V2 Brain Outputs endpoint.
- Added Brain Outputs to the Dashboard V2 nav.
- Added Brain Output summary to Dashboard V2 overview.
- Dashboard fields are DB-backed and return `mock_data=false`.

## 8. Tests Added

- Contract tests for valid Brain Output creation, numeric bounds, required fields, optional market/position, executable recommendation rejection, executable metadata rejection, dependency validation, and conflict validation.
- Repository/service tests for persistence, dependency persistence, missing Signal dependency rejection, list by market/brain/signal, conflict creation, conflict target validation, summary counts, and order table non-mutation.
- API tests for empty truth, recent/single/market/brain/signal routes, and conflict route.
- Dashboard tests for empty truth, count truth, and Dashboard V2 page integration.

## 9. Tests Run With Exact Results

- `docker compose config` -> passed; compose rendered successfully.
- `docker compose --profile test config` -> passed; test profile rendered successfully.
- `docker compose ps` -> passed; API, Postgres, Redis, and test Postgres healthy.
- `docker compose --profile test build api migrate test test_migrate` -> passed.
- `docker compose run --rm migrate` -> applied `0062_v2_neural_mesh_brain_output_contract.sql`.
- `docker compose --profile test run --rm test_migrate` -> applied `0062_v2_neural_mesh_brain_output_contract.sql`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_brain_output_contract.py tests/test_v2_brain_output_repository.py tests/test_v2_brain_output_api.py tests/test_v2_dashboard_brain_outputs.py -q` -> `28 passed in 9.06s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_brain_output_contract.py -q` -> `16 passed in 2.25s`.
- Parallel DB test attempt for repository/API produced transient failures from shared test DB/public fallback interference; rerunning those DB-backed files sequentially passed.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_brain_output_repository.py -q` -> `6 passed in 1.69s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_brain_output_api.py -q` -> `3 passed in 2.46s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_dashboard_brain_outputs.py -q` -> `3 passed in 11.71s`.
- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_neuron_signal_contract.py tests/test_v2_neuron_signal_repository.py tests/test_v2_neuron_signal_api.py tests/test_v2_dashboard_signals.py tests/test_v2_neuron_registry_contract.py tests/test_v2_neuron_registry_repository.py tests/test_v2_neuron_registry_api.py tests/test_v2_dashboard_neurons.py tests/test_v2_signal_event_binding_contract.py tests/test_v2_signal_event_binding_repository.py tests/test_v2_signal_event_binding_api.py tests/test_v2_dashboard_signal_lineage.py tests/test_v2_21_source_status.py tests/test_v2_22_rules_resolution_truth.py -q` -> `63 passed in 68.67s`.

## 10. Runtime Verification

After rebuilding and restarting API:

- `docker compose up -d api` -> API recreated and healthy.
- `/healthz` -> OK, `status=ok`.
- `/runtime/health` -> OK, `overall_status=HEALTHY`, `current_mode=DATA_ONLY`, `kill_switch_active=false`.
- `/runtime/state` -> OK, `current_mode=DATA_ONLY`; permissions block paper, shadow, live, new positions, closes, and attack engines.
- `/dashboard/api/v2/overview` -> responded, `status=DEGRADED`, `data_source.mock_data=false`.
- `/dashboard/api/v2/source-status` -> responded, `status=OK`, `mock_data=false`.
- `/dashboard/api/v2/rules` -> responded, `status=DEGRADED`, `mock_data=false`.
- `/signals/recent` -> responded, `status=OK`, `mock_data=false`, `count=50`.
- `/dashboard/api/v2/signals` -> responded, `status=DEGRADED`, `data_source.mock_data=false`.
- `/dashboard/api/v2/signal-lineage` -> responded, `status=OK`, `mock_data=false`, `total_signals_24h=19`.
- `/signals/{signal_id}/lineage` -> responded, `status=OK`, `mock_data=false`, `producer_name=rules_resolution_adapter`, `generated_from=rules_resolution`.
- `/neurons` -> responded, `status=OK`, `mock_data=false`, `count=22`.
- `/dashboard/api/v2/neurons` -> responded, `status=DEGRADED`, `mock_data=false`, `total_neurons=22`.
- `/brain-outputs/recent` -> responded, `status=OK`, `mock_data=false`, `count=0`.
- `/dashboard/api/v2/brain-outputs` -> responded, `status=OK`, `mock_data=false`, `total_outputs_24h=0`, `active_outputs=0`.

Production DB counts after runtime verification:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `brain_outputs=0`
- `brain_output_dependencies=0`
- `brain_output_conflicts=0`
- `neuron_signal_bindings=19`
- `neuron_signals=55`

## 11. Safety Verification

- No private keys were used.
- No secrets were printed in final documentation; command output containing local non-secret container DB URLs should not be treated as app-secret exposure.
- No orders were created.
- No cancel requests were sent.
- No signing path was touched.
- No live mutation path was touched.
- `LIVE_TRADING_ENABLED=false`.
- `LIVE_KILL_SWITCH=true`.
- Persisted runtime mode is `DATA_ONLY`.
- Persisted runtime kill switch is `false`, matching the previous known nuance.
- DATA_ONLY permissions block paper, shadow, live, new positions, closes, and attack engines.
- Brain Outputs reject executable recommendations and executable/order metadata keys.
- Dashboard uses real DB truth and `mock_data=false`.

## 12. What Is Complete

- Canonical Brain Output contract.
- Brain output persistence.
- Brain output dependency persistence.
- Brain output conflict persistence.
- Repository/service layer.
- Read APIs.
- Dashboard Brain Output truth.
- Overview compact Brain Output truth.
- Tests and regressions.
- Documentation.

## 13. What Is Partial

- Existing context/capital brain-specific outputs are not backfilled into `brain_outputs`.
- No automatic Brain Output producer loop was added.
- Brain Output store is empty in production until a future adapter/producer phase writes canonical outputs.

## 14. Remaining Risks

- Compose env still says `POLYBOT_RUNTIME_MODE=PAPER`, while persisted runtime state is `DATA_ONLY`. DATA_ONLY permissions block execution, but the mismatch should remain visible.
- Persisted `kill_switch_active=false` while env `LIVE_KILL_SWITCH=true`; this is the known safety nuance and was not changed.
- Parallel DB-backed tests can interfere because the repository uses a shared test DB/public fallback pattern. Sequential runs pass.
- Dashboard overview is DEGRADED because existing subsystem truth remains degraded/empty in places; this phase did not change those systems.

## 15. Recommended Next Phase

V2 Neural Mesh Activation Part 2B: Brain Output Producer Adapters.

Map existing context/capital/no-trade/risk advisory outputs into the canonical Brain Output Store without implementing Brain Coordinator, final decisions, or execution intents.

## 16. Final Status

GREEN.
