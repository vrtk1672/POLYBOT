# V2.20B-1 External Integrations Audit

Date: 2026-05-18

Scope: audit only. No providers were added, no scraping was added, no live trading was enabled, and no secret values are printed here.

## Executive Truth

POLYBOT has durable integration shells for news, social, whales, market data, orderbook/liquidity, AI, and dashboard truth. The repo is strong structurally, but live external-provider readiness is mixed:

- **Real active market source:** Gamma API is implemented and was runtime-reachable.
- **Real orderbook read path:** CLOB `book` reads happened at runtime, but **persisted `orderbook_snapshots` rows are zero**.
- **News:** RSS/manual collection is implemented, but no `news_sources` are configured in DB.
- **Social:** manual/RSS-mirror/public-trend abstractions exist; X/Reddit/Telegram/Discord are source types only, not real live adapters.
- **Whales:** manual/mock/internal source types exist; public/CLOB/chain/API are registry types, but scanner returns `source scanner not configured` for non-manual/non-mock.
- **AI:** local model routing exists, but Ollama/models are missing. Legacy Anthropic services can crash if invoked without `ANTHROPIC_API_KEY`; Hybrid AI degrades.
- **Secrets:** `.env` contains key names for Anthropic and Polymarket credentials, but audit scripts report only presence flags, not values.

## News Source Matrix

| Source | Category | Families | Provider | Env | Implemented | Key | DB Writes | Runtime Proof | Fallback | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Manual News | breaking/scheduled/official/manual | all | manual | none | YES | no | yes | stale manual row only | no-data/stale | LOW |
| RSS Feed | aggregator | all configured categories | RSS | none by default | PARTIAL | no | yes | no configured `news_sources` | empty collection | MEDIUM |
| AP News via legacy external intelligence | aggregator/fact-check | general | web/RSS-like HTML | none | PARTIAL | no | legacy runtime log fetched AP home | not canonical V2.4 source row | MEDIUM |
| Polymarket news/category source | market-specific | polymarket | source type | unknown | DOCS_ONLY/PARTIAL | unknown | schema supports | no source row | no-data | MEDIUM |
| Court | official | legal/court | source type | unknown | DOCS_ONLY | unknown | schema supports | none | insufficient_data | MEDIUM |
| Weather | official | weather | source type | unknown | DOCS_ONLY | unknown | schema supports | none | insufficient_data | MEDIUM |
| Sports | market-specific | sports | source type | unknown | DOCS_ONLY | unknown | schema supports | none | insufficient_data | MEDIUM |
| Crypto/security | market-specific | crypto/security | source type | unknown | DOCS_ONLY | unknown | schema supports | none | insufficient_data | MEDIUM |
| Macro | official | macro | source type | unknown | DOCS_ONLY | unknown | schema supports | none | insufficient_data | MEDIUM |
| GDELT/NewsAPI/Bing/Google News | aggregator | all | docs-only/unknown | possible keys not in `.env.example` | NO/DOCS_ONLY | unknown | no provider adapter found | none | not available | MEDIUM |
| Reuters | fact-check | all | docs-only | none found | DOCS_ONLY | unknown | none | none | not available | LOW |

News DB evidence:

- `news_sources`: `0`
- `news_raw_events`: `1`, latest `2026-05-11T16:48:30Z`
- `news_normalized_events`: `1`, latest `2026-05-11T16:48:31Z`
- `news_impact_scores`: `3`, latest `2026-05-11T16:48:39Z`
- Dashboard `/dashboard/api/v2/news`: `STALE`

Answers:

- Real news ingestion exists for manual and RSS only.
- There is no configured live news provider in `news_sources`.
- Missing news does not crash the V2.20B runtime; it becomes stale/no-data dashboard truth.
- DATA_ONLY can run without fresh news.
- PAPER can technically run without news, but market families that require official confirmation must become `INSUFFICIENT_DATA` or lower confidence.
- News alone must never bypass Risk. Current architecture routes news into context/risk/opportunity surfaces only.

## Social Source Matrix

| Source | Category | Platform | Provider | Env | Implemented | Key | DB Writes | Runtime Proof | Noise/Bot Handling | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Manual Social | community/manual | manual | manual | none | YES | no | yes | stale manual row | bot/noise scorers exist | LOW |
| RSS Mirror | social mirror | rss_mirror | stub | none | PARTIAL | no | yes if implemented fetcher returns | no configured source | dedup/noise pipeline exists | MEDIUM |
| Public Trend API | fast social | public_trends | stub | unknown | PARTIAL | unknown | yes if implemented | no configured source | hype/noise pipeline exists | MEDIUM |
| X/Twitter | fast social/KOL | x_twitter | source type only | no key in `.env.example` | DOCS_ONLY/PARTIAL | yes likely | schema supports | none | no live adapter | HIGH for social-full |
| Reddit | community | reddit | source type only | no key in `.env.example` | DOCS_ONLY/PARTIAL | likely | schema supports | none | no live adapter | MEDIUM |
| Telegram | community/KOL | telegram | source type plus legacy command bot | `POLYBOT_TELEGRAM_BOT_TOKEN` in settings only | PARTIAL | yes for bot | social source schema supports | no social feed | no live social adapter | MEDIUM |
| Discord | community | discord | source type only | no key in `.env.example` | DOCS_ONLY/PARTIAL | yes likely | schema supports | none | no live adapter | MEDIUM |
| Farcaster/YouTube/TikTok | social | unknown | none found | none found | NO/DOCS_ONLY | unknown | no | none | no pipeline input | LOW |

