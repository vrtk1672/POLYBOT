# V2 Neural Mesh Part 4C-S/X: Paper Intent Gate + No-Trade Ledger

## Purpose

Part 4C-S/X adds the safe boundary after Paper Eligibility:

- `ELIGIBLE` candidates may become non-executing Paper Intent records.
- blocked, ineligible, incomplete, or insufficient candidates become No-Trade ledger records.
- every candidate is accounted for by exactly one safe outcome in the run result.

This phase does not implement Paper Execution, Paper orders, order intents, fills, positions, signing, capital allocation, live actions, or shadow actions.

## Runtime Smoke Precondition

The Q/R runtime routes were rebuilt/restarted before this implementation. The following routes returned HTTP 200:

- `GET /healthz`
- `GET /runtime/health`
- `GET /exit/plans/recent`
- `GET /dashboard/api/v2/exit-foundation`
- `GET /paper/eligibility/recent`
- `GET /dashboard/api/v2/paper-eligibility`
- `GET /dashboard/api/v2/mesh`
- `GET /dashboard/api/v2/mesh-blockers`

## Contract

`PaperIntentGateService` loads runtime Paper Eligibility candidates and ignores dry-run-generated candidates by default.

Paper Intent hard requirements:

- `status=ELIGIBLE`
- `eligibility_id`, `thesis_id`, `risk_decision_id`, `exit_plan_id`, `market_id`, and `side`
- `orderbook_snapshot_id`
- `risk_approved=true`
- `exit_ready=true`
- `lineage_trusted=true`
- `not_dry_run=true`
- no hard blockers or missing requirements

Paper Intent safety invariants:

- `paper_only=true`
- `live=false`
- `execution_allowed=false`
- `order_intent_created=false`

No-Trade Ledger behavior:

- every non-eligible or incomplete candidate is recorded with blockers, missing requirements, evidence, source status, and category.
- No-Trade records link to eligibility, thesis, risk, exit, market, and side where available.
- blocked risk and blocked exit candidates cannot create Paper Intents.

## APIs

- `POST /paper/intents/build`
- `GET /paper/intents/recent`
- `GET /no-trade/recent`
- `GET /dashboard/api/v2/paper-intents`
- `GET /dashboard/api/v2/no-trade`

## Mesh

Mesh dashboard now includes:

- `layers.paper_intents`
- `flow.paper_intents`
- `readiness.paper_intent_summary`
- `layers.no_trade`
- `flow.no_trade`
- `readiness.no_trade_summary`

Mesh blockers now include:

- `NO_PAPER_INTENTS`
- `PAPER_INTENTS_BLOCKED_BY_ELIGIBILITY`
- `NO_TRADE_LEDGER_MISSING`
- `UNACCOUNTED_CANDIDATES`

`EXECUTION_NOT_ALLOWED` remains active and `paper_ready` remains false.

## Current Runtime Result

Current runtime truth after this phase:

- Paper Eligibility candidates: `100`
- Eligible candidates: `0`
- Blocked candidates: `100`
- Paper Intents: `0`
- No-Trade records from S/X: `100`
- Accounted candidates: `100`
- Unaccounted candidates: `0`
- Paper orders: `0`
- Shadow orders: `0`
- Live orders: `0`
- Order intents: absent
- Positions: `0`
- Historical `fills_v2`: `1`, unchanged

## Safety

This phase is Paper-intent-only and No-Trade-ledger-only. It does not create executable artifacts and does not make Paper ready.
