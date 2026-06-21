# POLYBOT Live Evidence Refresh

Phase: Step 3 of POLYBOT Life Injection

## Purpose

Live Evidence Refresh connects the awakened Brain Mesh to fresh market reality while preserving the non-executing safety boundary.

When SYSTEM ON is active, the autonomous runtime now refreshes:

- orderbook snapshots for relevant active markets
- signal-market binding evidence
- market link validation evidence
- side recovery only when strong YES/NO evidence exists
- dashboard truth for evidence freshness and blocker counts

This phase does not create orders, order intents, fills, positions, paper orders, shadow actions, or live actions.

## Runtime Contract

SYSTEM OFF blocks evidence refresh completely. No orderbook snapshots, signal-market links, side recovery, or evidence refresh run records are created while OFF.

SYSTEM ON allows EvidenceRefreshService to run after Brain Mesh Activation inside the existing MarketService runtime cycle.

Evidence refresh remains data-only:

- live trading stays disabled
- paper execution stays disabled
- shadow execution stays disabled
- execution_allowed stays false
- missing or weak evidence remains blocked

## Service

`EvidenceRefreshService` coordinates:

- orderbook refresh through `OrderbookSnapshotService`
- signal-market binding recovery through `SignalMarketBindingRecoveryService`
- side recovery from trusted signal-market link evidence only
- run summary persistence in `evidence_refresh_runs`
- dashboard summary generation

Side is never defaulted to YES or NO. It is recovered only when a trusted link has one unambiguous `matched_side` value.

## Dashboard Truth

`GET /dashboard/api/v2/evidence-refresh` returns:

- `mock_data=false`
- allowed and active state
- latest run status and timestamp
- markets checked
- orderbook snapshots created
- fresh/stale orderbook counts
- binding created/refreshed/rejected counts
- side recovery count
- blocker counts
- execution deltas, all expected to be zero

## Safety

This phase preserves:

- SYSTEM OFF as the strongest autonomous runtime block
- DATA_ONLY runtime mode
- no paper/live/shadow execution
- no order/fill/position mutation
- no fake orderbook rows
- no weak binding promotion
- no invented market, token, condition, snapshot, or side

Downstream Risk, Exit, and Eligibility may remain blocked after evidence refresh. That is safe and expected when blocker evidence is still valid.
