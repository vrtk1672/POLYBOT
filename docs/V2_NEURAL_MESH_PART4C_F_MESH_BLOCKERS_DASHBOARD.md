# V2 Neural Mesh Part 4C-F: Mesh Blockers Dashboard

## 1. Purpose

Part 4C-F adds a deterministic dashboard truth surface for Paper readiness blockers.

The endpoint answers why POLYBOT is not Paper-ready without fixing the blockers, enabling Paper, creating order intents, creating orders, calling AI, or changing runtime mode.

## 2. Why Mesh Blockers Matter

The Neural Mesh now has Signals, quality gates, processing state, link coverage, lineage coverage, dry-run provenance, Brain Outputs, Coordinator Decisions, and dashboard truth. The next safety need is explicit blocker explanation.

`paper_ready=false` is not enough. Operators need to see:

- which blocker is active
- how severe it is
- what evidence proves it
- which subsystem reported it
- whether it blocks Paper or is only safety info
- what the next correct build step is

## 3. Mesh Blocker Contract

Each blocker has:

- `code`
- `active`
- `severity`
- `category`
- `reason`
- `evidence`
- `source`
- `recommended_next_step`
- `blocks_paper`

Allowed severity:

- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`
- `INFO`

Allowed categories:

- `DATA`
- `SIGNALS`
- `LINKAGE`
- `LINEAGE`
- `PROVENANCE`
- `BRAIN`
- `COORDINATOR`
- `RISK`
- `EXIT`
- `RUNTIME`
- `EXECUTION`
- `DASHBOARD`

## 4. Paper Readiness Logic

`paper_ready` remains `false`.

The dashboard returns:

- `READY` only when no active Paper blockers exist
- `BLOCKED` when any active critical or high Paper blocker exists
- `DEGRADED` when only lower-severity Paper blockers exist
- `UNKNOWN` if analysis fails

Part 4C-F is diagnostic only. It does not certify Paper readiness.

## 5. Required Blockers

The analyzer evaluates these blocker codes:

- `ORDERBOOK_SNAPSHOTS_MISSING`
- `SIGNAL_PROCESSING_INCOMPLETE`
- `SIGNAL_QUALITY_GATE_BLOCKED`
- `SIGNAL_LINKING_TOO_LOW`
- `SIGNALS_STALE_HIGH`
- `SIGNAL_LINEAGE_COVERAGE_LOW`
- `BRAIN_OUTPUTS_DRY_RUN_ONLY`
- `COORDINATOR_DECISIONS_DRY_RUN_ONLY`
- `NO_RUNTIME_BRAIN_OUTPUTS`
- `NO_RUNTIME_COORDINATOR_DECISIONS`
- `DRY_RUN_EVIDENCE_BLOCKED_FROM_PAPER`
- `NO_THESIS_PROFILES`
- `NO_RISK_CORE`
- `NO_EXIT_FOUNDATION`
- `NO_PAPER_ELIGIBLE_SIGNALS`
- `ENV_PERSISTED_MODE_MISMATCH`
- `ENV_PERSISTED_KILL_SWITCH_MISMATCH`
- `EXECUTION_NOT_ALLOWED`
- `ORDER_INTENTS_ABSENT`
- `PAPER_ORDERS_ZERO`
- `LIVE_DISABLED`

`LIVE_DISABLED`, `PAPER_ORDERS_ZERO`, and `ORDER_INTENTS_ABSENT` are safety confirmations, not Paper blockers.

## 6. Evidence Sources

The Mesh Blockers Dashboard reads existing DB/runtime truth from:

- runtime health and permissions
- `orderbook_snapshots`
- Signal Quality summary
- Signal Processing summary
- Link Coverage summary
- Lineage Coverage summary
- Dry Run Provenance summary
- Position Thesis summary
- order/order-intent table counts
- coordinator `execution_allowed` counts
- dedicated future certification evidence tables, if they exist

No fake data is introduced.

## 7. API Route

`GET /dashboard/api/v2/mesh-blockers`

Response includes:

- `mock_data=false`
- `paper_ready=false`
- `overall_status`
- `blocked_by`
- `blockers`
- `info`
- `counts`
- `last_updated`
- `analysis_status`

## 8. Mesh Dashboard Integration

`GET /dashboard/api/v2/mesh` now includes:

- `layers.mesh_blockers`
- `flow.mesh_blockers`
- `readiness.overall_status`
- `readiness.blocker_counts`
- `readiness.top_blockers`
- canonical blocker codes in `readiness.blocked_by`

Existing layers remain intact:

- `signal_quality`
- `signal_processing`
- `link_coverage`
- `lineage_coverage`
- `dry_run_provenance`

## 9. Safety Rules

Part 4C-F does not:

- enable Paper
- enable Live
- create orders
- create order intents
- sign requests
- call AI
- fix blockers
- fabricate dashboard values
- treat dry-run evidence as production Paper evidence

`paper_ready=false` is hard-preserved.

## 10. Example

```json
{
  "mock_data": false,
  "paper_ready": false,
  "overall_status": "BLOCKED",
  "blocked_by": [
    "ORDERBOOK_SNAPSHOTS_MISSING",
    "SIGNAL_LINKING_TOO_LOW",
    "BRAIN_OUTPUTS_DRY_RUN_ONLY",
    "COORDINATOR_DECISIONS_DRY_RUN_ONLY",
    "NO_EXIT_FOUNDATION"
  ]
}
```

## 11. What Is Explicitly Not Included

This phase does not implement:

- Market Technical Truth
- orderbook snapshotter
- Risk Core
- Exit Foundation
- Thesis population
- runtime Brain producer adapters
- runtime Coordinator producer loop
- Paper Evidence Loop
- Paper trading
- Live trading

## 12. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Part 4C-G: Runtime Brain Producer Adapter Foundation.

Goal: produce non-executing runtime Brain Outputs from quality-gated, linked, lineage-trusted Signals while preserving dry-run/runtime provenance separation and `paper_ready=false`.
