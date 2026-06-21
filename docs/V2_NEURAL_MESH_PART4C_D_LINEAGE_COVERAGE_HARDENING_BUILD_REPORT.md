# V2 Neural Mesh Part 4C-D: Lineage Coverage Hardening Build Report

## Purpose

Implement a non-executing lineage coverage analyzer so every Signal can report producer/source/correlation/raw payload/generated-from provenance, missing lineage fields, trust score, dry-run/runtime split, and Paper blockers.

## Current Reality Found

- `neuron_signals` exists.
- `neuron_signal_bindings` exists.
- Signal Quality, Signal Processing, and Link Coverage phases exist and remain intact.
- Existing lineage summary endpoint `/dashboard/api/v2/signal-lineage` exists.
- Runtime persisted mode is `DATA_ONLY`.
- Env `POLYBOT_RUNTIME_MODE=PAPER`.
- Env `LIVE_TRADING_ENABLED=false`.
- Env `LIVE_KILL_SWITCH=true`.
- Persisted `kill_switch_active=false`.
- The env/persisted mode and kill-switch mismatches remain tracked, not fixed.

Runtime lineage analysis result after this phase:
- analyzed: 100
- created_or_updated: 100
- total_signals: 139
- total_analyzed: 100
- bound_signals: 100
- unbound_signals: 5
- complete_lineage: 0
- partial_lineage: 0
- dry_run_only_signals: 0
- runtime_verified_signals: 95
- avg_lineage_trust_score: 0.99
- dashboard status: `DEGRADED`
- mesh status: `DEGRADED`
- mesh `paper_ready=false`

## Files Created

- `app/db/migrations/0071_v2_neural_mesh_lineage_coverage_hardening.sql`
- `app/neural_mesh/lineage_coverage.py`
- `app/repositories/lineage_coverage_repository.py`
- `app/services/lineage_coverage.py`
- `app/api/lineage_coverage_routes.py`
- `tests/test_v2_lineage_coverage_contract.py`
- `tests/test_v2_lineage_coverage_repository.py`
- `tests/test_v2_lineage_coverage_api.py`
- `tests/test_v2_dashboard_lineage_coverage.py`
- `tests/test_v2_lineage_coverage_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_D_LINEAGE_COVERAGE_HARDENING.md`
- `docs/V2_NEURAL_MESH_PART4C_D_LINEAGE_COVERAGE_HARDENING_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/services/mesh_dashboard.py`

## DB Migration

`0071_v2_neural_mesh_lineage_coverage_hardening.sql`

Created:
- `signal_lineage_coverage_analysis`
- `signal_lineage_coverage_runs`

The migration is idempotent and creates analysis truth only. It does not mutate execution, Paper, Shadow, or Live tables.

## API Routes

- `GET /signals/lineage-coverage/recent`
- `GET /signals/{signal_id}/lineage-coverage`
- `POST /signals/lineage-coverage/analyze/recent`
- `POST /signals/{signal_id}/lineage-coverage/analyze`
- `GET /dashboard/api/v2/lineage-coverage`

## Dashboard Changes

- Added `/dashboard/api/v2/lineage-coverage`.
- Added `layers.lineage_coverage` to `/dashboard/api/v2/mesh`.
- Added `flow.lineage_coverage` to `/dashboard/api/v2/mesh`.
- Added readiness blockers:
  - `LINEAGE_ANALYSIS_MISSING`
  - `SIGNAL_LINEAGE_COVERAGE_LOW`
  - `SIGNALS_UNBOUND_HIGH`
  - `SIGNALS_MISSING_PRODUCER`
  - `SIGNALS_MISSING_SOURCE`
  - `SIGNALS_MISSING_RAW_PAYLOAD_REF`
  - `SIGNALS_MISSING_CORRELATION_ID`
  - `DRY_RUN_LINEAGE_BLOCKED_FROM_PAPER`

All dashboard responses use DB/runtime truth and `mock_data=false`.

## Lineage Coverage Contract Summary

The contract records:
- lineage status
- trust score
- bound/unbound state
- primary unbound reason
- all missing lineage fields
- producer/source/correlation/raw payload/generated-from/generated-by/generated-at
- dry-run/runtime/manual/adapter provenance
- event/payload/producer traceability
- informational brain/Paper lineage eligibility

## Unbound Reason Classifier Summary

The classifier detects:
- missing producer
- missing source
- missing correlation id
- missing raw payload reference
- missing generated_from
- missing generated_at
- dry-run-only provenance
- unknown origin
- missing event/payload/producer trace
- already-bound state
- unknown fallback

## Lineage Trust Score Summary

The score is deterministic, clamped 0..1, and uses:
- producer/source/correlation/raw payload/generated_from/generated_at/runtime provenance as positive evidence
- dry-run-only and unknown origin as penalties

## Dry Run vs Runtime Provenance Summary

Dry-run lineage is detected from quality flags and local evidence/provenance tokens such as `mesh_dry_run`. Dry-run lineage is audit-visible but blocked from Paper evidence. Runtime provenance improves trust score but does not enable global Paper readiness.

## Tests Added

- Contract/scoring tests.
- Repository idempotency/run-summary tests.
- API route tests.
- Dashboard/mesh integration tests.
- Safety tests for order counts and dry-run Paper blocking.

## Tests Run And Exact Results

