# Pre-Paper Final Hardening Bundle Report

## 1. Purpose

Implement the Phase 9C-B through 9G pre-paper hardening bundle without activating Paper Simulation or creating paper/live/shadow artifacts.

The bundle prepares Phase 10 Controlled Paper Certification by exposing:

- candidate-scoped event truth
- coordinator-to-paper actionability mapping
- pre-paper safety invariants
- unified blocker shape
- paper certification run plan

## 2. Current Reality Found

The active system already had DATA_ONLY supervisor life, candidate producer freshness, orderbook refresh, all-five event-native mesh opinions, mesh evidence bundles, and candidate/event correlation visibility.

The remaining active runtime truth was:

- latest orderbook events are still market-level only
- candidate-scoped events: 0
- paper actionability: 0 actionable candidates
- Paper Simulation: OFF
- paper readiness: BLOCKED
- historical paper artifacts exist, but no new forbidden artifacts were created by this bundle

## 3. Sub-Phase 9C-B Result

Candidate-targeted refresh now carries candidate metadata into normalized orderbook snapshot metadata when a candidate-specific refresh path is used.

The orderbook event producer now preserves candidate metadata from snapshot metadata into `orderbook.snapshot.created` payloads. The new Candidate-Scoped Events API classifies events as:

- `CANDIDATE_EVENT_SCOPED`
- `MARKET_EVENT_ONLY`
- `UNLINKED_WITH_REASON`
- `AMBIGUOUS_CANDIDATE_EVENT`
- `TOKEN_SIDE_MISMATCH`
- `UNKNOWN`

Controlled smoke result: candidate-scoped events remained `0`; the endpoint returned explicit `NO_CANDIDATE_SCOPED_EVENT` instead of fake actionability.

## 4. Sub-Phase 9D Result

Added a read-only coordinator-to-paper actionability contract.

Canonical states include:

