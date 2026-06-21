# V2 Neural Mesh Part 4C-M Build Report: Orderbook Snapshot Foundation

## Purpose

Implement real, read-only orderbook snapshot collection and dashboard truth so POLYBOT can reason about best bid, best ask, spread, depth, liquidity, freshness, and orderbook readiness without enabling Paper or execution.

## Current Reality Found

- Runtime Producer Evidence exists.
- Runtime Signals exist.
- Runtime Brain Outputs exist.
- Runtime Coordinator Decisions exist.
- Runtime Brain Outputs: 100.
- Dry-run Brain Outputs: 48.
- Runtime Coordinator Decisions: 100.
- Dry-run Coordinator Decisions: 12.
- `orderbook_snapshots` existed before this phase but had 0 rows.
- `markets_v2` had active, accepting markets with YES/NO token IDs.
- `ORDERBOOK_SNAPSHOTS_MISSING` was active before collection.
- `paper_ready=false`.
- `paper_orders=0`, `shadow_orders=0`, `live_orders=0`.
- `order_intents` table absent.
- `positions=0`.
- `fills_v2=1` pre-existing historical row.

## Audit Findings

- Existing orderbook table schema was usable but lacked directional depth, freshness, source, status, liquidity, run tracking, and raw payload references.
- Existing local market truth is `markets_v2`.
- Existing safe read-only orderbook source pattern is Polymarket CLOB `/book`.
- Existing data foundation orderbook normalizer and repository were extended instead of duplicated.
- Existing mesh blocker logic counted total snapshots only; it now checks freshness and coverage.
- Safest path was to collect CLOB books for active, non-closed, accepting markets with token IDs, persist normalized snapshots, and leave Paper blocked.

## Files Created

- `app/db/migrations/0078_v2_neural_mesh_orderbook_snapshot_foundation.sql`
- `app/services/orderbook_snapshots.py`
- `tests/test_v2_orderbook_snapshot_contract.py`
- `tests/test_v2_orderbook_snapshot_repository.py`
- `tests/test_v2_orderbook_snapshot_service.py`
- `tests/test_v2_orderbook_snapshot_api.py`
- `tests/test_v2_dashboard_orderbook.py`
- `tests/test_v2_orderbook_snapshot_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_M_ORDERBOOK_SNAPSHOT_FOUNDATION.md`
- `docs/V2_NEURAL_MESH_PART4C_M_ORDERBOOK_SNAPSHOT_FOUNDATION_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/data_foundation/contracts.py`
- `app/data_foundation/orderbook_snapshotter.py`
- `app/repositories/orderbook_snapshot_repository.py`
- `app/services/mesh_blockers.py`
- `app/services/mesh_dashboard.py`

## DB Migration

Migration:
- `0078_v2_neural_mesh_orderbook_snapshot_foundation.sql`

Changes:
- Extended `orderbook_snapshots` with directional depth, total depth, liquidity score, source, status, stale flags, raw payload refs, correlation IDs, collected_at, and created_at.
- Added snapshot status constraint.
- Added orderbook indexes.
- Added `orderbook_snapshot_runs`.

Runtime migration verification:
- `0078_v2_neural_mesh_orderbook_snapshot_foundation.sql` applied.
- New columns present: `collected_at`, `depth_bid_1c`, `liquidity_score`, `snapshot_status`.

## API Routes

Added:
- POST `/orderbook/snapshots/collect`
- GET `/orderbook/snapshots/recent`
- GET `/dashboard/api/v2/orderbook`

Updated:
- GET `/dashboard/api/v2/mesh`
- GET `/dashboard/api/v2/mesh-blockers`

## Dashboard Changes

- Added `layers.orderbook`.
- Added `flow.orderbook`.
- Added `readiness.orderbook_summary`.
- Added orderbook freshness, coverage, spread, and liquidity into mesh summary.
- Dashboard orderbook endpoint returns `mock_data=false`.

## Orderbook Snapshot Contract

The collector:
- discovers candidate markets from `markets_v2`
- fetches read-only Polymarket CLOB books
- normalizes best bid, best ask, spread, mid price, depth bands, total depth, and liquidity score
- detects EMPTY, PARTIAL, STALE, ERROR, and OK states
- persists snapshots and run audit rows
- reports safety deltas

## Data Source Used

Read-only Polymarket CLOB `/book` endpoint, using token IDs from existing local `markets_v2` truth. No fake orderbook data was introduced.

## Markets Checked

Runtime collection checked 11 active accepting markets.

## Snapshots Created / Updated

Runtime collection result:
- markets_checked=11
- snapshots_created=22
- snapshots_updated=0
- ok_snapshots=22
- partial_snapshots=0
- empty_orderbooks=0
- stale_snapshots=0
- error_count=0

## Spread / Depth / Liquidity Summary

Runtime dashboard:
- total_snapshots=22
- fresh_snapshots=22
- markets_with_orderbook=11
- active_tradable_markets=11
- orderbook_coverage_ratio=1.0
- avg_spread=0.030909
- avg_liquidity_score=0.847595

## Stale Detection Summary

- freshness_window_seconds=120
- stale_snapshots=0 after runtime collection
- top_stale_markets=[]
- stale, empty, and partial states remain explicit and visible.

## Mesh Blockers Before / After

Before:
- `ORDERBOOK_SNAPSHOTS_MISSING` active because `orderbook_snapshots=0`.

