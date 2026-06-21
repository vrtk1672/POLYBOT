# V2.8 Market Technical Neurons

## Purpose

V2.8 adds the technical market truth layer for POLYBOT. It turns existing V2.2 market snapshots, orderbook snapshots, liquidity snapshots, and fee snapshots into auditable technical signals.

This phase is intelligence only. It does not create orders, order intents, exit intents, positions, strategy routes, opportunity scores, or live trading behavior.

## Architecture

The V2.8 layer lives in `app/market_neuron/`:

- `market_analyzer.py`: price movement, volatility, momentum, trend, and market regime.
- `orderbook_analyzer.py`: bid/ask, spread, depth, imbalance, queue quality, and orderbook quality.
- `liquidity_analyzer.py`: fill expectation, slippage, exit quality, max safe size, and liquidity blocks.
- `time_analyzer.py`: time to close, urgency, lockup penalty, ROI per hour reference, and TTL bucket.
- `fee_reward_analyzer.py`: maker/taker/spread/slippage costs, reward score, net edge after costs, and friction.
- `technical_signal_builder.py`: combines all five layers into `TechnicalMarketTruth`.
- `service.py`: persists all signals, publishes events, and exposes read-only query helpers.

The service can consume existing V2.2 DB snapshots or an explicit operator/test manual payload through `/market-neuron/analyze`.

## DB Tables

Migration `0046_v2_8_market_technical_neurons.sql` adds signal tables:

- `market_technical_signals`
- `orderbook_signals`
- `liquidity_signals`
- `time_signals`
- `fee_reward_signals`

These are signal tables, not execution tables. Raw V2.2 snapshot tables remain the canonical raw data source.

## API Routes

- `GET /market-neuron/health`
- `GET /market-neuron/market/{market_id}`
- `GET /market-neuron/signals/recent`
- `GET /market-neuron/blocked/recent`
- `GET /market-neuron/top`
- `POST /market-neuron/analyze`

The POST route is intelligence-only and requires a reason. It respects the State Governor collection permission.

## Event Types

V2.8 publishes redacted technical events:

- `market.technical_signal.created`
- `orderbook.signal.created`
- `liquidity.signal.created`
- `time.signal.created`
- `fee_reward.signal.created`
- `market.technical_truth.created`
- `market.technical_truth.blocked`

No order, order-intent, risk-approved, strategy-routed, or exit-intent events are emitted by V2.8.

## Blocking Logic

Technical readiness is blocked when core technical truth is unsafe or missing:

- missing bid/ask
- missing depth
- stale orderbook
- wide spread
- low exit depth
- poor exit liquidity
- high expected slippage
- market expired
- high friction costs

Rewards can improve a fee/reward subscore only when orderbook and liquidity are valid. Rewards cannot override missing bid/ask/depth or poor exit liquidity.

Short TTL increases urgency, but it does not override bad liquidity.

## Dashboard Fields

The dashboard overview now includes `market_technical`:

- `technical_neuron_status`
- `signals_today`
- `blocked_today`
- `stale_orderbooks`
- `average_spread_bps`
- `average_exit_quality`
- `average_slippage_bps`
- `average_time_efficiency`
- `top_technical_markets`
- `recent_block_reasons`
- `latest_signal_ts`
- `errors`

All values are DB-backed. If the tables or DB are unavailable, the dashboard reports empty/disabled/error truth instead of fake data.

## Safety Boundaries

V2.8 cannot:

- create orders
- create order intents
- create exit intents
- approve risk
- route strategies
- enable live trading
- bypass State Governor
- bypass Data Foundation
- bypass Rules / Compliance

V2.8 produces technical signals and blocks for later phases.

## Known Limitations

- Runtime orderbook ingestion still depends on V2.2 snapshot availability. When orderbook data is missing, V2.8 persists a blocked technical truth instead of pretending readiness.
- Fee/reward scoring is deterministic and conservative until richer reward data exists.
- Cancel burst and queue quality are heuristic where historical orderbook depth changes are not available.

## Future Phases

V2.9 Market Memory can consume V2.8 technical signal history. V2.11 Opportunity Cortex can later combine these technical blocks with News, Rules, Social, and Whale signals.

