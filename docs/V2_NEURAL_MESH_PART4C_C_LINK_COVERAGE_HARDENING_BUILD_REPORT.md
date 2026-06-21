# V2 Neural Mesh Part 4C-C Link Coverage Hardening Build Report

## 1. Purpose

Implemented Link Coverage Hardening to analyze why Signals are linked or unlinked and to store evidence-only suggested market links separately from actual market links.

This phase is non-executing and does not force-link Signals.

## 2. Current Reality Found

Before implementation:

- `neuron_signals=139`
- `signal_quality_evaluations=100`
- `signal_processing_states=100`
- `unlinked_signals=119`
- `signal_market_links=20`
- `signal_position_links=0`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `execution_allowed_true=0`
- persisted runtime state: `DATA_ONLY`
- env `POLYBOT_RUNTIME_MODE=PAPER`
- env `LIVE_TRADING_ENABLED=false`
- env `LIVE_KILL_SWITCH=true`
- persisted `kill_switch_active=false`

The env/persisted mismatches remain tracked and were not fixed.

## 3. Files Created

- `app/db/migrations/0070_v2_neural_mesh_link_coverage_hardening.sql`
- `app/neural_mesh/link_coverage.py`
- `app/repositories/link_coverage_repository.py`
- `app/services/link_coverage.py`
- `app/api/link_coverage_routes.py`
- `tests/test_v2_link_coverage_contract.py`
- `tests/test_v2_link_coverage_repository.py`
- `tests/test_v2_link_coverage_api.py`
- `tests/test_v2_dashboard_link_coverage.py`
- `tests/test_v2_link_coverage_safety.py`
- `docs/V2_NEURAL_MESH_PART4C_C_LINK_COVERAGE_HARDENING.md`
- `docs/V2_NEURAL_MESH_PART4C_C_LINK_COVERAGE_HARDENING_BUILD_REPORT.md`

## 4. Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/services/mesh_dashboard.py`

## 5. DB Migration

Migration applied:

- `0070_v2_neural_mesh_link_coverage_hardening.sql`

Tables created:

- `signal_link_coverage_analysis`
- `signal_suggested_market_links`
- `signal_link_coverage_runs`

## 6. API Routes

New routes:

- `GET /signals/link-coverage/recent`
- `GET /signals/{signal_id}/link-coverage`
- `POST /signals/link-coverage/analyze/recent`
- `POST /signals/{signal_id}/link-coverage/analyze`
- `GET /dashboard/api/v2/link-coverage`

## 7. Dashboard Changes

Added:

- `/dashboard/api/v2/link-coverage`
- `layers.link_coverage` in `/dashboard/api/v2/mesh`
- `flow.link_coverage` in `/dashboard/api/v2/mesh`
- link coverage readiness blockers

## 8. Link Coverage Contract Summary

Allowed `linkability_status`:

- `LINKED`
- `LINKABLE`
- `NOT_LINKABLE`
- `NEEDS_MORE_EVIDENCE`
- `STALE`
- `DRY_RUN_ONLY`
- `ERROR`

Allowed `suggested_link_action`:

- `NONE`
- `REVIEW_ONLY`
- `SAFE_TO_LINK_EXISTING_MARKET_ID`
- `BLOCKED_WEAK_EVIDENCE`
- `BLOCKED_DRY_RUN_ONLY`
- `BLOCKED_STALE`
- `BLOCKED_MISSING_MARKET`
- `BLOCKED_MISSING_ENTITY`
- `BLOCKED_MISSING_SOURCE`
- `BLOCKED_NO_MATCHER`

## 9. Unlinked Reason Classifier Summary

Implemented deterministic reasons:

- `MISSING_MARKET_ID`
- `MISSING_ENTITY`
- `MISSING_SOURCE`
- `MISSING_RULES_CONTEXT`
- `MISSING_PRODUCER`
- `MISSING_RAW_PAYLOAD_REF`
- `NO_MATCHER_AVAILABLE`
- `WEAK_MATCHER_EVIDENCE`
- `DRY_RUN_ONLY`
- `STALE_SIGNAL`
- `ALREADY_LINKED`
- `POSITION_LINK_MISSING`
- `UNKNOWN`

## 10. Suggested Market Links Summary

Suggested links are stored in `signal_suggested_market_links`.

Runtime analysis defaulted to:

- `create_suggestions=true`
- `apply_safe_links=false`

No actual links were applied during runtime verification.

Safe apply exists only inside service logic for explicit existing `market_id` links and requires `apply_safe_links=true`. It rejects stale, dry-run, weak, or missing-evidence suggestions.

## 11. Analysis Result

Runtime command:

`POST /signals/link-coverage/analyze/recent {"limit":100,"create_suggestions":true,"apply_safe_links":false}`

Result:

- `status=OK`
- `mock_data=false`
- `analyzed=100`
- `created_or_updated=100`
- `applied_links=0`
- `total_signals=139`
- `linked_signals=20`
- `unlinked_signals=80`
- `linkable_signals=0`
- `non_linkable_signals=12`
- `needs_more_evidence=0`
- `stale_unlinked=68`
- `dry_run_only_unlinked=0`
- `suggested_market_links_count=0`
- `safe_to_link_count=0`
- `applied_suggestions_count=0`
- `paper_ready=false`

