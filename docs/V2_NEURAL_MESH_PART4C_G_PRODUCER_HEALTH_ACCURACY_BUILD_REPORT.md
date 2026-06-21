# V2 Neural Mesh Part 4C-G Producer Health Accuracy Build Report

## 1. Purpose

Implement Producer Health Accuracy so the Neuron Registry can be compared with runtime producer evidence.

This phase detects and explains producer health. It does not fix producers, enable Paper, create orders, create order intents, call AI, or touch execution/live/risk/state governor mutation logic.

## 2. Current Reality Found

Runtime and DB truth after implementation:

- `neuron_signals=139`
- `neuron_registry=22`
- `neuron_producers=6`
- `signal_quality_evaluations=100`
- `signal_processing_states=100`
- `dry_run_provenance_analysis=160`
- Brain Outputs remain dry-run only.
- Coordinator Decisions remain dry-run only.
- `paper_ready=false`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents` table absent.
- `execution_allowed_true=0`
- persisted runtime mode remains `DATA_ONLY`
- env `POLYBOT_RUNTIME_MODE=PAPER`
- env `LIVE_TRADING_ENABLED=false`
- env `LIVE_KILL_SWITCH=true`
- persisted `kill_switch_active=false`

The env/persisted mode and kill switch mismatches remain tracked, not fixed.

## 3. Files Created

- `app/neural_mesh/producer_health.py`
- `app/services/producer_health.py`
- `tests/test_v2_producer_health_contract.py`
- `tests/test_v2_producer_health_service.py`
- `tests/test_v2_producer_health_api.py`
- `tests/test_v2_dashboard_producer_health.py`
- `tests/test_v2_producer_health_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_G_PRODUCER_HEALTH_ACCURACY.md`
- `docs/V2_NEURAL_MESH_PART4C_G_PRODUCER_HEALTH_ACCURACY_BUILD_REPORT.md`

## 4. Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`
- `app/services/mesh_blockers.py`

## 5. DB Migration

None.

Producer health is computed from existing DB/runtime truth. No derived snapshot table was required for this phase.

## 6. API Routes

Added:

- `GET /dashboard/api/v2/producer-health`

Updated:

- `GET /dashboard/api/v2/mesh`
- `GET /dashboard/api/v2/mesh-blockers`

## 7. Dashboard Changes

`/dashboard/api/v2/producer-health` returns:

- `mock_data=false`
- `overall_status`
- `paper_ready=false`
- producer counts
- silent/missing/degraded/dry-run-only groups
- `producer_health` list
- `neuron_runtime_truth`

`/dashboard/api/v2/mesh` now includes:

- `layers.producer_health`
- `flow.producer_health`
- `readiness.producer_health_summary`

`/dashboard/api/v2/mesh-blockers` can include producer-derived blockers when active.

## 8. Producer Health Contract Summary

The contract records registered/expected/observed state, Signal counts, runtime/dry-run split, stale counts, Brain/Coordinator output counts, lineage coverage, average quality, health classification, evidence, and Paper/Brain eligibility flags.

Allowed health statuses:

- `HEALTHY`
- `ACTIVE`
- `DEGRADED`
- `SILENT`
- `MISSING`
- `DRY_RUN_ONLY`
- `REGISTERED_ONLY`
- `UNKNOWN`
- `ERROR`

## 9. Neuron Runtime Truth Summary

`neuron_runtime_truth` groups:

- `runtime_active`
- `dry_run_only`
- `silent_expected`
- `degraded`
- `missing`
- `unknown`

Runtime verification showed no runtime-active producers, multiple dry-run-only producer sources, and several silent expected neurons.

## 10. Registered vs Observed Producers

Runtime endpoint reported:

- `total_producers=34`
- `registered_producers=20`
- `observed_producers=17`

Registered producers come from `neuron_producers` and expected registry neurons. Observed producers come from Signals, lineage/provenance, and Brain/Coordinator provenance evidence.

## 11. Runtime-Active Producers

Runtime endpoint reported:

- `runtime_active_producers=0`

This is a truthful blocker. Producer health did not fabricate runtime activity.

## 12. Dry-Run-Only Producers

Runtime endpoint reported:

- `dry_run_only_producers=5`

Dry-run-only producer evidence can feed observability but cannot feed Paper readiness.

## 13. Silent Expected Neurons

Runtime endpoint reported silent expected neurons:

- `capital`
- `execution`
- `exit`
- `fees`
- `liquidity`
- `no_trade`
- `opportunity`
- `position`
- `resolution`
- `risk`
- `strategy`
- `time`
- `whale`

## 14. Degraded Neurons

Runtime endpoint reported degraded neurons:

- `ai`
- `market`
- `orderbook`
- `rules`
- `source`
- `whale`

## 15. Missing Neurons

Runtime endpoint reported missing neurons:

- `capital`
- `execution`
- `exit`
- `fees`
- `liquidity`
- `no_trade`
- `opportunity`
- `position`
- `resolution`
- `risk`
- `strategy`
- `time`

