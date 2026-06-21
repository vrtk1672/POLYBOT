# V2.6 Social / Hype Neuron

## Purpose

V2.6 adds a durable Social / Hype Neuron for public attention, mention velocity, sentiment, narrative formation, bot/spam risk, hype pressure, and social price lead/lag interpretation.

Social is not truth and not a trading engine. It is pressure, attention, narrative, and possible manipulation. V2.6 produces auditable intelligence only.

## Architecture

The implementation adds `app/social_neuron/` with:

- social source registry
- collector abstraction
- deterministic normalizer
- deduplicator
- mention velocity tracker
- sentiment classifier
- narrative detector
- bot/spam filter
- market linker
- hype pressure scorer
- social price lead/lag detector
- optional AI social context analyzer
- orchestration service

It uses V2.1 Event Bus, V2.2 Data Foundation, V2.3 AI Brain, V2.4 News as read-only context, and V2.5 Rules/Compliance as read-only risk awareness.

## Source Registry

`SocialSourceRegistry` manages social/trend sources. It supports manual, RSS mirror, public trend API, X/Twitter, Reddit, Telegram, Discord, and news social mirror source types without requiring paid keys or secrets.

Default category support includes crypto, politics, sports, macro, weather, legal, geopolitics, entertainment, polymarket, and general.

## Collector

`SocialCollector` stores raw social events, computes content hashes, publishes `social.raw.collected`, and updates source fetch status. Manual ingestion is supported for tests and operator verification.

Network/API collection is abstracted and safe; tests do not require internet or credentials.

## Normalizer

`SocialNormalizer` lowercases and normalizes text, extracts entities, hashtags, cashtags, topics, category, engagement score, influence score, and novelty score. It publishes `social.event.created` and `social.event.normalized`.

## Deduplicator

`SocialDeduplicator` groups repeated posts deterministically by URL or normalized text signature. Duplicate risk feeds the noise scorer.

## Mention Velocity

`MentionVelocityTracker` computes mention count, unique authors, mentions per minute, spam ratio, and velocity z-score over configurable windows. Zero data returns honest zeroes.

## Sentiment Classifier

`SentimentClassifier` is deterministic and conservative. It can classify YES, NO, BULLISH, BEARISH, NEUTRAL, MIXED, or UNKNOWN. Unclear text stays neutral/unknown.

## Narrative Detector

`NarrativeDetector` clusters social events by topics, hashtags, cashtags, and entities. It tracks narrative strength, confidence, status, first/last seen, and market IDs.

## Bot / Spam Filter

`BotSpamFilter` produces risk scores only. It does not accuse users. It considers repeated text, excessive tags, promotional wording, short low-content posts, and suspicious handles.

## Market Linker

`SocialMarketLinker` links social events to `markets_v2` only when deterministic evidence is strong enough. Closed, stale, or compliance-blocked markets are penalized. Direction remains UNKNOWN when deterministic rules cannot justify YES/NO.

## Hype Pressure

`HypePressureScorer` combines mention velocity, unique authors, sentiment confidence, narrative strength, spam ratio, and bot risk into a bounded `SocialSignal`:

```json
{
  "node": "social",
  "market_id": "abc",
  "hype_pressure": 0.78,
  "sentiment": "YES",
  "mentions_velocity": 3.4,
  "bot_risk": 0.22,
  "confidence": 0.61
}
```

## Price Lead / Lag

`PriceLeadLagDetector` compares social activity timing to market snapshot movement and returns SOCIAL_LEADS_PRICE, SOCIAL_LAGS_PRICE, SIMULTANEOUS, or INSUFFICIENT_DATA. It does not claim causation.

## AI Context Analyzer

`SocialAIContextAnalyzer` uses V2.3 AI Brain only as optional enrichment. It is local-first, cache/budget controlled through AI Brain, cloud-disabled by default, and skipped for low deterministic value.

## Database Tables

Migration `0044_v2_social_hype_neuron.sql` adds:

- `social_sources`
- `social_raw_events`
- `social_normalized_events`
- `social_market_links`
- `social_sentiment_scores`
- `social_hype_scores`
- `social_noise_scores`
- `social_narratives`

## API Routes

- `GET /social/recent`
- `GET /social/sources`
- `GET /social/market/{market_id}`
- `GET /social/hype/top`
- `GET /social/narratives`
- `POST /social/collect`
- `POST /social/manual`

All routes return DB truth. Manual ingestion is safe and non-trading.

## Dashboard Truth Fields

The operator dashboard overview now includes:

- social feed health
- enabled social sources
- social events today
- latest social timestamp
- top hype markets
- top narratives
- social market links today
- average bot risk
- average spam ratio
- social AI calls today
- social errors today
- lead/lag summary

No fake values are generated.

## Event Bus Integration

V2.6 publishes redacted non-trading events:

- `social.source.registered`
- `social.raw.collected`
- `social.event.created`
- `social.event.normalized`
- `social.event.deduped`
- `social.market.linked`
- `social.sentiment.scored`
- `social.hype.scored`
- `social.noise.scored`
- `social.narrative.detected`
- `social.ai.analyzed`
- `social.signal.created`

No opportunity, strategy, risk, order intent, or order events are published.

## Safety Guarantees

- Social cannot create orders.
- Social cannot create order intents.
- Social cannot approve risk.
- Social cannot bypass State Governor.
- Social cannot bypass AI Budget Governor.
- Social cannot bypass Data Foundation or Rules/Compliance.
- Missing market link means no market signal.
- Spam/bot risk lowers confidence.
- Compliance-blocked markets are penalized.
- No paid API calls are required for tests.
- No secrets are printed or stored in payloads.

## Known Limitations

Runtime orderbook ingestion remains partial from V2.2. Social source network collectors are abstractions and require future configured sources. Bot/spam scoring is risk estimation only. Lead/lag detection is heuristic and non-causal.

Future phases can feed social signals into Opportunity Cortex, but V2.6 does not score opportunities or trade.
