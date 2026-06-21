# Mesh Session Evidence Bundle Report

## 1. Purpose

Phase 9 builds a shared evidence bundle view for real Mesh decision rooms.

The bundle is keyed by event `correlation_id` and assembles the same orderbook event, market, side, token, brain opinions, capital/lifecycle opinions when available, conflicts, and coordinator decision into one source-backed room.

This phase is visibility and DATA_ONLY Mesh truth only. It does not enable paper, shadow, live, order creation, fills, or positions.

## 2. Current Reality Found

Phase 8 proved `orderbook.snapshot.created` wakes Liquidity, Risk, Exit, and Coordinator. The remaining gap was that operators could see the event proof but not a single shared bundle containing the room evidence and explicit missing/conflicting opinions.

Existing production truth before the Phase 9 smoke:

- `event_log`: 551223
- `event_delivery_attempts`: 192
- `brain_outputs`: 20708
- `coordinator_decisions`: 20576
- `coordinator_decision_inputs`: 20708
- `brain_dialogue_events`: 299575
- `mesh_sessions`: 192
- `capital_brain_evaluations`: 192
- `lifecycle_governance_decisions`: 10751

## 3. Existing Mesh / Event / Brain / Coordinator Sources Reused

Reused existing tables:

- `event_log`
- `orderbook_snapshots`
- `brain_outputs`
- `coordinator_decisions`
- `coordinator_decision_inputs`
- `mesh_sessions`
- `capital_brain_evaluations`
- `lifecycle_governance_decisions`
- `paper_eligibility_candidates`

No new table was added.

## 4. Bundle Model

Bundle identity:

- `bundle_id = mesh_bundle_{correlation_id}`
- keyed by `correlation_id`
- includes `event_id`, `market_id`, `candidate_id` if available, `side`, `token_id`

Bundle states:

- `COMPLETE`
- `PARTIAL`
- `STALE`
- `MISSING`
- `CONFLICTED`
- `UNKNOWN`

Opinion states:

- `PRESENT`
- `MISSING`
- `STALE`
- `CONFLICTING`
- `NOT_APPLICABLE`
- `UNKNOWN`

Coordinator resolution states:

- `RESOLVED`
- `PARTIAL`
- `BLOCKED`
- `CONFLICTED`
- `NO_DECISION`
- `UNKNOWN`

## 5. Files Inspected

- `app/control_center/event_mesh_proof.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/events/event_bus.py`
- `app/events/types.py`
- `app/control_center/candidate_price_path.py`
- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/query_service.py`
- `app/control_center/truth_contract.py`
- `app/api/routes.py`
- frontend Control Center API/query/page files
- `tests/test_event_mesh_proof.py`
- `docs/MINIMAL_EVENT_DRIVEN_MESH_PROOF_REPORT.md`
- relevant DB migrations for events, brain outputs, coordinator decisions, mesh sessions, capital, lifecycle, risk, exit, and orderbook snapshots

## 6. Files Changed

- `app/api/routes.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_control_center_read_only_apis.py`

## 7. Files Created

- `app/control_center/mesh_evidence_bundle.py`
- `tests/test_mesh_evidence_bundle.py`
- `docs/MESH_SESSION_EVIDENCE_BUNDLE_REPORT.md`

## 8. APIs Added / Changed

Added:

- `GET /dashboard/api/v2/control/mesh-evidence-bundles`
- `GET /dashboard/api/v2/control/mesh-evidence-bundles/{correlation_id}`

The list endpoint supports:

- `limit`
- `offset`
- `market_id`
- `candidate_id`
- `correlation_id`
- `event_id`
- `state`
- `include_opinions`
- `include_conflicts`

## 9. Frontend Changes

Added Control Center panel:

- `Mesh Evidence Bundles`

It shows:

- bundle state
- mesh session state
- bundle counts
- liquidity/risk/exit opinion states
- capital/lifecycle opinion states
- coordinator decision
- correlation/event id
- market/side/token
- orderbook freshness
- conflicts or missing opinions

No mock data or new design system was introduced.

## 10. Tests Added

Added `tests/test_mesh_evidence_bundle.py`, covering:

- bundle assembly for `orderbook.snapshot.created`
- market/side/token/orderbook evidence
- liquidity/risk/exit opinions
- explicit capital/lifecycle opinion state
- coordinator decision linkage
- endpoint counts and items
- single bundle endpoint
- conflict detection
- no paper artifact creation from read-only bundle assembly

## 11. Tests Run And Exact Results

- `.venv\Scripts\python.exe -m pytest tests/test_mesh_evidence_bundle.py -q`
  - Result: `4 skipped in 2.36s`
  - Reason: DB-backed tests skip when the local test DB fixture is unavailable.

- `.venv\Scripts\python.exe -m pytest tests/test_mesh_evidence_bundle.py tests/test_control_center_read_only_apis.py -q`
  - Result: `5 passed, 4 skipped in 5.68s`

- `.venv\Scripts\python.exe -m pytest tests/test_event_mesh_proof.py tests/test_candidate_price_path.py tests/test_candidate_explanations.py tests/test_eligible_intent_bridge.py tests/test_paper_readiness.py tests/test_control_center_read_only_apis.py -q`
  - Result: `6 passed, 54 skipped in 7.12s`

- `.venv\Scripts\python.exe -m pytest tests -q -k "mesh or event or coordinator or brain or evidence_bundle"`
  - Result: `114 passed, 288 skipped, 1532 deselected in 7.50s`

- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed

- `npm run typecheck`
  - Result: passed

- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed (3), 18 passed (18)`

- `npm run build`
  - Result: passed, with existing Vite chunk-size warning

