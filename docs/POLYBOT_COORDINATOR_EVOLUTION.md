# POLYBOT V3.4 Coordinator Evolution

## Purpose

V3.4 adds the Mesh Decision Judge.

The Neural Event Bus transports facts, Mesh Sessions organize the discussion, Shared Awareness builds session state, and Multi-Brain Consumption produces source-backed opinions. V3.4 lets the coordinator judge those opinions without replacing the existing runtime coordinator or mutating trading truth.

Mesh coordinator decisions are derived, non-executing records. They do not create paper intents, orders, fills, positions, capital mutations, risk decisions, exit plans, eligibility changes, legacy coordinator decisions, or brain outputs.

## Current Reality

The existing runtime path still has legacy coordinator concepts:

- `RuntimeCoordinatorDecisionService` writes non-executing records to `coordinator_decisions` from `brain_outputs`.
- `BrainCoordinatorService` has conflict/consensus concepts for canonical `brain_outputs`.
- Runtime coordinator distribution is still mostly single-brain in legacy truth.
- V3.3 introduced `mesh_brain_opinions` and `mesh_coordinator_input_bundles`, but those bundles were not judged.

V3.4 leaves the old path intact and adds a parallel derived mesh judgment layer.

## Data Model

Migration `0105_v3_coordinator_evolution.sql` creates:

- `mesh_coordinator_decisions`
- `mesh_coordinator_decision_sources`
- `mesh_conflict_records`

`mesh_coordinator_decisions` stores final mesh stance/action, source brain counts, conflict counts, winners, losers, supporting/opposing opinions, decision reason, safety status, and readiness.

`mesh_coordinator_decision_sources` links each decision back to the source `mesh_brain_opinions`.

`mesh_conflict_records` records deterministic opinion conflicts and the rule-based winner.

## Final Stances

- `STRONG_SUPPORT`
- `SUPPORT`
- `WATCH`
- `NO_TRADE`
- `BLOCK`
- `EXIT_WATCH`
- `EXIT_RECOMMENDED`
- `INSUFFICIENT_DATA`

## Final Actions

- `OBSERVE`
- `WATCH`
- `NO_TRADE`
- `BLOCK`
- `PAPER_CANDIDATE_REVIEW`
- `EXIT_REVIEW`
- `HOLD_REVIEW`
- `INSUFFICIENT_DATA`

There are no execution actions in this phase.

## Arbitration Rules

Rules are deterministic and intentionally conservative:

- Risk `BLOCK` beats all support.
- Capital `BLOCK` beats trade support.
- Exit `BLOCK` blocks entry interpretation.
- Context `SUPPORT` alone cannot approve a trade review.
- Most brains `NO_SIGNAL` resolves to `INSUFFICIENT_DATA`.
- Risk `CAUTION` plus Capital/Exit `SUPPORT` resolves to `WATCH`.
- All key protective brains `SUPPORT` resolves to `PAPER_CANDIDATE_REVIEW`, not execution.
- Position session with adverse Risk/Exit context resolves to `EXIT_REVIEW`.
- Remaining disagreements resolve to `WATCH`.

## Conflict Detection

V3.4 records basic conflicts only:

- `support_vs_block`
- `caution_vs_support`

Hard protective brains win by rule:

- Risk wins Risk `BLOCK` conflicts.
- Capital wins Capital `BLOCK` conflicts.
- Exit wins Exit `BLOCK` conflicts.
- Protective `CAUTION` can force `WATCH`.

Conflicts are recorded but not resolved into execution decisions.

## Runtime Integration

The flow is:

Neural event -> Mesh Session -> Shared Awareness -> Multi-Brain Opinions -> Coordinator Input Bundle -> Mesh Coordinator Decision

Integration point:

- `MultiBrainConsumptionService.consume_session_with_conn()` calls `MeshCoordinatorDecisionService.judge_session_with_conn()` when the V3.4 tables exist.

System behavior:

- System OFF blocks publishing and direct mesh coordinator mutation.
- System ON allows derived mesh decisions from real bundles.
- Dashboard reads remain allowed.

## API

Dashboard routes:

- `GET /dashboard/api/v2/mesh-coordinator`
- `GET /dashboard/api/v2/mesh-coordinator/{decision_id}`
- `GET /dashboard/api/v2/mesh-coordinator/session/{session_id}`

All routes return `mock_data=false`.

## Dialogue

`BrainDialogueService` materializes source-backed coordinator messages from:

- `mesh_coordinator_decisions`
- `mesh_conflict_records`

Example messages:

- `Coordinator: Final mesh decision: WATCH with action WATCH because Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.`
- `Coordinator: Conflict detected: RISK_BRAIN CAUTION vs CAPITAL_BRAIN SUPPORT. RISK_BRAIN wins.`

## Safety

V3.4 does not mutate:

- `live_orders`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_intents`
- `orders_v2`
- `fills_v2`
- canonical `positions`
- paper capital balances
- `risk_decisions`
- `exit_plans`
- eligibility outcomes
- legacy `coordinator_decisions`
- `brain_outputs`

## Next Phase

The next safe phase is Position-Aware Reactions / Capital Brain Upstream, after ChatGPT review.
