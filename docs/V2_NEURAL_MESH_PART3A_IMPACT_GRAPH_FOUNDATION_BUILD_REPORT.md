# V2 Neural Mesh Part 3A Impact Graph Foundation Build Report

## 1. Purpose

Implement the Impact Graph foundation for linking events, entities, Signals, markets, positions, thesis profiles, and non-executing Cortex action hints.

## 2. Current Reality Found

- `neuron_signals` exists and `/signals/recent` works.
- `neuron_signal_entities` exists.
- `neuron_signal_bindings` exists and `/signals/{signal_id}/lineage` works for a real Signal.
- `neuron_registry` exists and `/neurons` works.
- `brain_outputs` exists and `/brain-outputs/recent` works.
- `coordinator_decisions` exists and `/coordinator/decisions/recent` works.
- Runtime persisted state remains `DATA_ONLY`.
- Env still reports `POLYBOT_RUNTIME_MODE=PAPER` and `LIVE_KILL_SWITCH=true`; persisted runtime state reports `DATA_ONLY` and `kill_switch_active=false`.
- `paper_orders=0`, `shadow_orders=0`, `live_orders=0`.

## 3. Files Created

- `app/db/migrations/0064_v2_neural_mesh_impact_graph_foundation.sql`
- `app/db/migrations/0065_v2_neural_mesh_impact_graph_delete_semantics.sql`
- `app/neural_mesh/impact_graph.py`
- `app/repositories/impact_graph_repository.py`
- `app/services/impact_graph.py`
- `app/api/impact_graph_routes.py`
- `tests/test_v2_impact_graph_contract.py`
- `tests/test_v2_impact_graph_repository.py`
- `tests/test_v2_impact_graph_api.py`
- `tests/test_v2_dashboard_impact_graph.py`
- `docs/V2_NEURAL_MESH_PART3A_IMPACT_GRAPH_FOUNDATION.md`
- `docs/V2_NEURAL_MESH_PART3A_IMPACT_GRAPH_FOUNDATION_BUILD_REPORT.md`

## 4. Files Changed

- `app/main.py`: registers the Impact Graph router.
- `app/api/routes.py`: adds `/dashboard/api/v2/impact-graph`.
- `app/services/query/dashboard_v2_query_service.py`: adds Impact Graph dashboard page and compact overview truth.

## 5. DB Migration

`0064_v2_neural_mesh_impact_graph_foundation.sql` creates:

- `event_entities`
- `entity_market_links`
- `signal_market_links`
- `signal_position_links`
- `position_thesis_profiles`
- `impact_links`

`0065_v2_neural_mesh_impact_graph_delete_semantics.sql` changes `impact_links` anchor references for `signal_id`, `entity_id`, and `thesis_id` to `ON DELETE CASCADE`. This is required because `impact_links` enforces subject/target integrity; nulling an anchor during cleanup would violate the graph contract.

## 6. API Routes

Added:

- `GET /impact/entities`
- `GET /impact/entities/{entity_id}`
- `GET /impact/signals/{signal_id}/markets`
- `GET /impact/signals/{signal_id}/positions`
- `GET /impact/markets/{market_id}`
- `GET /impact/positions/{position_id}`
- `GET /impact/positions/{position_id}/thesis`
- `GET /impact/links/{impact_link_id}`
- `GET /impact/unlinked-signals`
- `POST /impact/entities`
- `POST /impact/link/entity-market`
- `POST /impact/link/signal-market`
- `POST /impact/link/signal-position`
- `POST /impact/positions/{position_id}/thesis`
- `POST /impact/links`
- `GET /dashboard/api/v2/impact-graph`

All write routes are non-executing graph writes only.

## 7. Dashboard Changes

Added Impact Graph truth:

- `entities_total`
- `signal_market_links_total`
- `signal_position_links_total`
- `impact_links_total`
- `unlinked_signals`
- `links_by_status`
- `impacts_by_direction`
- `cortex_action_hints`
- `latest_impacts`
- `positions_with_thesis`
- `signals_without_market_link`

Runtime endpoint verification returned `mock_data=false`.

## 8. Tests Added

- Contract validation tests.
- Repository persistence and summary tests.
- API read/write route tests.
- Dashboard Impact Graph truth tests.
- Safety test confirming graph writes do not mutate order tables.

## 9. Tests Run With Exact Results