Social DB evidence:

- `social_sources`: `0`
- `social_raw_events`: `1`, latest `2026-05-13T12:19:29Z`
- `social_normalized_events`: `1`, latest `2026-05-13T12:19:30Z`
- Dashboard `/dashboard/api/v2/social`: `STALE`

Answers:

- Social ingestion is mostly shell/manual. X/Reddit/Telegram/Discord are schema/source-type ready, not live providers.
- Missing social does not crash runtime.
- DATA_ONLY can run without social.
- PAPER can run without social unless a specific route/engine requires social confirmation.
- Social alone cannot make a trade ready; it can wake attention/context only when implemented and risk-safe.

## Whale Source Matrix

| Source | Provider | Implemented | Key | DB Writes | Runtime Proof | Notes | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Manual Whale Input | manual | YES | no | via service/manual path | historical rows exist | real identity not guaranteed | LOW |
| Mock Whale Feed | mock | YES for tests | no | yes if invoked | historical/test-like rows exist | disabled by default | LOW |
| Internal Paper Flow | internal | PARTIAL | no | intended | no current source row | can learn from internal outcomes later | LOW |
| Polymarket Public | public/API | DOCS_ONLY/PARTIAL | unknown | schema supports | no source row | no scanner configured | HIGH for whale-live |
| CLOB Public | public/API | DOCS_ONLY/PARTIAL | unknown | schema supports | no source row | no scanner configured | HIGH for whale-live |
| Chain/API/CSV | chain/API/manual import | DOCS_ONLY/PARTIAL | unknown | schema supports | no source row | scanner not configured | MEDIUM |

Whale DB evidence:

- `whale_sources`: `0`
- `whale_events`: `2228`, latest `2026-05-15T14:33:36Z`
- `whale_profiles`: `1110`, latest `2026-05-15T14:33:44Z`
- Dashboard `/dashboard/api/v2/whales`: `STALE`

Conclusion: whale memory/history exists, but current live whale source registry is empty and public whale scanning is not configured.

## Market / Orderbook / Liquidity / Fees Matrix

| Source | Provider | Implemented | Runtime Reachable | DB Writes | Freshness | Required DATA_ONLY | Required PAPER | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gamma events/markets | `https://gamma-api.polymarket.com/events` | YES | yes, 2500 events fetched | `markets_v2`, `market_snapshots_v2` | fresh | yes | yes | NONE for DATA_ONLY |
| CLOB orderbook book reads | `https://clob.polymarket.com/book` | PARTIAL | yes, logs show `200` | **no persisted rows** | not verified in DB | no | yes | HIGH for PAPER |
| Liquidity snapshots | internal analyzer | YES | yes via runtime cycle | `liquidity_snapshots` | fresh | helpful | yes | NONE if orderbook source fixed |
| Fee snapshots | internal analyzer | YES | yes via runtime cycle | `fee_snapshots` | fresh | helpful | yes | LOW |
| Trade/fill truth | internal paper/shadow only | YES | API/DB | `orders_v2`, `fills_v2` | stale smoke rows | no | yes for paper outcomes | MEDIUM |

DB evidence:

- `markets_v2`: `11`, latest `2026-05-18T13:05:09Z`
- `market_snapshots_v2`: `1286`, latest `2026-05-18T13:05:14Z`
- `orderbook_snapshots`: `0`
- `liquidity_snapshots`: `1288`, latest `2026-05-18T13:05:10Z`
- `fee_snapshots`: `1287`, latest `2026-05-18T13:05:12Z`

Conclusion: DATA_ONLY has enough market/liquidity truth to run. PAPER must remain blocked until persisted orderbook/depth truth exists.

## AI / Model Readiness Matrix

| Task | Module | Model/Provider | Local/Cloud | Implemented | Present | Cache/Cost | Fallback | Crash Risk | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Market classification | Hybrid AI | `qwen3:8b` | local | YES | missing | yes | `UNAVAILABLE` | LOW | MEDIUM |
| News dedup | Hybrid AI | `qwen3:8b` | local | YES | missing | yes | `UNAVAILABLE` | LOW | MEDIUM |
| Rules summary | Hybrid AI | `qwen3:14b` | local | YES | missing | yes | `UNAVAILABLE` | LOW | MEDIUM |
| Market linking/context summary/wording precheck | Hybrid AI | `qwen3:14b` | local | YES | missing | yes | `UNAVAILABLE` | LOW | MEDIUM |
| Trap/contradiction reasoning | Hybrid AI | `deepseek-r1:14b` or `cloud-critical-reasoner` | local/cloud | YES | missing local | yes | local unavailable/cloud gated | LOW/MEDIUM | MEDIUM |
| Legacy event interpretation | `app/services/event_interpreter.py` | `claude-opus-4-6` | cloud | PARTIAL | key absent in audit shell | legacy logs | raises if key missing when invoked | MEDIUM | MEDIUM |
| Legacy resolution/invalidation/cognition | `app/services/*lite.py` | `claude-opus-4-6` | cloud | PARTIAL | key absent in audit shell | legacy logs | raises if key missing when invoked | MEDIUM | MEDIUM |

