# V2.6 Build Report - Social / Hype Neuron

## Summary

V2.6 is implemented and GREEN. POLYBOT now has a Social / Hype Neuron that collects manual/mockable social inputs, normalizes and deduplicates them, scores bot/spam risk, links justified items to markets, classifies sentiment, detects narratives, computes mention velocity and hype pressure, exposes APIs, publishes redacted events, and adds dashboard truth fields.

No trading behavior was added.

## Files Created

- `app/social_neuron/*`
- `app/api/social_routes.py`
- `app/repositories/social_source_repository.py`
- `app/repositories/social_raw_event_repository.py`
- `app/repositories/social_normalized_event_repository.py`
- `app/repositories/social_market_link_repository.py`
- `app/repositories/social_sentiment_repository.py`
- `app/repositories/social_hype_repository.py`
- `app/repositories/social_noise_repository.py`
- `app/repositories/social_narrative_repository.py`
- `app/db/migrations/0044_v2_social_hype_neuron.sql`
- `tests/test_v2_6_*.py`
- `docs/V2_6_SOCIAL_HYPE_NEURON.md`
- `docs/V2_6_BUILD_REPORT.md`

## Files Changed

- `app/events/types.py`
- `app/main.py`
- `app/api/routes.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration Added

`0044_v2_social_hype_neuron.sql`

Tables added: `social_sources`, `social_raw_events`, `social_normalized_events`, `social_market_links`, `social_sentiment_scores`, `social_hype_scores`, `social_noise_scores`, `social_narratives`.

## API Routes Added

- `GET /social/recent`
- `GET /social/sources`
- `GET /social/market/{market_id}`
- `GET /social/hype/top`
- `GET /social/narratives`
- `POST /social/collect`
- `POST /social/manual`

## Dashboard Changes

Added DB-backed Social / Hype overview fields:

- social feed health
- social sources enabled
- social events today
- latest social timestamp
- top hype markets
- top narratives
- social market links today
- average bot risk
- average spam ratio
- social AI calls today
- social errors today
- social lead/lag summary

## Events Published

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

Payloads are redacted and non-trading.

## Tests Added

- `tests/test_v2_6_social_contracts.py`
- `tests/test_v2_6_social_source_registry.py`
- `tests/test_v2_6_social_collector.py`
- `tests/test_v2_6_social_normalizer.py`
- `tests/test_v2_6_social_deduplicator.py`
- `tests/test_v2_6_mention_velocity.py`
- `tests/test_v2_6_sentiment_classifier.py`
- `tests/test_v2_6_narrative_detector.py`
- `tests/test_v2_6_bot_spam_filter.py`
- `tests/test_v2_6_social_market_linker.py`
- `tests/test_v2_6_hype_pressure_scorer.py`
- `tests/test_v2_6_price_lead_lag_detector.py`
- `tests/test_v2_6_social_ai_context_analyzer.py`
- `tests/test_v2_6_social_api.py`
- `tests/test_v2_6_social_service_integration.py`
- `tests/test_v2_6_social_safety_guards.py`

## Tests Run

Targeted deterministic V2.6:

- `python -m uv run pytest tests/test_v2_6_social_contracts.py tests/test_v2_6_social_normalizer.py tests/test_v2_6_social_deduplicator.py tests/test_v2_6_sentiment_classifier.py tests/test_v2_6_bot_spam_filter.py tests/test_v2_6_hype_pressure_scorer.py tests/test_v2_6_social_ai_context_analyzer.py -q` -> 9 passed

Targeted V2.6 without DB:

- `python -m uv run pytest tests/test_v2_6_social_source_registry.py tests/test_v2_6_social_collector.py tests/test_v2_6_mention_velocity.py tests/test_v2_6_narrative_detector.py tests/test_v2_6_social_market_linker.py tests/test_v2_6_price_lead_lag_detector.py tests/test_v2_6_social_api.py tests/test_v2_6_social_service_integration.py tests/test_v2_6_social_safety_guards.py -q` -> 11 skipped because `POLYBOT_DATABASE_URL` was absent

Explicit DB V2.6 one-by-one:

- `test_source_registered_enabled_disabled_and_fetch_status` -> 1 passed
- `test_manual_item_collected_deduped_and_bad_source_status` -> 1 passed
- `test_manual_social_goes_through_full_pipeline` -> 1 passed
- `test_social_api_endpoints_and_manual_processing` -> 1 passed
- `test_social_linked_only_when_justified_and_closed_penalized` -> 1 passed
- `test_mention_velocity_burst_unique_authors_and_spam_ratio` -> 1 passed
- `test_repeated_topic_creates_stronger_narrative_and_fades` -> 1 passed
- `tests/test_v2_6_price_lead_lag_detector.py -q` -> 2 passed
- `tests/test_v2_6_social_safety_guards.py -q` -> 2 passed

Combined explicit DB V2.6 batch timed out due the existing isolated-schema migration cost. The individual DB-backed tests passed.

Regression batch:

- `python -m uv run pytest tests/test_v2_5_rules_api.py tests/test_v2_5_rules_service_integration.py tests/test_v2_5_rules_safety_guards.py tests/test_v2_4_news_api.py tests/test_v2_4_news_service_integration.py tests/test_v2_4_news_safety_guards.py tests/test_v2_3_ai_api.py tests/test_v2_3_ai_safety_guards.py tests/test_v2_3_1_runtime_startup_responsiveness.py tests/test_v2_2_data_foundation_api.py tests/test_v2_2_data_completeness.py tests/test_v2_1_event_api.py tests/test_v2_1_event_bus.py tests/test_runtime_modes.py tests/test_mode_manager.py tests/test_runtime_api.py tests/test_stage4.py tests/test_stage4_env_isolation.py tests/test_env_runtime.py -q` -> 72 passed, 35 skipped

Full suite:

- `python -m uv run pytest -q` -> 185 passed, 349 skipped

## Runtime Verification

Commands run:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`