- `ACTIONABLE_SMALL_PAPER`
- `WATCH_FOR_CONFIRMATION`
- `WAITING_FOR_PRICE_REFRESH`
- `WAITING_FOR_LIFECYCLE`
- `WAITING_FOR_CAPITAL`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_EXIT`
- `BLOCKED_BY_CAPITAL`
- `BLOCKED_BY_LIFECYCLE`
- `BLOCKED_BY_DATA`
- `BLOCKED_BY_GOVERNOR`
- `BLOCKED_BY_RUNTIME`
- `BLOCKED_BY_PAPER_SIMULATION`
- `NO_TRADE`
- `UNKNOWN`

The endpoint never creates intents or orders and always keeps `execution_allowed=false`.

Controlled smoke result: `ACTIONABLE_SMALL_PAPER=0`, `BLOCKED_BY_LIFECYCLE=50`, with market-scoped and missing candidate-event blockers visible.

## 5. Sub-Phase 9E Result

Added `/dashboard/api/v2/control/pre-paper-safety`.

The endpoint answers whether Controlled Paper Certification can safely start later. It checks live/shadow disabled, Paper Simulation OFF, runtime/supervisor truth, candidate scoped events, paper actionability, duplicate intent risk, open paper position conflict, and blocker shape availability.

Current active result: `PRE_PAPER_NOT_READY`.

Primary blockers:

- `PAPER_SIMULATION_OFF`
- `NO_CANDIDATE_SCOPED_EVENT`
- `NO_PAPER_ACTIONABILITY`
- `DUPLICATE_ACTIVE_INTENT_RISK`
- `OPEN_PAPER_POSITION_CONFLICT`

## 6. Sub-Phase 9F Result

Added a shared unified blocker helper and integrated it into new and existing read-only surfaces.

Unified blocker fields include:

- `blocker_code`
- `severity`
- `source`
- `candidate_id`
- `event_id`
- `correlation_id`
- `market_id`
- `side`
- `token_id`
- `required_to_pass`
- `is_refreshable`
- `is_operator_action_required`
- `created_at`

Existing historical rows were not rewritten.

## 7. Sub-Phase 9G Result

Added `/dashboard/api/v2/control/paper-certification-plan`.

The plan defines the dry Phase 10 contract:

- duration and cycle targets
- allowed and forbidden actions
- pre-checks
- start and stop conditions
- before/after counts
- expected and forbidden artifacts
- GREEN/YELLOW/RED criteria
- cleanup and abort rules

The endpoint does not activate paper.

## 8. Files Inspected

- `app/control_center/candidate_event_correlation.py`
- `app/control_center/event_mesh_proof.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/candidate_price_path.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/candidate_producer_freshness.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/repositories/orderbook_snapshot_repository.py`
- `app/services/trusted_orderbook.py`
- `app/services/paper_intents.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_dashboard_truth.py`
- `app/services/paper_capital.py`
- `app/runtime/state_governor.py`
- `app/control_center/runtime_supervisor.py`
- `app/api/routes.py`
- frontend Control Center API/query/page files
- Phase 8, 9, 9B, and 9C reports

## 9. Files Changed

Created:

- `app/control_center/unified_blockers.py`
- `app/control_center/candidate_scoped_events.py`
- `app/control_center/paper_actionability.py`
- `app/control_center/pre_paper_safety.py`
- `app/control_center/paper_certification_plan.py`
- `tests/test_candidate_scoped_event_production.py`
- `tests/test_paper_actionability_contract.py`
- `tests/test_pre_paper_safety_invariants.py`
- `tests/test_unified_blocker_shape.py`
- `tests/test_paper_certification_plan.py`
- `docs/PRE_PAPER_FINAL_HARDENING_BUNDLE_REPORT.md`

Updated:

- `app/data_foundation/orderbook_snapshotter.py`
- `app/services/trusted_orderbook.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/control_center/candidate_event_correlation.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`

## 10. APIs Added/Changed

Added:

- `GET /dashboard/api/v2/control/candidate-scoped-events`
- `GET /dashboard/api/v2/control/paper-actionability`
- `GET /dashboard/api/v2/control/pre-paper-safety`
- `GET /dashboard/api/v2/control/paper-certification-plan`

Extended:

- candidate-event correlation unified blockers
- mesh evidence bundle candidate link blockers
- candidate explanations unified blockers
- eligible-intent bridge unified blockers
- paper readiness unified blockers

## 11. Frontend Changes

Control Center now has read-only panels for:

- Candidate-Scoped Events
- Paper Actionability
- Pre-Paper Safety
- Unified Blockers
- Paper Certification Plan

No Paper ON action was added.

## 12. Tests Added

- candidate-scoped event production tests
- paper actionability contract tests
- pre-paper safety invariant tests
- unified blocker shape tests
- paper certification plan tests

## 13. Tests Run And Exact Results

New bundle tests:

```text
.venv\Scripts\python.exe -m pytest tests/test_candidate_scoped_event_production.py tests/test_paper_actionability_contract.py tests/test_pre_paper_safety_invariants.py tests/test_unified_blocker_shape.py tests/test_paper_certification_plan.py -q
12 passed in 2.15s
```

Related backend tests:

```text
.venv\Scripts\python.exe -m pytest tests/test_candidate_event_correlation.py tests/test_lifecycle_capital_event_native_opinions.py tests/test_mesh_evidence_bundle.py tests/test_event_mesh_proof.py tests/test_candidate_price_path.py tests/test_eligible_intent_bridge.py tests/test_paper_readiness.py tests/test_control_center_read_only_apis.py -q
8 passed, 55 skipped in 5.76s
```

Broad related slice:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "paper_actionability or pre_paper or candidate_scoped or blocker or certification or mesh or event"
79 passed, 223 skipped, 1658 deselected in 6.10s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

Frontend:

```text
npm run typecheck
passed

npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts
3 passed, 18 tests passed

