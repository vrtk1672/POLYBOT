# V2 Neural Mesh Part 4C-H: Tests + Regression Hardening

Date: 2026-05-28
Status: GREEN

## Purpose

Part 4C-H adds a consolidated regression suite that validates the full 4C safety and truth chain.

These tests prove that the 4C Mesh Hardening layers (Signal Quality, Signal Processing, Link Coverage, Lineage Coverage, Dry Run Provenance, Mesh Blockers, Producer Health) remain correct and safe with respect to:

- quality score correctness and determinism
- market-link and lineage requirements for Paper readiness
- dry-run separation from production evidence
- unlinked reason persistence
- paper_ready=False enforcement
- no order creation across all 4C services
- no order intents creation
- no live/shadow/paper execution activation
- dashboard truth accuracy and blocker transparency

## Test Files Added

### tests/test_v2_4c_regression_safety.py (9 tests)

Consolidated safety regression. Proves that running every 4C service layer does not:
- create paper/shadow/live orders (tests 29-31)
- create order_intents (test 32)
- flip paper_ready to True (test 28)
- produce execution_allowed=True in coordinator decisions (test 33)
- activate any execution path (test 34)
- return mock_data=True from any 4C service (test 36 mirror)

Also includes pure-Python contract-level safety proofs that MeshBlockerReport and ProducerHealthSummary cannot have paper_ready=True, and that the signal quality evaluator produces valid output without touching DB.

### tests/test_v2_4c_mesh_truth_regression.py (26 tests)

Pure-Python truth chain regression across all 4C domains:

**Signal Quality (tests 1-4):**
- quality_score is deterministic across identical inputs
- full-metadata signal has GOOD status with score ≥ 0.8
- stale signal blocks both brain and Paper feeding
- missing source + lineage + market reduces score below 0.6

**Market/Link readiness (tests 5-8):**
- no market_id → can_feed_paper=False, market_id in missing_fields
- no market link → quality_status=UNLINKED, can_feed_paper=False
- dry-run signals produce BLOCKED suggested_link_action (not applied links)
- unlinked_reason is always a named, valid classifier value

**Lineage (tests 9-12):**
- missing producer → MISSING_PRODUCER reason, can_feed_paper_by_lineage=False
- missing correlation_id → MISSING_CORRELATION_ID in missing_lineage_fields
- dry-run lineage → lineage_status=DRY_RUN_ONLY, can_feed_paper_by_lineage=False
- runtime lineage → lineage_trust_score ≥ 0.85, does not flip global paper_ready

**Dry Run Provenance (tests 13-17):**
- Brain Output with generated_by=mesh_dry_run → DRY_RUN_ONLY, blocked from Paper
- Coordinator Decision with dry_run_id → DRY_RUN_ONLY, blocked from Paper
- all object types with dry_run provenance → can_feed_paper_by_provenance=False
- unknown provenance → UNKNOWN, blocked from Paper (conservative)
- explicit dry_run → provenance_confidence ≥ 0.9

**Mesh Blockers (tests 18-22):**
- CRITICAL active blockers → paper_ready=False, overall_status=BLOCKED
- BRAIN_OUTPUTS_DRY_RUN_ONLY and COORDINATOR_DECISIONS_DRY_RUN_ONLY both in blocked_by
- every active blocker has non-empty evidence
- LIVE_DISABLED has severity=INFO, blocks_paper=False

**Producer Health (tests 23-27):**
- dry-run-only producer → health_status=DRY_RUN_ONLY, runtime_active=False
- silent expected producer → health_status=SILENT, silent_expected=True
- degraded producer → health_status=DEGRADED, can_feed_paper=False
- producer health never flips paper_ready=True for any status
- runtime_active_producers count matches actual runtime_active producers

### tests/test_v2_4c_dashboard_readiness_regression.py (11 tests)

Dashboard truth regression using FastAPI TestClient:

**Layer presence (test 35):**
- /dashboard/api/v2/mesh contains all 7 required 4C layers
- /dashboard/api/v2/mesh contains all 6 required core layers
- every layer in the mesh dashboard returns mock_data=False

**Endpoint truth (test 36):**
- all 8 4C dashboard endpoints return mock_data=False
- all 4C dashboard endpoints with paper_ready field return paper_ready=False

**Blocker visibility (test 37):**
- readiness.blocked_by is non-empty when paper_ready=False
- /dashboard/api/v2/mesh-blockers shows active blockers, overall_status not READY

**Status honesty (test 38):**
- overall_status is not READY when blocked_by is non-empty
- /dashboard/api/v2/mesh-blockers overall_status not READY with active blockers
- /dashboard/api/v2/dry-run-provenance exposes dry-run truth fields

**Cross-layer safety:**
- calling all 8 4C dashboard endpoints does not create any orders

## How to Run the 4C Regression Suite

### Targeted: new 4C regression files only

```
docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py -v
```

### By domain group

Signal Quality + Processing:
```
docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_contract.py tests/test_v2_signal_quality_repository.py tests/test_v2_signal_quality_api.py tests/test_v2_signal_quality_gate_enforcement.py tests/test_v2_signal_processing_state_contract.py tests/test_v2_signal_processing_state_repository.py tests/test_v2_signal_processing_state_api.py tests/test_v2_dashboard_signal_quality.py tests/test_v2_dashboard_signal_processing.py -q
```

Link Coverage + Lineage:
```
docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_contract.py tests/test_v2_link_coverage_repository.py tests/test_v2_link_coverage_api.py tests/test_v2_dashboard_link_coverage.py tests/test_v2_link_coverage_safety.py tests/test_v2_lineage_coverage_contract.py tests/test_v2_lineage_coverage_repository.py tests/test_v2_lineage_coverage_api.py tests/test_v2_dashboard_lineage_coverage.py tests/test_v2_lineage_coverage_safety.py -q
```

Dry Run Provenance + Mesh Blockers:
```
docker compose --profile test run --rm test python -m pytest tests/test_v2_dry_run_provenance_contract.py tests/test_v2_dry_run_provenance_repository.py tests/test_v2_dry_run_provenance_api.py tests/test_v2_dashboard_dry_run_provenance.py tests/test_v2_dry_run_provenance_safety.py tests/test_v2_mesh_blockers_contract.py tests/test_v2_mesh_blockers_service.py tests/test_v2_mesh_blockers_api.py tests/test_v2_dashboard_mesh_blockers.py tests/test_v2_mesh_blockers_safety.py -q
```

Producer Health + Mesh Dashboard + Brain + Coordinator + Dry Run Flow:
```
docker compose --profile test run --rm test python -m pytest tests/test_v2_producer_health_contract.py tests/test_v2_producer_health_service.py tests/test_v2_producer_health_api.py tests/test_v2_dashboard_producer_health.py tests/test_v2_producer_health_safety.py tests/test_v2_dashboard_mesh.py tests/test_v2_brain_output_contract.py tests/test_v2_dashboard_brain_outputs.py tests/test_v2_brain_coordinator_contract.py tests/test_v2_dashboard_coordinator.py tests/test_v2_mesh_dry_run_contract.py tests/test_v2_mesh_dry_run_flow.py tests/test_v2_dashboard_mesh_dry_run.py -q
```

## Scope

This phase is tests and documentation only.

No app/ source code was modified.
No DB migrations were applied.
No runtime behavior was changed.
No orders were created.
No Paper was enabled.
No AI was called.
