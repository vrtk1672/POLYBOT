# Minimal Event Driven Mesh Proof Report

## 1. Purpose

Phase 8 proves the first minimal real event-driven Mesh path:

`orderbook.snapshot.created -> liquidity brain -> risk brain -> exit brain -> coordinator trace -> Control Center API/UI`

This phase does not implement the full mesh. It proves one durable event can wake multiple deterministic, non-executing brain reactions and produce a visible coordinator trace.

## 2. Current Reality Found

Before implementation, the production database had durable event and intelligence tables, but no active event consumers:

- `event_log`: 551094
- `event_consumers`: 0
- `event_delivery_attempts`: 0
- `neural_events`: 4178
- `neural_event_delivery`: 1
- `brain_outputs`: 20554
- `coordinator_decisions`: 20518
- `orderbook_snapshots`: 50912

The canonical event type `orderbook.snapshot.created` already existed, but orderbook snapshot persistence did not publish a durable mesh proof event or fan out to consumers.

## 3. Existing Event / Mesh Sources Reused

Reused existing tables and contracts:

- `event_log`
- `event_consumers`
- `event_delivery_attempts`
- `brain_outputs`
- `coordinator_decisions`
- `coordinator_decision_inputs`
- `orderbook_snapshots`
- `EventType.ORDERBOOK_SNAPSHOT_CREATED`
- `OrderbookSnapshotRepository`
- Control Center truth envelope patterns

No new database migration was required.

## 4. Files Inspected

- `AGENTS.md`
- `docs/POLYBOT_AGENT_DISPATCH_PROTOCOL.md`
- `docs/POLYBOT_CONTEXT_INDEX.md`
- `docs/POLYBOT_SAFETY_RULES.md`
- `docs/POLYBOT_AGENT_WORKFLOW.md`
- `docs/POLYBOT_ULTIMATE_FORENSIC_AUTOPSY.md`
- `docs/FRESH_ORDERBOOK_PRICE_PATH_REPORT.md`
- `docs/CANDIDATE_TARGETED_REFRESH_BEFORE_EXECUTION_REPORT.md`
- `app/events/event_bus.py`
- `app/events/types.py`
- `app/services/orderbook_snapshots.py`
- `app/repositories/orderbook_snapshot_repository.py`
- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/candidate_price_path.py`
- `app/control_center/query_service.py`
- `app/api/routes.py`
- frontend Control Center API/query/page files
- related event, orderbook, and control center tests

## 5. Files Changed

- `app/repositories/orderbook_snapshot_repository.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_control_center_read_only_apis.py`

## 6. Files Created

- `app/events/consumers/__init__.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/control_center/event_mesh_proof.py`
- `tests/test_event_mesh_proof.py`
- `docs/MINIMAL_EVENT_DRIVEN_MESH_PROOF_REPORT.md`

## 7. APIs Added / Changed

Added:

- `GET /dashboard/api/v2/control/event-mesh-proof`
- `GET /dashboard/api/v2/control/event-mesh-proof/{correlation_id}`

The list endpoint supports:

- `limit`
- `offset`
- `event_type`
- `market_id`
- `candidate_id`
- `correlation_id`
- `state`
- `include_reactions`

## 8. Frontend Changes

The Control Center now has a Minimal Event Mesh Proof panel showing:

- proof state
- event delivery state
- latest event/correlation id
- liquidity/risk/exit reaction counts
- coordinator trace count and decision
- blockers and warnings

No mock data or new design system was introduced.

## 9. Event Type Implemented / Reused

Reused canonical event type:

- `orderbook.snapshot.created`

Events are emitted from the durable orderbook snapshot write path.

## 10. Brain Reactions Implemented

For each snapshot event, the mesh proof consumer records separate non-executing brain outputs:

- `liquidity`: spread, bid/ask, depth, usability
- `risk`: freshness/status, price risk, spread/liquidity risk
- `exit`: exit side price, exit liquidity, exit path availability

All recommendations are observe-only and do not create intents, orders, fills, or positions.

## 11. Coordinator Trace Implemented

The coordinator writes a trace tied to the same `correlation_id` and `event_id`.

Coordinator decisions are limited to:

- `PRICE_READY`
- `PRICE_BLOCKED`

The persisted coordinator decision explicitly sets:

- `execution_allowed = false`
- blocked actions include paper/live/order/position actions

## 12. Tests Added

Added `tests/test_event_mesh_proof.py` covering:

- event emitted from orderbook snapshot repository path
- event has correlation id
- liquidity/risk/exit reactions
- coordinator trace
- one event producing multiple brain reactions
- missing consumer is not fake proof
- failed consumer is recorded
- endpoint returns proof counts and traces
- read-only path creates no paper artifacts

## 13. Tests Run And Exact Results

- `.venv\Scripts\python.exe -m pytest tests/test_event_mesh_proof.py -q`
  - Result: `4 skipped in 2.16s`
  - Reason: DB-backed tests skip when the local test DB fixture is unavailable.

- `.venv\Scripts\python.exe -m pytest tests/test_candidate_price_path.py tests/test_orderbook_price_readiness.py tests/test_candidate_producer_freshness.py tests/test_control_center_read_only_apis.py -q`
  - Result: `6 passed, 21 skipped in 6.92s`

- `.venv\Scripts\python.exe -m pytest tests -q -k "event_bus or neural_bus or mesh or coordinator or brain"`
  - Result: `94 passed, 213 skipped, 1623 deselected in 7.93s`

- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed

- `npm run typecheck`
  - Result: passed

- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed (3), 18 passed (18)`

