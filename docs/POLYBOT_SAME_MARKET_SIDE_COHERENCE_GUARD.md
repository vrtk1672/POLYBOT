# POLYBOT Same-Market Side Coherence Guard

## Purpose

Prevent accidental Paper exposure on both YES and NO for the same market unless an explicit, source-backed strategic rationale exists.

This is a Paper risk guard. It does not create trades, close trades, alter historical positions, or infer strategy intent.

## Guard Model

For every proposed Paper entry, the guard evaluates:

- open same-side paper positions
- open opposite-side paper positions
- active same-side paper intents
- active opposite-side paper intents
- opposing YES/NO candidates in the same intent batch
- recently closed opposite-side paper trades from the same run/correlation
- active token locks for the market
- active capital locks for the market

The durable audit table is `same_market_side_guard_decisions`.

## Decisions

- `ALLOW`: no coherence conflict, or explicit source-backed rationale exists.
- `BLOCK`: opposing-side exposure or opposing batch candidate exists without valid rationale.
- `REVIEW`: same-side duplicate exposure or recent same-run opposite close requires review.

Primary blocker reasons:

- `SAME_MARKET_OPPOSING_SIDE_BLOCK`
- `SAME_MARKET_OPPOSING_INTENT_BLOCK`
- `SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW`
- `SAME_MARKET_RECENT_OPPOSING_SIDE_REVIEW`
- `MISSING_STRATEGIC_RATIONALE`
- `RATIONALE_NOT_SOURCE_BACKED`

## Allowed Rationales

Only exact, source-backed rationales can allow opposing-side exposure:

- `HEDGE_RATIONALE`
- `ARBITRAGE_RATIONALE`
- `PARTIAL_EXIT_RATIONALE`
- `MARKET_MAKING_RATIONALE`
- `EXPOSURE_REDUCTION_RATIONALE`
- `POSITION_REPAIR_RATIONALE`

The guard can recognize rationale from explicit evidence/metadata or a coordinator decision, but it must verify that the cited source row exists. Free-text or missing-source rationale is not enough.

## Runtime Integration

`PaperIntentGateService.build_intents()` runs the guard before inserting `paper_intents`.

If the guard returns `BLOCK` or `REVIEW`, the candidate becomes a `no_trade_log` row with the guard decision in evidence. No Paper intent is created.

`PaperExecutionService._validate_intents()` reruns the guard before capital precheck and execution. This protects old or externally inserted bad intents.

## Dashboard And Forensics

Dashboard endpoints:

- `GET /dashboard/api/v2/same-market-side-guard`
- `GET /dashboard/api/v2/same-market-side-guard/{market_id}`

Paper trade forensics now includes:

- `same_market_guard_decision`
- `same_market_guard_decisions`
- `same_market_guard_status`
- `same_market_guard_lineage`

Brain dialogue materializes source-backed messages from guard decisions under component `Same-Market Guard`.

## Safety Boundary

The guard is read-first. It may write guard audit decisions and no-trade rows when runtime services are invoked, but it does not create orders, fills, positions, live orders, or real orders.

Security governance status for this phase: `YELLOW_ACCEPTED_BY_OPERATOR`.
