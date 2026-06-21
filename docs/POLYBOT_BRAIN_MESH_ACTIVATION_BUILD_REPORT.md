# POLYBOT Brain Mesh Activation Build Report

Phase: `POLYBOT_BRAIN_MESH_ACTIVATION`

## Current Reality Found

- SYSTEM ON/OFF was GREEN.
- Scheduler and MarketService were active under SYSTEM ON.
- Runtime producer evidence, brain adapter, coordinator, and thesis builders existed but were manual-only.
- `position_thesis_profiles` was `0` before this phase.

## Files Created

- `app/db/migrations/0086_polybot_brain_mesh_activation.sql`
- `app/services/brain_mesh_activation.py`
- `tests/test_brain_mesh_activation_service.py`
- `tests/test_brain_mesh_activation_scheduler.py`
- `tests/test_dashboard_brain_mesh_activation_truth.py`
- `docs/POLYBOT_BRAIN_MESH_ACTIVATION.md`
- `docs/POLYBOT_BRAIN_MESH_ACTIVATION_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/services/runtime_brain_adapter.py`

## DB Changes

Added `brain_mesh_activation_runs` to record non-executing activation summaries.

## Runtime Integration Point

`MarketService.refresh()` now calls `BrainMeshActivationService.run_activation()` after existing runtime intelligence work and before the paper stage. The paper stage remains blocked by `DATA_ONLY`.

## Dashboard / API Changes

Added `GET /dashboard/api/v2/brain-mesh-activation`.

## Tests Added

- OFF blocks activation.
- ON calls producer evidence, brain adapter, coordinator, and thesis services.
- Activation records a run summary.
- Partial failures are reported as `DEGRADED`.
- MarketService refresh invokes activation under SYSTEM ON.
- Dashboard returns real activation truth.

## Tests Run

- `tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py`
  - Result: `5 passed, 1 warning`
- Step 1 system power tests
  - Result: `9 passed, 1 warning`
- Runtime/state regressions
  - Result: `19 passed`
- Brain/coordinator/thesis regressions
  - Result: `19 passed`
- Safety regressions
  - Result: `7 passed`
- Post-fix targeted contract/service/activation set
  - Result: `11 passed, 1 warning`

Warnings were the existing Starlette TestClient deprecation warning.

## Runtime Smoke

Baseline before OFF:

- `neuron_signals=147`
- `runtime_producer_evidence_runs=1`
- `brain_outputs=148`
- `runtime_brain_producer_runs=1`
- `coordinator_decisions=112`
- `runtime_coordinator_runs=1`
- `thesis_profiles=100`
- `position_thesis_profiles=0`
- `brain_mesh_activation_runs=0`
- `paper_orders=0`
- `paper_fills=0` table absent
- `paper_positions=0`
- `orders_v2=1` historical
- `live_orders=0`
- `fills_v2=1` historical
- `positions=0`

SYSTEM OFF observation after one scheduler interval stayed unchanged.

Final SYSTEM ON observation:

- `neuron_signals=195`
- `runtime_producer_evidence_runs=7`
- `brain_outputs=196`
- `runtime_brain_producer_runs=4`
- `coordinator_decisions=160`
- `runtime_coordinator_runs=7`
- `thesis_profiles=148`
- `position_thesis_profiles=30`
- `brain_mesh_activation_runs=6`
- `paper_orders=0`
- `paper_fills=0` table absent
- `paper_positions=0`
- `orders_v2=1` unchanged historical
- `live_orders=0`
- `fills_v2=1` unchanged historical
- `positions=0`

Latest dashboard activation:

- `status=OK`
- `brain_mesh_activation_allowed=true`
- `last_evidence_created_count=8`
- `last_brain_outputs_created_count=8`
- `last_coordinator_decisions_created_count=8`
- `last_thesis_profiles_created_count=8`
- `last_position_thesis_profiles_created_count=4`
- `orders_created=0`
- `fills_created=0`
- `positions_created=0`
- `live_actions_created=0`

## Safety Confirmation

- SYSTEM OFF blocked activation.
- SYSTEM ON woke the Brain Mesh automatically.
- No paper, shadow, or live orders were created.
- No fills or positions were created.
- Runtime mode remained `DATA_ONLY`.
- Risk, Exit, and Eligibility were not bypassed.

## Remaining Risks

- Orderbook and binding refresh are still outside this phase, so downstream Risk/Exit/Eligibility may remain blocked.
- Some old decorative service registry statuses still exist; dashboard activation truth is based on DB output, not those labels.
- Early smoke runs before the bookkeeping fix were `DEGRADED`; the latest post-fix autonomous runs are `OK`.

## Next Recommended Step

Step 3: Fresh Orderbook + Signal Market Binding Evidence, behind SYSTEM ON/OFF and with execution still disabled.

## Phase Status

GREEN. The Brain Mesh now wakes automatically under SYSTEM ON and remains silent under SYSTEM OFF.
