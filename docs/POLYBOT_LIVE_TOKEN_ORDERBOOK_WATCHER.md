# POLYBOT Live Token / Orderbook Watcher

Phase 3 adds a bounded read-only CLOB polling sense organ for fresh verified
Polymarket outcome tokens.

Security governance for this phase is:

`SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR`

The watcher does not trade, does not decide, and does not create paper artifacts.
It watches only source-backed verified market/token identities.

## Watchlist Model

Watch items are operational state in `live_orderbook_watchlist`.

Each item carries:

- `market_id`
- `condition_id`
- `side`
- `token_id`
- `source_type`
- `source_id`
- `priority`
- last poll/success/failure timestamps
- last best bid, best ask, spread, liquidity score
- failure count and status

Allowed statuses:

- `ACTIVE`
- `DEGRADED`
- `TOKEN_UNAVAILABLE`
- `MARKET_RESOLVED`
- `DISABLED`

## Selection Rules

Priority 1:

- `fresh_candidate_seeds` with `status='BOOK_VERIFIED'`

Priority 2:

- trusted orderbook evidence links created from fresh seeds

Priority 3:

- `paper_eligibility_candidates` with `identity_status='FRESH_VERIFIED'`

The selector rejects:

- stale markets
- missing market id
- missing condition id
- missing side
- missing token id
- closed or archived markets
- inactive markets
- `accepting_orders=false`
- ambiguous token mappings

## Polling Rules

The watcher is bounded by request parameters:

- `limit`
- `max_seconds`
- `include_priority`
- `dry_run`

For each active watch item it calls CLOB `/book` by `token_id` only.

The response must satisfy:

- `asset_id == token_id`
- `market == condition_id`
- bids are present
- asks are present

Valid books create source-backed `orderbook_snapshots`.

## Change Detection

The watcher publishes:

- `ORDERBOOK_REFRESHED` for every valid refreshed book
- `SPREAD_CHANGED` if absolute spread delta is at least `0.005` or relative delta is at least `20%`
- `LIQUIDITY_CHANGED` if absolute liquidity delta is at least `0.10` or relative delta is at least `25%`
- `TOKEN_BOOK_UNAVAILABLE` when a previously watched token cannot return a usable book
- `MARKET_RESOLVED` when the market is closed, archived, inactive, or no longer accepting orders
- `MARKET_REPRICING` when mid price changes by at least `0.01`

All events use:

- `source_component='Live Token / Orderbook Watcher'`
- `source_type='CLOB_READ_ONLY'`
- `source_table='live_orderbook_watcher_traces'`

## Mesh Flow

Watcher events enter the neural bus and then flow through the existing mesh path:

`neural_events -> mesh_sessions -> mesh_shared_awareness -> mesh_brain_opinions -> mesh_coordinator_decisions`

No downstream truth is faked.

## API

Read-only dashboard:

`GET /dashboard/api/v2/live-orderbook-watcher`

Controlled bounded run:

`POST /live-orderbook-watcher/run`

Request fields:

- `limit`
- `cycle_id`
- `dry_run`
- `max_seconds`
- `include_priority`

`SYSTEM OFF` blocks polling and mutation. Dashboard reads remain allowed.

## Safety

The watcher must not change:

- `live_orders`
- `paper_intents`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_capital_ledger`
- `orders_v2`
- `fills_v2`
- canonical `positions`

Public Polymarket token ids are preserved in neural payloads for lineage. Secret
fields such as API keys, bearer tokens, passphrases, passwords, and private keys
remain redacted.
