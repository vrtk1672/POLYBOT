# V2.9 Market Memory V2

## Purpose

V2.9 turns Postgres into behavioral memory. It summarizes what the system has observed about markets, market families, engines, sources, whales, slippage, rules risk, and no-trade decisions without duplicating raw signal truth.

This phase is memory infrastructure only. It does not create orders, order intents, exits, risk approvals, opportunity scores, strategy routes, or live trading behavior.

## Architecture

The Market Memory package lives in `app/market_memory/`:

- `contracts.py` defines bounded, explicit memory contracts and `MarketMemorySnapshot`.
- `market_memory_builder.py` aggregates V2.8 technical truth by market.
- `market_family_memory_builder.py` aggregates behavior by market family.
- `engine_performance_memory_builder.py` records engine outcome memory only from evidence.
- `source_reliability_memory_builder.py` summarizes source usefulness and reliability.
- `whale_memory_builder.py` summarizes V2.7 whale behavior without treating size alone as intelligence.
- `slippage_memory_builder.py` compares expected and realized slippage when available.
- `rules_risk_memory_builder.py` preserves V2.5 wording/dispute/resolution risk.
- `no_trade_memory_builder.py` stores support for regret analysis only when post-fact evidence exists.
- `service.py` rebuilds memory from existing DB truth and publishes redacted events.

Repository classes in `app/repositories/` persist each memory table. The API is exposed from `app/api/market_memory_routes.py`.

## DB Tables

Migration: `app/db/migrations/0047_v2_9_market_memory_v2.sql`

Tables:

- `market_memory_v2`
- `market_family_memory`
- `engine_performance_memory`
- `source_reliability_memory`
- `whale_memory`
- `slippage_memory`
- `rules_risk_memory`
- `no_trade_memory`

These are summary tables. Raw V2.8 technical signals, V2.7 whale events, V2.5 rules analysis, and source events remain in their canonical tables.

## API Routes

Prefix: `/market-memory`

- `GET /market-memory/health`
- `GET /market-memory/market/{market_id}`
- `GET /market-memory/family/{market_family}`
- `GET /market-memory/engines`
- `GET /market-memory/sources`
- `GET /market-memory/whales`
- `GET /market-memory/slippage`
- `GET /market-memory/rules-risk`
- `GET /market-memory/no-trade`
- `GET /market-memory/recent`
- `POST /market-memory/rebuild`

`POST /market-memory/rebuild` supports `dry_run=true` and is memory-only. It respects the State Governor and cannot create trading side effects.

## Event Types

V2.9 publishes redacted memory events:

- `market.memory.updated`
- `market_family.memory.updated`
- `engine_performance.memory.updated`
- `source_reliability.memory.updated`
- `whale.memory.updated`
- `slippage.memory.updated`
- `rules_risk.memory.updated`
- `no_trade.memory.updated`
- `market.memory.insufficient_data`

Payloads use IDs, confidence, and insufficient-data flags. They do not include secrets or execution details.

## Builder Logic

Market memory consumes V2.8 technical truth:

- spread, depth, slippage, exit quality, time efficiency
- stale rate
- technical block rate
- liquidity failure rate
- wording/dispute risk when V2.5 rules analysis exists

Family memory aggregates market memory by family/category.

Engine memory is evidence-based. With no outcomes, `best_engine` stays `UNKNOWN` and confidence stays low.

Source memory increases reliability only from supported evidence and penalizes false, stale, duplicate, or noisy signals.

Whale memory summarizes follow value, noise, timing, and outcome proxies. Large size alone is not intelligence.

Slippage memory keeps expected-only memory low-confidence until realized fills exist.

Rules risk memory preserves wording risk, dispute risk, clarity, ambiguous terms, edge cases, and block rates.

No-trade memory records regret only when post-fact evidence exists.

## Confidence And Insufficient Data

Every memory contract exposes explicit confidence. Missing evidence produces `insufficient_data`, not guessed scores.

Examples:

- no V2.8 rows: `missing_v2_8_technical_signals`
- no engine outcomes: `missing_engine_outcomes`
- no rules history: `missing_rules_history`
- no whale history: `missing_whale_history`
- no no-trade regret data: `missing_no_trade_regret_history`

## Dashboard Fields

The dashboard overview now includes `market_memory` with DB-backed truth:

- `memory_status`
- `last_memory_update`
- `market_memories_count`
- `family_memories_count`
- `engine_memories_count`
- `source_memories_count`
- `whale_memories_count`
- `insufficient_data_count`
- `top_market_families_by_confidence`
- `best_engine_by_family`
- `worst_slippage_families`
- `highest_wording_risk_families`
- `top_reliable_sources`
- `top_whales_by_memory_score`
- `no_trade_regret_rate`
- `recent_memory_updates`
- `errors`

If memory tables are absent or empty, the dashboard reports `EMPTY` or `DISABLED`; it does not fabricate data.

## Safety Boundaries

Market Memory cannot:

- create orders
- create order intents
- create exits
- approve risk
- route strategies
- produce opportunity scores
- enable live trading

The rebuild endpoint checks the State Governor with `RuntimeAction.COLLECT_DATA`. `KILL` blocks new rebuilds. Read endpoints remain read-only.

## Testing

V2.9 tests cover:

- market memory aggregation
- insufficient-data behavior
- family aggregation
- engine scoring from outcomes only
- source reliability scoring
- whale memory and size-alone safeguards
- slippage memory
- rules risk memory
- no-trade memory
- service persistence/events
- API endpoints
- safety guards

## Known Limitations

- Engine performance remains `UNKNOWN` until real engine outcome records exist.
- Realized slippage memory is low-confidence until fills or fill proxies exist.
- No-trade regret memory is infrastructure only; full V2.17 no-trade intelligence is future work.
- Source reliability remains low-confidence without later market reaction evidence.

## Next Recommended Phase

V2.10 Context Brain + Capital Brain can use V2.9 memory once V2.9 tests, migrations, APIs, and safety regressions are GREEN.