- `python -m py_compile app\neural_mesh\impact_graph.py app\repositories\impact_graph_repository.py app\services\impact_graph.py app\api\impact_graph_routes.py`: passed.
- Host `python -m pytest tests/test_v2_impact_graph_contract.py -q`: not available, host Python has no `pytest`.
- `docker compose --profile test build api migrate test test_migrate`: passed.
- `docker compose run --rm migrate`: applied `0064_v2_neural_mesh_impact_graph_foundation.sql`.
- `docker compose --profile test run --rm test_migrate`: applied `0064_v2_neural_mesh_impact_graph_foundation.sql`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_impact_graph_contract.py tests/test_v2_impact_graph_repository.py tests/test_v2_impact_graph_api.py tests/test_v2_dashboard_impact_graph.py -q`: `17 passed`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_impact_graph_contract.py -q`: `8 passed`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_impact_graph_repository.py -q`: `4 passed`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_impact_graph_api.py -q`: `2 passed`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_impact_graph.py -q`: `3 passed`.
- First broad regression run found an `impact_links` delete semantics issue.
- `docker compose --profile test build migrate test_migrate; docker compose run --rm migrate; docker compose --profile test run --rm test_migrate`: initially failed because a `DO $$` block did not match the repo migration runner.
- Migration `0065` was rewritten as simple `ALTER TABLE` statements.
- `docker compose --profile test build migrate test_migrate; docker compose run --rm migrate; docker compose --profile test run --rm test_migrate`: applied `0065_v2_neural_mesh_impact_graph_delete_semantics.sql`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_impact_graph_contract.py tests/test_v2_impact_graph_repository.py tests/test_v2_impact_graph_api.py tests/test_v2_dashboard_impact_graph.py -q`: `17 passed`.
- Broad regression after rebuilding test image:
  `docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_coordinator_contract.py tests/test_v2_brain_coordinator_repository.py tests/test_v2_brain_coordinator_rules.py tests/test_v2_brain_coordinator_api.py tests/test_v2_dashboard_coordinator.py tests/test_v2_brain_output_contract.py tests/test_v2_brain_output_repository.py tests/test_v2_brain_output_api.py tests/test_v2_dashboard_brain_outputs.py tests/test_v2_neuron_signal_contract.py tests/test_v2_neuron_signal_repository.py tests/test_v2_neuron_signal_api.py tests/test_v2_dashboard_signals.py tests/test_v2_neuron_registry_contract.py tests/test_v2_neuron_registry_repository.py tests/test_v2_neuron_registry_api.py tests/test_v2_dashboard_neurons.py tests/test_v2_signal_event_binding_contract.py tests/test_v2_signal_event_binding_repository.py tests/test_v2_signal_event_binding_api.py tests/test_v2_dashboard_signal_lineage.py tests/test_v2_21_source_status.py tests/test_v2_22_rules_resolution_truth.py -q`: `116 passed`.

## 10. Runtime Verification

- `docker compose config`: OK.
- `docker compose --profile test config`: OK.
- `docker compose ps`: API, Postgres, test Postgres, and Redis running healthy.
- `docker compose up -d api`: API recreated on rebuilt image and started.
- `GET /healthz`: `ok`.
- `GET /runtime/health`: `HEALTHY`, current mode `DATA_ONLY`.
- `GET /runtime/state`: persisted mode `DATA_ONLY`.
- `GET /dashboard/api/v2/overview`: `DEGRADED`, `mock_data=false`, no explicit errors; existing no-data/degraded module truth remains.
- `GET /dashboard/api/v2/source-status`: `OK`, `mock_data=false`.
- `GET /dashboard/api/v2/rules`: `DEGRADED`, `mock_data=false`.
- `GET /signals/recent`: `OK`, `mock_data=false`, count `50`.
- `GET /signals/{signal_id}/lineage`: `OK`, `mock_data=false`, `generated_from=rules_resolution`.
- `GET /dashboard/api/v2/signals`: `DEGRADED`, real dashboard envelope.
- `GET /dashboard/api/v2/signal-lineage`: `OK`, `mock_data=false`.
- `GET /neurons`: `OK`, `mock_data=false`, count `22`.
- `GET /dashboard/api/v2/neurons`: `DEGRADED`, `mock_data=false`.
- `GET /brain-outputs/recent`: `OK`, `mock_data=false`, count `0`.
- `GET /dashboard/api/v2/brain-outputs`: `OK`, `mock_data=false`.
- `GET /coordinator/decisions/recent`: `OK`, `mock_data=false`, count `0`.
- `GET /dashboard/api/v2/coordinator`: `OK`, `mock_data=false`.
- `GET /impact/entities`: `OK`, `mock_data=false`, count `0`.
- `GET /impact/unlinked-signals`: `OK`, `mock_data=false`, count `50`.
- `GET /dashboard/api/v2/impact-graph`: `OK`, `mock_data=false`, `impact_links_total=0`, `unlinked_signals=93`.

## 11. Safety Verification

- Env `POLYBOT_RUNTIME_MODE=PAPER`; persisted runtime mode remains `DATA_ONLY`.
- Env `POLYBOT_EXECUTION_BACKEND=paper`.
- Env `LIVE_TRADING_ENABLED=false`.
- Env `LIVE_KILL_SWITCH=true`; persisted runtime `kill_switch_active=false`.
- `paper_orders=0`.
- `shadow_orders=0`.
- `live_orders=0`.
- `coordinator_execution_allowed=0`.
- No private keys were printed.
- No signing path was used.
- No order or cancel path was touched.
- Impact Graph rejects executable Cortex action hints.

## 12. What Is Complete

- Impact Graph DB foundation exists.
- Event/entity storage exists.
- Entity-market links persist.
- Signal-market links persist.
- Signal-position links persist.
- Position thesis profiles persist.
- Impact links persist.
- Impact Graph API works.
- Dashboard Impact Graph truth works with `mock_data=false`.
- Tests and regressions pass.

## 13. What Is Partial

- Production graph is currently empty except for unlinked Signal counts.
- No automatic producer/backfill from existing `neuron_signal_entities` or Signal `market_id` fields is included.
- No AI entity extraction is included.

## 14. Remaining Risks

- Existing Signals are largely unlinked until a later safe backfill/producer phase.
- Dashboard overview remains `DEGRADED` because existing module truth includes no-data/degraded states; this phase did not attempt to resolve unrelated runtime truth.
- Env/persisted runtime safety nuance remains: env says `PAPER` and `KILL=true`; persisted state says `DATA_ONLY` and `kill_switch_active=false`.

## 15. Recommended Next Phase

V2 Neural Mesh Part 3B: Impact Graph Safe Producer / Backfill.

Suggested scope:

- Convert existing `neuron_signal_entities` into `event_entities`.
- Create suggested `signal_market_links` from existing Signal `market_id`.
- Keep all links suggested/confirmed based on deterministic existing fields only.
- Do not add AI extraction, trading logic, order intents, or execution.

## 16. Final Status

GREEN.

The Impact Graph foundation is implemented, persisted, tested, exposed through API/dashboard truth, and remains non-executing. Safety remained intact.
