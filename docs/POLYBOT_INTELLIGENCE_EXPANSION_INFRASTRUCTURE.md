# POLYBOT V3.7 Intelligence Expansion Infrastructure

## Purpose

V3.7 prepares external intelligence sources without enabling production ingestion or trading behavior.

This phase adds a source readiness control plane for:

- News
- Whale activity
- Social activity
- AI context
- Market memory inputs

The infrastructure reports what is ready now, what requires credentials, which Neural Event Bus event each source will publish into, and which Shared Awareness domain it feeds.

## Existing Reality

The repository already contains partial source-specific infrastructure:

- `news_sources`, RSS/manual news collection, normalization, deduplication, market linking, and impact scoring.
- `social_sources`, manual/social source contracts, normalization, hype/noise/narrative scoring shells.
- `whale_sources`, manual/mock/internal/polymarket source contracts, whale normalization, profiles, market scoring, and follow decisions.
- `intelligence_sources`, `intelligence_ingestion_runs`, and external raw/normalized event tables from earlier external intelligence foundation work.
- `source_status` for Gamma, CLOB orderbook/prices/spreads, Polymarket activity, Ollama, and placeholder news/social providers.
- AI Brain contracts, model router, budget governor, cache, local worker, and cloud escalation skeleton.
- Market Memory builders for market, source reliability, whale, slippage, rules, and no-trade memory.

The missing piece was one unified readiness layer that tells the operator exactly what accounts/keys/configuration are missing and how each provider will enter the V3 nervous system.

## Source Registry

The V3.7 registry lives in `intelligence_source_registry`.

Each source defines:

- `source_id`
- `source_type`
- `provider_name`
- `requires_api_key`
- `required_env_vars`
- `optional_env_vars`
- `status`
- `health_status`
- `setup_url_or_notes`
- `cost_model`
- `priority`
- `enabled_by_default`
- `neural_event_type`
- `awareness_domain`
- `target_tables_json`
- `metadata_json`

The canonical in-code catalog is `app/intelligence_sources/catalog.py`.

## Provider Contracts

V3.7 adds provider readiness contracts in `app/intelligence_sources/contracts.py`:

- `IntelligenceSourceDefinition`
- `CredentialCheck`
- `ProviderReadiness`
- `IntelligenceProviderContract`

These contracts intentionally validate readiness, not real production ingestion.

## Credential Validation

`IntelligenceSourceReadinessService` validates only:

- whether an env var is present
- whether it is required or optional
- whether a provider is blocked by missing credentials

It never returns secret values.

Statuses:

- `READY_NO_KEY`: no credential required
- `READY_FOR_CONNECTOR_TEST`: required credentials are present, but provider-specific connector testing still needs to run
- `BLOCKED`: missing required credentials
- `AVAILABLE_DISABLED_BY_DEFAULT`: provider contract exists but is intentionally disabled until operator selection

## Neural Bus Mapping

Provider mappings are explicit:

- News providers publish `NEWS_DETECTED`
- Whale providers publish `WHALE_DETECTED`
- Social providers publish `SOCIAL_SPIKE`
- AI providers publish `AI_CONTEXT_UPDATED`
- Market Memory providers publish `MEMORY_UPDATED`

V3.7 does not publish production intelligence events by itself.

## Shared Awareness Mapping

Provider mappings are explicit:

- News -> `NEWS`
- Whale -> `WHALE`
- Social -> `SOCIAL`
- AI context -> `CANDIDATE`
- Market memory -> `MEMORY`

Missing domains remain missing until source-backed evidence exists.

## API

Added:

- `GET /dashboard/api/v2/intelligence-sources`
- `GET /dashboard/api/v2/intelligence-sources/requirements`
- `GET /dashboard/api/v2/intelligence-sources/health`
- `POST /intelligence-sources/validate`

All return `mock_data=false`.

## Safety

V3.7 does not:

- modify `.env`
- expose secrets
- create fake intelligence
- enable live or shadow
- create orders, fills, positions, or paper intents
- mutate paper capital
- change risk, exit, coordinator, or brain output source truth

Validation writes only readiness metadata to V3.7 readiness tables.
