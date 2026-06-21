# V2 Neural Mesh Part 4C-Q/R: Exit Foundation + Paper Eligibility

## Purpose

Part 4C-Q/R combines the already implemented Exit Foundation with the new Paper Eligibility Gate. It proves that a future Paper candidate must have thesis, risk, exit, orderbook, binding, lineage, and runtime provenance before it can become eligible.

This phase does not create Paper intents, order intents, orders, fills, positions, shadow actions, live actions, strategy routes, signing, or execution.

## Exit Foundation Contract

Exit Foundation reads runtime `risk_decisions` and linked `thesis_profiles` / `orderbook_snapshots`, then writes `exit_plans` with `created_from='exit_foundation'`.

Exit plans are:

- `COMPLETE` only when risk is approved and market, side, fresh orderbook, target, stop, time, invalidation, emergency, and liquidity rules exist.
- `BLOCKED` when risk is BLOCK/REJECT/ERROR or the setup must not be entered.
- `INCOMPLETE` when non-risk missing evidence prevents a complete plan.

All 4C-Q/R exit plans keep:

- `paper_intent_allowed=false`
- `execution_allowed=false`
- global `paper_ready=false`

## Paper Eligibility Contract

Paper Eligibility reads Exit Foundation plans and joins Risk Core, Thesis Profiles, Coordinator Decisions, Brain Outputs, Signals, signal-market bindings, and orderbook snapshots where available.

`ELIGIBLE` requires all mandatory evidence:

- runtime signal evidence
- runtime brain output evidence
- runtime coordinator decision
- market_id
- side
- trusted signal-market binding
- fresh orderbook snapshot
- thesis profile
- risk decision with `risk_approved=true`
- exit plan with `paper_exit_ready=true`
- trusted lineage / provenance
- non-dry-run evidence

Blocked, incomplete, stale, missing, dry-run, weak-lineage, blocked-risk, or blocked-exit evidence remains persisted as `BLOCKED` or `INCOMPLETE`.

All 4C-R candidates keep:

- `paper_intent_allowed=false`
- `execution_allowed=false`
- global `paper_ready=false`

## API

Added:

- `POST /paper/eligibility/evaluate`
- `GET /paper/eligibility/recent`
- `GET /dashboard/api/v2/paper-eligibility`

Preserved from 4C-Q:

- `POST /exit/plans/build`
- `GET /exit/plans/recent`
- `GET /dashboard/api/v2/exit-foundation`

## Dashboard / Mesh

Mesh now includes:

- `layers.exit_foundation`
- `flow.exit_foundation`
- `readiness.exit_summary`
- `layers.paper_eligibility`
- `flow.paper_eligibility`
- `readiness.paper_eligibility_summary`

Mesh blockers now use Paper Eligibility truth:

- `NO_EXIT_FOUNDATION` resolves only when exit plans exist.
- `NO_PAPER_ELIGIBLE_SIGNALS` resolves only when `eligible_count > 0`.
- `PAPER_ELIGIBILITY_ALL_BLOCKED` activates when all candidates are blocked.
- missing exit/risk/binding/orderbook blockers are surfaced from candidate truth.

## Current Runtime Result

Runtime DB/service verification after migration and one non-executing service run:

- `risk_decisions_checked=100`
- `exit_plans=100`
- `complete_exit_count=0`
- `blocked_exit_count=100`
- `paper_eligibility_candidates=100`
- `eligible_count=0`
- `blocked_count=100`
- `paper_ready=false`
- `paper_intent_allowed_count=0`
- `execution_allowed_count=0`
- `paper_orders=0`
- `shadow_orders=0`
- `live_orders=0`
- `positions=0`
- `fills_v2=1` historical row unchanged

The correct result is blocked eligibility because all current Risk Core decisions are blocked and all exit plans are blocked.

## Safety

This phase is GREEN only as a controlled evidence gate. It does not make POLYBOT Paper-ready. It keeps `EXECUTION_NOT_ALLOWED` active and leaves Paper Intent Gate, Paper Execution, Paper Exit Loop, and Paper PnL out of scope.

## Next Phase

Recommended next phase: 4C-S Paper Intent Gate, but only after ChatGPT review. Current runtime still has zero eligible candidates, so the next practical work may first be evidence recovery for risk/thesis/orderbook/binding/side freshness.
