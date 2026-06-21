# Candidate Event Correlation Hardening Report

## 1. Purpose

Phase 9C hardens the link between paper-relevant `orderbook.snapshot.created` events and paper candidates. Event-level mesh proof is no longer treated as candidate-actionable unless the event can be tied to one candidate through market, side, and token evidence.

## 2. Current Reality Found

- `orderbook.snapshot.created` events are durable and wake the five mesh opinions from Phase 9B.
- Many fresh orderbook events are market-level only because they do not carry `candidate_id`.
- Latest active runtime verification showed:
  - `events_checked`: 50
  - `linked_to_candidate`: 0
  - `market_level_only`: 44 to 46
  - `token_side_mismatch`: 4 to 6
  - `candidate_scoped`: 0
- This is safe truth: current mesh proof can be complete at event level while remaining non-actionable for candidate progress.

## 3. Candidate/Event Correlation Model

Candidate event link states:

- `LINKED_TO_CANDIDATE`
- `MARKET_LEVEL_ONLY_WITH_REASON`
- `UNLINKED_WITH_REASON`
- `AMBIGUOUS_MULTIPLE_CANDIDATES`
- `TOKEN_SIDE_MISMATCH`
- `STALE_CANDIDATE_LINK`
- `MISSING_CANDIDATE`
- `MISSING_EVENT`
- `UNKNOWN`

Candidate actionability scopes:

- `CANDIDATE_SCOPED`
- `MARKET_SCOPED_ONLY`
- `NOT_ACTIONABLE`
- `AMBIGUOUS`
- `UNKNOWN`

Only `LINKED_TO_CANDIDATE` with `HIGH` confidence and `FRESH` link freshness becomes `CANDIDATE_SCOPED`.

## 4. Existing Sources Reused

- `event_log`
- `orderbook_snapshots`
- `paper_eligibility_candidates`
- `brain_outputs`
- `coordinator_decisions`
- `mesh evidence bundle` assembly
- `candidate explanations`
- `eligible intent bridge`
- `paper readiness`

No new DB table or migration was added.

## 5. Files Inspected

- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/event_mesh_proof.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/candidate_price_path.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/events/event_bus.py`
- `app/events/types.py`
- `app/repositories/orderbook_snapshot_repository.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_intents.py`
- `app/runtime/state_governor.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- Phase 8, 9, and 9B reports and related tests.

## 6. Files Changed

- `app/control_center/candidate_event_correlation.py`
- `app/control_center/event_mesh_proof.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/paper_readiness.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_candidate_event_correlation.py`
- `docs/CANDIDATE_EVENT_CORRELATION_HARDENING_REPORT.md`

## 7. APIs Added/Changed

Added:

- `GET /dashboard/api/v2/control/candidate-event-correlation`
- `GET /dashboard/api/v2/control/candidate-event-correlation/{candidate_id}`

Extended:

- `GET /dashboard/api/v2/control/event-mesh-proof`
- `GET /dashboard/api/v2/control/mesh-evidence-bundles`
- `GET /dashboard/api/v2/control/candidate-explanations`
- `GET /dashboard/api/v2/control/eligible-intent-bridge`
- `GET /dashboard/api/v2/control/paper-readiness`

## 8. Frontend Changes

The Control Center now includes a Candidate Event Correlation panel showing linked, market-level, unlinked, ambiguous, confidence, sample event, coordinator decision, and top unlinked reasons. The endpoint is wired into the API map, query hooks, and refresh policy.

## 9. Tests Added

- `tests/test_candidate_event_correlation.py`
  - Pure classifier tests for exact candidate linkage and ambiguity.
  - DB-backed integration tests for linked, unlinked, ambiguous, token mismatch, market-level-only, API read-only behavior, mesh bundle/proof integration, bridge blocking, and paper readiness counts.

## 10. Tests Run And Exact Results

- `.venv\Scripts\python.exe -m pytest tests/test_candidate_event_correlation.py -q`
  - `2 passed, 9 skipped`
- `.venv\Scripts\python.exe -m pytest tests/test_lifecycle_capital_event_native_opinions.py tests/test_mesh_evidence_bundle.py tests/test_event_mesh_proof.py tests/test_candidate_price_path.py tests/test_candidate_explanations.py tests/test_eligible_intent_bridge.py tests/test_paper_readiness.py tests/test_control_center_read_only_apis.py -q`
  - `6 passed, 61 skipped`
