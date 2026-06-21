# POLYBOT V3.7 Intelligence Expansion Infrastructure Build Report

## Summary

V3.7 adds an intelligence source readiness control plane. It does not enable production ingestion, create intelligence events, or mutate trading state.

## Current Reality Found

- News: `news_sources`, RSS/manual collection, normalization, deduplication, market linking, impact scoring, and AI context analysis exist. Production `news_sources=0`.
- Social: `social_sources`, manual/RSS/public-trend contracts, normalization, hype/noise/narrative services exist. Production `social_sources=0`.
- Whale: `whale_sources`, manual/mock/internal/polymarket contracts, scanner shell, profile builder, market scoring, and follow decisions exist. Production `whale_sources=0`.
- AI: model router, budget governor, cache, local worker, and cloud escalation skeleton exist. Provider credentials are not unified in the template.
- Market Memory: source reliability, whale, no-trade, slippage, rules, and market memory builders exist.
- Existing `source_status` already performs safe read-only Gamma/CLOB/activity/Ollama checks and has placeholder news/social checks.
- Existing `intelligence_sources` from Phase 4A has 4 rows and remains unchanged.
- Missing: unified provider registry, credential requirement status, health/readiness rollup, Neural Bus mapping, Shared Awareness mapping, operator setup plan, and V3 dashboard endpoints.

## Provider Contracts Built

- `IntelligenceSourceDefinition`
- `CredentialCheck`
- `ProviderReadiness`
- `IntelligenceProviderContract`

## Source Registry Built

Registry sources: 20.

By type after runtime validation:

- `NEWS`: 5
- `WHALE`: 4
- `SOCIAL`: 5
- `AI_CONTEXT`: 4
- `MARKET_MEMORY`: 2

Provider health after validation:

- `READY_NO_KEY`: 8
- `DISABLED`: 4
- `BLOCKED_MISSING_CREDENTIALS`: 8

## DB Migration

Migration: `0108_v3_intelligence_source_readiness.sql`

Created:

- `intelligence_source_registry`
- `intelligence_source_credentials_status`
- `intelligence_provider_health`
- `intelligence_missing_requirements`
- `intelligence_connector_tests`

## API Routes

- `GET /dashboard/api/v2/intelligence-sources`
- `GET /dashboard/api/v2/intelligence-sources/requirements`
- `GET /dashboard/api/v2/intelligence-sources/health`
- `POST /intelligence-sources/validate`

All return `mock_data=false`.

## Env Template

Updated `.env.example` only.

Added:

