# POLYBOT V3.8 Real Intelligence Validation Flow Report

## Summary

V3.8 validated real external intelligence readiness and proved one source-backed provider flow through the V3 nervous system.

This phase did not enable live trading, shadow trading, paper execution, order creation, fill creation, position creation, or paper intent creation.

## Dispatch

- Executor: Codex
- Task mode: CONTROLLED_VALIDATION + SAFE_FIX_IF_NEEDED + INTELLIGENCE_FLOW_VERIFICATION
- Risk: HIGH
- ChatGPT review: REQUIRED

## Current Reality Found

- V3.7 official intelligence env names are present in `.env.example` and passed into the API container by `docker-compose.yml`.
- Real `.env` contains configured Polymarket CLOB, NewsAPI, RSS, Ollama, OpenAI, and Anthropic values. Values were inspected masked only.
- API container sees the configured V3.7 names.
- Missing providers remain CryptoPanic, X/Twitter, Reddit, Telegram, and Discord.
- `news_sources`, `news_raw_events`, `news_normalized_events`, and `news_impact_scores` exist, but production rows are currently zero.
- RSS collection and news normalization code exists, but no production `news_sources` rows are registered from `NEWS_RSS_FEEDS` yet.
- NewsAPI has credentials and validates against the provider, but the repo currently marks NewsAPI as a planned connector contract rather than an implemented collector.
- Polymarket Gamma validates with real active events and token candidates.
- Polymarket CLOB read-only validates after fixing the token-candidate probe to use tradable/orderbook-enabled Gamma markets.
- Ollama validates after adding Docker-host fallback for `localhost:11434`; configured model `qwen3:4b` exists and a tiny local prompt succeeded.
- OpenAI and Anthropic keys validate with safe model-list checks. No generation request was sent to either cloud provider.

## Provider Validation Table

| Provider | Env present | API container visible | Auth OK | Endpoint OK | Sample data OK | Normalized path OK | Neural mapping OK | Mesh/session flow | Awareness | Brain opinion | Coordinator | Status | Exact issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Polymarket Gamma | N/A | N/A | N/A | YES | YES | YES, via market normalization | YES, `MARKET_REPRICING` | Mapping exists | Mapping exists | Via session awareness | Via mesh bundle | GREEN | None |
| Polymarket CLOB book/prices/spreads | YES | YES | N/A for `/book` | YES | YES | YES, source-status metrics | YES, `ORDERBOOK_REFRESHED` / `SPREAD_CHANGED` / `LIQUIDITY_CHANGED` | YES | YES | YES | YES | GREEN | Fixed probe was using non-orderbook Gamma tokens |
| RSS feeds | YES | YES | N/A | YES | YES | YES, `NewsCollector` + `NewsNormalizer` | YES, `NEWS_DETECTED` from `news_normalized_events` | Not run for NEWS | Mapping exists | Mapping exists | Mapping exists | YELLOW | Production `news_sources=0`; env RSS feeds are not auto-registered |
| NewsAPI | YES | YES | YES | YES | YES | PARTIAL | YES, `NEWS_DETECTED` | Not run for NEWS | Mapping exists | Mapping exists | Mapping exists | YELLOW | Provider auth works, but NewsAPI collector is still planned contract |
| Ollama | YES | YES | N/A | YES | YES | PARTIAL | YES, `AI_CONTEXT_UPDATED` | Not run for AI | Mapping exists | Mapping exists | Mapping exists | YELLOW | Local HTTP validation works; Hybrid AI local worker still lacks production Ollama transport wiring |
| OpenAI | YES | YES | YES | YES | YES | PARTIAL | YES, `AI_CONTEXT_UPDATED` | Not run for AI | Mapping exists | Mapping exists | Mapping exists | YELLOW | Provider auth works; OpenAI is planned optional cloud path, not wired production ingestion |
| Anthropic / Claude | YES | YES | YES | YES | YES | PARTIAL | YES, `AI_CONTEXT_UPDATED` | Not run for AI | Mapping exists | Mapping exists | Mapping exists | YELLOW | Provider auth works; existing Anthropic services are guarded and not run in this validation |
| CryptoPanic | NO | NO | NO | NO | NO | Planned | YES, `NEWS_DETECTED` | NO | NO | NO | NO | YELLOW | Missing `CRYPTOPANIC_API_KEY` |
| X/Twitter | NO | NO | NO | NO | NO | Planned | YES, `SOCIAL_SPIKE` | NO | NO | NO | NO | YELLOW | Missing `X_BEARER_TOKEN` |
| Reddit | NO | NO | NO | NO | NO | Stub | YES, `SOCIAL_SPIKE` | NO | NO | NO | NO | YELLOW | Missing `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`; optional `REDDIT_USER_AGENT` missing |
| Telegram | NO | NO | NO | NO | NO | Planned | YES, `SOCIAL_SPIKE` | NO | NO | NO | NO | YELLOW | Missing `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`; optional bot/channel vars missing |
| Discord | NO | NO | NO | NO | NO | Optional disabled | YES, `SOCIAL_SPIKE` | NO | NO | NO | NO | YELLOW | Optional disabled provider; token/channels missing |

## CLOB Root Cause

