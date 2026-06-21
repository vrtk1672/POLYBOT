# V2 Neural Mesh Part 4C-Q: Exit Foundation

## Purpose

4C-Q adds the first non-executing Exit Foundation layer before Paper readiness.

Hard rule: no entry without exit. Future Paper intent phases must require an `exit_plan_id`; this phase only creates derived exit plan contracts and never creates orders, order intents, fills, positions, paper intents, or live actions.

## Contract

Exit Foundation reads runtime `risk_decisions` and their linked `thesis_profiles` / `orderbook_snapshots`, then creates `exit_plans` with `created_from='exit_foundation'`.

Every plan includes:

- `target_exit`
- `stop_loss`
- `max_hold_seconds`
- `invalidation_rules`
- `emergency_exit_rules`
- `liquidity_exit_check`
- `missing_exit_evidence`
- `blockers`
- runtime provenance flags

## Status Rules

- `BLOCKED`: created for `BLOCK` or `REJECT` risk decisions.
- `INCOMPLETE`: created when required market, side, orderbook, mid price, or risk approval is missing.
- `COMPLETE`: allowed only when risk is approved and market, side, fresh orderbook, target, stop, and rules exist.

Current production reality after the 4C-Q runtime run: 100 exit plans exist, all are `BLOCKED`, and none allow Paper intents or execution.

## Safety Invariants

- `paper_ready=false`
- `paper_intent_allowed=false`
- `execution_allowed=false`
- blocked risk cannot create Paper-ready exits
- missing market/orderbook/side blocks complete exit
- no legacy Exit Cortex evaluator is invoked
- no `exit_intents` are created

## Dashboard And Mesh

New API truth:

- `POST /exit/plans/build`
- `GET /exit/plans/recent`
- `GET /dashboard/api/v2/exit-foundation`

Mesh additions:

- `layers.exit_foundation`
- `flow.exit_foundation`
- `readiness.exit_summary`

Mesh blocker integration:

- `NO_EXIT_FOUNDATION` resolves only when real Exit Foundation plans exist.
- `EXIT_PLANS_ALL_BLOCKED` activates when every plan is blocked.
- `EXIT_PLANS_INCOMPLETE` activates when incomplete plans exist.
- `EXIT_MISSING_ORDERBOOK` activates when fresh orderbook evidence is missing.
- `EXIT_MISSING_RISK_APPROVAL` activates when Risk Core did not approve.

## Current Result

Exit Foundation exists and is honest: all current risk decisions are blocked, so all current exit plans are blocked. This resolves the absence of Exit Foundation without weakening Paper gates.

Paper remains blocked by missing Paper Eligibility, blocked Risk, missing/weak evidence, stale orderbook state, and runtime configuration blockers.
