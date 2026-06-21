# POLYBOT V3 Neural Event Bus Foundation

## Purpose

V3 adds the Neural Event Bus foundation: an append-only nervous-system surface for source-backed changes that should wake interested POLYBOT organs.

This is not a queue replacement, a scheduler rewrite, or a trading pipeline. It does not create orders, fills, positions, paper intents, capital movements, or live actions.

## Event Contract

`neural_events` stores immutable events with:

- `event_id`
- `event_type`
- `correlation_id`
- `market_id`
- `candidate_id`
- `position_id`
- `source_component`
- `source_type`
- `priority`
- `payload_json`
- `created_at`
- `consumed_count`
- `status`

The bus also records `source_table` and `source_record_id` so dialogue and dashboard rows can cite the source-backed origin.

## Event Types

Supported V3 foundation event types:

- `NEWS_DETECTED`
- `WHALE_DETECTED`
- `SOCIAL_SPIKE`
- `MARKET_REPRICING`
- `LIQUIDITY_CHANGED`
- `SPREAD_CHANGED`
- `ORDERBOOK_REFRESHED`
- `SIDE_DETERMINED`
- `TRUSTED_ORDERBOOK_CREATED`
- `RISK_CHANGED`
- `EXIT_CHANGED`
- `ELIGIBILITY_CHANGED`
- `PAPER_INTENT_CREATED`
- `POSITION_OPENED`
- `POSITION_CLOSED`
- `PNL_CHANGED`
- `CAPITAL_CHANGED`
- `NO_TRADE_RECORDED`
- `AI_CONTEXT_UPDATED`
- `MEMORY_UPDATED`

## Persistence

Migration `0101_v3_neural_event_bus_foundation.sql` adds:

- `neural_events`
- `neural_event_consumers`
- `neural_event_delivery`
- `neural_event_replay`

Existing `event_log`, `event_consumers`, `event_delivery_attempts`, and `event_replay_jobs` remain intact for V2 compatibility. V3 does not duplicate truth tables such as paper, risk, exit, eligibility, capital, memory, or orderbook tables; it transports references and snapshots of source truth.

## Publisher

`NeuralEventBusService.publish_event()` is the central publisher. Publishers do not know consumers.

SYSTEM OFF blocks publishing. SYSTEM ON allows publishing.

## Consumer Registry

`NeuralEventBusService.register_consumer()` registers consumer interest in event types and optional source components. This phase records interest only; no business logic handlers are attached.

## Delivery Tracking

`NeuralEventBusService.deliver_pending()` records which interested consumers received each event. Delivery rows are tracking/audit records and do not invoke trading logic.

SYSTEM OFF blocks delivery. SYSTEM ON allows delivery.

## Replay

`NeuralEventBusService.replay_events()` supports replay by:

- event type
- single event id
- id range
- market id
- correlation id

Replay records rows in `neural_event_replay` and delivery rows marked `REPLAYED`.

## Dashboard

`GET /dashboard/api/v2/neural-bus` returns:

- `mock_data=false`
- `events_last_hour`
- `events_last_day`
- `event_types`
- `active_consumers`
- `consumer_lag`
- `failed_deliveries`
- `latest_events`
- event registry

Dashboard remains read-only when SYSTEM OFF.

## Dialogue

`BrainDialogueService.materialize_recent()` now materializes `neural_events` into source-backed dialogue such as:

- `Orderbook: Published ORDERBOOK_REFRESHED`
- `News Neuron: Published NEWS_DETECTED`
- `Risk: Published RISK_CHANGED`

Dialogue cites `source_table='neural_events'` and the neural `event_id`. It does not invent events.

## Runtime Integration

`MarketService.refresh()` now calls:

1. `NeuralEventBusService.publish_source_backed_events()`
2. `NeuralEventBusService.deliver_pending()`
3. existing `BrainDialogueService.materialize_recent()`

This happens after existing evidence, paper-safe, exit, and PnL stages. It is guarded by SYSTEM power and exception-contained so it does not rewrite or replace runtime.

## Safety

- No live enablement.
- No shadow enablement.
- No execution/router/risk bypass.
- No orders, fills, positions, or capital rows created by the Neural Event Bus.
- SYSTEM OFF blocks publish and delivery.
- Dashboard reads remain allowed while OFF.
