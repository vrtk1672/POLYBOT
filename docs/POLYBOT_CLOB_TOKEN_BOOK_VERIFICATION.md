# POLYBOT CLOB Token Book Verification

Phase 2 verifies Polymarket CLOB books only after fresh market identity exists.

Security governance status for this phase:

`SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR`

## Scope

Implemented:

- Process only `paper_eligibility_candidates.identity_status='FRESH_VERIFIED'`.
- Skip `STALE_MARKET` candidates and record that skip.
- Seed isolated `fresh_candidate_seeds` from current Gamma markets when there are too few fresh verified candidates.
- Request CLOB `/book` by `expected_token_id`.
- Validate CLOB response `asset_id` equals `expected_token_id`.
- Validate CLOB response `market` equals `condition_id`.
- Persist `orderbook_snapshots` only from valid source-backed books.
- Persist `trusted_orderbook_evidence_links` only after asset, condition, bid/ask, spread, and liquidity checks.
- Expose dashboard truth at `GET /dashboard/api/v2/clob-token-book-verification`.
- Run controlled verification at `POST /clob-token-book-verification/run`.

Out of scope:

- Live token/orderbook watcher.
- Position token watchdog.
- Strategy routing.
- Opportunity scoring.
- Paper intent/order/fill/position creation.
- Live/shadow execution.

## Validation Rules

A candidate or seed is eligible for CLOB verification only if:

- market identity is `FRESH_VERIFIED` or isolated `FRESH_SEED`
- `market_id` exists
- `condition_id` exists
- `side` is `YES` or `NO`
- `expected_token_id` exists
- market is not closed/archived/inactive
- `accepting_orders` is not false

CLOB book is trusted only if:

- `/book` is requested by `expected_token_id`
- response `asset_id` matches `expected_token_id`
- response `market` matches `condition_id`
- bids and asks exist
- normalized snapshot status is `OK`
- spread is within trusted orderbook policy
- liquidity is within trusted orderbook policy

## Fresh Seeds

Fresh seeds live in `fresh_candidate_seeds`.

They are not paper candidates, not eligible candidates, not paper intents, and not trading artifacts. They exist so current Gamma markets can be verified by CLOB before later phases decide how to consume them.

Seed statuses:

- `SEEDED`
- `BOOK_VERIFIED`
- `BOOK_REJECTED`
- `NOT_TRADABLE`
- `AMBIGUOUS`

## Safety

This phase must not mutate:

- `paper_intents`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_capital_ledger`
- `live_orders`
- `orders_v2`
- `fills_v2`
- canonical `positions`

`SYSTEM OFF` blocks mutating verification. Dashboard reads remain allowed.
