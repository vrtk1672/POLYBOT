# V2 Neural Mesh Part 4C-Q: Exit Foundation Build Report

## Purpose

Build the first real non-executing Exit Foundation layer so future Paper candidates must have an auditable exit contract before any Paper intent can exist.

## Current Reality Found

- Runtime Producer Evidence exists.
- Runtime Signals, Brain Outputs, and Coordinator Decisions exist.
- Thesis Profiles exist: 100.
- Risk Core exists: 100 risk decisions.
- Risk approved count: 0.
- Risk blocked count: 100.
- `paper_ready=false`.
- `paper_orders=0`, `shadow_orders=0`, `live_orders=0`.
- `order_intents` table is absent.
- `fills_v2=1` historical row, unchanged by this phase.
- `positions=0`.
- `execution_allowed_true=0`.

## Audit Findings

- Existing `exit_plans` table existed from legacy Exit Cortex V2, but it was order/position oriented and required non-null `market_id` / `side`.
- Existing Exit Cortex service can create `exit_intents`, so 4C-Q does not call it.
- A safe migration extended `exit_plans` for foundation metadata while preserving legacy columns.
- All current Risk Core decisions are blocked, so current Exit Foundation output should be blocked, not complete.

## Files Created

- `app/db/migrations/0082_v2_neural_mesh_exit_foundation.sql`
- `app/neural_mesh/exit_foundation.py`
- `app/repositories/exit_foundation_repository.py`
- `app/services/exit_foundation.py`
- `tests/test_v2_exit_foundation_contract.py`
- `tests/test_v2_exit_foundation_repository.py`
- `tests/test_v2_exit_foundation_service.py`
- `tests/test_v2_exit_foundation_api.py`
- `tests/test_v2_dashboard_exit_foundation.py`
- `tests/test_v2_exit_foundation_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_Q_EXIT_FOUNDATION.md`
- `docs/V2_NEURAL_MESH_PART4C_Q_EXIT_FOUNDATION_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`
- `app/services/mesh_blockers.py`

## DB Migrations

`0082_v2_neural_mesh_exit_foundation.sql`:

- Extends `exit_plans` with thesis/risk/runtime provenance, status, exit type, blockers, warnings, missing evidence, and safety booleans.
- Adds `exit_plan_runs`.
- Adds `exit_plan_rules`.
- Adds checks preventing `paper_intent_allowed=true` and `execution_allowed=true` on `exit_plans`.

## API Routes

- `POST /exit/plans/build`
- `GET /exit/plans/recent`
- `GET /dashboard/api/v2/exit-foundation`

## Dashboard Changes

- Mesh layer: `layers.exit_foundation`
- Mesh flow: `flow.exit_foundation`
- Readiness summary: `readiness.exit_summary`
- Dashboard response includes complete/incomplete/blocked split, target/stop counts, emergency/liquidity rule counts, safety counters, and missing evidence counts.

## Exit Foundation Contract

Exit plans are generated only from runtime Risk Core decisions. They always set:

- `generated_by=runtime`
- `producer_name=exit_foundation`
- `is_runtime_generated=true`
- `is_dry_run_generated=false`
- `paper_intent_allowed=false`
- `execution_allowed=false`

## Exit Rules

Deterministic rules include:

- thesis invalidated
- risk decision changed
- market link lost
- orderbook stale
- spread too wide
- liquidity below threshold
- emergency kill active
- source data stale
- manual kill / missing price / liquidity collapse emergency exits

Target/stop logic is clamped to `0.01..0.99` and only becomes complete when side and mid price exist.

## Runtime Verification Results

`POST /exit/plans/build {"limit":100,"include_blocked":true,"write_plans":true}`:

- HTTP 200
- `mock_data=false`
- `risk_decisions_checked=100`
- `exit_plans_created=100`
- `exit_plans_updated=0`
- `complete_exit_count=0`
- `incomplete_exit_count=0`
- `blocked_exit_count=100`
- `missing_market_count=24`
- `missing_orderbook_count=100`
- `missing_side_count=100`
- `missing_risk_approval_count=100`
- `paper_ready_before=false`
- `paper_ready_after=false`
- `orders_created=0`
- `order_intents_created=0`
- `fills_created=0`
- `positions_created=0`
- `live_actions_created=0`

