# POLYBOT Risk Evidence Mesh + Source-Backed Edge Calibration

Date: 2026-06-05

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Purpose

Risk now has a derived evidence-quality layer instead of relying only on legacy chain-completeness risk decisions.

The legacy Risk Core remains conservative and non-executing. The new Risk Evidence Mesh evaluates whether a candidate, intent, position, or lifecycle plan has:

- fresh critical evidence
- source-backed supporting evidence
- optional missing context
- blocking evidence
- a source-backed edge type

It does not create Paper intents, orders, fills, positions, closes, capital ledger rows, live orders, or balance changes.

## Evidence Classes

Critical evidence must be present and fresh before Paper can be authorized:

- market id
- condition id
- side
- token id
- active fresh trusted orderbook
- executable price
- spread/liquidity within risk bounds
- no stale critical source
- no same-market active conflict
- no capital block

Supporting evidence strengthens the case:

- payout/odds
- exit-hold reasoning
- capital efficiency
- lifecycle governance
- news context

Optional context is useful but no longer hard-blocks by itself:

- whale context
- memory context
- social context
- fair probability
- news/AI context when not strategy-critical

## Risk Decisions

Risk Evidence Mesh emits:

- `RISK_SUPPORT`
- `RISK_WATCH`
- `RISK_REVIEW`
- `RISK_BLOCK`

Critical blockers still produce `RISK_BLOCK`. Optional missing context produces `RISK_WATCH` or `RISK_REVIEW`, not a hard block.

## Edge Source Types

Allowed source-backed edge types:

- `PRICE_PAYOUT_ASYMMETRY`
- `NEWS_REPRICING_SIGNAL`
- `WHALE_SIGNAL`
- `ORDERBOOK_LIQUIDITY_SETUP`
- `NEAR_RESOLUTION_PAYOUT`
- `CAPITAL_EFFICIENCY_SETUP`
- `RULES_CLARITY_EDGE`
- `AI_CONTEXT_EDGE`
- `MULTI_FACTOR_MESH_EDGE`
- `NO_SOURCE_BACKED_EDGE`
- `UNKNOWN`

No fair probability or expected value is fabricated. Missing fair probability is recorded as optional context unless the strategy explicitly requires it.

## Governance Mapping

Lifecycle Governance now consults the latest Risk Evidence Mesh verdict.

- `RISK_BLOCK` remains a critical hard blocker.
- `RISK_WATCH` and `RISK_REVIEW` do not inherit legacy generic `RISK_BLOCKED`.
- Existing legacy Risk behavior is preserved when no Risk Evidence Mesh evaluation exists.

This preserves safety while preventing optional missing context or partial non-critical lineage from automatically becoming a hard risk block.

## Runtime Smoke Result

Bounded SYSTEM OFF smoke evaluated 25 recent lifecycle plans.

All 25 remained blocked, correctly, because the sampled plans had stale critical orderbook evidence:

- `RISK_BLOCK`: 25
- `RISK_BLOCKED_STALE_CRITICAL_SOURCE`: 25
- Paper/live/capital counts unchanged

This means the calibration did not fake actionability. Fresh runtime data is still required before any Paper authorization can happen.
