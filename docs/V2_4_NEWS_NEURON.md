# V2.4 News Neuron

## Purpose

V2.4 adds the POLYBOT News Neuron: a durable, auditable news intelligence layer that ingests, normalizes, deduplicates, links, scores, and persists news events.

News does not equal trade. The News Neuron produces structured intelligence only. It does not create orders, order intents, positions, opportunity scores, risk approvals, or execution decisions.

## Architecture

The News Neuron is additive to the existing V2 stack:

- V2.0 State Governor controls runtime mode and blocks collection in KILL.
- V2.1 Event Bus records news lifecycle events.
- V2.2 Data Foundation provides market registry, snapshots, family, and completeness truth for linking.
- V2.3 Hybrid AI Brain is optional enrichment only, local-first, budget-gated, cache-aware, and cloud-disabled by default.

Main package: `app/news_neuron/`.

## Source Registry

`NewsSourceRegistry` manages `news_sources`.

It supports registering, enabling, disabling, fetch status updates, and default category placeholders. Defaults are registry slots only; no paid keys or fake feeds are added.

## Collector

`NewsCollector` supports:

- manual ingestion
- RSS collection through an injectable fetcher
- enabled-source collection
- raw event persistence
- content hash dedup prevention
- source fetch status updates

Tests mock RSS responses and do not require internet access.

## Normalizer

`NewsNormalizer` converts raw items into canonical `NormalizedNewsEvent` rows using deterministic heuristics:

- title/text normalization
- basic entity extraction
- topic/category inference
- bounded importance, urgency, novelty, and source reliability scores

No AI is required for normalization.

## Deduplicator

`NewsDeduplicator` groups same-story items using deterministic signatures from normalized title terms, entities, topics, URL/content signals, and time-local grouping.

It updates `news_dedup_groups` and marks normalized events as deduped.

## Source Reliability

`SourceReliabilityScorer` tracks operational reliability, not final truthfulness.

Scores start neutral at `0.50`, improve with useful linked events, and degrade with source errors or ignored events.

## Market Linker

`NewsMarketLinker` uses V2.2 market truth from `markets_v2`.

It links only when deterministic overlap is justified:

- exact entity/topic/category overlap
- market question terms
- market family/category
- closed/inactive market penalty

Direction remains `UNKNOWN` unless deterministic evidence supports otherwise. It does not hallucinate YES/NO.

## Impact Scorer

`NewsImpactScorer` writes bounded `NewsImpactScore` records and `NewsSignal` payloads.

Inputs:

- link score
- news importance/urgency
- source reliability
- latest market data completeness
- stale/closed market status
- already-priced-in score
- TTL policy

Poor data completeness, stale markets, missing price history, and closed markets reduce confidence.

## Already Priced-In Detector

`AlreadyPricedInDetector` uses V2.2 market snapshots.

It returns:

- low score when no meaningful move is present
- high score if price moved before the news was seen
- neutral risk-flagged result when price history is missing

## TTL Engine

`NewsTTLEngine` computes non-negative TTL:

- sports and crypto are short-lived
- politics/legal/geopolitics can last longer
- high urgency, low confidence, and already-priced-in evidence shorten TTL

## AI News Context Analyzer

`NewsAIContextAnalyzer` is optional enrichment.

Rules:

- skips low-value news AI calls
- uses V2.3 AI Brain with cache and budget controls
- cloud is disabled unless explicitly allowed upstream
- AI failure does not block news persistence
- AI output is interpretation only and cannot create trades

## DB Tables

Migration: `app/db/migrations/0042_v2_news_neuron.sql`

Tables:

- `news_sources`
- `news_raw_events`
- `news_normalized_events`
- `news_dedup_groups`
- `news_market_links`
- `news_impact_scores`
- `news_source_reliability`
- `news_ai_analysis`

## API Routes

Mounted under `/news`:

- `GET /news/recent`
- `GET /news/sources`
- `GET /news/market/{market_id}`
- `GET /news/impact/top`
- `POST /news/collect`
- `POST /news/manual`

Read endpoints return persisted truth. Manual ingestion is safe operator/test input and has no trading side effects.

## Dashboard Truth

The dashboard overview includes `news_neuron`:

- `news_feed_health`
- `news_sources_enabled`
- `news_events_today`
- `latest_news_at`
- `latest_breaking_news`
- `top_news_market_links`
- `top_news_impact_scores`
- `source_reliability_summary`
- `news_ai_calls_today`
- `news_latency_seconds`
- `news_errors_today`

No fake data is generated. Empty DB means empty/zero truth.

## Event Bus Integration

Published event types:

- `news.source.registered`
- `news.raw.collected`
- `news.event.created`
- `news.event.normalized`
- `news.event.deduped`
- `news.market.linked`
- `news.impact.scored`
- `news.ai.analyzed`
- `news.source.reliability.updated`

Payloads carry ids, scores, hashes, and short summaries. They do not include secrets or full raw body text.

## State Governor Integration

News collection checks `COLLECT_DATA`.

- `DATA_ONLY`, `PAPER`, and `SHADOW_LIVE` allow collection.
- `KILL` blocks new collection.
- Read-only API endpoints remain available.

## Safety Guarantees

- News cannot create orders.
- News cannot create order intents.
- News cannot approve risk.
- News cannot bypass State Governor.
- News cannot bypass AI Budget Governor.
- News cannot bypass Data Foundation completeness.
- Missing market links produce no signal.
- Weak source reliability lowers confidence.
- Priced-in news lowers impact.
- Closed/stale markets lower confidence.
- Tests do not call real paid APIs, Ollama, or cloud AI.

## Known Limitations

- Runtime orderbook ingestion remains partial from V2.2, so missing orderbook still lowers confidence downstream.
- Market direction is conservative and often `UNKNOWN`.
- Source reliability is operational and preliminary.
- RSS support is intentionally simple and mocked in tests.
- AI enrichment is optional and not called for every item.

## Future Phases

V2.5 should build the Rules / Wording / Compliance Neuron. It should use News as one source of context, but keep rules interpretation separate from news ingestion.

