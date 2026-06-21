# V2 Neural Mesh Part 4C-I Runtime Producer Evidence Loop Build Report

## Purpose

Implement a controlled, non-executing runtime producer evidence loop that creates runtime Signals from existing local producer observations and updates the full 4C truth chain while keeping Paper blocked.

## Current Reality Found

- 4C-H consolidated regression suite was already GREEN.
- Existing `NeuronSignalService` can create Signals with lineage.
- Existing `source_status` rows are safe local runtime observations.
- Existing analyzers expose per-signal methods for quality, processing, lineage coverage, and link coverage.
- Dry-run provenance, producer health, mesh blockers, and mesh dashboard are computed from DB truth.
- Existing Brain Outputs and Coordinator Decisions remain dry-run-only.

## Audit Findings

- Safe local producer path found: `source_status -> NeuronSignalService.create_signal_with_lineage`.
- Existing source status adapter emitted Signals but did not explicitly mark `generated_by=runtime`.
- No need to touch execution, risk, capital, state governor mutation, order, fill, or live paths.
- Runtime evidence can make producer health runtime-active, but Paper remains blocked by orderbook, risk, exit, brain, coordinator, and quality blockers.

## Files Created

- `app/db/migrations/0075_v2_neural_mesh_runtime_producer_evidence_loop.sql`
- `app/neural_mesh/runtime_producer_evidence.py`
- `app/repositories/runtime_producer_evidence_repository.py`
- `app/services/runtime_producer_evidence.py`
- `tests/test_v2_runtime_producer_evidence_contract.py`
- `tests/test_v2_runtime_producer_evidence_service.py`
- `tests/test_v2_runtime_producer_evidence_api.py`
- `tests/test_v2_dashboard_runtime_producer_evidence.py`
- `tests/test_v2_runtime_producer_evidence_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_I_RUNTIME_PRODUCER_EVIDENCE_LOOP.md`
- `docs/V2_NEURAL_MESH_PART4C_I_RUNTIME_PRODUCER_EVIDENCE_LOOP_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`

## DB Migration

Applied:

- `0075_v2_neural_mesh_runtime_producer_evidence_loop.sql`

Tables:

- `runtime_producer_evidence_runs`
- `runtime_producer_evidence_items`

Both tables enforce non-executing invariants: `paper_ready=false`, `orders_created=0`, `order_intents_created=0`, and `live_actions_created=0`.

## API Routes

- `POST /producers/runtime-evidence/run`
- `GET /dashboard/api/v2/runtime-producer-evidence`

## Dashboard Changes

- `/dashboard/api/v2/runtime-producer-evidence` added.
- `/dashboard/api/v2/mesh` now includes:
  - `layers.runtime_producer_evidence`
  - `flow.runtime_producer_evidence`
  - `readiness.runtime_producer_evidence_summary`
  - runtime evidence counts in `mesh_summary`

## Runtime Producer Evidence Contract

Runtime Signals created by the loop include:

- `producer_name`
- `source`
- `correlation_id`
- `raw_payload_ref`
- `generated_from=source_status`
- `generated_by=runtime`
- `is_runtime_generated=true`
- `is_dry_run_generated=false`

## Producers Checked

Runtime verification checked 8 local `source_status` producer observations.

## Runtime Producers Activated

Runtime verification:

- Before: `runtime_active_producers=0`
- After: `runtime_active_producers=2`
- Runtime-active neurons reported: `orderbook`, `source`

## Signals Created / Updated

Runtime verification:

- `signals_created=8`
- `signals_updated=0`

## Downstream Evaluations Updated

Runtime verification:

- `quality_updated=8`
- `processing_updated=8`
- `lineage_updated=8`
- `link_coverage_updated=8`
- `provenance_updated=160`
- `producer_health_updated=true`
- `mesh_blockers_updated=true`

## Mesh Blockers Before / After

Resolved by this phase:

- `PRODUCER_RUNTIME_EVIDENCE_MISSING` no longer appeared after runtime evidence existed.

Remaining blockers include:

