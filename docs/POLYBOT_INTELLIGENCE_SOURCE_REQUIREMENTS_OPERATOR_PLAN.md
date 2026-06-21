# POLYBOT V3.7 Intelligence Source Requirements Operator Plan

## Exact Keys And Accounts

| Priority | Provider | Required Now | Free/Paid | Env Var |
| --- | --- | --- | --- | --- |
| 1 | Public RSS feeds | No key | Free | `NEWS_RSS_FEEDS` optional |
| 2 | GDELT | No key | Free | none |
| 3 | Polymarket Gamma | No key | Free | none |
| 4 | Polymarket CLOB/Data API public trades | No key | Free | none |
| 5 | Ollama local | No key | Local compute | `OLLAMA_BASE_URL` optional |
| 6 | Reddit API | Optional | Free account | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` |
| 7 | X/Twitter API | Optional | Paid or limited free | `X_BEARER_TOKEN` |
| 8 | NewsAPI | Optional | Free tier or paid | `NEWS_API_KEY` |
| 9 | CryptoPanic | Optional | Free tier or paid | `CRYPTOPANIC_API_KEY` |
| 10 | Telegram public channels | Optional | Free account | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_CHANNELS`; `TELEGRAM_BOT_TOKEN` only for bot delivery/control |
| 11 | Polymarket CLOB authenticated read-only | Optional | Free account | `POLYMARKET_CLOB_API_KEY`, `POLYMARKET_CLOB_SECRET`, `POLYMARKET_CLOB_PASSPHRASE` |
| 12 | OpenAI API | Optional | Paid usage | `OPENAI_API_KEY` |
| 13 | Anthropic API | Optional | Paid usage | `ANTHROPIC_API_KEY` |
| 14 | Discord optional | Optional, disabled | Free account | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNELS` |

## What Each Key Enables

- `NEWS_API_KEY`: full general/news search API connector readiness for `NEWS_DETECTED`.
- `CRYPTOPANIC_API_KEY`: crypto and market-moving crypto news readiness for `NEWS_DETECTED`.
- `X_BEARER_TOKEN`: X/Twitter social spike connector readiness for `SOCIAL_SPIKE`.
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT`: Reddit discussion and narrative readiness for `SOCIAL_SPIKE`.
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_CHANNELS`: Telegram public/channel ingestion readiness for `SOCIAL_SPIKE`.
- `TELEGRAM_BOT_TOKEN`: optional Telegram bot delivery/control token; not required for public channel API readiness.
- `DISCORD_BOT_TOKEN` and `DISCORD_CHANNELS`: optional Discord ingestion readiness; disabled until explicit allowlist approval.
- `OPENAI_API_KEY`: optional cloud AI context escalation readiness for `AI_CONTEXT_UPDATED`.
- `ANTHROPIC_API_KEY`: optional cloud AI context escalation readiness for `AI_CONTEXT_UPDATED`.
- `OLLAMA_BASE_URL`: local AI endpoint readiness.
- `POLYMARKET_CLOB_API_KEY`, `POLYMARKET_CLOB_SECRET`, `POLYMARKET_CLOB_PASSPHRASE`: authenticated read-only Polymarket CLOB readiness. This does not enable orders.

## Where To Get Them

- NewsAPI: https://newsapi.org/
- CryptoPanic: https://cryptopanic.com/developers/api/
- X developer access: https://developer.x.com/
- Reddit apps: https://www.reddit.com/prefs/apps
- Telegram API: https://my.telegram.org/
- Ollama: https://ollama.com/
- OpenAI API: https://platform.openai.com/
- Anthropic API: https://console.anthropic.com/
- Polymarket CLOB credentials: operator Polymarket/CLOB account configuration.

## How To Test

After adding credentials to local `.env`, run:

```powershell
POST /intelligence-sources/validate
GET /dashboard/api/v2/intelligence-sources
GET /dashboard/api/v2/intelligence-sources/requirements
GET /dashboard/api/v2/intelligence-sources/health
```

The response must show:

- `mock_data=false`
- env vars as present or missing
- no secret values
- providers still disabled until connector-specific health checks are implemented/enabled

## Priority Order

1. Choose public RSS feeds and configure `NEWS_RSS_FEEDS`.
2. Confirm GDELT and Polymarket public sources are acceptable for MVP.
3. Configure local Ollama if AI context should run locally.
4. Obtain Reddit credentials for social baseline.
5. Obtain NewsAPI or CryptoPanic for richer news.
6. Obtain X/Twitter access if budget and terms are acceptable.
7. Add Telegram only with an operator-approved channel allowlist.
8. Add OpenAI or Anthropic only after AI budget policy is confirmed.
9. Add authenticated CLOB read-only credentials only after confirming no live permissions are enabled.

## Minimum Viable Source Set

- RSS feeds
- GDELT
- Polymarket Gamma
- Polymarket CLOB/Data API public trades
- Internal whale profile builder
- Manual social ingestion
- Ollama local if available
- AI budget/cache internal surface
- Market memory outcomes

## Full Professional Source Set

- RSS feeds
- GDELT
- NewsAPI
- CryptoPanic
- Polymarket Gamma
- Polymarket CLOB/Data API public trades
- Polymarket CLOB authenticated read-only
- Internal whale profile builder
- X/Twitter API
- Reddit API
- Telegram public channels with allowlist
- Ollama local
- OpenAI API
- Anthropic API
- AI budget/cache internal surface
- Market memory outcomes

## What Codex Can Do After Keys Are Supplied

After credentials are present, Codex can implement provider-specific connector tests, enable source-specific ingestion behind the State Governor, publish source-backed `NEWS_DETECTED`, `WHALE_DETECTED`, `SOCIAL_SPIKE`, `AI_CONTEXT_UPDATED`, and `MEMORY_UPDATED` events, and verify Shared Awareness updates without creating trades or changing execution behavior.