After runtime collection:
- `ORDERBOOK_SNAPSHOTS_MISSING` inactive.
- `ORDERBOOK_SNAPSHOTS_STALE` inactive.
- `ORDERBOOK_COVERAGE_LOW` inactive.
- `NO_RISK_CORE` remains active.
- `NO_EXIT_FOUNDATION` remains active.
- `NO_PAPER_ELIGIBLE_SIGNALS` remains active.
- `EXECUTION_NOT_ALLOWED` remains active.
- `paper_ready=false`.

## Tests Added

- `tests/test_v2_orderbook_snapshot_contract.py`
- `tests/test_v2_orderbook_snapshot_repository.py`
- `tests/test_v2_orderbook_snapshot_service.py`
- `tests/test_v2_orderbook_snapshot_api.py`
- `tests/test_v2_dashboard_orderbook.py`
- `tests/test_v2_orderbook_snapshot_safety.py`

## Tests Run and Exact Results

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_orderbook_snapshot_contract.py -q` -> 6 passed in 1.35s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_orderbook_snapshot_repository.py -q` -> 1 passed in 9.68s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_orderbook_snapshot_service.py -q` -> 2 passed in 19.10s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_orderbook_snapshot_api.py -q` -> 1 passed, 1 warning in 13.29s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_orderbook.py -q` -> 1 passed, 1 warning in 16.55s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_orderbook_snapshot_safety.py -q` -> 1 passed in 8.94s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_2_orderbook_snapshots.py tests/test_v2_2_data_foundation_api.py tests/test_v2_8_orderbook_analyzer.py -q` -> 9 passed, 1 warning in 38.70s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py -q` -> 46 passed, 1 warning in 153.14s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_brain_adapter_contract.py tests/test_v2_runtime_brain_adapter_service.py tests/test_v2_runtime_brain_adapter_api.py tests/test_v2_dashboard_runtime_brain.py tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_contract.py tests/test_v2_runtime_coordinator_service.py tests/test_v2_runtime_coordinator_api.py tests/test_v2_dashboard_runtime_coordinator.py tests/test_v2_runtime_coordinator_safety.py -q` -> 25 passed, 1 warning in 191.01s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py tests/test_v2_dashboard_mesh.py -q` -> 17 passed, 1 warning in 61.78s
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_producer_evidence_contract.py tests/test_v2_runtime_producer_evidence_service.py tests/test_v2_runtime_producer_evidence_api.py tests/test_v2_dashboard_runtime_producer_evidence.py tests/test_v2_runtime_producer_evidence_safety.py tests/test_v2_signal_quality_contract.py tests/test_v2_signal_processing_state_contract.py tests/test_v2_link_coverage_contract.py tests/test_v2_lineage_coverage_contract.py tests/test_v2_dry_run_provenance_contract.py tests/test_v2_producer_health_contract.py -q` -> 51 passed, 1 warning in 74.85s

## Runtime Verification Results

Runtime endpoints:
- GET `/healthz` -> 200, status ok
- GET `/runtime/health` -> 200, overall_status HEALTHY, current_mode DATA_ONLY
- POST `/orderbook/snapshots/collect` with `{"limit":50,"market_ids":[],"source":"auto"}` -> 200
- GET `/orderbook/snapshots/recent` -> 200, mock_data=false
- GET `/dashboard/api/v2/orderbook` -> 200, mock_data=false
- GET `/dashboard/api/v2/mesh-blockers` -> 200, mock_data=false
- GET `/dashboard/api/v2/mesh` -> 200, mock_data=false

Runtime orderbook truth:
- markets_checked=11
- snapshots_created=22
- snapshots_updated=0
- total_snapshots=22
- fresh_snapshots=22
- stale_snapshots=0
- ok_snapshots=22
- partial_snapshots=0
- empty_orderbooks=0
- avg_spread=0.030909
- avg_liquidity_score=0.847595

Runtime safety truth:
- paper_ready=false
- paper_orders=0
- shadow_orders=0
- live_orders=0
- order_intents absent
- fills_v2=1, unchanged historical row
- positions=0
- coordinator execution_allowed true count=0

## Safety Verification

- No order intents were created.
- No paper, shadow, or live orders were created.
- No fills were created by this phase.
- No positions were created.
- No risk approvals were created.
- No exit plans were created.
- No Paper mode enablement occurred.
- No live execution path was touched.
- `paper_ready=false`.
- `execution_allowed=false`.

## Blockers Resolved

- `ORDERBOOK_SNAPSHOTS_MISSING` resolved by 22 fresh DB-backed orderbook snapshots.

## Blockers Remaining

- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `EXECUTION_NOT_ALLOWED`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNALS_STALE_HIGH`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `DRY_RUN_EVIDENCE_BLOCKED_FROM_PAPER`
- `NO_THESIS_PROFILES`
- producer health blockers
- env/persisted mode mismatch
- env/persisted kill-switch mismatch

## Remaining Risks

- CLOB availability and rate limits can affect future collection runs.
- Orderbook freshness is time-sensitive and requires repeated collection before any future Paper phase.
- Signal-to-market linkage and Paper eligibility remain insufficient.
- Risk Core and Exit Foundation are still missing.

## Next Recommended Phase

V2 Neural Mesh Part 4C-N: Signal / Market Binding Recovery.

## Final Status

GREEN.

