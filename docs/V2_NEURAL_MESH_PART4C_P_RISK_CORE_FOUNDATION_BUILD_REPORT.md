# V2 Neural Mesh Part 4C-P Risk Core Foundation Build Report

## Purpose

Create the first thesis-derived Risk Core layer before Paper. Risk Core evaluates runtime Thesis Profiles, persists deterministic Risk Decisions, exposes dashboard truth, and keeps Paper and execution blocked.

## Current Reality Found

- Runtime Producer Evidence exists.
- Runtime Signals exist.
- Runtime Brain Outputs exist.
- Runtime Coordinator Decisions exist.
- Orderbook Snapshot Foundation exists.
- Signal / Market Binding Recovery exists.
- Thesis Profile Foundation exists.
- `thesis_profiles=100` before Risk Core runtime evaluation.
- `complete_thesis_profiles=0`.
- `blocked_thesis_profiles=100`.
- `risk_decisions=0` before this phase.
- Legacy V2.14 `risk_gate_runs` exists, but is route/allocation oriented.
- `risk_decisions` table was absent before this phase.
- `paper_ready=false`.
- `execution_allowed_true=0`.
- `paper_orders=0`.
- `shadow_orders=0`.
- `live_orders=0`.
- `order_intents=absent`.
- `positions=0`.
- `fills_v2=1` historical row unchanged.

## Audit Findings

The older V2.14 Risk Gate and Risk Governor remain useful for execution-era checks, but they are not the 4C-P thesis-derived Paper-readiness Risk Core. A new `risk_decisions` table was required, while `risk_gate_runs` was safely extended with nullable/defaulted 4C-P batch audit columns.

Current thesis truth is real but blocked. The correct Risk Core output is therefore blocked risk decisions, not Paper approvals.

## Files Created

- `app/db/migrations/0081_v2_neural_mesh_risk_core_foundation.sql`
- `app/neural_mesh/risk_core.py`
- `app/repositories/risk_core_repository.py`
- `app/services/risk_core.py`
- `tests/test_v2_risk_core_contract.py`
- `tests/test_v2_risk_core_repository.py`
- `tests/test_v2_risk_core_service.py`
- `tests/test_v2_risk_core_api.py`
- `tests/test_v2_dashboard_risk_core.py`
- `tests/test_v2_risk_core_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_P_RISK_CORE_FOUNDATION.md`
- `docs/V2_NEURAL_MESH_PART4C_P_RISK_CORE_FOUNDATION_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`
- `app/services/mesh_blockers.py`

## DB Migrations

- `0081_v2_neural_mesh_risk_core_foundation.sql`

Created:

- `risk_decisions`

Extended:

- `risk_gate_runs` with 4C-P batch audit counters.
- `risk_limits` with compatibility fields for Risk Core defaults.

Seeded:

- `risk_core_max_position_size`
- `risk_core_max_loss`
- `risk_core_confidence_threshold`
- `risk_core_max_spread`
- `risk_core_min_liquidity_score`
- `risk_core_daily_exposure_placeholder`

No order, intent, fill, position, exit, Paper, or execution tables were changed.

## API Routes

- `POST /risk/core/evaluate`
- `GET /risk/decisions/recent`
- `GET /dashboard/api/v2/risk-core`

## Dashboard Changes

- `/dashboard/api/v2/risk-core` exposes Risk Core truth.
- `/dashboard/api/v2/mesh` includes `layers.risk_core`.
- Mesh `flow` includes `risk_core`.
- Mesh readiness includes `risk_summary`.
- Mesh blockers now resolve `NO_RISK_CORE` only from `risk_decisions > 0`.

## Risk Core Contract

Risk Decisions include thesis ID, market ID, decision, status, aggregate score, component risk scores, limits, blockers, warnings, missing evidence, source thesis status, orderbook reference, runtime provenance, and hard false `paper_candidate_allowed` / `execution_allowed` fields.

## Risk Limits

- `max_position_size_default=10.0`
- `max_loss_default=5.0`
- `confidence_threshold=0.6`
- `max_spread=0.08`
- `min_liquidity_score=0.25`
- `daily_exposure_placeholder=50.0`