## 12. Deployment / Restart Results

Deployment action:

- `docker compose build api`
- `docker compose up -d --no-deps api`

Active server served the new endpoint on port 8000.

## 13. Controlled SYSTEM ON Smoke Procedure

Before:

- System power: OFF
- Runtime: STOPPED
- Paper Simulation: OFF
- Paper readiness: BLOCKED

Action:

- `POST /dashboard/api/v2/control/actions/system-on`
- actor: `codex_phase9_smoke`
- reason: `Phase 9 controlled mesh evidence bundle smoke; keep Paper Simulation OFF`

During:

- Waited for supervisor cycles.
- Polled event mesh proof, mesh evidence bundles, candidate explanations, eligible bridge, and paper readiness.

Cleanup:

- `POST /dashboard/api/v2/control/actions/system-off`
- actor: `codex_phase9_smoke`
- reason: `Phase 9 controlled smoke cleanup; keep Paper Simulation OFF`

## 14. Before / After Mesh / Bundle Counts

Before smoke:

- `event_log`: 551223
- `event_delivery_attempts`: 192
- `brain_outputs`: 20708
- `coordinator_decisions`: 20576
- `coordinator_decision_inputs`: 20708
- `brain_dialogue_events`: 299575
- `mesh_sessions`: 192
- `capital_brain_evaluations`: 192
- `lifecycle_governance_decisions`: 10751

After smoke:

- `event_log`: 551320
- `event_delivery_attempts`: 384
- `brain_outputs`: 20862
- `coordinator_decisions`: 20634
- `coordinator_decision_inputs`: 20862
- `brain_dialogue_events`: 299577
- `mesh_sessions`: 192
- `capital_brain_evaluations`: 192
- `lifecycle_governance_decisions`: 10751

Bundle endpoint after smoke:

- `bundles`: 1 on `limit=1`
- `bundle_state`: `CONFLICTED`
- `with_liquidity_opinion`: 1
- `with_risk_opinion`: 1
- `with_exit_opinion`: 1
- `with_capital_opinion`: 1
- `with_lifecycle_opinion`: 0
- `with_coordinator_decision`: 1

## 15. Sample Bundle

Sample active-server bundle:

- `bundle_id`: `mesh_bundle_live_orderbook_watcher_affb06164a414774a143b73a84a49e0e:ob_c7916eb8503d43ccbceaec597e9f398c`
- `event_id`: `bbbe27cb-b136-4c7d-bf5b-a24cc0a8958a`
- `correlation_id`: `live_orderbook_watcher_affb06164a414774a143b73a84a49e0e:ob_c7916eb8503d43ccbceaec597e9f398c`
- `market_id`: `597967`
- `side`: `YES`
- `token_id`: `34554555827438551101000555305203609600029621153428996114009350892614396532498`
- `orderbook.freshness_state`: `FRESH`
- `orderbook.trusted_state`: `TRUSTED_FRESH`
- `best_bid`: `0.19`
- `best_ask`: `0.20`
- `spread`: `0.01`
- `liquidity`: `PRESENT`
- `risk`: `PRESENT`
- `exit`: `PRESENT`
- `capital`: `PRESENT`
- `lifecycle`: `CONFLICTING`
- `coordinator.decision`: `PRICE_READY`
- `coordinator.execution_allowed`: `false`

## 16. Conflict Detection Results

Detected conflicts:

- `LIFECYCLE_DENIED_COORDINATOR_PRICE_READY`
- `STALE_OPINION_RELATIVE_TO_EVENT`

Required to resolve:

- coordinator must downgrade or lifecycle blockers must clear
- lifecycle opinion must refresh relative to the orderbook event

This is correct visibility. The system did not fake a complete bundle.

## 17. Candidate / Bridge Integration Results

Candidate explanations now include:

- `mesh_evidence_bundle`
- `mesh_evidence_bundle_state`
- `mesh_evidence_correlation_id`

Eligible-to-intent bridge now includes the same fields.

Current sample candidates did not have matching event bundle links because the latest event bundle is market/token-based and not candidate-linked. The missing link is explicit as `MISSING`.

## 18. Paper Readiness Before / During / After

Before:

- `paper_readiness_state`: `BLOCKED`
- `paper_simulation_state`: `OFF`
- `system_power_state`: `OFF`
- `runtime_life_state`: `STOPPED`

During:

- `paper_readiness_state`: `BLOCKED`
- `paper_simulation_state`: `OFF`
- `system_power_state`: `ON`
- `runtime_life_state`: `ALIVE`

After:

- `paper_readiness_state`: `BLOCKED`
- `paper_simulation_state`: `OFF`
- `system_power_state`: `OFF`
- `runtime_life_state`: `STOPPED`

## 19. Artifact Safety Counts

Forbidden artifacts did not increase.

Before:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `live_orders`: 0
- `positions`: 0

After:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `live_orders`: 0
- `positions`: 0

## 20. Remaining Mesh Risks

- Bundle is assembled read-only; no canonical persisted bundle table exists yet.
- Current bundle is `CONFLICTED`, not complete, because lifecycle governance conflicts with the event coordinator's price-ready trace.
- Candidate linkage remains partial when an orderbook event has market/token evidence but no candidate id.
- Capital/lifecycle are source-backed when matched; otherwise they are explicit missing/conflicting states, not generated opinions.
- The coordinator trace remains non-executing and price-focused; later phases must decide how lifecycle/capital should participate before any paper activation.

## 21. Next Recommended Phase

Create a coordinator room resolver that consumes the shared bundle and resolves lifecycle/capital conflicts before any candidate can be considered paper-intent-ready.