Verified existing endpoints:

- `/healthz`
- `/runtime/state`
- `/runtime/health`
- `/events/lag`
- `/data/coverage`
- `/ai/health`
- `/news/recent`
- `/rules/coverage`

Verified new Social endpoints:

- `/social/recent`
- `/social/sources`
- `/social/hype/top`
- `/social/narratives`

Manual safe ingestion:

- `POST /social/manual` with BTC test text succeeded.
- Manual social was stored and normalized.
- Matching crypto markets were linked.
- Hype scores and narratives were persisted.
- `social.sentiment.scored`, `social.noise.scored`, `social.hype.scored`, and `social.signal.created` events appeared in `/events/recent`.

Runtime remained DATA_ONLY with live permissions false.

## Fully Implemented

- source registry
- manual/social collector abstraction
- raw and normalized social persistence
- deterministic deduplication
- mention velocity
- sentiment classification
- narrative detection
- bot/spam/noise scoring
- market linking with compliance penalty
- hype pressure scoring and social signal contract
- price lead/lag detector
- optional AI context analyzer
- API, dashboard truth, events, tests, docs

## Partial / Future

- real external social collectors require configured sources and credentials in a later phase
- bot/spam risk is heuristic and not certainty
- lead/lag is heuristic and non-causal
- Opportunity Cortex consumption is future work

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Social cannot create orders: YES
- Social cannot create order intents: YES
- Social cannot bypass State Governor: YES
- Social cannot bypass AI Budget Governor: YES
- spam ignored or penalized: YES
- mentions velocity calculated: YES
- sentiment classified: YES
- narrative detected: YES
- bot activity penalized: YES
- social linked to market only when justified: YES
- irrelevant social ignored: YES
- hype pressure computed: YES
- social price lead/lag detected or insufficient honestly: YES
- AI analysis optional and safe: YES
- no secrets printed: YES
- social events redacted: YES
- dashboard uses real data only: YES

## Remaining Risks

Runtime orderbook ingestion remains partial from V2.2. Social source network collectors are intentionally minimal and safe until sources are configured. Social hype is not truth and must not be used as a trading decision without future Opportunity Cortex and Risk Governor phases.

## Recommendation

Can move to V2.7 Whale Neuron: YES.
