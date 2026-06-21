# POLYBOT V3.1 Mesh Sessions Foundation Build Report

## Dispatch

- Executor: Codex
- Task mode: CORE_ARCHITECTURE + BRAIN_MESH_FOUNDATION
- Risk: HIGH
- ChatGPT review: REQUIRED

## Current Reality Found

V3.0 neural events are stored in `neural_events` and delivered through
`neural_event_consumers`, `neural_event_delivery`, and `neural_event_replay`.
Events include enough identity to resolve sessions: `market_id`,
`candidate_id`, `position_id`, and `correlation_id`.

Runtime inspection before implementation found:

- `neural_events`: 1
- Recent neural events: 1
- Recent events with `market_id`: 1
- Recent events with `candidate_id`: 0
- Recent events with `position_id`: 0
- Recent unassignable events: 0
- Existing event type: `ORDERBOOK_REFRESHED`

Safe session types now: market, candidate, position, threat, opportunity,
global, and unassigned sessions. Duplication risk is limited by keeping sessions
as event organization only. Events remain immutable transport records and
trading/source tables remain authoritative.

Prompt-listed `docs/POLYBOT_VISION_2.md`,
`docs/POLYBOT_CURRENT_REALITY_AUDIT.md`, and
`docs/POLYBOT_NEURAL_EVENT_BUS_FOUNDATION*.md` were not present under `docs/`.
Equivalent repository files read:

- `POLYBOT_CURRENT_REALITY_AUDIT.md`
- `docs/POLYBOT_V3_NEURAL_EVENT_BUS_FOUNDATION.md`
- `docs/POLYBOT_V3_NEURAL_EVENT_BUS_FOUNDATION_BUILD_REPORT.md`

## Files Created

- `app/db/migrations/0102_v3_mesh_sessions_foundation.sql`
- `app/mesh_sessions/__init__.py`
- `app/mesh_sessions/types.py`
- `app/mesh_sessions/repository.py`
- `app/mesh_sessions/service.py`
- `tests/test_v3_mesh_sessions_foundation.py`
- `docs/POLYBOT_MESH_SESSIONS_FOUNDATION.md`
- `docs/POLYBOT_MESH_SESSIONS_FOUNDATION_BUILD_REPORT.md`

## Files Changed

- `app/neural_bus/service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Migration: `0102_v3_mesh_sessions_foundation.sql`

Tables:

- `mesh_sessions`
- `mesh_session_events`
- `mesh_session_participants`
- `mesh_session_state`

Idempotency:

- `mesh_sessions.session_id` is unique.
- `mesh_session_events(session_id, event_id)` is unique.
- `mesh_session_participants(session_id, component)` is unique.

## Session Model

`mesh_sessions` stores identity, lifecycle, counters, context flags, and
metadata. `mesh_session_events` links immutable neural events to rooms.
`mesh_session_participants` records real source components from events.
`mesh_session_state` stores latest observational state snapshots extracted from
event payloads.

Sessions organize truth; they do not become truth.

## Session Identity Rules

- `position_id` -> `POSITION_SESSION`
- `candidate_id` -> `CANDIDATE_SESSION`
- `market_id` -> `MARKET_SESSION`
- `correlation_id` only -> `GLOBAL_SESSION`
- no entity -> `UNASSIGNED_SESSION`
- adverse risk/exit/no-trade payloads also -> `THREAT_SESSION`
- positive/trusted/opportunity payloads also -> `OPPORTUNITY_SESSION`

## Runtime Integration

`NeuralEventBusService.publish_event()` persists the V3.0 event and resolves it
to mesh sessions in the same transaction. `publish_source_backed_events()` uses
the same integration. `MeshSessionService.materialize_unlinked_events()` can
link historical neural events while SYSTEM ON.

SYSTEM OFF blocks publish, which blocks new session creation from new events.
Dashboard reads remain allowed.

## API Routes

- `GET /dashboard/api/v2/mesh-sessions`
- `GET /dashboard/api/v2/mesh-sessions/{session_id}`

Both return `mock_data=false`.

## Dialogue

`BrainDialogueService.materialize_recent()` now materializes source-backed mesh
session messages from:

- `mesh_sessions`
- `mesh_session_events`

Messages include session opened, event linked, and session became active.

## Tests Added

`tests/test_v3_mesh_sessions_foundation.py`

Coverage:

- market event creates `MARKET_SESSION`
- candidate event creates `CANDIDATE_SESSION`
- position event creates `POSITION_SESSION`
- adverse position event marks `threat_context`
- positive signal marks `opportunity_context`
- unassigned event creates `UNASSIGNED_SESSION`
- same event is not linked twice
- participant is recorded from `source_component`
- session becomes `ACTIVE`
- dashboard returns `mock_data=false`
- detail endpoint returns timeline
- SYSTEM OFF blocks session creation from new publish
- no paper/live/order/fill/position mutation
- brain dialogue materializes session events

## Tests Run

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v3_mesh_sessions_foundation.py -q"`

