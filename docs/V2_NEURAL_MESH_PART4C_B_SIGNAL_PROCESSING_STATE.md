# V2 Neural Mesh Part 4C-B: Signal Processing State

## 1. Purpose

Part 4C-B adds a persisted, queryable processing state for each Signal and a deterministic quality gate that classifies whether a Signal is merely created, linked, quality checked, brain-used, coordinator-used, stale, ignored, rejected, errored, or blocked.

This is mesh hardening only. It does not enable Paper, Live, order intents, orders, AI calls, or any execution behavior.

## 2. Why Signal Processing State Matters

Signal Quality answers whether a Signal is usable. Signal Processing State answers where that Signal currently sits in the mesh.

POLYBOT now has a DB-backed way to answer:

- Was the Signal evaluated?
- Was it linked to market or position context?
- Did it pass the brain-quality gate?
- Was it consumed by a Brain Output?
- Was it consumed by the Coordinator?
- Is it stale, rejected, ignored, or errored?
- Why is it blocked from Paper evidence?

## 3. Processing State Contract

Latest state is stored in `signal_processing_states`, one row per `signal_id`.

Allowed `processing_state` values:

- `NEW`
- `LINKED`
- `QUALITY_CHECKED`
- `BRAIN_USED`
- `COORDINATOR_USED`
- `IGNORED`
- `STALE`
- `REJECTED`
- `ERROR`

Allowed `gate_status` values:

- `NOT_EVALUATED`
- `BLOCKED`
- `BRAIN_ELIGIBLE`
- `PAPER_BLOCKED`
- `PAPER_ELIGIBLE_INFORMATIONAL_ONLY`
- `STALE`
- `ERROR`

## 4. Quality Gate Enforcement

The gate reads existing DB truth from Signals, Signal Quality, Impact Graph links, Brain Output dependencies, and Coordinator inputs.

Rules:

- No quality evaluation means `NOT_EVALUATED`.
- Existing links can move an unevaluated Signal to `LINKED`.
- Quality evaluation moves it to `QUALITY_CHECKED`.
- Stale Signals become `STALE` and cannot feed Brain or Paper.
- Brain-used Signals become `BRAIN_USED`.
- Coordinator-used Signals become `COORDINATOR_USED`.
- `can_feed_brain=true` yields `BRAIN_ELIGIBLE`.
- `can_feed_paper=true` yields `PAPER_ELIGIBLE_INFORMATIONAL_ONLY`.
- `can_feed_paper` remains informational and does not set global `paper_ready`.
- Dry-run generated evidence remains blocked from production Paper evidence.

## 5. DB Schema

Migration: `0069_v2_neural_mesh_signal_processing_state.sql`

Tables:

- `signal_processing_states`
- `signal_processing_state_history`

`signal_processing_states` stores latest state, quality snapshot fields, gate blockers, missing requirements, usage booleans, readiness flags, and timestamps.

`signal_processing_state_history` stores state and gate transitions when they actually change.

## 6. Repository and Service Behavior

Repository:

- Reads signal context from existing mesh truth.
- Upserts one latest processing row per Signal.
- Records transition history only when state or gate changes.
- Lists recent states and summarizes counts.

Service:

- Evaluates one Signal.
- Evaluates recent Signals.
- Optionally refreshes Signal Quality first.
- Marks ignored/error states with required reasons.
- Returns `paper_ready=false` in summaries.

## 7. API Routes

New routes:

- `GET /signals/processing/recent`
- `GET /signals/{signal_id}/processing`
- `POST /signals/processing/evaluate/recent`
- `POST /signals/{signal_id}/processing/evaluate`
- `GET /dashboard/api/v2/signal-processing`

All return `mock_data=false`.

## 8. Dashboard Fields

`/dashboard/api/v2/signal-processing` exposes:

- total
- by_state
- by_gate_status
- unprocessed_count
- quality_checked_count
- brain_used_count
- coordinator_used_count
- stale_count
- rejected_count
- error_count
- brain_eligible_count
- paper_eligible_informational_count
- top_gate_blockers
- latest_states
- paper_ready=false

`/dashboard/api/v2/mesh` now includes `layers.signal_processing` and `flow.signal_processing`.

## 9. Mesh Readiness Blockers

Mesh readiness can now surface:

- `SIGNAL_PROCESSING_NOT_COMPLETE`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `SIGNALS_STALE`
- `SIGNALS_NOT_LINKED`

These are observational dashboard blockers only.

## 10. Safety Rules

- No orders.
- No order intents.
- No private keys.
- No signing.
- No live mutation.
- No runtime mode mutation.
- No global Paper readiness mutation.
- `can_feed_paper` is informational only.
- Missing data blocks readiness.
- Dashboard data is real DB/runtime truth only.

## 11. Example

```json
{
  "signal_id": "signal_123",
  "processing_state": "QUALITY_CHECKED",
  "gate_status": "BRAIN_ELIGIBLE",
  "quality_score": 0.72,
  "quality_status": "PARTIAL",
  "can_feed_brain": true,
  "can_feed_paper": false,
  "blocked_by": ["linked_to_position", "paper_quality_gate"],
  "missing_requirements": ["linked_to_position"]
}
```

## 12. What Is Explicitly Not Included

- Paper trading
- Live trading
- Order intents
- Orders
- Market Technical Truth
- News/Social/Whale connectors
- AI calls
- Risk Core
- Exit Foundation
- Opportunity Cortex
- Runtime mode or kill-switch fixes

## 13. Next Phase Recommendation

Next recommended phase: `V2 Neural Mesh Part 4C-C: Automatic Signal Quality + Processing Evaluation Hook`.

Goal: safely update quality and processing state when Signals are created or when safe mesh dry-run writes occur, without creating background trading behavior or execution paths.