- `npm run build`
  - Result: passed, with existing Vite chunk-size warning

## 14. Deployment / Restart Results

Deployment action:

- `docker compose build api`
- `docker compose up -d --no-deps api`

Active API container after restart:

- `polybot_api`
- image `polybot_server-api`
- port `0.0.0.0:8000->8000/tcp`
- status healthy

## 15. Controlled SYSTEM ON Smoke Procedure

Before smoke:

- Paper Simulation: OFF
- Runtime: STOPPED
- System power: OFF
- Event mesh proof endpoint: `MISSING`

Action:

- `POST /dashboard/api/v2/control/actions/system-on`
- actor: `codex_phase8_smoke`
- reason: `Phase 8 controlled event mesh proof smoke; keep Paper Simulation OFF`

During:

- Waited for supervisor cycles.
- Polled runtime health, event mesh proof, orderbook price readiness, candidate price path, and paper readiness.

Cleanup:

- `POST /dashboard/api/v2/control/actions/system-off`
- actor: `codex_phase8_smoke`
- reason: `Phase 8 controlled smoke cleanup; keep Paper Simulation OFF`

## 16. Before / After Event, Brain, Coordinator Counts

Before smoke:

- `event_log`: 551094
- `event_consumers`: 0
- `event_delivery_attempts`: 0
- `neural_events`: 4178
- `neural_event_delivery`: 1
- `brain_outputs`: 20554
- `coordinator_decisions`: 20518
- `brain_dialogue_events`: 299573
- `mesh_sessions`: 192
- `orderbook_snapshots`: 50912

After smoke:

- `event_log`: 551191
- `event_consumers`: 4
- `event_delivery_attempts`: 192
- `neural_events`: 4215
- `neural_event_delivery`: 1
- `brain_outputs`: 20708
- `coordinator_decisions`: 20576
- `brain_dialogue_events`: 299573
- `mesh_sessions`: 192
- `orderbook_snapshots`: 50960

## 17. Sample Correlation Trace

Sample returned by active server:

- `event_id`: `276a6b82-8ab0-4ded-9495-911d9d08831a`
- `correlation_id`: `live_orderbook_watcher_395b6d3ff97c41e9ba0c7ad903f554ef:ob_5a41be47ba4b400c9102c4c97ebdee21`
- `event_type`: `orderbook.snapshot.created`
- `market_id`: `677404`
- `side`: `YES`
- `token_id`: `36135303630970774358991758965953725374791089628290212294816140371870983436829`
- `event_delivery_state`: `DELIVERED`
- `mesh_proof_state`: `PROVEN`
- `liquidity`: `REACTED`
- `risk`: `REACTED`
- `exit`: `REACTED`
- `coordinator`: `DECISION_CREATED`

## 18. UI / API Proof

Active GET verification after deployment and smoke:

- `GET /healthz`: 200
- `GET /runtime/health`: 200, `runtime_life_state=STOPPED`, `system_power_state=OFF` after cleanup
- `GET /dashboard/api/v2/control/event-mesh-proof?limit=1`: 200, `mesh_proof_state=PROVEN`, `fully_proven_events=1`
- `GET /dashboard/api/v2/control/paper-readiness`: 200, `paper_readiness_state=BLOCKED`, `paper_simulation_state=OFF`, `system_power_state=OFF` after cleanup
- `GET /dashboard/api/v2/control/eligible-intent-bridge?limit=1`: 200
- `GET /dashboard/api/v2/control/orderbook-price-readiness?limit=1`: 200
- `GET /dashboard/api/v2/control/candidate-price-path?limit=1`: 200

## 19. Artifact Safety Counts

Forbidden artifacts did not increase:

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

- This proves one event type only, not the full mesh.
- The proof consumer is deterministic and observe-only; production decision engines still need broader event-native integration in later phases.
- Candidate linkage is best-effort when orderbook snapshot metadata can be matched to an eligibility candidate.
- `neural_event_delivery` remains mostly legacy/sparse because this phase reused durable event log and existing brain/coordinator tables rather than rewriting the neural bus.

## 21. Next Recommended Phase

Expand from one proven event to a bounded event mesh:

- add consumer health/readiness monitoring
- route candidate price path events
- route candidate eligibility state changes
- connect coordinator traces into Decision X-Ray / Mesh Dialogues
- keep all trading execution gated behind existing Governor, risk, exit, capital, and paper simulation controls

