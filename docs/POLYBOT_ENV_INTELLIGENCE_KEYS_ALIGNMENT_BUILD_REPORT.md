# POLYBOT ENV Intelligence Keys Alignment + Validation Build Report

## Summary

The real `.env`, `.env.example`, config/settings code, V3.7 intelligence source readiness layer, and provider-related env lookups were audited. Code was aligned to prefer official V3.7 intelligence names while retaining legacy aliases where they protect existing runtime compatibility.

No real `.env` values were modified or printed.

## Classification

- Executor: Codex
- Task mode: CONFIG_AUDIT + SAFE_FIX + PROVIDER_VALIDATION
- Risk: MEDIUM-HIGH
- ChatGPT review: REQUIRED

## Files Inspected

- `.env`
- `.env.example`
- `docker-compose.yml`
- `app/config.py`
- `app/db/config.py`
- `app/stage4/config.py`
- `app/intelligence_sources/*`
- `app/services/source_status.py`
- `app/services/runtime_intelligence.py`
- `app/services/external_intelligence.py`
- `app/services/alerts.py`
- `app/services/telegram_bot.py`
- `app/news_neuron/*`
- `app/social_neuron/*`
- `app/whale_neuron/*`
- `app/ai_brain/*`
- `app/market_memory/*`
- env references found by `rg` for `os.getenv`, `os.environ`, settings aliases, dotenv, Polymarket, News, Reddit, Telegram, Discord, OpenAI, Anthropic, and Ollama names.

## Real `.env` Vars Found

Masked only:

- `POLYMARKET_CLOB_HOST`: present, `htt....com`
- `POLYMARKET_CHAIN_ID`: present
- `POLYMARKET_SIGNATURE_TYPE`: present
- `POLYMARKET_FUNDER_ADDRESS`: present, `0xC...2c30`
- `POLYMARKET_CLOB_API_KEY`: present, `758...35f4`
- `POLYMARKET_CLOB_SECRET`: present, `qbE...i3Y=`
- `POLYMARKET_CLOB_PASSPHRASE`: present, `461...83f3`
- `NEWS_API_KEY`: present, `57f...821a`
- `NEWS_RSS_FEEDS`: present, `htt.../rss`
- `OPENAI_API_KEY`: present, `sk-...WqUA`
- `OLLAMA_BASE_URL`: present, `htt...1434`
- `OLLAMA_MODEL_FAST`: present
- `OLLAMA_MODEL_PRIMARY`: present
- `OLLAMA_MODEL_REASONING`: present
- `ANTHROPIC_API_KEY`: present, `sk-...KQAA`
- Runtime/safety vars present: `POLYBOT_RUNTIME_MODE`, `POLYBOT_EXECUTION_BACKEND`, `LIVE_TRADING_ENABLED`, `LIVE_MAX_ORDER_USD`, `LIVE_KILL_SWITCH`, `LIVE_USE_ADAPTIVE_SELECTOR`, `LIVE_OPTIONAL_WHITELIST_MODE`, `LIVE_MIN_CONFIDENCE`.

Missing from real `.env` among official V3.7 names:

- `CRYPTOPANIC_API_KEY`
- `X_BEARER_TOKEN`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNELS`
- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNELS`

## Expected By Code After Alignment

Official V3.7 names:

- `POLYMARKET_CLOB_API_KEY`
- `POLYMARKET_CLOB_SECRET`
- `POLYMARKET_CLOB_PASSPHRASE`
- `POLYMARKET_CLOB_HOST`
- `NEWS_API_KEY`
- `CRYPTOPANIC_API_KEY`
- `NEWS_RSS_FEEDS`
- `X_BEARER_TOKEN`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNELS`
- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNELS`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL_FAST`
- `OLLAMA_MODEL_PRIMARY`
- `OLLAMA_MODEL_REASONING`

Legacy aliases retained:

- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`
- `POLY_CLOB_HOST`
- `POLY_CHAIN_ID`
- `POLY_SIGNATURE_TYPE`
- `POLY_FUNDER`
- `POLYBOT_TELEGRAM_BOT_TOKEN`
- `POLYBOT_TELEGRAM_DEFAULT_CHAT_ID`
- `POLYBOT_TELEGRAM_WEBHOOK_SECRET`

## Mismatches Found

| Area | `.env` / standard | Previous code expectation | Status | Fix |
| --- | --- | --- | --- | --- |
| Polymarket CLOB credentials | `POLYMARKET_CLOB_*` | `POLY_API_*` | NAME_MISMATCH | Stage4 settings now prefer official names and retain legacy aliases |
| Polymarket CLOB host | `POLYMARKET_CLOB_HOST` | `POLYBOT_CLOB_API_BASE_URL` / `POLY_CLOB_HOST` | NAME_MISMATCH | Source status now reads `POLYMARKET_CLOB_HOST` first |
| Polymarket chain/signature/funder | `POLYMARKET_CHAIN_ID`, `POLYMARKET_SIGNATURE_TYPE`, `POLYMARKET_FUNDER_ADDRESS` | `POLY_CHAIN_ID`, `POLY_SIGNATURE_TYPE`, `POLY_FUNDER` | NAME_MISMATCH | Stage4 settings now support both |
| Telegram bot | `TELEGRAM_BOT_TOKEN` | `POLYBOT_TELEGRAM_BOT_TOKEN` via prefix | NAME_MISMATCH | Settings now support both |
| Reddit user agent | official V3.7 name | not listed in catalog | MISSING_IN_CODE | Added as optional provider env |
| Telegram channels | official V3.7 name | not listed in catalog | MISSING_IN_CODE | Added as optional provider env |
| Discord channels | official V3.7 name | not listed in catalog | MISSING_IN_CODE | Added as optional provider env |
| API container env | real `.env` had keys | Docker API did not pass them through | NAME_MISMATCH / RUNTIME_VISIBILITY | Added safe variable-name pass-through in `docker-compose.yml` |

