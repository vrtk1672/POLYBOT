# POLYBOT Lifecycle Governance Gate

## Purpose

The Lifecycle Governance Gate makes the Trade Lifecycle Reasoning Mesh govern the Paper path.

Core rule:

- Mesh decides.
- Paper Intent and Paper Execution execute only after lifecycle governance authorizes them.
- Critical blockers block.
- Optional missing context lowers actionability, but does not hard-block alone.

The gate writes derived governance records only. It does not create paper orders, fills, positions, closes, or capital ledger rows.

## Actionability Ladder

Allowed classes:

- `HARD_BLOCK`: Paper Intent and Paper Execution are denied.
- `NO_TRADE`: not dangerous, but not worth trading.
- `WATCH_FOR_CONFIRMATION`: monitor only; optional or context-dependent inputs are missing.
- `ACTIONABLE_SMALL_PAPER`: critical blockers are clear and existing gates may continue for small/default Paper.
- `ACTIONABLE_STANDARD_PAPER`: stronger lifecycle quality; existing gates may continue for normal Paper.
- `COMPLETE_HIGH_CONFIDENCE`: complete mesh context, observational unless requested through Paper gates.

Actionable classes do not bypass Risk, Exit, Eligibility, Capital, same-market guard, or State Governor.

## Missing Input Classification

Critical blockers include:

- `PRICE_MISSING`
- `EXECUTABLE_PRICE_MISSING`
- `TRUSTED_ORDERBOOK_MISSING`
- `TOKEN_MISSING`
- `SIDE_MISSING`
- `MARKET_ID_MISSING`
- `CONDITION_ID_MISSING`
- `CAPITAL_RECONCILIATION_RED`
- `CAPITAL_LOCK_MISSING`
- `SAME_MARKET_OPPOSING_SIDE_BLOCK`
- `SAME_MARKET_OPPOSING_INTENT_BLOCK`
- `RISK_BLOCKED`
- `EXIT_BLOCKED`
- `CAPITAL_BLOCKED`
- `PAPER_LINEAGE_RED`
- `OPEN_POSITION_WITHOUT_FILL`
- `BOOK_UNAVAILABLE_FOR_OPEN_POSITION`
- `STALE_MARKET`
- `TOKEN_NOT_FOUND`
- `CLOB_NO_BOOK`

Optional context includes:

- `WHALE_CONTEXT_MISSING`
- `NEWS_CONTEXT_MISSING`
- `SOCIAL_CONTEXT_MISSING`
- `MEMORY_CONTEXT_MISSING`
- `FAIR_PROBABILITY_MISSING`
- `AI_CONTEXT_MISSING`
- `SOURCE_RELIABILITY_MISSING`

Context-dependent inputs include:

- `TIME_TO_RESOLUTION_MISSING`
- `RULES_RISK_UNKNOWN`
- `EXIT_PRICE_MISSING`
- `LIQUIDITY_DEPTH_MISSING`
- `SAME_MARKET_GUARD_MISSING`
- `EXIT_HOLD_MISSING`
- `CAPITAL_EFFICIENCY_MISSING`

## Integrations

Paper Intent:

- `PaperIntentGateService.build_intents()` calls `LifecycleGovernanceGateService.authorize_paper_intent()`.
- Denied candidates become no-trade records with lifecycle governance blockers.

Paper Execution:

- `PaperExecutionService._validate_intents()` calls `authorize_paper_execution()` before capital precheck and execution.
- Old `CREATED` intents cannot execute silently without lifecycle authorization.

Legacy Runtime Paper:

- The old `RuntimePaperTradingService` `ExecutionAwarePaperService.record_cycle()` path is blocked.
- Legacy staged paper order/position command mutations are denied unless lifecycle governance explicitly authorizes them.

Dashboard/API:

- `GET /dashboard/api/v2/lifecycle-governance`
- `GET /dashboard/api/v2/lifecycle-governance/{decision_id}`
- `POST /lifecycle-governance/evaluate`

Forensics:

- Paper trade forensics now includes latest lifecycle governance actionability, blockers, optional missing context, and intent/execution allowance flags.

Dialogue:

- Brain Dialogue can materialize `Lifecycle Governance` events from `lifecycle_governance_decisions`.

## Safety

The governance gate is derived truth only. It must not mutate:

- paper orders
- paper fills
- paper positions
- paper closes
- paper capital ledger
- live orders
- balances

Rollback:

```sql
DROP TABLE IF EXISTS lifecycle_governance_sources;
DROP TABLE IF EXISTS lifecycle_governance_decisions;
```
