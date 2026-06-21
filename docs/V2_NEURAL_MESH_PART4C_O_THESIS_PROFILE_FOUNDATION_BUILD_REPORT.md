# V2 Neural Mesh Part 4C-O Thesis Profile Foundation Build Report

## Purpose

Create a runtime Thesis Profile layer so future Paper candidates require an auditable thesis before any Paper eligibility can exist. This phase stores why-now, evidence, missing evidence, invalidation rules, and risk notes, while keeping Paper and execution disabled.

## Current Reality Found

- `thesis_profiles=0` before build
- `position_thesis_profiles=0`
- `coordinator_decisions=112`
- runtime Coordinator Decisions from `runtime_coordinator_adapter=100`
- runtime Coordinator Decisions with `market_id=76`
- runtime Coordinator Decision states: `NO_TRADE=100`
- `orderbook_snapshots=22`
- `signal_market_links=20`
- `brain_outputs=148`
- `paper_ready=false`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents=absent`
- `positions=0`
- `fills_v2=1` historical row unchanged
- `execution_allowed_true=0`

## Audit Findings

The existing `position_thesis_profiles` table is position-oriented and requires `market_id`, so it cannot safely store incomplete runtime thesis records with missing market evidence. A new `thesis_profiles` table was required for 4C-O runtime Coordinator-derived thesis truth.

Runtime Coordinator Decisions already contain enough provenance to build blocked/incomplete thesis profiles:

- `generated_by=runtime`
- `producer_name=runtime_coordinator_adapter`
- source Brain Output IDs
- source Signal IDs where available
- blockers/missing requirements
- `execution_allowed=false`

Current runtime Coordinator Decisions are all `NO_TRADE`, so the correct output is blocked thesis truth, not complete Paper-candidate thesis truth.

## Files Created

- `app/db/migrations/0080_v2_neural_mesh_thesis_profile_foundation.sql`
- `app/neural_mesh/thesis_profiles.py`
- `app/repositories/thesis_profile_repository.py`
- `app/services/thesis_profiles.py`
- `tests/test_v2_thesis_profile_contract.py`
- `tests/test_v2_thesis_profile_repository.py`
- `tests/test_v2_thesis_profile_service.py`
- `tests/test_v2_thesis_profile_api.py`
- `tests/test_v2_dashboard_thesis_profile_foundation.py`
- `tests/test_v2_thesis_profile_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_O_THESIS_PROFILE_FOUNDATION.md`
- `docs/V2_NEURAL_MESH_PART4C_O_THESIS_PROFILE_FOUNDATION_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/mesh_dashboard.py`
- `app/services/mesh_blockers.py`
- `tests/test_v2_dashboard_thesis.py`

## DB Migrations

- `0080_v2_neural_mesh_thesis_profile_foundation.sql`

Created:

- `thesis_profiles`
- `thesis_profile_runs`
- `thesis_profile_evidence_items`

No order, intent, fill, position, risk, exit, or execution tables were changed.

## API Routes

- `POST /thesis/profiles/build`
- `GET /thesis/profiles/recent`
- `GET /dashboard/api/v2/thesis`

## Dashboard Changes

- `/dashboard/api/v2/thesis` now returns runtime thesis profile truth.
- `/dashboard/api/v2/mesh` includes `layers.thesis_profiles`.
- Mesh `flow` includes `thesis_profiles`.
- Mesh readiness includes `thesis_summary`.
- Mesh blockers now use runtime thesis truth for `NO_THESIS_PROFILES`.

## Thesis Profile Contract

The contract requires deterministic runtime Coordinator evidence and stores:

- `market_id`
- `side`
- `status`
- `thesis_type`
- `why_now`
- `expected_move`
- `confidence`
- `evidence`
- `missing_evidence`
- `invalidation_rules`
- `risk_notes`
- source Coordinator, Brain, and Signal IDs
- optional fresh orderbook snapshot ID

`paper_candidate_allowed=false`, `risk_required=true`, and `exit_required=true` are enforced.

## Evidence Rules

Complete thesis requires runtime Coordinator evidence, non-dry-run provenance, market ID, source trace, fresh orderbook, and signal-market binding. Missing evidence produces `INCOMPLETE`, `BLOCKED`, or `WEAK`, never Paper-ready. `NO_TRADE` produces `BLOCKED_NO_TRADE_THESIS`.

## Coordinator Decisions Checked

Runtime verification checked `100` runtime Coordinator Decisions.

## Thesis Profiles Before / After

- before: `0`
- after: `100`

## Complete / Incomplete / Blocked / Weak Split

Runtime verification:

- complete: `0`
- incomplete: `0`
- blocked: `100`
- weak: `0`

## Missing Evidence Summary

Runtime verification:

- `missing_market_count=24`
- `missing_orderbook_count=76`
- `missing_binding_count=80`
- `missing_evidence_count=260`

## Invalidation Rules Summary

Every profile carries deterministic invalidation rules, including stale orderbook, missing signal-market binding, and superseded runtime Coordinator Decision checks. `NO_TRADE` profiles also include a no-trade coordinator-state invalidation/blocking rule.

## Risk Notes Summary

Every profile includes:

- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `paper_candidate_allowed=false_until_paper_eligibility_gate`

Profiles missing fresh orderbook or binding include the corresponding risk note.

## Mesh Blockers Before / After

Resolved:

- `NO_THESIS_PROFILES`

Still active after runtime verification:

- `THESIS_PROFILES_INCOMPLETE`
- `THESIS_PROFILES_MISSING_MARKET`
- `THESIS_PROFILES_MISSING_ORDERBOOK`
- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `SIGNALS_STALE_HIGH`
- `EXECUTION_NOT_ALLOWED`
- env/persisted mismatch blockers
- producer/dry-run blockers
- orderbook freshness blockers in the current restarted runtime

## Tests Added

Focused tests cover contract validation, repository persistence, service derivation, dry-run ignore behavior, missing market/orderbook/binding, NO_TRADE blocked thesis, API/dashboard truth, mesh layer presence, and safety counters.

## Tests Run and Exact Results

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_thesis_profile_contract.py tests/test_v2_thesis_profile_repository.py tests/test_v2_thesis_profile_service.py tests/test_v2_thesis_profile_api.py tests/test_v2_dashboard_thesis.py tests/test_v2_dashboard_thesis_profile_foundation.py tests/test_v2_thesis_profile_safety.py -q` -> `15 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py -q` -> `46 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_orderbook_snapshot_contract.py tests/test_v2_orderbook_snapshot_repository.py tests/test_v2_orderbook_snapshot_service.py tests/test_v2_orderbook_snapshot_api.py tests/test_v2_dashboard_orderbook.py tests/test_v2_orderbook_snapshot_safety.py tests/test_v2_signal_market_binding_contract.py tests/test_v2_signal_market_binding_repository.py tests/test_v2_signal_market_binding_service.py tests/test_v2_signal_market_binding_api.py tests/test_v2_dashboard_market_binding.py tests/test_v2_signal_market_binding_safety.py -q` -> `26 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_producer_evidence_contract.py tests/test_v2_runtime_producer_evidence_service.py tests/test_v2_runtime_producer_evidence_api.py tests/test_v2_dashboard_runtime_producer_evidence.py tests/test_v2_runtime_producer_evidence_safety.py tests/test_v2_runtime_brain_adapter_contract.py tests/test_v2_runtime_brain_adapter_service.py tests/test_v2_runtime_brain_adapter_api.py tests/test_v2_dashboard_runtime_brain.py tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_contract.py tests/test_v2_runtime_coordinator_service.py tests/test_v2_runtime_coordinator_api.py tests/test_v2_dashboard_runtime_coordinator.py tests/test_v2_runtime_coordinator_safety.py -q` -> `35 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_contract.py tests/test_v2_link_coverage_repository.py tests/test_v2_link_coverage_api.py tests/test_v2_dashboard_link_coverage.py tests/test_v2_link_coverage_safety.py tests/test_v2_signal_quality_contract.py tests/test_v2_signal_quality_repository.py tests/test_v2_signal_quality_api.py tests/test_v2_dashboard_signal_quality.py tests/test_v2_signal_processing_state_contract.py tests/test_v2_signal_processing_state_repository.py tests/test_v2_signal_processing_state_api.py tests/test_v2_dashboard_signal_processing.py tests/test_v2_signal_quality_gate_enforcement.py -q` -> `56 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_lineage_coverage_contract.py tests/test_v2_lineage_coverage_repository.py tests/test_v2_lineage_coverage_api.py tests/test_v2_dashboard_lineage_coverage.py tests/test_v2_lineage_coverage_safety.py tests/test_v2_dry_run_provenance_contract.py tests/test_v2_dry_run_provenance_repository.py tests/test_v2_dry_run_provenance_api.py tests/test_v2_dashboard_dry_run_provenance.py tests/test_v2_dry_run_provenance_safety.py tests/test_v2_producer_health_contract.py tests/test_v2_producer_health_service.py tests/test_v2_producer_health_api.py tests/test_v2_dashboard_producer_health.py tests/test_v2_producer_health_safety.py -q` -> `50 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py tests/test_v2_dashboard_mesh.py tests/test_v2_position_thesis_api.py tests/test_v2_position_thesis_contract.py tests/test_v2_position_thesis_repository.py -q` -> `35 passed, 1 warning`

