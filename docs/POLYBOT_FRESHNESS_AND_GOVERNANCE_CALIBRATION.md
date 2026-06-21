# POLYBOT Freshness Gate + Governance Blocker Calibration

Date: 2026-06-04

Security governance status: `YELLOW_ACCEPTED_BY_OPERATOR`

## Purpose

This phase makes freshness a first-class governance input.

Fresh data may support Paper action. Historical data may explain decisions. Stale data may only block, request refresh, or support forensics.

The phase also calibrates lifecycle governance blockers so:

- critical blockers remain hard blockers,
- optional missing context does not hard-block by itself,
- old paper intents and old lifecycle/governance decisions cannot authorize Paper,
- same-market historical closed exposure is informational only,
- active same-market exposure still blocks or reviews precisely.

## Freshness Model

The new freshness governance service evaluates source freshness for lifecycle plans, governance decisions, paper intents, paper candidates, and source-backed lifecycle plan inputs.

Freshness statuses:

- `FRESH`
- `STALE`
- `EXPIRED`
- `HISTORICAL_ONLY`
- `REFRESH_REQUIRED`
- `UNKNOWN_FRESHNESS`

Default TTLs:

- Orderbook, executable price, trusted orderbook: 180 seconds
- Market identity, token identity, risk, exit, capital, payout/odds, exit-hold, capital efficiency, lifecycle plan, lifecycle governance, same-market guard, paper intent, paper candidate: 600 seconds
- Historical closed trades: no authorization TTL; forensics/memory only

Critical source types cannot authorize Paper if stale, expired, unknown, or requiring refresh:

- market identity
- token identity
- trusted orderbook
- executable price
- risk decision
- exit plan
- capital evaluation
- same-market guard
- lifecycle plan
- lifecycle governance
- paper intent / paper candidate

## Stale Blockers

The governance gate can now emit precise stale-data blockers:

- `STALE_PAPER_INTENT`
- `STALE_PAPER_CANDIDATE`
- `STALE_LIFECYCLE_PLAN`
- `STALE_GOVERNANCE_DECISION`
- `STALE_RISK_DECISION`
- `STALE_EXIT_PLAN`
- `STALE_CAPITAL_EVALUATION`
- `STALE_ORDERBOOK`
- `STALE_MARKET_IDENTITY`
- `STALE_SAME_MARKET_GUARD`
- `STALE_PAYOUT_ODDS`
- `STALE_EXIT_HOLD`
- `STALE_CAPITAL_EFFICIENCY`
- `REFRESH_REQUIRED_BEFORE_EXECUTION`

## Paper Intent / Execution Safety

Existing old paper intents are preserved but cannot execute silently.

Before Paper execution, stale intents now receive:

- `STALE_PAPER_INTENT`
- `REFRESH_REQUIRED_BEFORE_EXECUTION`

Execution remains lifecycle-governed and must still pass existing Risk, Exit, Capital, and Paper lineage checks.

## Same-Market Calibration

The same-market guard was tightened around active exposure and relaxed around stale historical artifacts.

Hard/review blockers are now precise:

- `SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK`
- `SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK`
- `SAME_MARKET_BATCH_CONFLICT_BLOCK`
- `SAME_MARKET_RECENT_CLOSE_REVIEW`
- `SAME_MARKET_HISTORICAL_ONLY`
- `SAME_MARKET_RATIONALE_MISSING`
- `SAME_MARKET_RATIONALE_NOT_SOURCE_BACKED`

Old unexecuted intents outside the active intent TTL are treated as stale historical context. They are not allowed to authorize action, and they do not hard-block solely as active exposure.

Open opposite positions and fresh opposite intents still block.

## Risk Blocker Precision

Generic `RISK_BLOCKED` is retained for compatibility, but lifecycle governance now records precision where possible:

- `RISK_BLOCKED_BAD_LIQUIDITY`
- `RISK_BLOCKED_SPREAD`
- `RISK_BLOCKED_STALE_DATA`
- `RISK_BLOCKED_NO_TRUSTED_ORDERBOOK`
- `RISK_BLOCKED_MISSING_EXECUTABLE_PRICE`
- `RISK_BLOCKED_LOW_CONFIDENCE`
- `RISK_BLOCKED_NO_EDGE`
- `RISK_BLOCKED_LINEAGE`
- `RISK_BLOCKED_UNKNOWN`

Stale data is represented as stale/refresh blockers instead of being hidden behind a generic risk block.

## Capital Blocker Precision

Capital hard blocks are reserved for real capital/accounting constraints:

- `CAPITAL_BLOCKED_RECONCILIATION`
- `CAPITAL_BLOCKED_INSUFFICIENT_BALANCE`
- `CAPITAL_BLOCKED_MAX_EXPOSURE`
- `CAPITAL_BLOCKED_MAX_OPEN_POSITIONS`
- `CAPITAL_BLOCKED_DAILY_LOSS`

Weak efficiency or missing optional context should remain watch/review input, not a hard capital block by itself.

## Actionability Ladder

Lifecycle governance keeps the existing ladder:

- `HARD_BLOCK`
- `NO_TRADE`
- `WATCH_FOR_CONFIRMATION`
- `ACTIONABLE_SMALL_PAPER`
- `ACTIONABLE_STANDARD_PAPER`
- `COMPLETE_HIGH_CONFIDENCE`

Calibration rule:

- Critical blockers force `HARD_BLOCK`.
- Poor economics can produce `NO_TRADE`.
- Optional context missing can produce `WATCH_FOR_CONFIRMATION`.
- `ACTIONABLE_SMALL_PAPER` requires all critical blockers clear, fresh identity/book/price, fresh lifecycle governance, same-market guard clear, and existing official gates passing.
- `ACTIONABLE_STANDARD_PAPER` and `COMPLETE_HIGH_CONFIDENCE` require stronger completeness and agreement.

This phase does not create actionable plans artificially.

## Dashboard/API

New endpoints:

- `GET /dashboard/api/v2/freshness-governance`
- `GET /dashboard/api/v2/governance-calibration`
- `POST /freshness-governance/evaluate`

All return `mock_data=false`.

## Forensics / Dialogue

Paper forensics now exposes:

- freshness checks,
- governance freshness,
- blocker classification,
- actionability/freshness lineage.

Brain dialogue now reports precise same-market blocker reasons without inventing rationale.

## Safety

No live trading was enabled.

No shadow-live mode was enabled.

No Paper orders, fills, positions, closes, capital ledger rows, or balances were mutated by this phase. Only derived freshness/governance records were created.

One process caveat: raw `docker-compose.yml` was displayed during early inspection. It contained repository configuration and environment placeholders/defaults; no `.env` contents or secret values were printed.