## Thesis Profiles Checked

Runtime verification checked `100` runtime Thesis Profiles.

## Risk Decisions Before / After

- before: `0`
- after: `100`

## Approved / Rejected / Blocked Split

Runtime verification:

- approved: `0`
- rejected: `0`
- blocked: `100`
- warnings: `0`

## Top Risk Blockers

Runtime verification activated:

- `THESIS_BLOCKED`
- `MISSING_FRESH_ORDERBOOK`
- `MISSING_SIGNAL_MARKET_BINDING`
- `MISSING_MARKET_ID`
- downstream blocker warnings for missing Exit Foundation remain visible through dashboard and mesh blockers.

## Risk Score Summary

Runtime verification:

- `avg_risk_score=1.0`
- `risk_approved_count=0`
- `paper_candidate_allowed_count=0`
- `execution_allowed_count=0`

The score is expected because all current thesis profiles are blocked or missing required evidence.

## Mesh Blockers Before / After

Resolved:

- `NO_RISK_CORE`

Active after runtime verification:

- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `RISK_DECISIONS_ALL_BLOCKED`
- `RISK_CORE_MISSING_DATA`
- thesis missing/incomplete blockers
- signal quality/linkage/lineage blockers
- stale signal/orderbook freshness blockers in the restarted runtime
- producer/dry-run blockers
- env/persisted mode and kill-switch mismatches
- `EXECUTION_NOT_ALLOWED`

## Tests Added

Focused tests cover contract safety, repository persistence, service evaluation, blocked/incomplete/missing evidence rules, score clamping, API/dashboard truth, mesh layer presence, and safety counters.

## Tests Run and Exact Results

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_risk_core_contract.py tests/test_v2_risk_core_repository.py tests/test_v2_risk_core_service.py tests/test_v2_risk_core_api.py tests/test_v2_dashboard_risk_core.py tests/test_v2_risk_core_safety.py -q` -> initial stale image import failure; rebuilt test image.
- `docker compose --profile test build test | Out-Null; docker compose --profile test run --rm test python -m pytest tests/test_v2_risk_core_contract.py tests/test_v2_risk_core_repository.py tests/test_v2_risk_core_service.py tests/test_v2_risk_core_api.py tests/test_v2_dashboard_risk_core.py tests/test_v2_risk_core_safety.py -q` -> `14 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py -q` -> `46 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_thesis_profile_contract.py tests/test_v2_thesis_profile_repository.py tests/test_v2_thesis_profile_service.py tests/test_v2_thesis_profile_api.py tests/test_v2_dashboard_thesis.py tests/test_v2_dashboard_thesis_profile_foundation.py tests/test_v2_thesis_profile_safety.py tests/test_v2_orderbook_snapshot_contract.py tests/test_v2_orderbook_snapshot_repository.py tests/test_v2_orderbook_snapshot_service.py tests/test_v2_orderbook_snapshot_api.py tests/test_v2_dashboard_orderbook.py tests/test_v2_orderbook_snapshot_safety.py tests/test_v2_signal_market_binding_contract.py tests/test_v2_signal_market_binding_repository.py tests/test_v2_signal_market_binding_service.py tests/test_v2_signal_market_binding_api.py tests/test_v2_dashboard_market_binding.py tests/test_v2_signal_market_binding_safety.py -q` -> `41 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_producer_evidence_contract.py tests/test_v2_runtime_producer_evidence_service.py tests/test_v2_runtime_producer_evidence_api.py tests/test_v2_dashboard_runtime_producer_evidence.py tests/test_v2_runtime_producer_evidence_safety.py tests/test_v2_runtime_brain_adapter_contract.py tests/test_v2_runtime_brain_adapter_service.py tests/test_v2_runtime_brain_adapter_api.py tests/test_v2_dashboard_runtime_brain.py tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_contract.py tests/test_v2_runtime_coordinator_service.py tests/test_v2_runtime_coordinator_api.py tests/test_v2_dashboard_runtime_coordinator.py tests/test_v2_runtime_coordinator_safety.py tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py tests/test_v2_dashboard_mesh.py -q` -> `52 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_contract.py tests/test_v2_link_coverage_repository.py tests/test_v2_link_coverage_api.py tests/test_v2_dashboard_link_coverage.py tests/test_v2_link_coverage_safety.py tests/test_v2_signal_quality_contract.py tests/test_v2_signal_quality_repository.py tests/test_v2_signal_quality_api.py tests/test_v2_dashboard_signal_quality.py tests/test_v2_signal_processing_state_contract.py tests/test_v2_signal_processing_state_repository.py tests/test_v2_signal_processing_state_api.py tests/test_v2_dashboard_signal_processing.py tests/test_v2_signal_quality_gate_enforcement.py tests/test_v2_lineage_coverage_contract.py tests/test_v2_lineage_coverage_repository.py tests/test_v2_lineage_coverage_api.py tests/test_v2_dashboard_lineage_coverage.py tests/test_v2_lineage_coverage_safety.py tests/test_v2_dry_run_provenance_contract.py tests/test_v2_dry_run_provenance_repository.py tests/test_v2_dry_run_provenance_api.py tests/test_v2_dashboard_dry_run_provenance.py tests/test_v2_dry_run_provenance_safety.py tests/test_v2_producer_health_contract.py tests/test_v2_producer_health_service.py tests/test_v2_producer_health_api.py tests/test_v2_dashboard_producer_health.py tests/test_v2_producer_health_safety.py -q` -> `106 passed, 1 warning`

## Runtime Verification Results

Runtime endpoints used `http://127.0.0.1:8000`.