Dashboard checks:

- `/healthz`: HTTP 200
- `/runtime/health`: HTTP 200, `current_mode=DATA_ONLY`
- `/exit/plans/recent`: HTTP 200, `count=50`, first status `BLOCKED`
- `/dashboard/api/v2/exit-foundation`: HTTP 200, `mock_data=false`, `paper_ready=false`, `total_exit_plans=100`
- `/dashboard/api/v2/mesh-blockers`: HTTP 200, `paper_ready=false`, `overall_status=BLOCKED`
- `/dashboard/api/v2/mesh`: HTTP 200, `layers.exit_foundation` present, `readiness.exit_summary` present

Safety DB counts:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents` absent
- `fills_v2=1` historical row unchanged
- `positions=0`
- `exit_foundation_execution_allowed_true=0`
- `exit_foundation_paper_intent_allowed_true=0`
- `exit_foundation_paper_exit_ready_true=0`

## Tests Run

Targeted:

- `tests/test_v2_exit_foundation_contract.py`
- `tests/test_v2_exit_foundation_repository.py`
- `tests/test_v2_exit_foundation_service.py`
- `tests/test_v2_exit_foundation_api.py`
- `tests/test_v2_dashboard_exit_foundation.py`
- `tests/test_v2_exit_foundation_safety.py`
- Result: 15 passed, 1 warning.

4C consolidated:

- `tests/test_v2_4c_regression_safety.py`
- `tests/test_v2_4c_mesh_truth_regression.py`
- `tests/test_v2_4c_dashboard_readiness_regression.py`
- Result: 46 passed, 1 warning.

Risk/thesis/orderbook/binding regressions:

- `tests/test_v2_risk_core_*.py`
- `tests/test_v2_thesis_profile_*.py`
- `tests/test_v2_orderbook_snapshot_*.py`
- `tests/test_v2_signal_market_binding_*.py`
- Result: 49 passed, 1 warning.

Runtime/mesh regressions:

- `tests/test_v2_runtime_producer_evidence_*.py`
- `tests/test_v2_runtime_brain_adapter_*.py`
- `tests/test_v2_runtime_coordinator_*.py`
- `tests/test_v2_mesh_blockers_*.py`
- `tests/test_v2_dashboard_mesh.py`
- Result: 44 passed, 1 warning.

Signal/provenance/producer regressions:

- `tests/test_v2_link_coverage_*.py`
- `tests/test_v2_signal_quality_*.py`
- `tests/test_v2_signal_processing_*.py`
- `tests/test_v2_lineage_coverage_*.py`
- `tests/test_v2_dry_run_provenance_*.py`
- `tests/test_v2_producer_health_*.py`
- Result: 92 passed, 1 warning.

## Mesh Blockers Before/After

Resolved by this phase:

- `NO_EXIT_FOUNDATION`

Active after runtime verification:

- `EXIT_PLANS_ALL_BLOCKED`
- `EXIT_MISSING_ORDERBOOK`
- `EXIT_MISSING_RISK_APPROVAL`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `RISK_DECISIONS_ALL_BLOCKED`
- `RISK_CORE_MISSING_DATA`
- signal quality/linkage/lineage/stale blockers
- dry-run/provenance and producer health blockers
- env/persisted mode and kill-switch mismatches
- `EXECUTION_NOT_ALLOWED`

Note: runtime orderbook blockers were active during verification because the previous snapshots were stale by the 120-second freshness window.

## Safety Verification

No Paper or live path was enabled. No orders, order intents, fills, positions, strategy routes, paper intents, or live actions were created. `paper_ready` and `execution_allowed` remained false.

## Remaining Risks

- All current exit plans are blocked because all current risk decisions are blocked.
- Current runtime thesis/risk records still lack side and fresh linked orderbook evidence.
- Paper Eligibility Gate does not exist yet.
- Runtime configuration mismatches remain tracked and unresolved.

## Next Recommended Phase

4C-R Paper Eligibility Gate, after refreshing/closing the evidence gaps that keep all current Risk and Exit records blocked.
