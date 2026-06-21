# V2 Neural Mesh Part 4C-I: Runtime Producer Evidence Loop

## Purpose

Part 4C-I moves POLYBOT from dashboard-only mesh truth toward non-executing runtime evidence. It lets existing local producer observations emit runtime Signals and then updates the full 4C truth chain without creating orders, order intents, fills, positions, risk approvals, or Paper readiness.

## What This Phase Does

Flow:

`source_status producer -> runtime Signal -> Signal Quality -> Signal Processing -> Lineage Coverage -> Link Coverage -> Dry Run / Runtime Provenance -> Producer Health -> Mesh Blockers -> Dashboard Truth`

The loop currently uses existing local `source_status` rows as safe producer evidence. It does not call AI models, create external orders, or activate Paper.

## Runtime Evidence Contract

Every runtime evidence Signal created by this loop must include:

- `producer_name`
- `source`
- `correlation_id`
- `raw_payload_ref`
- `generated_from`
- `generated_by=runtime`
- `is_runtime_generated=true`
- `is_dry_run_generated=false`

The evidence is observational only. It is not a trade recommendation and cannot imply execution approval.

## API Routes

- `POST /producers/runtime-evidence/run`
- `GET /dashboard/api/v2/runtime-producer-evidence`
- `GET /dashboard/api/v2/producer-health` now reflects runtime producer evidence.
- `GET /dashboard/api/v2/mesh-blockers` remains honest about remaining Paper blockers.
- `GET /dashboard/api/v2/mesh` includes `layers.runtime_producer_evidence` and `flow.runtime_producer_evidence`.

## Dashboard Fields

The runtime producer evidence dashboard reports:

- latest run
- runtime producers before/after
- dry-run-only producers before/after
- Signals created/updated
- quality/processing/lineage/link/provenance updates
- producer health updated
- mesh blockers updated
- `paper_ready=false`
- orders/order intents/live actions created, which must remain `0`
- remaining blockers

## Safety Rules

- Paper remains disabled.
- Live remains disabled.
- No private keys are used.
- No signing is performed.
- No orders, order intents, fills, positions, or live actions are created.
- Runtime evidence does not remove Risk, Exit, Orderbook, or runtime Brain/Coordinator blockers.
- Dry-run evidence remains separate from runtime evidence.
- `paper_ready` remains false.

## What Is Explicitly Not Included

This phase does not implement:

- Paper trading
- Market Technical Truth
- Orderbook Snapshotter
- Risk Core
- Exit Foundation
- Runtime Brain Producer Adapters
- Runtime Coordinator Decisions
- Opportunity Cortex
- News/Social/Whale/AI expansion

## Readiness Impact

The phase can resolve `PRODUCER_RUNTIME_EVIDENCE_MISSING` when valid local runtime evidence exists. It must not resolve:

- `ORDERBOOK_SNAPSHOTS_MISSING`
- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `NO_RUNTIME_BRAIN_OUTPUTS`
- `NO_RUNTIME_COORDINATOR_DECISIONS`
- `NO_PAPER_ELIGIBLE_SIGNALS`

## Next Phase Recommendation

The next phase should be **V2 Neural Mesh Part 4C-J: Runtime Brain Producer Adapter Skeleton**. It should create non-executing Brain Outputs from quality-gated runtime Signals while preserving `execution_allowed=false` and `paper_ready=false`.