## Fixes Applied

- `app/stage4/config.py`: official Polymarket aliases preferred, legacy aliases retained.
- `app/services/source_status.py`: `POLYMARKET_CLOB_HOST` preferred for CLOB read-only checks.
- `app/config.py`: Telegram settings accept official and `POLYBOT_` aliases.
- `app/intelligence_sources/catalog.py`: added `REDDIT_USER_AGENT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNELS`, and `DISCORD_CHANNELS` provider requirements.
- `.env.example`: added official missing placeholders.
- `docker-compose.yml`: passes official V3.7 intelligence env var names into the API container with blank/default interpolation.
- `tests/conftest.py`: isolates official Polymarket env vars in Stage4 tests.
- `tests/test_v3_intelligence_source_readiness.py`: added official-name recognition test.
- `tests/test_stage4.py`: clarified missing-credential branch setup by explicitly enabling live config in the in-memory test object while keeping this isolated from runtime.
- `docs/POLYBOT_INTELLIGENCE_SOURCE_REQUIREMENTS_OPERATOR_PLAN.md`: updated Reddit, Telegram, and Discord requirements.

## Provider Validation Results

Service-level validation against real `.env`:

- Validated sources: 20
- Ready/present or no-key: `news_rss_public`, `newsapi`, `polymarket_gamma_public`, `polymarket_clob_public_trades`, `polymarket_clob_authenticated_readonly`, `whale_profile_builder_internal`, `ollama_local`, `openai_api`, `anthropic_api`, `ai_budget_cache_internal`, `market_memory_outcomes`, `mock_intelligence_provider`
- Blocked by missing required env: `cryptopanic`, `reddit_api`, `telegram_public_channels`, `x_twitter_api`
- Optional missing: Discord token/channels, Reddit user agent, Telegram bot token/channels
- Secret exposure: false

Runtime API validation after compose pass-through:

- SYSTEM OFF
- `POST /intelligence-sources/validate`: `status=OK`, `mock_data=false`, `validated_sources=20`, `blocked_sources=4`
- Missing required vars: `CRYPTOPANIC_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `TELEGRAM_API_HASH`, `TELEGRAM_API_ID`, `X_BEARER_TOKEN`
- Optional missing vars: `DISCORD_BOT_TOKEN`, `DISCORD_CHANNELS`, `REDDIT_USER_AGENT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNELS`
- Secret scan over API JSON: false

No provider auth calls were made. Validation is env-presence and safe readiness only.

Read-only source-status HTTP probes:

- `polymarket_gamma`: `ACTIVE`, `FRESH`
- `polymarket_activity_readonly`: `ACTIVE`, `FRESH`
- `polymarket_clob_orderbook`: `DEGRADED`, `UNKNOWN`
- `polymarket_clob_prices`: `DEGRADED`, `UNKNOWN`
- `polymarket_clob_spreads`: `DEGRADED`, `UNKNOWN`
- `ollama_local_model`: `DEGRADED`, `UNKNOWN`
- `news_provider`: `DISABLED`, key present
- `reddit_or_social_provider`: `DISABLED`, key missing
- All probes were `read_only=true`, `mutation_allowed=false`.

## Tests Run

- `docker-compose --profile test run --rm --no-deps test python -m pytest tests/test_v3_intelligence_source_readiness.py -q -s`: `11 passed, 1 warning in 119.01s`
- `docker-compose --profile test run --rm --no-deps test sh -lc 'unset POLYBOT_RUNTIME_MODE; python -m pytest tests/test_env_runtime.py -q'`: `1 passed in 2.18s`
- `docker-compose --profile test run --rm --no-deps test python -m pytest tests/test_v2_21_source_status.py tests/test_stage4.py tests/test_stage4_env_isolation.py -q`: `47 passed, 1 warning in 25.09s`

An earlier combined config test run failed because compose injected `POLYBOT_RUNTIME_MODE=PAPER` into `test_env_runtime.py`; rerun with that env var unset passed.

## Runtime Smoke

- API image rebuilt and API service recreated.
- `SYSTEM OFF` confirmed.
- Validation endpoints returned `mock_data=false`.
- `GET /dashboard/api/v2/source-status` completed safe read-only probes.
- No likely secret pattern detected in endpoint JSON.

Safety counts before and after validation remained unchanged:

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

## Remaining Operator Actions

- Add `CRYPTOPANIC_API_KEY` if CryptoPanic is desired.
- Add `X_BEARER_TOKEN` if X/Twitter is approved and budgeted.
- Add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` for Reddit.
- Add `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_CHANNELS` before Telegram public channel ingestion.
- Add `DISCORD_BOT_TOKEN` and `DISCORD_CHANNELS` only if Discord is explicitly approved.

## Phase Status

YELLOW.

Names are aligned, validation works, tests pass, no secrets were exposed, and no trading mutation occurred. Status remains YELLOW because several external providers still need operator credentials before they can pass readiness.