## 16. Evidence Sources

- `neuron_registry`
- `neuron_producers`
- `neuron_signals`
- `neuron_signal_bindings`
- `signal_quality_evaluations`
- `signal_processing_states`
- `signal_lineage_coverage_analysis`
- `dry_run_provenance_analysis`
- runtime health/state endpoints

## 17. Tests Added

- `tests/test_v2_producer_health_contract.py`
- `tests/test_v2_producer_health_service.py`
- `tests/test_v2_producer_health_api.py`
- `tests/test_v2_dashboard_producer_health.py`
- `tests/test_v2_producer_health_safety.py`

## 18. Tests Run And Exact Results

Host Python:

- `python -m pytest tests/test_v2_producer_health_contract.py -q` -> failed: `No module named pytest`

Docker build/config/migrations:

- `docker compose build api test` -> passed.
- `docker compose config` -> passed, config rendered.
- `docker compose --profile test config` -> passed, config rendered.
- `docker compose ps` -> api/postgres/postgres_test/redis healthy before API restart.
- `docker compose run --rm migrate` -> `No pending migrations.`
- `docker compose --profile test run --rm test_migrate` -> `No pending migrations.`

Targeted:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_producer_health_contract.py -q` -> `2 passed in 0.84s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_producer_health_service.py -q` -> `8 passed in 0.90s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_producer_health_api.py -q` -> `2 passed in 20.57s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_producer_health.py -q` -> `2 passed in 21.87s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_producer_health_safety.py -q` -> `2 passed in 2.19s`

Regressions:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py -q` -> `12 passed in 46.59s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dry_run_provenance_contract.py tests/test_v2_dry_run_provenance_repository.py tests/test_v2_dry_run_provenance_api.py tests/test_v2_dashboard_dry_run_provenance.py tests/test_v2_dry_run_provenance_safety.py -q` -> `15 passed in 67.37s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_lineage_coverage_contract.py tests/test_v2_lineage_coverage_repository.py tests/test_v2_lineage_coverage_api.py tests/test_v2_dashboard_lineage_coverage.py tests/test_v2_lineage_coverage_safety.py -q` -> `19 passed in 78.09s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_contract.py tests/test_v2_signal_processing_state_contract.py tests/test_v2_link_coverage_contract.py tests/test_v2_dashboard_mesh.py -q` -> `28 passed in 16.52s`

## 19. Runtime Verification Results

Commands:

- `docker compose up -d api` -> API recreated and started.
- `docker compose ps` -> `polybot_api` healthy.
- `GET /healthz` -> `status=ok`
- `GET /runtime/health` -> `overall_status=HEALTHY`
- `GET /dashboard/api/v2/producer-health` -> `mock_data=false`, `paper_ready=false`, `overall_status=DEGRADED`
- `GET /dashboard/api/v2/mesh` -> `mock_data=false`, `readiness.paper_ready=false`, `layers.producer_health` present
- `GET /dashboard/api/v2/mesh-blockers` -> `overall_status=BLOCKED`

Runtime producer values:

- `total_producers=34`
- `registered_producers=20`
- `observed_producers=17`
- `runtime_active_producers=0`
- `dry_run_only_producers=5`
- `producer_health list count=34`
- producer blockers active: `EXPECTED_NEURONS_SILENT`, `PRODUCER_HEALTH_DEGRADED`, `PRODUCER_RUNTIME_EVIDENCE_MISSING`

## 20. Safety Verification

Environment check:

- `MODE= PAPER`
- `BACKEND= paper`
- `LIVE= false`
- `KILL= true`

Persisted runtime state:

- `current_mode=DATA_ONLY`
- `kill_switch_active=false`
- `can_run_paper_engine=false`
- `can_create_shadow_orders=false`
- `can_create_live_orders=false`

DB safety counts:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents_exists=0`
- `execution_allowed_true=0`

No order, order-intent, signing, private key, Paper, Shadow, Live, risk, exit, capital, or State Governor mutation paths were changed.

## 21. Remaining Risks

- Producer health is computed, not persisted. This is intentional for this phase.
- `runtime_active_producers=0`, so runtime producer evidence remains blocked.
- Several expected neurons are silent or missing.
- Dry-run-only producers remain useful for observability only.
- Brain Outputs and Coordinator Decisions remain dry-run only.
- Env/persisted mode and kill switch mismatches remain unresolved.
- Paper readiness remains blocked.

## 22. Next Recommended Phase

V2 Neural Mesh Part 4C-H: Runtime Producer Evidence Loop.

Goal: improve runtime producer evidence without enabling Paper, orders, or execution. The first step should be non-executing producer evidence for existing source/rules/market observations, with strict provenance and quality gates.

## 23. ChatGPT Review

Review result: PASS.

Scope stayed within the allowed files. No runtime core, order, execution, risk, state governor, capital, live/paper activation, destructive DB behavior, AI, or secret paths were touched. Tests and runtime safety checks passed.

## 24. Final Status

GREEN.

Can continue: YES.
