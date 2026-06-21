# POLYBOT Polymarket Binding Recovery

Date: 2026-06-02

## Purpose

This phase adds deterministic Polymarket market / condition / outcome-token
binding recovery for paper eligibility candidates.

The service is evidence-only. It never creates paper intents, orders, fills,
positions, live orders, or real orders.

## Official Mapping Contract

Implemented assumptions:

- Polymarket CLOB orderbooks are requested by outcome `token_id`.
- CLOB book response `asset_id` must equal the requested outcome token.
- CLOB book response `market` must equal the Polymarket `condition_id` when
  condition id is known.
- YES candidates use `markets_v2.yes_token_id`.
- NO candidates use `markets_v2.no_token_id`.
- Buy price maps to best ask.
- Sell price maps to best bid.
- Spread is `best_ask - best_bid`.

## Recovery Model

`PolymarketIdentityBindingService.run_recovery()` performs a bounded pass:

1. Loads blocked paper eligibility candidates.
2. Backfills candidate `market_id` only from one deterministic trusted
   `signal_market_links` match.
3. Backfills candidate side only from one deterministic matched side.
4. Backfills market condition and YES/NO token mapping only from stored Gamma
   market snapshot payloads.
5. Resolves expected token for candidate side.
6. Calls read-only CLOB `/book` by expected token.
7. Rejects responses with wrong `asset_id`, wrong `condition_id`, no bid/ask,
   closed markets, or `accepting_orders=false`.
8. Persists a real orderbook snapshot only for valid source-backed books.
9. Creates/refreshes trusted orderbook links only after all validation passes.
10. Writes a candidate trace for every checked candidate.

Missing or ambiguous identity remains blocked.

## API

### GET /dashboard/api/v2/polymarket-binding

Returns:

- `mock_data=false`
- candidate identity coverage
- expected-token coverage
- CLOB book coverage
- fresh orderbook coverage
- trusted orderbook coverage
- precise blocker counts
- latest recovery run
- sample traces
- safety counts

### POST /polymarket-binding/recover

Body:

- `cycle_id`
- `limit`
- `refresh_orderbooks`
- `apply_backfill`

The endpoint is blocked while SYSTEM is OFF.

## Runtime Result

The bounded 100-candidate smoke checked:

- `31` candidates with market, side, condition, and expected token.
- `69` candidates with no deterministic market id.

The 31 expected-token CLOB checks returned `TOKEN_NOT_FOUND`. No snapshots or
trusted links were created, which is correct: POLYBOT did not fabricate books or
trust stale/wrong-token evidence.

## Current Blockers

Remaining main blockers:

- `NO_MARKET_ID`: 5192
- `NO_SIDE`: 6556
- `NO_CONDITION_ID`: 1286
- `NO_YES_NO_TOKEN_MAPPING`: 1286
- `MISSING_FRESH_ORDERBOOK`: 6579

The next useful recovery layer is upstream signal-market identity production for
generic source-status candidates that currently have no market-specific signal.