Host Python did not have pytest available earlier in this workspace, so Docker test profile was used.

## Runtime Verification Results

Runtime endpoints used `http://127.0.0.1:8000`.

- `GET /healthz`: HTTP `200`
- `GET /runtime/health`: HTTP `200`, `overall_status=HEALTHY`
- `POST /thesis/profiles/build`: HTTP `200`, `mock_data=false`, `status=OK`
- `GET /thesis/profiles/recent`: HTTP `200`, count `50` returned by default limit
- `GET /dashboard/api/v2/thesis`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/mesh-blockers`: HTTP `200`, `mock_data=false`
- `GET /dashboard/api/v2/mesh`: HTTP `200`, `mock_data=false`, `layers.thesis_profiles` present

Runtime build result:

- `coordinator_decisions_checked=100`
- `eligible_decisions=100`
- `thesis_profiles_created=100`
- `thesis_profiles_updated=0`
- `complete_thesis_count=0`
- `incomplete_thesis_count=0`
- `blocked_thesis_count=100`
- `weak_thesis_count=0`
- `missing_market_count=24`
- `missing_orderbook_count=76`
- `missing_binding_count=80`
- `paper_candidate_allowed_count=0`
- `paper_ready_after=false`
- `orders_created=0`
- `order_intents_created=0`
- `fills_created=0`
- `positions_created=0`
- `live_actions_created=0`

Safety counters:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents=absent`
- `fills_v2=1` historical row unchanged
- `positions=0`
- `execution_allowed_true=0`

