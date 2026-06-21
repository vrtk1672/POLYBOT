# POLYBOT V2.1 Event Bus / Neural Mesh Foundation

## Purpose

V2.1 adds POLYBOT's first durable Event Bus foundation. It is the nervous-system layer for the future Neural Mesh: typed events, a strict envelope, Postgres persistence, in-process consumers, retry tracking, DLQ, replay, API visibility, and dashboard truth.

This phase does not implement future neurons, strategy engines, Risk Governor V2, or live execution.

## Architecture

- `app/events/types.py`: stable event type contract.
- `app/events/envelope.py`: typed event envelope with correlation, causation, payload, metadata, and redaction helpers.
- `app/events/event_bus.py`: publish, store, subscribe, dispatch, and delivery recording.
- `app/events/consumer_registry.py`: in-memory handlers plus Postgres consumer status.
- `app/events/retry_policy.py`: simple retry/DLQ policy.
- `app/events/dlq.py`: DLQ operations.
- `app/events/replay.py`: recorded replay jobs and safe redispatch.
- `app/repositories/event_*_repository.py`: Postgres persistence.
- `app/api/event_routes.py`: event inspection and replay routes.

## Event Model

Event names are stable strings. Unknown event types are rejected unless a future phase explicitly adds a custom event policy.

Required event families include market, orderbook, rules, news, social, whale, signal, opportunity, strategy, risk, order intent, position, exit, trade, learning, runtime, DLQ, and replay events.

## Event Envelope

Every event contains:

- `event_id`
- `event_type`
- `aggregate_type`
- `aggregate_id`
- `source_service`
- `correlation_id`
- `causation_id`
- `cycle_id`
- `mode`
- `occurred_at`
- `payload`
- `metadata`
- `schema_version`

`correlation_id` is generated if missing. Payload and metadata must be JSON-serializable. API output redacts secret-like keys.

## DB Tables

Migration: `app/db/migrations/0039_v2_event_bus_foundation.sql`

- `event_log`: append-only durable event store.
- `event_consumers`: consumer registry and status truth.
- `event_delivery_attempts`: per-consumer delivery attempts.
- `event_dlq`: permanently failed delivery records.
- `event_replay_jobs`: replay requests and outcomes.

## Event Store Behavior

Publishing stores the event first. The event store is append-only; replay redispatches existing events and does not create a second original event.

## Event Bus Behavior

`EventBus.publish()` creates or accepts an envelope, writes it to `event_log`, and dispatches to registered in-process consumers. Consumer failure is recorded and does not crash publishing.

## Consumer Registry

Consumers can be registered, paused, resumed, listed, and subscribed to one or more event types. Runtime handlers live in memory; consumer status is persisted in Postgres.

## Retry Policy

Default policy:

- max attempts: `3`
- backoff seconds: `5`, `30`, `120`
- after max attempts: move to DLQ

## DLQ Behavior

DLQ entries preserve event id, consumer name, reason, redacted failed payload, attempt count, and status. Events are never silently dropped.

## Replay Behavior

Replay jobs are persisted, run against existing `event_log` events, preserve original `event_id` and `correlation_id`, and redispatch only. Replay blocks order side-effect event types so it cannot send live orders or bypass the State Governor.

## API Routes

- `GET /events/recent`
- `GET /events/dlq`
- `POST /events/replay`
- `GET /events/lag`

Payloads and metadata are redacted in API output.

## Dashboard Truth

The existing dashboard overview now includes real event bus fields:

- event bus health
- events per minute
- failed event count
- DLQ count
- open DLQ count
- consumer count
- last event time
- replay jobs running
- event store status

No fake event data is produced.

## Runtime Integration

- `app/main.py` includes event routes and registers event services.
- `app/scheduler.py` publishes runtime cycle start/finish events.
- `app/ingestion/market_service.py` publishes runtime cycle start/finish and market snapshot events.
- Runtime mode changes through the runtime API publish `runtime.mode.changed`.

MarketService direct behavior is preserved; this phase wraps key boundaries only.

## Safety Guarantees

- Event Bus does not send orders.
- Replay does not send live orders.
- Order side-effect event replay is blocked.
- V2.0 State Governor remains the trading authority.
- KILL, DATA_ONLY, PAPER, SHADOW_LIVE, COOLDOWN, and live-disabled defaults remain intact.
- Secrets are redacted in event API and DLQ payloads.
- Consumer failure is isolated and persisted.

## Testing

V2.1 tests cover event types, store, bus, consumers, retry/DLQ, replay, API, and MarketService publishing.

## Known Limitations

- Dispatch is in-process only.
- Retry scheduling records `next_retry_at`; no background retry worker exists yet.
- MarketService integration is intentionally minimal.
- Dashboard panel is truth-only and read-only.
- Redis/distributed workers are future work.

## Future Phases

V2.2 should build canonical data truth on top of this event foundation. Later phases can add neurons, memory, opportunity scoring, strategy routing, risk, execution, exits, and learning without changing the event envelope contract.
