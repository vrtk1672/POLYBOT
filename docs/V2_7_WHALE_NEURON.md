# V2.7 Whale Neuron

## Purpose

V2.7 adds a durable Whale Neuron for large participant intelligence. It detects, normalizes, profiles, categorizes, scores, and exposes whale activity without creating trades, order intents, positions, approvals, or exits.

Size alone is not intelligence. The neuron treats a large event as evidence to measure, not as alpha.

## Architecture

- `app/whale_neuron/source_registry.py` registers manual, mock, internal, public, chain, API, and CSV whale sources.
- `app/whale_neuron/scanner.py` provides safe manual/mockable collection abstractions.
- `app/whale_neuron/normalizer.py` turns raw activity into canonical `WhaleEvent` contracts.
- `app/whale_neuron/registry.py` maintains canonical whale identity records.
- `app/whale_neuron/event_classifier.py` classifies entry, exit, late chase, distribution, hedge, market mover, and unknown behavior.
- `app/whale_neuron/profile_builder.py` builds rolling behavior profiles from events and performance history.
- `app/whale_neuron/category_engine.py` assigns smart, noisy, copy-worthy, specialist, late-chaser, and unknown categories.
- `app/whale_neuron/market_score.py` creates bounded market whale scores and signal JSON.
- `app/whale_neuron/follow_value.py` logs follow/watch/ignore/penalize/insufficient decisions.
- `app/whale_neuron/noise_penalty.py` penalizes churn, late chasing, inconsistency, and broad random behavior.
- `app/whale_neuron/performance_history.py` records honest outcome proxies or insufficient data.
- `app/whale_neuron/ai_context_analyzer.py` optionally enriches with V2.3 AI Brain under cache/budget/cloud controls.
- `app/whale_neuron/service.py` coordinates the full pipeline.

## DB Tables

Migration `app/db/migrations/0045_v2_whale_neuron.sql` adds `whale_sources`, `whale_performance_history`, and `whale_follow_decisions`.

It extends existing Phase 5 whale tables instead of duplicating truth:

- `whale_events`
- `whale_registry`
- `whale_profiles`
- `whale_categories`
- `whale_market_scores`

Legacy UUID primary keys remain intact. V2.7 public identifiers are stored in new text columns such as `whale_event_id`, `whale_id`, and `whale_market_score_id`.

## API Routes

- `GET /whales`
- `GET /whales/{whale_id}`
- `GET /whales/market/{market_id}`
- `GET /whales/events/recent`
- `GET /whales/scores/top`
- `GET /whales/sources`
- `POST /whales/scan`
- `POST /whales/manual`

Manual ingestion is for operator/test input and has no trading side effects.

## Dashboard Truth Fields

The existing operator dashboard overview now includes real DB-backed `whale_neuron` data:

- `whale_neuron_health`
- `whale_events_today`
- `active_whales`
- `copy_worthy_whales`
- `noisy_whales`
- `top_whale_market_scores`
- `top_follow_value_whales`
- `average_whale_noise`
- `whale_reversal_risk_count`
- `latest_whale_event_at`
- `whale_errors_today`

Empty tables return empty or zero truth. No fake data is generated.

## Event Bus Integration

V2.7 publishes redacted V2.1 events:

- `whale.source.registered`
- `whale.event.collected`
- `whale.event.created`
- `whale.event.normalized`
- `whale.registered`
- `whale.profile.updated`
- `whale.category.assigned`
- `whale.market.scored`
- `whale.follow.decided`
- `whale.performance.updated`
- `whale.signal.created`
- `whale.ai.analyzed`

No `order.intent.created`, `order.created`, `risk.approved`, or exit events are published.

## Integrations

- State Governor: scanning and manual ingestion require `COLLECT_DATA`; KILL blocks new collection.
- AI Brain: optional local-first analysis only, cloud disabled by default and blocked on low confidence.
- Data Foundation: whale market score reads market/completeness truth when available and lowers confidence for missing or weak data.
- Rules: active blocking compliance lowers whale signal confidence; whale signals cannot override compliance.
- News/Social: reserved for read-only awareness in later scoring refinements; this phase does not mutate those neurons.

## Safety Guarantees

- Whale Neuron cannot create orders.
- Whale Neuron cannot create order intents.
- Whale Neuron cannot approve risk.
- Whale Neuron cannot trigger exits.
- Unknown whales are not auto-followed.
- Large trades increase presence, not automatic follow value.
- Bad/noisy/late whales are penalized.
- Whale dumps create signals only.
- Events and API payloads are redacted.

## Known Limitations

- External whale feeds are abstraction-ready but not enabled without credentials.
- Performance history is proxy-based unless later market outcomes are available.
- Orderbook ingestion remains partial from V2.2 limitations.
- AI enrichment is optional and not required for tests or runtime.

## Future Work

V2.8 may use whale signals as read-only inputs to market/orderbook/liquidity/time/fees neurons. Opportunity Cortex, Strategy Router, Risk Governor V2, Execution Cortex, and Exit Cortex remain future phases.