## Safety Verification

No orders, order intents, fills, positions, live actions, risk approvals, exit plans, Paper intents, Paper eligibility candidates, or Paper readiness flips were created. Thesis profiles are explanatory records only.

## Blockers Resolved

- `NO_THESIS_PROFILES`

## Blockers Remaining

- `THESIS_PROFILES_INCOMPLETE`
- `THESIS_PROFILES_MISSING_MARKET`
- `THESIS_PROFILES_MISSING_ORDERBOOK`
- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `SIGNALS_STALE_HIGH`
- `EXECUTION_NOT_ALLOWED`
- env/persisted mode and kill-switch mismatches
- producer/dry-run blockers
- current orderbook freshness blockers after runtime restart

## Remaining Risks

The thesis layer is live, but current profiles are blocked because runtime Coordinator truth is `NO_TRADE` and many profiles lack market, fresh orderbook, and binding evidence. Risk Core and Exit Foundation remain mandatory before Paper eligibility.

## Next Recommended Phase

V2 Neural Mesh Part 4C-P: Risk Core Foundation, or a focused freshness/binding recovery pass if the operator wants more complete thesis profiles before Risk Core.

## Final Status

GREEN: implementation complete, runtime thesis profiles exist, tests pass, runtime verification completed, safety intact, `paper_ready=false`, and no executable artifacts were created.