npm run build
passed
```

Focused post-fix safety rerun:

```text
.venv\Scripts\python.exe -m pytest tests/test_pre_paper_safety_invariants.py -q
2 passed in 1.63s
```

## 14. Deployment/Restart Results

Port 8000 owner: Docker container `polybot_api`.

Deployment action:

```text
docker compose build api
docker compose up -d --no-deps api
```

No DB deletion, volume reset, or migrations were run.

## 15. Controlled SYSTEM ON Smoke Procedure

Before:

- captured DB counts
- captured active GET endpoint state

Action:

- `POST /dashboard/api/v2/control/actions/system-on`
- waited 45 seconds
- did not enable Paper Simulation
- did not start Full Monitor Run

During:

- polled candidate-scoped-events
- polled paper-actionability
- polled pre-paper-safety
- polled mesh-evidence-bundles
- polled candidate-event-correlation
- polled paper-readiness

Cleanup:

- `POST /dashboard/api/v2/control/actions/system-off`
- verified runtime health returned blocked/stopped truth

## 16. Before/After Counts

Before:

```json
{"brain_outputs":21212,"coordinator_decisions":20712,"event_log":551745,"live_orders":0,"mesh_sessions":192,"orderbook_snapshots":51076,"paper_eligibility_candidates":20252,"paper_fills":9,"paper_intents":20,"paper_orders":12,"paper_positions":12,"positions":0}
```

During:

```json
{"brain_outputs":21362,"coordinator_decisions":20750,"event_log":551818,"live_orders":0,"mesh_sessions":192,"orderbook_snapshots":51104,"paper_eligibility_candidates":20252,"paper_fills":9,"paper_intents":20,"paper_orders":12,"paper_positions":12,"positions":0}
```

After SYSTEM OFF:

```json
{"brain_outputs":21362,"coordinator_decisions":20750,"event_log":551819,"live_orders":0,"mesh_sessions":192,"orderbook_snapshots":51104,"paper_eligibility_candidates":20252,"paper_fills":9,"paper_intents":20,"paper_orders":12,"paper_positions":12,"positions":0}
```

Only DATA_ONLY event/orderbook/brain/coordinator activity increased.

## 17. Candidate-Scoped Event Results

During smoke:

```json
{"events_checked":50,"candidate_event_scoped":0,"market_event_only":44,"unlinked_with_reason":0,"ambiguous_candidate_event":0,"token_side_mismatch":6}
```

After cleanup:

```json
{"events_checked":50,"candidate_event_scoped":0,"market_event_only":45,"unlinked_with_reason":0,"ambiguous_candidate_event":0,"token_side_mismatch":5}
```

Result: candidate-scoped production remains partial. The system now exposes `NO_CANDIDATE_SCOPED_EVENT` and does not treat market-level events as actionable.

## 18. Paper Actionability Results

During smoke:

```json
{"items_checked":50,"actionable_small_paper":0,"watch_for_confirmation":0,"waiting_for_price_refresh":0,"blocked_by_lifecycle":50,"blocked_by_capital":0,"blocked_by_data":0,"no_trade":0,"unknown":0}
```

Result: no actionable paper candidates. Market-scoped-only and lifecycle blockers are visible.

## 19. Pre-Paper Safety Results

Current result:

```text
PRE_PAPER_NOT_READY
```

Blockers include:

- `PAPER_SIMULATION_OFF`
- `NO_CANDIDATE_SCOPED_EVENT`
- `NO_PAPER_ACTIONABILITY`
- `DUPLICATE_ACTIVE_INTENT_RISK`
- `OPEN_PAPER_POSITION_CONFLICT`

## 20. Unified Blocker Samples

Examples exposed by active endpoints:

- `PAPER_SIMULATION_OFF`
- `NO_CANDIDATE_SCOPED_EVENT`
- `NO_PAPER_ACTIONABILITY`
- `MARKET_SCOPED_ONLY_EVENT`
- `BLOCKED_BY_LIFECYCLE`
- `MISSING_CANDIDATE_EVENT_LINK`

Each new blocker includes severity, source, identifiers where available, `required_to_pass`, refreshability, operator-action flag, and `created_at`.

## 21. Paper Certification Plan Summary

The plan endpoint exists and returns the dry Phase 10 contract.

Phase 10 is defined as controlled certification only, with explicit Paper Simulation ON only in Phase 10, explicit pre-check acceptance, before/after counts, forbidden artifact checks, and system-off cleanup.

## 22. Artifact Safety Counts

Forbidden artifact counts were unchanged:

- `paper_intents`: 20 to 20
- `paper_orders`: 12 to 12
- `paper_fills`: 9 to 9
- `paper_positions`: 12 to 12
- `live_orders`: 0 to 0
- `positions`: 0 to 0

## 23. Remaining Risks

- Candidate-scoped event production did not appear during the active smoke, even though candidate-targeted price readiness is fresh.
- Current latest events are still market-level-only or token/side mismatch.
- Pre-paper safety is NOT_READY due Paper Simulation OFF, no candidate-scoped event, no actionable paper state, duplicate active intent risk, and open paper position conflict.
- Historical paper artifacts already exist; this bundle did not create new ones.

## 24. Can Proceed To Phase 10

NO for full GREEN activation.

YES only if Phase 10 explicitly accepts YELLOW risk and begins by resolving candidate-scoped event production or treating missing candidate-scoped events as a blocking pre-check.