Initial CLOB source-status rows were degraded because the bounded Gamma token selection included markets whose token IDs returned:

- HTTP 404
- `No orderbook exists for the requested token id`

The CLOB endpoint itself was healthy. Filtering Gamma markets to active, open, accepting-orders, orderbook-enabled candidates returned a real CLOB book:

- sample market id: `691547`
- best bid: `0.32`
- best ask: `0.33`
- spread: `0.01`
- depth within 1c: `785.8`

Fix applied in `app/services/source_status.py`.

## Ollama Root Cause

Initial Ollama status was degraded because `.env` configured `OLLAMA_BASE_URL=http://localhost:11434`.

That works from Windows host, but inside the API container `localhost` points to the container. The API container can reach Ollama through:

- `http://host.docker.internal:11434`

Configured model validation:

- `qwen3:4b` present
- tiny local prompt succeeded

Fix applied in `app/services/source_status.py` to fall back from localhost to Docker host for the health probe.

## RSS And NewsAPI

RSS:

- `NEWS_RSS_FEEDS` parsed.
- At least one configured feed reachable.
- Sample feed host: `feeds.bbci.co.uk`
- Items fetched: `34`
- News normalization path exists through `NewsCollector` and `NewsNormalizer`.
- Production persistence path requires registering `news_sources`; current production `news_sources=0`.

NewsAPI:

- `NEWS_API_KEY` visible in API container.
- Auth OK.
- Endpoint OK.
- Sample query returned one article.
- Repo status remains partial because NewsAPI connector is cataloged as `planned_contract`.

## AI Providers

Ollama:

- endpoint OK after Docker-host fallback.
- configured model exists.
- tiny local prompt OK.

OpenAI:

- `OPENAI_API_KEY` visible in API container.
- safe `/v1/models` check returned 200.
- no generation request made.

Anthropic:

- `ANTHROPIC_API_KEY` visible in API container.
- safe `/v1/models` check returned 200.
- no generation request made.

## Real Flow Trace

Source-backed CLOB flow was verified:

```text
Polymarket Gamma
-> CLOB /book read-only source-status probe
-> source_status row: polymarket_clob_orderbook ACTIVE/FRESH
-> Neural Event: ORDERBOOK_REFRESHED
-> Mesh Session: MARKET_SESSION for market_id=691547
-> Shared Awareness: ORDERBOOK PARTIAL/PRESENT source-backed state
-> Multi-Brain: Risk, Exit, Capital, Context opinions
-> Coordinator Input Bundle: source_brain_count=4
-> Mesh Coordinator Decision: WATCH / WATCH
-> Brain Dialogue materialized source-backed messages
```

Flow identifiers:

- event id: `neural_event_d4ffe0d8af51460bb690566eb5818bd9`
- session id: `mesh_session_market_session_90a091a6b60a09e2871fb0ca`
- awareness id: `shared_awareness_mesh_session_market_session_90a091a6b60a09e2871fb0ca`
- coordinator decision id: `mesh_decision_mesh_session_market_session_90a091a6b60a09e2871fb0ca`

## Safety Counts

Before flow:

- `live_orders=0`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `paper_intents=6`
- `paper_capital_ledger=1`
- `risk_decisions=10332`
- `exit_plans=10332`
- `coordinator_decisions=10636`
- `brain_outputs=10672`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- paper account current/available/locked/exposure: `1000/1000/0/0`

After flow:

- all safety counts unchanged.
- V3 derived rows increased by one real event/session/awareness/opinion/decision chain.

## Secret Exposure Check

- Real `.env` was not modified.
- Secrets were inspected masked only.
- API endpoint responses were checked against actual configured secret values.
- Actual secret hits: `0`.

## Remaining Operator Actions

- Configure CryptoPanic if desired.
- Configure X/Twitter only if budget and terms are approved.
- Configure Reddit client id/secret and user agent if Reddit ingestion is desired.
- Configure Telegram API id/hash and approved channels before Telegram ingestion.
- Configure Discord only with explicit channel allowlist approval.
- Decide whether RSS feeds should be auto-registered into `news_sources` in the next ingestion phase.

## Remaining Engineering Actions

- Implement real NewsAPI collector if NewsAPI should produce persisted news rows.
- Add RSS source registration/sync from `NEWS_RSS_FEEDS`.
- Wire local Ollama transport into `HybridAIBrainService` if local AI should produce `AI_CONTEXT_UPDATED`.
- Decide whether OpenAI should be implemented as a cloud worker alongside existing Anthropic paths.
- Add provider-specific source-backed ingestion workers behind SYSTEM ON and State Governor controls.

## Phase Status

GREEN for configured provider validation and first source-backed nervous-system flow.

YELLOW for full intelligence ingestion readiness because NewsAPI/OpenAI/Ollama production ingestion wiring remains partial and some social/news providers lack credentials.

## Can Move To Actual News/Whale/Social/AI Ingestion Phase

YES, with scope split:

- YES for RSS, NewsAPI collector implementation, CLOB/orderbook source-backed ingestion, and Ollama transport wiring.
- NO for CryptoPanic, X/Twitter, Reddit, Telegram, and Discord until the missing credentials/operator allowlists are supplied.
