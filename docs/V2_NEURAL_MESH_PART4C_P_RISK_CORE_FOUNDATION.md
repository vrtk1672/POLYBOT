# V2 Neural Mesh Part 4C-P Risk Core Foundation

## Purpose

Part 4C-P adds a thesis-derived Risk Core layer before any Paper eligibility can exist. It evaluates runtime Thesis Profiles, persists deterministic Risk Decisions, exposes dashboard truth, and keeps all execution surfaces disabled.

## Scope

Implemented:

- Risk Core contract and run result contract.
- Thesis Profile risk evaluation service.
- `risk_decisions` persistence.
- `risk_gate_runs` audit fields for 4C-P batch runs.
- Default risk limits for max position size, max loss, confidence threshold, spread, liquidity, and daily exposure placeholder.
- API routes for risk evaluation, recent Risk Decisions, and Risk Core dashboard truth.
- Mesh dashboard and mesh blocker integration.

Not implemented:

- Exit Foundation.
- Paper Eligibility Gate.
- Paper Intent Gate.
- Paper Execution.
- Capital allocator.
- Live execution.

## Contract

Each Risk Decision stores:

- `risk_decision_id`
- `thesis_id`
- optional `market_id`
- `decision`
- `risk_status`
- aggregate and component risk scores
- max position size and max loss defaults
- blockers, warnings, risk reasons, and required missing evidence
- source thesis status and optional orderbook snapshot reference
- `paper_candidate_allowed=false`
- `execution_allowed=false`
- `exit_required=true`
- runtime provenance flags

Allowed decisions:

- `APPROVE`
- `REJECT`
- `BLOCK`
- `WARN_ONLY`
- `ERROR`

Allowed statuses:

- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`
- `BLOCKED`
- `ERROR`

## Risk Limits

Defaults:

- `max_position_size=10.00` paper units
- `max_loss=5.00` paper units
- `confidence_threshold=0.60`
- `max_spread=0.08`
- `min_liquidity_score=0.25`
- `daily_exposure_limit=50.00` paper units placeholder

These are persisted as Risk Core defaults only. They do not allocate capital and do not create orders.

## Risk Rules

Risk Core blocks:

- blocked thesis
- incomplete thesis
- weak thesis
- missing market ID
- missing or stale orderbook
- missing signal-market binding
- weak lineage/provenance
- confidence below threshold
- spread above threshold
- liquidity below threshold

Risk Core warns on:

- missing Exit Foundation
- daily exposure placeholder only

Even future risk-layer approvals remain:

- `paper_candidate_allowed=false`
- `execution_allowed=false`
- `exit_required=true`

## Dashboard Truth

New endpoints:

- `POST /risk/core/evaluate`
- `GET /risk/decisions/recent`
- `GET /dashboard/api/v2/risk-core`

Mesh additions:

- `layers.risk_core`
- `flow.risk_core`
- `readiness.risk_summary`

Mesh blocker changes:

- `NO_RISK_CORE` resolves only when `risk_decisions > 0`.
- `RISK_DECISIONS_ALL_BLOCKED` activates when all decisions are blocked.
- `RISK_CORE_MISSING_DATA` activates when missing evidence dominates.
- `RISK_CORE_APPROVALS_BLOCKED_BY_EXIT` activates only if risk approvals exist while Exit Foundation is missing.

## Safety

This phase does not create orders, order intents, fills, positions, exit plans, strategy routes, Paper candidates, or live actions. Paper readiness and execution remain false.

