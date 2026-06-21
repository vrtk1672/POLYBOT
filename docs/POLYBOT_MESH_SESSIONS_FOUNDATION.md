# POLYBOT V3.1 Mesh Sessions Foundation

## Purpose

V3.1 builds conversation rooms on top of the V3.0 Neural Event Bus.

Neural events remain immutable transport records. Mesh sessions do not replace
events, risk, exit, eligibility, paper, live, or position truth. They organize
source-backed events into parallel context rooms so POLYBOT can reason across
many markets, candidates, positions, opportunities, and threats at the same
time.

## Session Tables

- `mesh_sessions`: session identity, lifecycle, counters, and context flags.
- `mesh_session_events`: idempotent event-to-session links.
- `mesh_session_participants`: source components that have contributed events.
- `mesh_session_state`: latest observational snapshots extracted from event
  payloads.

## Session Types

- `MARKET_SESSION`
- `CANDIDATE_SESSION`
- `POSITION_SESSION`
- `OPPORTUNITY_SESSION`
- `THREAT_SESSION`
- `GLOBAL_SESSION`
- `UNASSIGNED_SESSION`

## Identity Rules

Primary session resolution follows entity specificity:

1. `position_id` creates or reuses a `POSITION_SESSION`.
2. `candidate_id` creates or reuses a `CANDIDATE_SESSION`.
3. `market_id` creates or reuses a `MARKET_SESSION`.
4. `correlation_id` creates or reuses a `GLOBAL_SESSION`.
5. No entity creates or reuses an `UNASSIGNED_SESSION`.

Context sessions are additive:

- Adverse risk/exit/no-trade or adverse payloads also link to `THREAT_SESSION`.
- Positive/trusted/opportunity payloads also link to `OPPORTUNITY_SESSION`.

## Lifecycle

- `OPEN`: created with first linked event.
- `ACTIVE`: more than one linked event or more than one participant.
- `STALE`: no event for the configured stale threshold.
- `CLOSED`: explicit close event or source payload indicating closed position or
  closed market.

V3.1 does not close sessions aggressively.

## Runtime Integration

`NeuralEventBusService.publish_event()` persists a neural event through the
existing V3.0 repository and then resolves that persisted event into mesh
sessions in the same transaction.

`publish_source_backed_events()` uses the same path for source-backed runtime
events.

System power behavior is inherited from V3.0:

- SYSTEM OFF blocks publishing, therefore blocks new session creation from new
  events.
- Dashboard reads remain available.
- Controlled materialization of unlinked historical events requires SYSTEM ON.

## Dashboard Truth

`GET /dashboard/api/v2/mesh-sessions` returns DB-backed session counts,
coverage, latest sessions, active sessions, stale sessions, and orphan neural
events.

`GET /dashboard/api/v2/mesh-sessions/{session_id}` returns session metadata,
linked events, participants, latest state, dialogue messages, and event
timeline.

Both endpoints return `mock_data=false`.

## Dialogue Visibility

`BrainDialogueService.materialize_recent()` now emits source-backed mesh session
messages from `mesh_sessions` and `mesh_session_events`, including session open,
event link, and active-state messages.

No dialogue message is generated without a real source row.

## Safety Boundary

Mesh sessions do not mutate:

- `live_orders`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `orders_v2`
- `fills_v2`
- canonical `positions`
- paper capital balances

They do not create orders, fills, positions, coordinator decisions, risk
decisions, exit plans, eligibility outcomes, or paper intents.