AI readiness script:

- Ollama binary: missing.
- Missing local models: `qwen3:8b`, `qwen3:14b`, `deepseek-r1:14b`.
- `ANTHROPIC_API_KEY`: absent in audit process; canonical runtime may load `.env`.

Install commands if local model runtime is required:

```powershell
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull deepseek-r1:14b
```

## Secrets / ENV Matrix

Names only, no values:

| Env Var | Category | In `.env` | In `.env.example` | Required DATA_ONLY | Required PAPER | Missing Behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `POLYBOT_DATABASE_URL` | Database | no | yes | yes | yes | DB-backed tests/runtime fail unless script sets it |
| `PHASE1_PERSISTENCE_ENABLED` | Database | no | yes | yes | yes | may run non-persistent/partial |
| `PHASE1_AUTO_MIGRATE` | Database | no | yes | no | no | migrations manual |
| `POLYBOT_RUNTIME_MODE` | Runtime | yes | yes | yes | yes | defaults can be misleading |
| `POLYBOT_EXECUTION_BACKEND` | Runtime | yes | yes | yes | yes | defaults to paper in scripts |
| `POLYBOT_REFRESH_INTERVAL_SECONDS` | Runtime | no | yes | no | no | defaults 60 |
| `POLYBOT_API_HOST` / `POLYBOT_API_PORT` | Runtime | no | yes | no | no | defaults 127.0.0.1:8000 |
| `ANTHROPIC_API_KEY` | AI | yes | yes | no | no | Hybrid degrades; legacy AI raises if invoked |
| `OPENAI_API_KEY` | AI | no | no | no | no | no code requirement found |
| `NEWS_API_KEY` | News | no | no | no | no | no adapter found |
| `TWITTER_API_KEY` / X keys | Social | no | no | no | no | no adapter found |
| `REDDIT_CLIENT_ID` | Social | no | no | no | no | no adapter found |
| `TELEGRAM_BOT_TOKEN` / `POLYBOT_TELEGRAM_BOT_TOKEN` | Webhook/control/social | no | no | no | no | Telegram alerts/control unavailable |
| `DISCORD_BOT_TOKEN` | Social | no | no | no | no | no adapter found |
| `POLY_PRIVATE_KEY` | Live trading | yes | yes | no | no | live auth invalid; safe for V2.20 |
| `POLY_FUNDER` | Live trading | yes | yes | no | no | live auth invalid; safe for V2.20 |
| `POLY_API_KEY` / `POLY_API_SECRET` / `POLY_API_PASSPHRASE` | CLOB/live | yes | yes | no | no | live/auth balance disabled by safety fix |
| `LIVE_TRADING_ENABLED` | Safety | yes | yes | must be false | must be false | unsafe if true without certification |
| `LIVE_KILL_SWITCH` | Safety | yes | yes | should be true | should be true | critical safety boundary |

Missing key list from audit process:

- `OPENAI_API_KEY`
- `NEWS_API_KEY`
- `TWITTER_API_KEY`
- `REDDIT_CLIENT_ID`
- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`

`ANTHROPIC_API_KEY` is present in `.env` by name but absent from the direct audit process unless loaded by runtime script.

## Docs-Only / Partial Integrations

- X/Twitter live ingestion.
- Reddit live ingestion.
- Telegram social ingestion.
- Discord social ingestion.
- Farcaster, YouTube, TikTok.
- GDELT/NewsAPI/Bing/Google News as provider adapters.
- Official court/weather/sports/macro/SEC/CFTC/Fed/BLS/BEA source adapters.
- Polymarket public whale/CLOB whale scanning.
- Chain/API whale feeds.
- Real Ollama transport.

## What Can Run Degraded

- DATA_ONLY without AI: yes, with `AI_UNAVAILABLE`/no AI output.
- DATA_ONLY without fresh news/social/whales: yes, dashboard shows stale/no-data.
- Opportunity/strategy/risk surfaces can consume stale/no-data and should reduce confidence/block when required.
- PAPER without news/social/whales: possible only for markets not requiring those confirmations.

## What Blocks PAPER

- Persisted orderbook/depth freshness missing.
- Exit liquidity must be verified from real orderbook/depth.
- Risk/execution must not rely on last price alone.

## Recommended External Setup Order

1. Fix persisted orderbook snapshot writing from CLOB book responses.
2. Configure at least one real RSS/news source in `news_sources`.
3. Decide local-AI policy: install Ollama/models or formally run AI-degraded.
4. Configure social providers only after choosing specific platform APIs and keys.
5. Implement/enable real whale public/CLOB scanner only after source semantics are defined.