Unlinked reasons:

- `STALE_SIGNAL=68`
- `ALREADY_LINKED=20`
- `MISSING_ENTITY=12`

## 12. Tests Added

- `tests/test_v2_link_coverage_contract.py`
- `tests/test_v2_link_coverage_repository.py`
- `tests/test_v2_link_coverage_api.py`
- `tests/test_v2_dashboard_link_coverage.py`
- `tests/test_v2_link_coverage_safety.py`

## 13. Tests Run and Exact Results

Config and migrations:

- `docker compose config --quiet` -> passed
- `docker compose --profile test config --quiet` -> passed
- `docker compose --profile test build migrate test_migrate test api` -> passed
- `docker compose run --rm migrate` -> applied `0070_v2_neural_mesh_link_coverage_hardening.sql`
- `docker compose --profile test run --rm test_migrate` -> applied `0070_v2_neural_mesh_link_coverage_hardening.sql`

Targeted tests:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_contract.py -q` -> `7 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_repository.py -q` -> `4 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_api.py -q` -> `3 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_link_coverage.py -q` -> `2 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_link_coverage_safety.py -q` -> `3 passed`

Regressions:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_quality_contract.py tests/test_v2_signal_quality_repository.py tests/test_v2_signal_quality_api.py tests/test_v2_dashboard_signal_quality.py -q` -> `18 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_processing_state_contract.py tests/test_v2_signal_processing_state_repository.py tests/test_v2_signal_processing_state_api.py tests/test_v2_dashboard_signal_processing.py tests/test_v2_signal_quality_gate_enforcement.py -q` -> `19 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_signal_event_binding_contract.py tests/test_v2_dashboard_signal_lineage.py -q` -> `6 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_neuron_signal_contract.py tests/test_v2_dashboard_signals.py -q` -> `11 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_dashboard_mesh.py -q` -> `5 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_mesh_dry_run_contract.py tests/test_v2_mesh_dry_run_flow.py tests/test_v2_dashboard_mesh_dry_run.py -q` -> `6 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_output_contract.py tests/test_v2_dashboard_brain_outputs.py -q` -> `19 passed`
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_brain_coordinator_contract.py tests/test_v2_dashboard_coordinator.py -q` -> `11 passed`

## 14. Runtime Verification Results

After restarting API:

- `GET /healthz` -> `status=ok`
- `GET /runtime/health` -> `overall_status=HEALTHY`
- `POST /signals/link-coverage/analyze/recent` -> `status=OK`, `mock_data=false`, `analyzed=100`, `applied_links=0`
- `GET /signals/link-coverage/recent` -> `count=50`
- `GET /dashboard/api/v2/link-coverage` -> `status=DEGRADED`, `mock_data=false`
- `GET /dashboard/api/v2/signal-quality` -> `mock_data=false`
- `GET /dashboard/api/v2/signal-processing` -> `mock_data=false`
- `GET /dashboard/api/v2/mesh` -> `status=DEGRADED`, `mock_data=false`, `paper_ready=false`

## 15. Safety Verification

Env:

- `MODE= PAPER`
- `BACKEND= paper`
- `LIVE= false`
- `KILL= true`

Persisted:

- `current_mode=DATA_ONLY`
- `kill_switch_active=false`
- `can_open_paper_positions=false`
- `can_create_shadow_orders=false`
- `can_create_live_orders=false`

DB safety:

- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `order_intents` table absent
- `execution_allowed_true=0`
- `signal_market_links=20`
- `suggestions=0`
- `applied_suggestions=0`

No order, cancel, signing, live, private key, execution, Risk, or State Governor path was touched.

## 16. What Is Complete

- Link Coverage Contract exists.
- Link Coverage analysis persists.
- Suggested links persist separately from actual links.
- Default runtime analysis does not apply links.
- Safe apply path is strict and opt-in.
- Dashboard link coverage truth works.
- Mesh dashboard includes link coverage layer and blockers.
- Targeted tests pass.
- Required regressions pass.
- Runtime is healthy.
- Safety is intact.

## 17. What Is Partial

- Only latest 100 Signals were analyzed during runtime verification.
- No local evidence produced safe suggestions in current runtime data.
- Most latest unlinked Signals are stale or missing entity context.
- Link coverage analysis is still on-demand.

## 18. Remaining Risks

- Env/persisted mode mismatch remains tracked: env `PAPER`, persisted `DATA_ONLY`.
- Env/persisted kill mismatch remains tracked: env kill true, persisted kill false.
- Link coverage remains low because stale Signals dominate the latest analyzed set.
- No Paper evidence can be produced from dry-run, stale, or weak links.

## 19. Next Recommended Phase

`V2 Neural Mesh Part 4C-D: Signal Freshness Recovery + Re-Evaluation Hooks`

Definition of done:

- New Signals trigger safe quality/processing/link coverage evaluation.
- Freshness state is explicit and dashboard-visible.
- Stale Signal blockage is reduced or explained.
- No Paper/Live/order/order-intent behavior is introduced.

## 20. Final Status

GREEN
