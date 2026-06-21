# V2 Neural Mesh Part 4C-J: Runtime Brain Producer Adapter Skeleton

## 1. Purpose
Part 4C-J adds the first non-executing runtime Brain producer. It reads quality-gated runtime Signals and writes runtime Brain Outputs that interpret those Signals without creating Coordinator decisions, order intents, orders, fills, positions, risk approvals, exit plans, or live actions.

## 2. Why This Matters
Before this phase, POLYBOT had runtime producer evidence but all Brain Outputs were dry-run generated. The mesh could observe runtime Signals, but it could not yet produce runtime Brain truth. This phase closes that gap while preserving Paper blockers.

## 3. Scope
Implemented:
- Runtime Brain adapter contract.
- Runtime Signal candidate selection.
- Deterministic Brain Output classification.
- Runtime Brain run persistence.
- Runtime Brain input persistence.
- Runtime Brain API and dashboard endpoint.
- Mesh dashboard runtime Brain layer.
- Dry-run/runtime provenance refresh after Brain Output creation.
- Producer health and mesh blocker refresh hooks.

Explicitly not implemented:
- Runtime Coordinator decisions.
- Strategy routing.
- Risk approval.
- Exit plans.
- Paper trading.
- Live trading.
- AI calls.
- Order intents, orders, fills, or positions.

## 4. Runtime Brain Adapter Contract
The adapter only reads Signals that are:
- runtime generated
- not dry-run generated
- marked `generated_by=runtime`
- backed by signal quality
- backed by signal processing state
- backed by lineage coverage
- backed by dry-run/runtime provenance analysis

Each produced Brain Output is marked:
- `brain=runtime_brain_adapter`
- `generated_by=runtime`
- `producer_name=runtime_brain_adapter`
- `generated_from=runtime_signal`
- `is_runtime_generated=true`
- `is_dry_run_generated=false`
- `source_signal_ids=[...]`
- `paper_allowed=false`
- `execution_allowed=false`

## 5. Brain Decision Logic
The adapter uses deterministic non-AI logic:
- `OBSERVE`: high-quality runtime Signal with trusted lineage and no blockers.
- `WEAK_SIGNAL`: stale or weak runtime Signal.
- `NO_TRADE_CANDIDATE`: runtime Signal can be observed, but missing market link or other requirements block Paper evidence.

All outputs are interpretive only. They are not trade decisions.

## 6. Persistence
Migration `0076_v2_neural_mesh_runtime_brain_producer_adapter.sql` adds:
- `runtime_brain_producer_runs`
- `runtime_brain_output_inputs`

The migration includes safety checks that keep:
- `paper_ready_before=false`
- `paper_ready_after=false`
- `orders_created=0`
- `order_intents_created=0`
- `fills_created=0`
- `positions_created=0`
- `live_actions_created=0`
- `coordinator_runtime_decisions=0`

## 7. API Routes
- `POST /brain/runtime/run`
- `GET /dashboard/api/v2/runtime-brain`

## 8. Dashboard / Mesh Fields
The runtime Brain dashboard exposes:
- latest run
- runtime Brain Outputs
- dry-run Brain Outputs
- runtime Brain Outputs created in latest run
- eligible runtime Signals
- weak runtime Signals
- no-trade candidates
- paper readiness false
- safety counters
- remaining blockers

`/dashboard/api/v2/mesh` now includes:
- `layers.runtime_brain`
- `flow.runtime_brain`
- `readiness.runtime_brain_summary`

## 9. Safety Rules
This phase keeps:
- `paper_ready=false`
- no Coordinator runtime decisions
- no order intents
- no paper orders
- no shadow orders
- no live orders
- no fills created by this phase
- no positions
- no live actions

Dry-run Brain Outputs remain separate from runtime Brain Outputs.

## 10. Current Runtime Result
Runtime verification created 100 runtime Brain Outputs from runtime Signals:
- runtime Brain Outputs: 100
- dry-run Brain Outputs: 48
- runtime Coordinator Decisions: 0
- dry-run Coordinator Decisions: 12
- `paper_ready=false`
- orders/intents/live actions created by the run: 0

## 11. Remaining Blockers
Paper remains blocked by:
- no runtime Coordinator decisions
- no Risk Core
- no Exit Foundation
- missing orderbook snapshots
- no Paper eligible Signals
- low linking and lineage coverage
- stale Signals
- env/persisted mode mismatch
- kill-switch mismatch

## 12. Recommended Next Phase
V2 Neural Mesh Part 4C-K: Runtime Coordinator Decision Skeleton.

That phase should consume runtime Brain Outputs and create non-executing Coordinator decisions with `execution_allowed=false`, while preserving all Paper and execution blockers.