- `.venv\Scripts\python.exe -m pytest tests -q -k "candidate_event or correlation or mesh or event or candidate_price"`
  - `62 passed, 207 skipped, 1679 deselected`
- `.venv\Scripts\python.exe -m compileall app tests`
  - passed
- `npm run typecheck`
  - passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - `3 passed`, `18 passed`
- `npm run build`
  - passed with existing Vite chunk-size warning

Local DB-backed tests skip when the local Postgres test fixture is unavailable.

## 11. Deployment/Restart Results

- Confirmed port 8000 is served by Docker Desktop/WSL relay and mapped to container `polybot_api`.
- Ran `docker compose build api`.
- Ran `docker compose up -d --no-deps api`.
- No DB deletion, no volume reset, no migrations.

## 12. Controlled SYSTEM ON Smoke Procedure

Before:

- Captured event/orderbook/brain/coordinator/candidate/paper/live counts.
- Paper readiness was BLOCKED with system power OFF.

Action:

- POST `/dashboard/api/v2/control/actions/system-on`
- Waited for supervisor/orderbook cycles.
- Polled GET-only control endpoints.
- POST `/dashboard/api/v2/control/actions/system-off`

No Paper Simulation, Full Monitor Run, Shadow, Live, paper action, or execution action was started.

## 13. Before/After Correlation Counts

Before smoke:

- `events_checked`: 50
- `linked_to_candidate`: 0
- `market_level_only`: 44
- `token_side_mismatch`: 6
- `candidate_scoped`: 0

During smoke:

- `events_checked`: 50
- `linked_to_candidate`: 0
- `market_level_only`: 46
- `token_side_mismatch`: 4
- `candidate_scoped`: 0

After cleanup:

- `events_checked`: 50
- `linked_to_candidate`: 0
- `market_level_only`: 44
- `token_side_mismatch`: 6
- `candidate_scoped`: 0

## 14. Sample Linked Candidate Event

The active production-like dataset did not contain a latest high-confidence candidate-scoped event during smoke. The DB-backed tests cover the linked case when one candidate exactly matches market, side, and token.

## 15. Sample Market-Level/Unlinked Event

Active endpoint sample classifies current latest events as `MARKET_LEVEL_ONLY_WITH_REASON` or `TOKEN_SIDE_MISMATCH`; these are not candidate-actionable. A single-candidate verification returned `UNLINKED_WITH_REASON` for a real candidate with no linked event.

## 16. Mesh Bundle Integration

Mesh evidence bundles now expose:

- `candidate_event_link_state`
- `candidate_event_link_freshness`
- `candidate_event_actionability_scope`
- `correlation_confidence`
- `candidate_link_blockers`
- `required_to_link_candidate`
- matched and ambiguous candidate lists

During smoke, mesh bundles remained `COMPLETE` at event level, while actionability stayed market-scoped/non-candidate-scoped.

## 17. Candidate/Bridge/Paper Readiness Integration

Candidate explanations now include latest event correlation fields. Eligible-to-intent bridge blocks candidate progress when mesh evidence is market-level-only, ambiguous, stale, mismatched, or missing. Paper readiness includes candidate/event correlation counts and state.

## 18. Artifact Safety Counts

Before smoke:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `live_orders`: 0
- `positions`: 0

After cleanup:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `live_orders`: 0
- `positions`: 0

Allowed DATA_ONLY event/mesh/orderbook counts increased during supervisor smoke:

- `event_log`: 551627 to 551695
- `orderbook_snapshots`: 51056 to 51076
- `brain_outputs`: 21112 to 21212
- `coordinator_decisions`: 20692 to 20712

## 19. Remaining Risks

- Current live dataset still has no latest candidate-scoped event in the 50-event window.
- Many latest orderbook events remain market-level-only. This is truthful and non-actionable, but candidate-specific actionability remains blocked until matching event candidate evidence exists.
- DB-backed tests were skipped locally because the local Postgres test fixture was unavailable; active container verification covered the live API path.

## 20. Next Recommended Phase

Define the Coordinator-to-Paper Actionability Contract so only candidate-scoped, high-confidence, fresh mesh evidence can ever be considered by a later paper-intent path, while Paper Simulation remains separately gated.