- `GET /healthz`: HTTP `200`, `status=ok`
- `GET /runtime/health`: HTTP `200`, `overall_status=HEALTHY`
- `POST /risk/core/evaluate`: HTTP `200`, `mock_data=false`, `status=OK`
- `GET /risk/decisions/recent`: HTTP `200`, `count=50`
- `GET /dashboard/api/v2/risk-core`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/mesh-blockers`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/mesh`: HTTP `200`, `mock_data=false`, `layers.risk_core` present

Runtime evaluation:

- `thesis_profiles_checked=100`
- `risk_decisions_created=100`
- `risk_decisions_updated=0`
- `approved_count=0`
- `rejected_count=0`
- `blocked_count=100`
- `warning_count=0`
- `avg_risk_score=1.0`
- `paper_candidate_allowed_count=0`
- `risk_approved_count=0`
- `execution_allowed_count=0`
- `paper_ready_after=false`

## Safety Verification

Runtime safety counters after Risk Core evaluation:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents=absent`
- `fills_v2=1` historical row unchanged
- `positions=0`
- `coordinator_execution_allowed_true=0`
- `risk_execution_allowed_true=0`
- `risk_paper_candidate_allowed_true=0`
- `risk_approved_true=0`

No orders, order intents, fills, positions, live actions, exit plans, Paper intents, Paper candidates, or execution permissions were created.

## Blockers Resolved

- `NO_RISK_CORE`

## Blockers Remaining

- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `RISK_DECISIONS_ALL_BLOCKED`
- `RISK_CORE_MISSING_DATA`
- `THESIS_PROFILES_INCOMPLETE`
- `THESIS_PROFILES_MISSING_MARKET`
- `THESIS_PROFILES_MISSING_ORDERBOOK`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `SIGNALS_STALE_HIGH`
- dry-run/provenance blockers
- producer health blockers
- env/persisted mode mismatch
- env/persisted kill-switch mismatch
- `EXECUTION_NOT_ALLOWED`

## Remaining Risks

Risk Core is now real, but all current thesis profiles are blocked. Exit Foundation does not exist, Paper Eligibility Gate does not exist, and signal/market/linkage/lineage quality still blocks Paper evidence.

## Next Recommended Phase

V2 Neural Mesh Part 4C-Q: Exit Foundation.

## Final Status

GREEN

## Can Continue to Next Phase

YES