- `ORDERBOOK_SNAPSHOTS_MISSING`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNALS_STALE_HIGH`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `BRAIN_OUTPUTS_DRY_RUN_ONLY`
- `COORDINATOR_DECISIONS_DRY_RUN_ONLY`
- `NO_RUNTIME_BRAIN_OUTPUTS`
- `NO_RUNTIME_COORDINATOR_DECISIONS`
- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `ENV_PERSISTED_MODE_MISMATCH`
- `ENV_PERSISTED_KILL_SWITCH_MISMATCH`

## Tests Added

Five targeted files with 10 tests:

- runtime evidence contract validation
- service loop creation and downstream analyzer updates
- API route
- dashboard route and mesh layer
- safety checks for no orders, no intents, no fills, no positions, no live actions, and remaining blockers

## Tests Run And Exact Results

- `python -m compileall app/neural_mesh/runtime_producer_evidence.py app/repositories/runtime_producer_evidence_repository.py app/services/runtime_producer_evidence.py app/api/routes.py app/services/mesh_dashboard.py`  
  Result: passed.

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_producer_evidence_contract.py tests/test_v2_runtime_producer_evidence_service.py tests/test_v2_runtime_producer_evidence_api.py tests/test_v2_dashboard_runtime_producer_evidence.py tests/test_v2_runtime_producer_evidence_safety.py -q`  
  Result: `10 passed in 53.42s`.

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py -q`  
  Result: `46 passed in 95.59s`.

- Signal quality / processing / link coverage / lineage coverage regression block  
  Result: `75 passed in 204.37s`.

- Dry-run provenance / mesh blockers / producer health / dashboard mesh regression block  
  Result: `48 passed in 99.36s`.

- Brain output / coordinator / dry-run mesh regression block  
  Result: `36 passed in 38.45s`.

Host `python -m pytest ...` could not run because host Python did not have pytest installed; Docker test profile was used.

## Runtime Verification Results

Commands:

- `docker compose config`: passed.
- `docker compose --profile test config`: passed.
- `docker compose ps`: API, Postgres, Postgres test, and Redis healthy.
- `docker compose --profile test run --rm test_migrate`: `No pending migrations.`
- `docker compose run --rm migrate`: applied `0075_v2_neural_mesh_runtime_producer_evidence_loop.sql`.
- `docker compose up -d api`: API restarted healthy.

Runtime API checks:

- `GET /healthz`: HTTP 200, `status=ok`.
- `GET /runtime/health`: HTTP 200, `overall_status=HEALTHY`, `current_mode=DATA_ONLY`.
- `POST /producers/runtime-evidence/run {"limit":100,"apply_evaluations":true}`:
  - `status=OK`
  - `mock_data=false`
  - `producers_checked=8`
  - `runtime_active_before=0`
  - `runtime_active_after=2`
  - `signals_created=8`
  - `quality_updated=8`
  - `processing_updated=8`
  - `lineage_updated=8`
  - `link_coverage_updated=8`
  - `provenance_updated=160`
  - `paper_ready_after=false`
  - `orders_created=0`
  - `order_intents_created=0`
  - `live_actions_created=0`
- `GET /dashboard/api/v2/runtime-producer-evidence`: HTTP 200, `mock_data=false`, latest run present.
- `GET /dashboard/api/v2/producer-health`: HTTP 200, `runtime_active_producers=2`, `dry_run_only_producers=5`.
- `GET /dashboard/api/v2/mesh-blockers`: HTTP 200, `paper_ready=false`, `overall_status=BLOCKED`, active blocker count `20`.
- `GET /dashboard/api/v2/mesh`: HTTP 200, `mock_data=false`, `layers.runtime_producer_evidence` present, `paper_ready=false`.

## Safety Verification

Environment:

- `POLYBOT_RUNTIME_MODE=PAPER`
- `POLYBOT_EXECUTION_BACKEND=paper`
- `LIVE_TRADING_ENABLED=false`
- `LIVE_KILL_SWITCH=true`

Persisted runtime:

- `/runtime/state`: `current_mode=DATA_ONLY`
- `kill_switch_active=false`
- `can_run_paper_engine=false`
- `can_create_live_orders=false`

DB safety counts:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents=0`
- `paper_fills=0`
- `positions=0`
- `execution_allowed_true=0`

## Blockers Resolved

- Runtime producer evidence now exists.
- Producer health now reports runtime-active producers.
- `PRODUCER_RUNTIME_EVIDENCE_MISSING` is no longer active after the runtime evidence run.

## Blockers Remaining

Paper remains blocked by missing orderbook snapshots, runtime brain outputs, runtime coordinator decisions, Risk Core, Exit Foundation, thesis profiles, paper-eligible Signals, link/lineage/quality gaps, stale Signals, dry-run-only Brain/Coordinator outputs, and env/persisted mismatches.

## Remaining Risks

- Runtime evidence currently comes from local `source_status` only.
- No runtime Brain Outputs or runtime Coordinator Decisions exist yet.
- Link coverage remains low and no Paper-eligible Signals exist.
- Env/persisted mode and kill switch mismatches remain tracked but not fixed.

## Next Recommended Phase

V2 Neural Mesh Part 4C-J: Runtime Brain Producer Adapter Skeleton.

Goal: create non-executing runtime Brain Outputs from runtime Signals that pass quality/processing/lineage gates, while preserving `execution_allowed=false`, `paper_ready=false`, and all order/live safety invariants.

## Final Status

GREEN.
