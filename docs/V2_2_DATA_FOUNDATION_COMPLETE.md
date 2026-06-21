# POLYBOT V2.2 Data Foundation Complete

## Purpose

V2.2 creates a durable, queryable market data truth layer before expanding AI, engines, risk, execution, and learning. The principle is simple: missing or stale data must degrade toward `NO_TRADE`, not blind confidence.

This phase does not implement Hybrid AI Brain, strategy routing, opportunity scoring, Risk Governor V2, or live execution.

## Existing Assets Reused

- Gamma fetch and `MarketService.refresh()`.
- Existing Phase 1 `market_snapshots` and `ranking_snapshots`.
- Postgres repository pattern.
- V2.0 State Governor.
- V2.1 Event Bus.
- Dashboard query service.

V2.2 adds explicit V2 tables rather than replacing older tables.

## Architecture

- `app/data_foundation/market_registry.py`: canonical market registry.
- `app/data_foundation/market_rules_store.py`: rules and resolution metadata.
- `app/data_foundation/market_snapshotter_v2.py`: append-only market snapshots.
- `app/data_foundation/orderbook_snapshotter.py`: orderbook normalization and persistence.
- `app/data_foundation/liquidity_profiler.py`: deterministic liquidity metrics.
- `app/data_foundation/fees_rewards_collector.py`: fee/reward friction snapshots.
- `app/data_foundation/market_family_classifier.py`: rule-based family classification.
- `app/data_foundation/market_lifecycle_tracker.py`: lifecycle event tracking.
- `app/data_foundation/data_completeness.py`: 0-100 completeness scoring.
- `app/data_foundation/data_staleness.py`: freshness policy.
- `app/data_foundation/service.py`: light MarketService integration.

## Market Registry

`markets_v2` stores one canonical row per `market_id`. Repeated upserts update `last_seen_at` and existing fields rather than duplicating markets.

## Market Rules Store

`market_rules` stores normalized rules text, resolution source, deadline, stable hash, and missing-rules flags. V2.2 does not analyze wording risk; that belongs to V2.5.

## Snapshots V2

`market_snapshots_v2` is append-only and stores current prices, bid/ask, spread, volume, liquidity, time-to-close, completeness score, stale flag, raw payload, and metadata.

## Orderbook Snapshots

`orderbook_snapshots` stores normalized bid/ask levels, best bid/ask, spread, midpoint, depth within 1c/2c/5c, and imbalance. Empty or malformed orderbooks are handled safely.

Runtime orderbook ingestion is partial: services and persistence exist, but `MarketService.refresh()` does not fetch external orderbooks yet.

## Liquidity Profiler

Liquidity scoring is deterministic:

- deeper near-price orderbooks improve liquidity score
- lower spread improves liquidity score
- balanced books improve exit quality
- missing orderbook produces low score and honest metadata

No AI is used.

## Fees / Rewards Collector

Fee snapshots store maker/taker fees, spread cost, estimated slippage cost, rewards, and net edge adjustment where available. Unknown fees are stored as null with metadata, not invented.

## Market Family Classifier

Rule-based classification supports families such as crypto, sports, politics, macro, weather, legal, geopolitics, entertainment, and generic.

## Lifecycle Tracker

Lifecycle events include `DISCOVERED`, `UPDATED`, `OPENED`, `PAUSED`, `CLOSED`, `RESOLVED`, `ARCHIVED`, `STALE`, and `REACTIVATED`.

## Data Completeness

Completeness is scored from 0-100 across:

- market id
- question
- outcome tokens
- price
- orderbook
- rules
- liquidity
- time to close
- resolution source

`candidate_allowed=false` if critical fields are missing, data is stale, the market is closed, or the market is not accepting orders.

## Staleness Policy

Defaults:

- market snapshot stale after 5 minutes
- orderbook stale after 60 seconds
- rules stale after 24 hours

## DB Tables

Migration: `app/db/migrations/0040_v2_data_foundation_complete.sql`

- `markets_v2`
- `market_rules`
- `market_snapshots_v2`
- `orderbook_snapshots`
- `liquidity_snapshots`
- `fee_snapshots`
- `market_lifecycle_events`
- `market_family_map`

## API Routes

- `GET /data/markets`
- `GET /data/markets/{market_id}`
- `GET /data/markets/{market_id}/snapshots`
- `GET /data/markets/{market_id}/orderbook/latest`
- `GET /data/coverage`
- `GET /data/families`

All values come from DB truth or deterministic computation.

## Dashboard Truth Fields

The dashboard overview includes:

- market count
- active market count
- tradable market count
- orderbook coverage
- rules coverage
- liquidity coverage
- stale market count
- closed market count
- average data completeness
- latest market snapshot time
- latest orderbook snapshot time

## Event Bus Integration

V2.2 publishes:

- `market.discovered`
- `market.snapshot.created`
- `orderbook.snapshot.created`
- `rules.snapshot.created`
- `market.lifecycle.updated`
- `data.completeness.updated`
- `liquidity.snapshot.created`
- `fee.snapshot.created`

No trading events are emitted by V2.2.

## Runtime Integration

`MarketService.refresh()` records V2 data for the configured top-N markets after normalization and persistence. This keeps startup bounded while proving the integration path. Full-universe bulk recording can be expanded in a later data ingestion pass.

## Safety Guarantees

- No live trading enabled.
- No orders created.
- State Governor remains authority.
- Event Bus is used for data events only.
- Missing rules/orderbook/liquidity lower completeness honestly.
- Closed and stale markets are blocked from `candidate_allowed`.
- Dashboard uses real DB-backed data only.

## Testing

V2.2 tests cover registry, rules, snapshots, orderbooks, liquidity, fees, family classification, lifecycle, completeness, API, and MarketService integration.

## Known Limitations

- Runtime orderbook external fetch is not wired yet.
- Runtime MarketService integration records top-N markets, not the full fetched universe.
- Completeness does not write a separate no-trade ledger yet.
- Rules are stored but not AI-analyzed.

## Future Phases

V2.3 can build Hybrid AI Brain on top of this data truth. V2.4-V2.8 can add neurons that enrich the same foundation without changing the safety baseline.