- `NEWS_RSS_FEEDS`
- `NEWS_API_KEY`
- `CRYPTOPANIC_API_KEY`
- `X_BEARER_TOKEN`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `DISCORD_BOT_TOKEN`
- `OPENAI_API_KEY`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL_FAST`
- `OLLAMA_MODEL_PRIMARY`
- `OLLAMA_MODEL_REASONING`
- `POLYMARKET_CLOB_API_KEY`
- `POLYMARKET_CLOB_SECRET`
- `POLYMARKET_CLOB_PASSPHRASE`
- `POLYMARKET_CLOB_HOST`

`ANTHROPIC_API_KEY` already existed and remains in the template.

## Neural Bus Mapping

- News -> `NEWS_DETECTED`
- Whale -> `WHALE_DETECTED`
- Social -> `SOCIAL_SPIKE`
- AI context -> `AI_CONTEXT_UPDATED`
- Market Memory -> `MEMORY_UPDATED`

## Shared Awareness Mapping

- News -> `NEWS`
- Whale -> `WHALE`
- Social -> `SOCIAL`
- AI context -> `CANDIDATE`
- Market Memory -> `MEMORY`

## Tests Added

`tests/test_v3_intelligence_source_readiness.py`

Coverage:

- registry loads
- missing credentials reported
- secrets not exposed
- mock provider health
- RSS provider no-key readiness
- dashboard returns `mock_data=false`
- validate endpoint safe reporting
- Neural Bus event mapping
- Shared Awareness domain mapping
- no trading mutation

## Tests Run

- `docker compose --profile test build test`: passed.
- `docker compose --profile test run --rm test python -m pytest tests/test_v3_intelligence_source_readiness.py -q`: `10 passed, 1 warning in 52.13s`.
- Initial combined V3 regression command with stale filenames: `no tests ran`, file not found.
- Combined broad V3 regression timed out at 304s without result.
- Parallel split V3.0/V3.1 + V3.2/V3.3 hit test Postgres teardown `out of shared memory` / `max_locks_per_transaction`; rerun sequentially after restarting `postgres_test`.
- `tests/test_v3_neural_event_bus.py`: `7 passed in 32.82s`.
- `tests/test_v3_mesh_sessions_foundation.py`: `11 passed, 1 warning in 55.55s`.
- `tests/test_v3_shared_awareness_layer.py`: `10 passed, 1 warning in 47.98s`.
- `tests/test_v3_multi_brain_consumption_layer.py`: `13 passed, 1 warning in 64.72s`.
- `tests/test_v3_mesh_coordinator_evolution.py`: `15 passed, 1 warning in 77.71s`.
- `tests/test_v3_capital_brain_upstream.py`: `18 passed, 1 warning in 84.18s`.
- `tests/test_v3_position_awareness.py`: `15 passed, 1 warning in 71.21s`.
- `tests/test_paper_capital_account.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_runtime_modes.py tests/test_state_governor.py tests/test_runtime_integration_guards.py`: `38 passed in 140.91s`.

## Runtime Smoke

Production runtime was rebuilt and migration applied.

Commands:

- `docker compose build api migrate`
- `docker compose run --rm migrate`: applied `0108_v3_intelligence_source_readiness.sql`
- `docker compose up -d api`

SYSTEM OFF state confirmed:

- `system_power=OFF`
- runtime work, scheduler, neurons, brains, paper, shadow, and live all disallowed
- dashboard read allowed

Smoke endpoint result:

- `GET /dashboard/api/v2/intelligence-sources`: `status=OK`, `mock_data=false`, `total_sources=20`, `missing_required_count=12`
- `GET /dashboard/api/v2/intelligence-sources/requirements`: `status=OK`, `mock_data=false`
- `GET /dashboard/api/v2/intelligence-sources/health`: `status=OK`, `mock_data=false`
- `POST /intelligence-sources/validate`: `status=OK`, `mock_data=false`, `validated_sources=20`, `blocked_sources=8`
- Secret scan over smoke JSON: `false`

## Before / After Counts

Before migration:

- `intelligence_source_registry`: absent
- `intelligence_provider_health`: absent
- `intelligence_missing_requirements`: absent
- `news_sources`: 0
- `social_sources`: 0
- `whale_sources`: 0
- `intelligence_sources`: 4
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `paper_intents`: 6
- `paper_capital_ledger`: 1
- `risk_decisions`: 10332
- `exit_plans`: 10332
- `coordinator_decisions`: 10636
- `brain_outputs`: 10672

After validation:

- `intelligence_source_registry`: 20
- `intelligence_source_credentials_status`: 20
- `intelligence_provider_health`: 20
- `intelligence_missing_requirements`: 19 open rows, 18 distinct env vars
- `intelligence_connector_tests`: 0
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `paper_intents`: 6
- `paper_capital_ledger`: 1
- `risk_decisions`: 10332
- `exit_plans`: 10332
- `coordinator_decisions`: 10636
- `brain_outputs`: 10672

## Missing Credentials

Required:

- `ANTHROPIC_API_KEY`
- `CRYPTOPANIC_API_KEY`
- `NEWS_API_KEY`
- `OPENAI_API_KEY`
- `POLYMARKET_CLOB_API_KEY`
- `POLYMARKET_CLOB_PASSPHRASE`
- `POLYMARKET_CLOB_SECRET`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `TELEGRAM_API_HASH`
- `TELEGRAM_API_ID`
- `X_BEARER_TOKEN`

Optional/configurable:

- `DISCORD_BOT_TOKEN`
- `NEWS_RSS_FEEDS`
- `OLLAMA_MODEL_FAST`
- `OLLAMA_MODEL_PRIMARY`
- `OLLAMA_MODEL_REASONING`
- `POLYMARKET_CLOB_HOST`

`OLLAMA_BASE_URL` was present in the runtime environment.

## Safety Checklist

- Real `.env` was not modified.
- `.env.example` only contains placeholders.
- Secret values were not printed by API responses.
- No fake production intelligence was created.
- No Neural Bus production intelligence events were published by V3.7.
- No orders, fills, positions, paper intents, or capital ledger rows were created.
- Risk, exit, coordinator, and brain output source tables were unchanged.
- Live and shadow remained disabled.

## Remaining Risks

- Provider-specific connector health calls are not implemented in this phase.
- Some optional providers require operator policy choices before enabling, especially X, Telegram, Discord, OpenAI, Anthropic, and authenticated CLOB.
- Existing Pack 1 source tables are still mostly empty until actual sources are configured.
- Current validation proves env presence only, not credential authenticity.

## Phase Status

GREEN.

The infrastructure exists, registry works, missing keys are reported safely, env template is updated, dashboard truth exists, no secrets were exposed, no trading mutation occurred, and targeted/regression tests pass.

## Next Recommended Phase

Actual source connection after the operator supplies at least the minimum viable source set configuration and selects which paid/social/AI providers are allowed.
