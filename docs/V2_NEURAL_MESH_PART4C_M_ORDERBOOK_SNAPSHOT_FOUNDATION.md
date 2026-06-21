# V2 Neural Mesh Part 4C-M: Orderbook Snapshot Foundation

## Purpose

Part 4C-M adds real orderbook snapshot truth to POLYBOT's Data Foundation. It collects read-only Polymarket CLOB orderbooks for locally known active markets, normalizes best bid/ask, spread, depth, liquidity, and freshness, persists the results, and exposes them through API and dashboard truth.

This phase does not enable Paper, create order intents, create orders, create fills, create positions, approve risk, create exit plans, or touch live execution.

## Contract

Orderbook snapshots are derived from real read-only market data and persisted as market technical truth.

Each snapshot records:
- market_id
- token_id
- side
- best_bid
- best_ask
- spread
- mid_price
- depth_bid_1c / depth_ask_1c
- depth_bid_2c / depth_ask_2c
- depth_bid_5c / depth_ask_5c
- total_bid_depth / total_ask_depth
- liquidity_score
- source
- snapshot_status
- is_stale
- stale_reason
- raw_orderbook
- raw_payload_ref
- correlation_id
- collected_at

Allowed snapshot_status values:
- OK
- PARTIAL
- EMPTY
- STALE
- ERROR

## Normalization Rules

- best_bid is the highest positive bid price with positive size.
- best_ask is the lowest positive ask price with positive size.
- spread is best_ask minus best_bid.
- mid_price is the midpoint when both sides exist.
- depth bands are directional depth within 0.01, 0.02, and 0.05 from the best price on each side.
- total depth is the sum of all positive size levels by side.
- liquidity_score is deterministic and clamped from 0.0 to 1.0.
- empty books are EMPTY and stale.
- one-sided books are PARTIAL and stale.
- snapshots older than the freshness window are STALE.

## Freshness

The conservative freshness window is 120 seconds.

A snapshot is stale when:
- collected_at is older than the freshness window
- source returned an error
- bid or ask side is missing
- raw orderbook is missing and normalized values are incomplete

## Data Source

The collector uses existing local market truth from `markets_v2` and fetches token books from the read-only Polymarket CLOB `/book` endpoint. It uses active, non-closed, accepting markets with known YES/NO token identifiers.

No fake prices, fake liquidity, or hardcoded market truth are introduced.

## API

Added:
- POST `/orderbook/snapshots/collect`
- GET `/orderbook/snapshots/recent`
- GET `/dashboard/api/v2/orderbook`

Updated:
- GET `/dashboard/api/v2/mesh`
- GET `/dashboard/api/v2/mesh-blockers`

## Dashboard Truth

The orderbook dashboard returns:
- mock_data=false
- total_snapshots
- fresh_snapshots
- stale_snapshots
- ok_snapshots
- partial_snapshots
- empty_orderbooks
- error_count
- markets_with_orderbook
- active_tradable_markets
- latest_collected_at
- freshness_window_seconds
- orderbook_coverage_ratio
- avg_spread
- avg_liquidity_score
- top_stale_markets
- last_run
- paper_ready=false
- analysis_status

## Mesh Blockers

ORDERBOOK_SNAPSHOTS_MISSING resolves only when fresh snapshots exist.

Additional orderbook blockers:
- ORDERBOOK_SNAPSHOTS_STALE when snapshots exist but all are stale
- ORDERBOOK_COVERAGE_LOW when fresh coverage is below threshold

Risk, Exit, Paper eligibility, signal quality, linkage, lineage, runtime mismatch, kill-switch mismatch, and execution blockers remain independent and active when proven by DB/runtime truth.

## Safety Invariants

- paper_ready remains false.
- execution_allowed remains false.
- no order intents are created.
- no paper, shadow, or live orders are created.
- no fills are created by this phase.
- no positions are created.
- no signing or live execution path is touched.
- dashboard truth is DB/runtime-backed with mock_data=false.

## Next Phase

Recommended next phase: V2 Neural Mesh Part 4C-N, Signal / Market Binding Recovery.

