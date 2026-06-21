# POLYBOT V2 Neural Mesh Part 3B Position Thesis Profile Build Report

## 1. Purpose
Implement the Position Thesis Profile Contract + Thesis Enforcement Foundation. This phase is non-executing and creates thesis validation, readiness scoring, APIs, dashboard truth, and documentation.

## 2. Current Reality Found
- `position_thesis_profiles` existed from Part 3A as an impact graph table.
- `signal_position_links`, `impact_links`, `coordinator_decisions`, and `brain_outputs` existed.
- Existing position/order tables existed: `positions`, `paper_positions`, `paper_orders`, `shadow_positions`, `shadow_orders`, and `live_orders`.
- Existing paper position state includes `thesis_state`, but no canonical thesis profile contract or entry enforcement existed.
- Existing Exit advisory/risk code did not use a canonical thesis profile.
- Runtime persisted state is `DATA_ONLY`.
- Environment still reports `POLYBOT_RUNTIME_MODE=PAPER` and `LIVE_KILL_SWITCH=true`.
- Persisted `kill_switch_active=false`; this known nuance was not changed.
- Order counts before and after this phase remained zero.

## 3. Files Created
- `app/db/migrations/0066_v2_neural_mesh_position_thesis_contract.sql`
- `app/neural_mesh/position_thesis.py`
- `app/repositories/position_thesis_repository.py`
- `app/services/position_thesis.py`
- `app/api/position_thesis_routes.py`
- `tests/test_v2_position_thesis_contract.py`
- `tests/test_v2_position_thesis_repository.py`
- `tests/test_v2_position_thesis_api.py`
- `tests/test_v2_dashboard_thesis.py`
- `docs/V2_NEURAL_MESH_PART3B_POSITION_THESIS_PROFILE.md`
- `docs/V2_NEURAL_MESH_PART3B_POSITION_THESIS_PROFILE_BUILD_REPORT.md`

## 4. Files Changed
- `app/main.py`
- `app/api/routes.py`
- `app/services/query/dashboard_v2_query_service.py`

## 5. DB Migration
Migration `0066_v2_neural_mesh_position_thesis_contract.sql` was added and applied to production and test databases.

Extended `position_thesis_profiles` with:
- `completeness_score`
- `paper_ready`
- `live_ready`
- `coordinator_decision_id`
- `brain_output_id`
- `source_signal_ids_json`
- `risk_flags_json`
- `thesis_version`
- `created_by`
- `reviewed_by`
- `reviewed_at`
- `expires_at`
- `metadata_json`

Created:
- `position_thesis_validation_events`

Constraints added:
- allowed thesis statuses
- allowed side values
- completeness range `0..1`
- `live_ready` requires `paper_ready`
- positive thesis version

## 6. API Routes
Added:
- `GET /thesis/profiles`
- `GET /thesis/profiles/{thesis_id}`
- `GET /thesis/positions/{position_id}`
- `GET /thesis/positions/{position_id}/validation`
- `GET /thesis/summary`
- `POST /thesis/profiles`
- `PUT /thesis/profiles/{thesis_id}`
- `POST /thesis/profiles/{thesis_id}/validate`
- `POST /thesis/profiles/{thesis_id}/needs-review`
- `POST /thesis/profiles/{thesis_id}/invalidate`

## 7. Dashboard Changes
Added:
- `GET /dashboard/api/v2/thesis`
- Dashboard V2 `thesis` page loader
- Compact thesis fields in Dashboard V2 overview summary
- Dashboard source tables for `position_thesis_profiles` and `position_thesis_validation_events`

No mock data was added.

## 8. Tests Added
- `tests/test_v2_position_thesis_contract.py`
- `tests/test_v2_position_thesis_repository.py`
- `tests/test_v2_position_thesis_api.py`
- `tests/test_v2_dashboard_thesis.py`

Coverage includes:
- valid thesis creation
- completeness scoring
- paper readiness
- live readiness
- missing invalidation/emergency rules
- executable language rejection
- API create/get/validate/status mutation
- dashboard truth
- no order table mutation