Result: `11 passed, 1 warning in 66.54s`

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v3_neural_event_bus.py tests/test_dashboard_neural_bus_api.py tests/test_brain_dialogue_materialization.py tests/test_dashboard_brain_dialogue_api.py tests/test_paper_no_live_safety.py tests/test_paper_execution_safety.py tests/test_v2_risk_core_safety.py tests/test_v2_exit_foundation_safety.py tests/test_v2_paper_eligibility_safety.py -q"`

Result: `19 passed, 1 warning in 108.44s`

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_safety.py -q"`

Result: `14 passed in 65.85s`

`python -m compileall app\mesh_sessions app\neural_bus\service.py app\services\brain_dialogue.py app\api\routes.py`

Result: success.

Post read-only dashboard adjustment rerun:

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v3_mesh_sessions_foundation.py tests/test_v3_neural_event_bus.py tests/test_dashboard_neural_bus_api.py -q"`

Result: `19 passed, 1 warning in 105.28s`

## Runtime Smoke

API rebuilt and restarted:

`docker compose up -d --build api`

Health:

`GET /healthz` -> `{"status":"ok","app":"polybot","ready":true}`

Smoke steps:

1. SYSTEM OFF.
2. Publish blocked with no new session.
3. SYSTEM ON.
4. Published `ORDERBOOK_REFRESHED` with `market_id=v31-smoke-market`.
5. Published `RISK_CHANGED` with same market and `candidate_id=v31-smoke-candidate`.
6. Verified neural events, sessions, event links, participants, dashboard, detail endpoint, dialogue.
7. SYSTEM OFF.
8. Controlled materialization linked one pre-existing V3.0 neural event.
9. SYSTEM OFF confirmed.

Dashboard:

- `GET /dashboard/api/v2/mesh-sessions?limit=5` -> 200
- `GET /dashboard/api/v2/mesh-sessions/{session_id}?limit=10` -> 200
- `mock_data=false`

Final event-to-session coverage:

- total events: 3
- linked events: 3
- coverage: 100.0%
- orphan events without session: 0

## Before / After Counts

Initial runtime smoke before:

- `neural_events`: 1
- `mesh_sessions`: 0
- `mesh_session_events`: 0
- `mesh_session_participants`: 0
- `market_sessions`: 0
- `candidate_sessions`: 0
- `position_sessions`: 0
- `opportunity_sessions`: 0
- `threat_sessions`: 0
- `unassigned_sessions`: 0
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- paper capital: available `1000.00000000`, locked `0.00000000`

Final runtime smoke after:

- `neural_events`: 3
- `mesh_sessions`: 4
- `mesh_session_events`: 4
- `mesh_session_participants`: 4
- `market_sessions`: 2
- `candidate_sessions`: 1
- `position_sessions`: 0
- `opportunity_sessions`: 0
- `threat_sessions`: 1
- `unassigned_sessions`: 0
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- paper capital: available `1000.00000000`, locked `0.00000000`

Trading mutation: none.

## Sample Sessions

- `MARKET_SESSION`, `market_id=smoke-market`, `event_count=1`,
  `participant_count=1`
- `MARKET_SESSION`, `market_id=v31-smoke-market`, `event_count=1`,
  `participant_count=1`
- `CANDIDATE_SESSION`, `candidate_id=v31-smoke-candidate`,
  `threat_context=true`
- `THREAT_SESSION`, `candidate_id=v31-smoke-candidate`,
  `threat_context=true`

Sample dialogue:

- `Mesh Session: Opened MARKET_SESSION for market_id=v31-smoke-market`
- `Mesh Session: Linked ORDERBOOK_REFRESHED to market session market_id=v31-smoke-market`
- `Mesh Session: Opened CANDIDATE_SESSION for candidate_id=v31-smoke-candidate`
- `Mesh Session: Linked RISK_CHANGED to candidate session candidate_id=v31-smoke-candidate`
- `Mesh Session: Linked RISK_CHANGED to threat session candidate_id=v31-smoke-candidate`

## Safety Checklist

- Live trading not enabled.
- Shadow mode not enabled.
- No orders created by sessions.
- No fills created by sessions.
- No positions created by sessions.
- No paper artifacts created by sessions.
- No risk/exit/eligibility outcomes mutated.
- Neural events remain immutable.
- Dashboard reads are DB-backed and return `mock_data=false`.
- SYSTEM OFF blocks new publish/session creation.
- System returned to OFF after smoke.

## Remaining Risks

- Runtime coverage depends on event publisher coverage; components that do not
  publish V3.0 neural events will not appear in mesh sessions yet.
- Opportunity/threat sessions are context flags only. They intentionally do not
  score, decide, aggregate, or trigger exits in this phase.
- Formal ChatGPT review is still required by project process.

## Next Recommended Phase

Shared Awareness Layer: allow existing organs to read session context without
mutating coordinator, risk, exit, eligibility, paper, live, or source truth.

## Phase Status

GREEN

## Can Move To Shared Awareness Layer

YES, after ChatGPT review.
