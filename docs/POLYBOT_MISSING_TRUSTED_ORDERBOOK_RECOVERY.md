# POLYBOT Missing Trusted Orderbook Recovery

Date: 2026-06-02

## Purpose

This note describes the controlled recovery path for candidates blocked by missing
trusted orderbook evidence.

The recovery path is evidence-only. It does not create paper intents, orders,
fills, positions, live orders, or real orders.

## Root Cause Found

The active dashboard blocker named `MISSING_TRUSTED_ORDERBOOK` maps to the
canonical candidate blocker `MISSING_FRESH_ORDERBOOK` in the current tables.

The live database showed:

- `MISSING_TRUSTED_ORDERBOOK`: 0 raw candidate rows
- `MISSING_FRESH_ORDERBOOK`: 6579 raw candidate rows
- Candidates with no market id: 5192
- Candidates with market but no usable expected token or side: 1356
- Candidates with stale side/token orderbook evidence: 31

The only recoverable class for this layer is the last class: candidates with a
market, side, expected token, trusted binding, and stale or missing fresh CLOB
evidence.

Candidates without market id, side, or expected token are not fixed by orderbook
refresh. They need upstream market-link and side recovery.

## Recovery Behavior

`TrustedOrderbookEvidenceService.resolve()` can now run a bounded,
candidate-specific CLOB recovery pass when `refresh_orderbooks=true`.

For each eligible candidate it:

1. Determines the expected CLOB token from market side.
2. Checks market/orderbook availability.
3. Fetches `/book` from the configured Polymarket CLOB host.
4. Normalizes and stores only a real source-backed snapshot.
5. Links trusted evidence only when the snapshot is fresh, side-aware,
   token-aware, liquid enough, and within spread bounds.
6. Records precise rejection reasons such as `CLOB_NO_BOOK`,
   `ORDERBOOK_STALE`, `TOKEN_SIDE_MISMATCH`, `SPREAD_TOO_WIDE`, or
   `LOW_LIQUIDITY`.

If CLOB has no usable book, no snapshot is created and the candidate remains
blocked.

## API

### POST /trusted-orderbook/resolve

Body fields:

- `cycle_id`: operator-supplied run label
- `limit`: bounded candidate limit
- `refresh_orderbooks`: enables candidate-specific CLOB recovery

The endpoint is blocked while SYSTEM is OFF.

### GET /dashboard/api/v2/orderbook-blockers

Returns dashboard truth with:

- `mock_data=false`
- missing trusted/fresh counts
- stale/token mismatch/CLOB no-book counts
- top market breakdown
- sample candidate traces
- latest recovery run
- safety counts

## Current Runtime Result

The 50-candidate bounded smoke created or refreshed real trusted evidence for
some candidates, including one fresh CLOB snapshot and three new trusted links.
The global `MISSING_FRESH_ORDERBOOK` count did not decrease because the dominant
blockers are missing market id, missing side, and missing market-link/thesis
dependencies.

The 5-candidate precision smoke rejected all five stale candidates as
`CLOB_NO_BOOK`. This is expected and safe: POLYBOT did not trust stale evidence
and did not fabricate an orderbook.

## Operator Guidance

Another paper-safe observation can run from a trading-safety perspective only if
the operator accepts that these blockers remain valid. Do not expect this fix by
itself to create new eligible paper trades.

The next useful fix is upstream: market id, side, expected token, and
signal-market binding recovery for the large no-market/no-side population.