## 9. Tests Run With Exact Results
Commands:
- `python -m py_compile app/neural_mesh/position_thesis.py app/repositories/position_thesis_repository.py app/services/position_thesis.py app/api/position_thesis_routes.py` -> passed.
- `docker compose config` -> passed.
- `docker compose --profile test config` -> passed.
- `docker compose ps` -> api/postgres/postgres_test/redis running and healthy after refresh.
- `docker compose --profile test build api migrate test test_migrate` -> passed.
- `docker compose run --rm migrate` -> applied `0066_v2_neural_mesh_position_thesis_contract.sql`.
- `docker compose --profile test run --rm test_migrate` -> applied `0066_v2_neural_mesh_position_thesis_contract.sql`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_position_thesis_contract.py -q` -> `9 passed in 0.74s`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_position_thesis_repository.py -q` -> `5 passed in 1.67s`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_position_thesis_api.py -q` -> initially `1 failed, 3 passed`; fixed route validation handling.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_position_thesis_api.py -q` -> `4 passed in 2.49s`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_thesis.py -q` -> `3 passed in 5.70s`.
- Regression sweep for Impact Graph, Coordinator, Brain Output, Signals, Neuron Registry, Signal Lineage, Source Status, and Rules Resolution -> initially `1 failed, 132 passed`; fixed `side=None` thesis row parsing.
- Regression sweep rerun -> `133 passed in 75.45s`.

## 10. Runtime Verification
After rebuilding and restarting the API:
- `docker compose up -d api` -> API recreated and started.
- `docker compose ps` -> API healthy.

Endpoint checks:
- `/healthz` -> `status=ok`
- `/runtime/health` -> `status=OK`
- `/runtime/state` -> `status=OK`, persisted mode `DATA_ONLY`
- `/dashboard/api/v2/overview` -> `status=DEGRADED`, `mock_data=false`
- `/dashboard/api/v2/source-status` -> `status=OK`, `mock_data=false`
- `/dashboard/api/v2/rules` -> `status=DEGRADED`, `mock_data=false`
- `/signals/recent` -> `status=OK`, `mock_data=false`, `count=50`
- `/dashboard/api/v2/signals` -> `status=DEGRADED`, `mock_data=false`
- `/dashboard/api/v2/signal-lineage` -> `status=OK`, `mock_data=false`
- `/neurons` -> `status=OK`, `mock_data=false`, `count=22`
- `/dashboard/api/v2/neurons` -> `status=DEGRADED`, `mock_data=false`
- `/brain-outputs/recent` -> `status=OK`, `mock_data=false`, `count=0`
- `/dashboard/api/v2/brain-outputs` -> `status=OK`, `mock_data=false`
- `/coordinator/decisions/recent` -> `status=OK`, `mock_data=false`, `count=0`
- `/dashboard/api/v2/coordinator` -> `status=OK`, `mock_data=false`, `total_decisions_24h=0`
- `/impact/entities` -> `status=OK`, `mock_data=false`, `count=0`
- `/dashboard/api/v2/impact-graph` -> `status=OK`, `mock_data=false`, `entities_total=0`
- `/thesis/profiles` -> `status=OK`, `mock_data=false`, `count=0`
- `/thesis/summary` -> `status=OK`, `mock_data=false`, `total_thesis_profiles=0`
- `/dashboard/api/v2/thesis` -> `status=OK`, `mock_data=false`, `total_thesis_profiles=0`

Dashboard overview and some existing modules are `DEGRADED` because the live repo truth has incomplete/stale upstream data, not because mock data was introduced.

## 11. Safety Verification
Environment check:
- `MODE= PAPER`
- `BACKEND= paper`
- `LIVE= false`
- `KILL= true`

Persisted runtime state:
- `current_mode=DATA_ONLY`
- `kill_switch_active=false`
- `can_open_paper_positions=false`
- `can_create_shadow_orders=false`
- `can_create_live_orders=false`
- `can_open_new_positions=false`
- `can_close_positions=false`
- `can_run_paper_engine=false`
- `can_run_shadow_engine=false`
- `can_run_live_engine=false`
- `max_risk_multiplier=0.0`

Counts after implementation:
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `coordinator_execution_allowed=0`
- `position_thesis_profiles=0`

No private keys were used. No signed requests were sent. No orders or cancels were created.

## 12. What Is Complete
- Position Thesis contract exists.
- Existing `position_thesis_profiles` was reused and extended.
- Thesis validation works.
- Completeness scoring works.
- Paper readiness rules work.
- Live readiness is computed and remains non-executing.
- API works.
- Dashboard thesis truth works with `mock_data=false`.
- Tests pass.
- Existing Signal/Neuron/Lineage/Brain/Coordinator/Impact APIs were preserved.

## 13. What Is Partial
- Future runtime enforcement is not wired into paper/shadow/live entry paths. This is intentional for this phase.
- Existing paper position `thesis_state` remains separate from canonical `position_thesis_profiles`. A future phase should link them before any entry flow can depend on thesis readiness.

## 14. Remaining Risks
- Env mode still reports `PAPER` while persisted runtime state is `DATA_ONLY`; this is tracked but unchanged.
- Env `LIVE_KILL_SWITCH=true` differs from persisted `kill_switch_active=false`; DATA_ONLY permissions still block execution.
- Thesis readiness flags are stored but not yet consumed by execution/risk/governor code.

## 15. Recommended Next Phase
Recommended next phase: V2 Neural Mesh Part 3C, thesis-aware non-executing review helpers for Risk/Exit/No-Trade preparation. Do not connect execution until a later explicit Governor/Execution phase.

## 16. Final Status
GREEN.

Can continue to next phase: YES.