Targeted:
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_lineage_coverage_contract.py -q` -> `9 passed in 1.13s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_lineage_coverage_repository.py -q` -> `3 passed in 16.86s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_lineage_coverage_api.py -q` -> `3 passed in 21.19s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_lineage_coverage.py -q` -> `2 passed in 16.32s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_lineage_coverage_safety.py -q` -> `2 passed in 11.90s`

Regressions:
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_contract.py tests/test_v2_signal_quality_repository.py tests/test_v2_signal_quality_api.py tests/test_v2_dashboard_signal_quality.py -q` -> `18 passed in 60.29s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_processing_state_contract.py tests/test_v2_signal_processing_state_repository.py tests/test_v2_signal_processing_state_api.py tests/test_v2_dashboard_signal_processing.py tests/test_v2_signal_quality_gate_enforcement.py -q` -> `19 passed in 61.39s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_contract.py tests/test_v2_link_coverage_repository.py tests/test_v2_link_coverage_api.py tests/test_v2_dashboard_link_coverage.py tests/test_v2_link_coverage_safety.py -q` -> `19 passed in 56.65s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_event_binding_contract.py tests/test_v2_dashboard_signal_lineage.py -q` -> `6 passed in 4.50s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_neuron_signal_contract.py tests/test_v2_dashboard_signals.py -q` -> `11 passed in 4.63s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_mesh.py -q` -> `5 passed in 9.32s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_dry_run_contract.py tests/test_v2_mesh_dry_run_flow.py tests/test_v2_dashboard_mesh_dry_run.py -q` -> `6 passed in 29.57s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_output_contract.py tests/test_v2_dashboard_brain_outputs.py -q` -> `19 passed in 4.64s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_coordinator_contract.py tests/test_v2_dashboard_coordinator.py -q` -> `11 passed in 4.69s`

Notes:
- Local host Python does not have `pytest`; Docker test runner was used.
- An initial parallel Docker test attempt hit a `test_migrate` container-name conflict. Tests were rerun serially and passed.
- One repository test fixture initially expected missing raw payload while the signal still had a raw payload ref. The fixture was corrected and the test passed.

## Runtime Verification Results

Commands:
- `docker compose config --quiet` -> passed
- `docker compose --profile test config --quiet` -> passed
- `docker compose ps` -> api/postgres/postgres_test/redis healthy before rebuild
- `docker compose --profile test build migrate test_migrate test api` -> passed
- `docker compose run --rm migrate` -> applied `0071_v2_neural_mesh_lineage_coverage_hardening.sql`
- `docker compose --profile test run --rm test_migrate` -> applied `0071_v2_neural_mesh_lineage_coverage_hardening.sql`
- `docker compose up -d api` -> API restarted successfully
- `GET /healthz` -> `200`, status `ok`
- `GET /runtime/health` -> `200`, overall_status `HEALTHY`, current_mode `DATA_ONLY`, kill_switch_active `false`
- `GET /runtime/state` -> `200`, current_mode `DATA_ONLY`, paper/live/shadow permissions false
- `POST /signals/lineage-coverage/analyze/recent {"limit":100}` -> `status=OK`, analyzed `100`, created_or_updated `100`
- `GET /signals/lineage-coverage/recent` -> `200`, count `50`, `mock_data=false`
- `GET /dashboard/api/v2/lineage-coverage` -> `200`, status `DEGRADED`, `mock_data=false`
- `GET /dashboard/api/v2/signal-quality` -> `200`, status `DEGRADED`, `mock_data=false`
- `GET /dashboard/api/v2/signal-processing` -> `200`, status `DEGRADED`, `mock_data=false`
- `GET /dashboard/api/v2/link-coverage` -> `200`, status `DEGRADED`, `mock_data=false`
- `GET /dashboard/api/v2/mesh` -> `200`, status `DEGRADED`, lineage coverage layer present, `paper_ready=false`

## Safety Verification

- Env `POLYBOT_RUNTIME_MODE=PAPER`
- Env `POLYBOT_EXECUTION_BACKEND=paper`
- Env `LIVE_TRADING_ENABLED=false`
- Env `LIVE_KILL_SWITCH=true`
- Persisted mode `DATA_ONLY`
- Persisted `kill_switch_active=false`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents` table absent
- `coordinator execution_allowed true=0`
- No private keys printed.
- No signing path used.
- No order/cancel/live mutation path touched.
- `paper_ready=false`.

## What Is Complete

- Lineage coverage DB foundation.
- Deterministic analyzer and trust scorer.
- Dry-run/runtime/manual/adapter provenance classification.
- Unbound reason classifier.
- API routes.
- Dashboard truth endpoint.
- Mesh layer and readiness blockers.
- Tests and regression coverage.
- Documentation and build report.

## What Is Partial

- Historical missing lineage remains missing by design.
- Runtime Signals still require producer/adapter hooks to attach complete lineage at creation time.
- Current dashboard status is honestly `DEGRADED` because some analyzed Signals remain unbound or missing raw payload refs.

## Remaining Risks

- Existing runtime source/adapters can still create Signals without full lineage until creation hooks are hardened.
- Env/persisted runtime and kill-switch mismatches remain tracked but unresolved.
- This phase analyzes lineage but does not repair historical provenance.

## Next Recommended Phase

V2 Neural Mesh Part 4C-E: Producer/Adapter Lineage Backfill + Signal Creation Hooks.

Goal: ensure future runtime-created Signals attach producer/source/correlation/raw payload/generated-from lineage at creation time, without fabricating missing historical truth or enabling Paper.

## Final Status

GREEN
