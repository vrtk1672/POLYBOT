# POLYBOT Source and Model Strategy Gap Report

Generated: 2026-05-21
Server path: `C:\Server\apps\polybot`

## 1. Executive Summary

POLYBOT is ready to start a controlled source-connectivity phase in DATA_ONLY/PAPER mode, but it is not ready for live trading.

The next best work is not "add many APIs." The next best work is to make the existing Polymarket-native truth path deeper:

1. Add read-only Polymarket CLOB/Data API ingestion for orderbook, spreads, depth, trades, activity, holders, and open interest.
2. Make source status and source reliability first-class dashboard truth.
3. Choose one news provider and one initial social source only.
4. Use `qwen3:4b` locally for cheap triage/classification.
5. Use Claude/Anthropic only as a budgeted, cached, cloud escalation path for hard ambiguity, rules/resolution wording, and high-impact context.

Final recommendation: YELLOW for starting source connectivity.

Reason: runtime is healthy and safe, the plan is clear, but Harel still needs to choose/register/configure a small number of providers and keys before full activation.

## 2. Current POLYBOT Status

Verified during this pass:

- Docker runtime: GREEN.
- API/Postgres/Redis: healthy.
- Migrations: `No pending migrations.`
- `/healthz`: `status=ok`, `ready=True`.
- `/runtime/health`: `overall_status=HEALTHY`, `current_mode=DATA_ONLY`, `stale_services=[]`.
- `/dashboard/api/v2/overview`: `status=OK`, `mock_data=false`, `stale=false`.
- Docker API safety env: `MODE=PAPER`, `BACKEND=paper`, `LIVE=false`, `KILL=true`.
- Docker API does not receive `ANTHROPIC_API_KEY`, `POLY_PRIVATE_KEY`, or Polymarket API secrets.
- Local `.env` contains operator secret key names, but values were not printed.
- Ollama is reachable from the API container; available model: `qwen3:4b`.
- Production table snapshot:
  - `market_snapshots_v2`: 1150 rows
  - `liquidity_snapshots`: 1150 rows
  - `event_log`: 5214 rows
  - `news_raw_events`: 0 rows
  - `social_raw_events`: 0 rows
  - `whale_events`: 0 rows
  - `opportunity_scores_v2`: 0 rows
  - `paper_orders`: 0 rows

## 3. Big Vision Gap Map

| Subsystem | Current status | Gap |
|---|---|---|
| Docker/runtime | ACTIVE | Continue operating in DATA_ONLY/PAPER only |
| DB/migrations | ACTIVE | Test DB isolated; production has prior audit test rows |
| Dashboard truth | ACTIVE/PARTIAL | Overview is real; many module panels are NO_DATA |
| Gamma ingestion | ACTIVE | Needs CLOB/orderbook enrichment |
| Data Foundation | ACTIVE | Needs persisted orderbook/trades/activity inputs |
| Event mesh | PARTIAL | Event log active; consumers/replay/DLQ not central yet |
| Source reliability | PARTIAL/SKELETON | Tables/learning exist; source freshness and score dashboard should be wired next |
| News V2 | SKELETON/PARTIAL | Tables/routes exist; no live news rows |
| Social | SKELETON | Tables/routes/tests exist; no live source |
| Whale/activity | SKELETON/PARTIAL | Tables/routes/tests exist; no live Polymarket activity feed |
| Rules/resolution | PARTIAL | Basic rules from market metadata; deep resolution analysis not runtime-wired |
| Market/orderbook neuron | PARTIAL | Code exists; CLOB orderbook not runtime-wired |
| AI/Ollama | PARTIAL | Ollama reachable; local worker/router not fully wired by default |
| Claude/Anthropic | PARTIAL/BLOCKED BY CONFIG | Code support exists; API key intentionally absent from Docker API |
| Opportunity Cortex | SKELETON/PARTIAL | Not writing `opportunity_scores_v2` in runtime |
| Strategy/capital/risk/execution/exit/no-trade/learning | SKELETON/PARTIAL | Surfaces exist; mostly not active in scheduler |
| Paper | PARTIAL | Tables exist; DATA_ONLY blocks paper stage; no clean paper evidence yet |
| Shadow/live | NOT READY | Live deliberately blocked and not certified |

## 4. Source Candidate Strategy

Source admission rule:

- It must help a chosen market family.
- It must strengthen a named neuron.
- It must improve a named decision.
- It must be classified as truth, signal, context, or noise.
- It must be safe to test in DATA_ONLY/PAPER.
- It must have source status, freshness, rate-limit, and reliability tracking.

Recommended source order:

1. Polymarket CLOB/Data API read-only.
2. Polymarket rules/resolution and market lifecycle truth.
3. Official RSS/official source registry for politics/macro and sports.
4. One news provider only.
5. One social source only.
6. Whale/activity based on Polymarket trades/activity.
7. Weather/crypto/on-chain only after market-family commitment.

## 5. public-apis Findings

The `public-apis/public-apis` repository is useful as a discovery catalog, not as source truth. It lists relevant categories including News, Finance, Government, Sports & Fitness, Cryptocurrency, Social, and Weather. Source: https://github.com/public-apis/public-apis

Shortlist:

| API/source | Category | Official docs URL | Auth/key | Free tier | Reliability | Market family | Target neuron | Status |
|---|---|---|---|---|---|---|---|---|
| Polymarket Gamma | Prediction market | https://docs.polymarket.com/api-reference/introduction | No for public discovery | Yes | High for POLYBOT target | All | Market/Data Foundation | Tier 1, already active |
| Polymarket CLOB/Data API read-only | Prediction market microstructure | https://docs.polymarket.com/api-reference/introduction | Some public endpoints; trading auth for private/trading paths | Yes for read paths | High | All | Market, liquidity, whale/activity | Tier 1 |
| GDELT DOC 2.0 | News/open data | https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/ | No key for public DOC API | Yes | Medium/high, noisy | Politics/Macro, global events | News/context | Tier 2 candidate |
| GNews | News | https://docs.gnews.io/ | API key | Free signup; paid for production scale | Medium/high | Politics/Macro, sports, events | News | Tier 2 candidate |
| NewsAPI.org | News | https://newsapi.org/pricing | API key | Dev only; 100/day; production requires paid plan | Medium/high | Politics/Macro | News | Reject for server production unless paid |
| AP Developer | News | https://developer.ap.org/ | API key/subscription | Likely subscription-oriented | High | Politics/Macro, sports | News truth/context | Tier 3 later |
| FRED | Finance/macro | https://fred.stlouisfed.org/docs/api/fred/ | API key | Free account key | High | Macro/economy | Macro official-source neuron | Tier 2 |
| BLS Public Data API | Government/macro | https://www.bls.gov/developers/api_faqs.htm | Optional; registered higher limits | Yes | High | Macro/economy | Macro official-source neuron | Tier 2 |
| Federal Register | Government | https://www.federalregister.gov/developers/documentation/api/v1 | No key | Yes | High | Politics/regulation | Rules/resolution/context | Tier 2 |
| TheSportsDB | Sports | https://www.thesportsdb.com/documentation | Free shared key or paid key | Free 30 req/min; paid cheap | Medium | Sports | Sports official-source neuron | Tier 2 |
| API-Football | Sports | https://www.api-football.com/pricing | API key | 100 req/day free | Medium/high for soccer | Sports | Sports official-source neuron | Tier 3 if soccer focus |
| balldontlie | Sports | https://www.balldontlie.io/docs/ | API key | Free 5 req/min | Medium/high | NBA/NFL/MLB/EPL | Sports official-source neuron | Tier 3 if US sports focus |
| Reddit Data API | Social | https://www.reddit.com/dev/api/ | OAuth/app | Limited/free but policy friction | Medium, noisy | Politics, crypto, sports | Social/noise/hype | Tier 2 candidate with caution |
| Telegram | Social/community | https://core.telegram.org/bots/api | Bot token | Yes | Medium; group-dependent | Crypto, niche events | Social/control | Tier 3 later |
| Etherscan API V2 | Blockchain/crypto | https://docs.etherscan.io/introduction | API key | Free limits | High for EVM | Crypto only | Whale/on-chain | Tier 3 only if crypto selected |
| Open-Meteo | Weather | https://open-meteo.com/en/docs | No key free; key for commercial endpoint | Free non-commercial; commercial plans | High | Weather | Weather official-source neuron | Tier 3 only if weather selected |

Notes from current docs:

- Polymarket docs split APIs into Gamma for markets/events/tags/search/public profiles and Data API for positions, trades, activity, holders, open interest, leaderboards, and analytics: https://docs.polymarket.com/api-reference/introduction
- Polymarket CLOB trading auth has L1 private-key signing and L2 HMAC API credentials; this must stay read-only until live certification: https://docs.polymarket.com/trading/overview
- GNews requires signup and uses `apikey` in requests: https://docs.gnews.io/
- NewsAPI Developer plan is development/testing only and cannot be used for staging/production: https://newsapi.org/pricing
- TheSportsDB free tier is 30 requests/minute; premium starts cheaply: https://www.thesportsdb.com/docs_pricing
- API-Football free tier is 100 requests/day: https://www.api-football.com/pricing
- BLS registered API offers 500 queries/day, 50 series/query, 20 years/query; unregistered is lower: https://www.bls.gov/developers/api_faqs.htm
- FRED requires an API key tied to a FRED account: https://fred.stlouisfed.org/docs/api/api_key.html
- Open-Meteo free API is non-commercial, 10,000 calls/day, no uptime guarantee; commercial use requires subscription: https://open-meteo.com/en/pricing
- Etherscan V2 supports 60+ EVM chains under one API key: https://docs.etherscan.io/introduction

## 6. Claude / Anthropic Plan

Existing support:

- `anthropic` is a project dependency.
- Local `.env` has `ANTHROPIC_API_KEY` by key name.
- Docker API intentionally does not receive `ANTHROPIC_API_KEY`.
- Existing AI tables include requests, responses, cache, cost ledger, model performance, prompt versions, and decision logs.

Recommended role:

- Claude is cloud escalation only.
- Claude must never place orders or authorize trades directly.
- Claude output should produce structured analysis, uncertainty, evidence links, and `NO_TRADE` recommendations when ambiguity is high.

Use Claude for:

- Rules/resolution wording ambiguity.
- Market title vs resolution criteria conflict.
- News/context cases where local model confidence is low.
- High-impact market ambiguity before PAPER decision generation.
- Post-facto trade review summaries.

Do not use Claude for:

- Every market.
- Simple Gamma field extraction.
- Direct execution decisions.
- Live trading authority.
- Uncached repeated prompts.

Budget guard idea:

- Default daily cloud budget: `$1/day` during DATA_ONLY exploration.
- Per-market escalation cap: one fresh cloud call per market per 6-24h unless rules/news changed materially.
- Hard fail mode: `AI_UNAVAILABLE` or `NO_TRADE`, never "assume okay."
- Cache-first policy: prompt version + market id + source hashes + task type as cache key.
- Required ledger: request id, model, task, estimated cost, cache hit, reason for escalation.

Current Anthropic pricing docs show model-specific input/output pricing and prompt-caching multipliers; cache hits are 10% of base input price. Source: https://platform.claude.com/docs/en/about-claude/pricing

## 7. Ollama / qwen3:4b Plan

Current local model:

- `qwen3:4b`
- Ollama reachable from API container.

Recommended use:

- Lightweight article triage.
- Source classification.
- Market-family tagging.
- Deduplication hints.
- Headline summarization.
- Rules wording first-pass classification.
- Social noise/hype classification.

Do not use `qwen3:4b` for:

- Final resolution-risk judgment on ambiguous high-impact markets.
- Legal/compliance interpretation.
- Direct trading decisions.
- Large multi-document synthesis where context is long and stakes are high.

Model strategy:

- Keep `qwen3:4b` for now.
- Do not chase heavier local models until source connectivity and cache/budget plumbing are proven.
- Consider `qwen3:8b` or `qwen3:14b` later only if server hardware can sustain latency and memory without harming runtime.
- Prefer deterministic source scoring over AI for anything the DB can compute.

Ollama's Qwen3 library lists 4B/8B/14B and larger model options; `qwen3:4b-instruct` is about 2.5GB Q4_K_M. Source: https://ollama.com/library/qwen3:4b-instruct

## 8. News Strategy

Recommended now:

- Keep official/RSS source support.
- Choose one news provider for provider-backed discovery.
- Add source status and source reliability before letting news influence scoring.

Provider recommendation:

- If Harel wants no signup and broad research discovery: start with GDELT DOC 2.0.
- If Harel wants a cleaner paid/free account-based news API with simpler JSON: choose GNews.
- Do not use NewsAPI.org for production unless Harel accepts its paid production plan.
- AP is high-quality but likely later due subscription/contract friction.

Decision use:

- News should initially influence `NO_TRADE`, context, and "needs review" states more than positive trade scoring.

## 9. Official Source Strategy

Priority official sources for first two market families:

- Politics/Macro:
  - Federal Register for regulatory/government action.
  - FRED for macro series.
  - BLS for CPI/jobs/labor data.
  - Official agency RSS pages where market-specific.
- Sports:
  - TheSportsDB for broad event/schedule metadata.
  - API-Football only if soccer becomes a focus.
  - balldontlie only if NBA/NFL/MLB/EPL markets are selected and key creation is acceptable.

Official sources should be labeled as "truth/context", not social signal.

## 10. Social Strategy

Recommended first social source: Reddit, with caution.

Why:

- Strong relevance for politics, crypto, sports narratives.
- Existing POLYBOT social neuron already models Reddit/Telegram/RSS mirror source types.
- Reddit API has official read endpoints and OAuth scopes, including subreddit search.

Risks:

- High noise and brigading.
- Policy/app access friction in 2026.
- Social should never be treated as truth.

Implementation posture:

- Start with one or two manually selected subreddits per market family.
- Cache aggressively.
- Use qwen3:4b to classify noise/hype only.
- Dashboard must separate social hype from truth.

Do not start X/Twitter now.

## 11. Whale / Activity Strategy

Recommended first whale source: Polymarket-native read-only trades/activity/holder/open-interest feeds.

Why:

- It strengthens prediction-market-specific signal without adding unrelated external APIs.
- It directly supports whale/activity neuron, liquidity neuron, and execution-quality analysis.
- It is testable safely in DATA_ONLY.

Do not start with Etherscan unless crypto markets become a selected first market family.

If crypto becomes a focus later, Etherscan V2 is a reasonable Tier 3 source for wallet/chain context, but it adds complexity and false attribution risk.

## 12. CLOB / Orderbook Strategy

Highest priority implementation after this report:

- Read-only CLOB book snapshots.
- Best bid/ask, spread, depth, midpoint, imbalance.
- Trade/activity ingestion from Polymarket Data API.
- Market freshness, stale orderbook detection, and dashboard source status.

Why:

- Current Gamma scoring is useful but incomplete.
- Orderbook depth and spread determine whether a scored opportunity is actually tradable.
- This improves DATA_ONLY/PAPER before any live path is considered.

Safety:

- No private key required for public read paths.
- Do not derive API credentials.
- Do not call order placement/cancel endpoints.

## 13. Key / Account Checklist For Harel

Priority 1:

- Anthropic Console account and API key
  - Key name: `ANTHROPIC_API_KEY`
  - Free tier: generally requires billing setup/credits depending account state.
  - Payment needed now: only if enabling cloud escalation.
  - Do not put it into Docker API until Codex adds budget/caching/ledger gates.

- News provider choice
  - Option A: GDELT, no key.
  - Option B: GNews, key name should be `GNEWS_API_KEY`.
  - Free tier: GNews free signup; production may need paid.
  - Do not sign up for multiple news APIs now.

Priority 2:

- FRED account/API key for macro
  - Key name: `FRED_API_KEY`
  - Free tier: yes.
  - Payment needed: no.

- BLS API registration key
  - Key name: `BLS_API_KEY`
  - Free tier: yes.
  - Payment needed: no.

- Sports provider decision
  - TheSportsDB: key name `THESPORTSDB_API_KEY`, free shared key works for testing; paid cheap if needed.
  - API-Football: key name `API_FOOTBALL_KEY`, free 100/day.
  - balldontlie: key name `BALLDONTLIE_API_KEY`, free 5/min.
  - Choose only one after deciding sports scope.

Priority 3:

- Reddit developer/OAuth access
  - Key names: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
  - Free tier: possible but policy/app friction exists.
  - Do not automate posting or account actions.

- Etherscan API key only if crypto markets become focus
  - Key name: `ETHERSCAN_API_KEY`.
  - Free tier: yes.
  - Do not add yet unless crypto is selected.

- Open-Meteo paid key only if weather markets become focus and commercial use is intended
  - Key name: `OPEN_METEO_API_KEY`.
  - Free non-commercial evaluation exists.
  - Do not add yet unless weather is selected.

## 14. What Codex Should Implement Later

Do not implement these until Harel approves the phase.

1. Add read-only CLOB/Data API source adapters with timeout/retry/rate-limit guards.
2. Add DB migrations for source status/freshness if existing tables are insufficient.
3. Wire orderbook snapshots into Data Foundation and dashboard V2 source status.
4. Add source reliability scoring and source freshness panels.
5. Add one news provider adapter chosen by Harel.
6. Add official macro source adapter for FRED/BLS if Politics/Macro is selected.
7. Add one sports source adapter if Sports is selected.
8. Add local qwen3:4b worker transport through Ollama with cache-first behavior.
9. Add Claude escalation service gated by budget, cache, prompt versioning, and mode.
10. Add tests proving DATA_ONLY/PAPER safety and no live endpoint mutation.

## 15. What Not To Do Yet

- Do not add Grafana.
- Do not add X/Twitter.
- Do not add many news providers.
- Do not wire Claude into every scoring path.
- Do not install heavier local models yet.
- Do not enable live trading.
- Do not derive Polymarket L2 credentials in Docker runtime.
- Do not use social data as truth.
- Do not add Etherscan unless crypto is selected.
- Do not add weather APIs unless weather markets are selected.
- Do not buy expensive sports/news feeds before proving Data Foundation/CLOB value.

## 16. Next 10 Steps

| # | Owner | Objective | Expected output | Success criteria | Risk | Priority |
|---|---|---|---|---|---|---|
| 1 | Harel | Choose first two market families | Decision: recommended Politics/Macro + Sports | Scope is written in docs | Picking too broad | P0 |
| 2 | Harel | Choose one news provider | GDELT or GNews selected | One source only | API sprawl | P0 |
| 3 | Codex | Implement read-only Polymarket CLOB/Data API adapters | Source adapters + tests | No private key, no mutations | Endpoint drift | P0 |
| 4 | Codex | Persist orderbook/trade/activity snapshots | Migrations/repos/services | Dashboard can show freshness | DB shape mismatch | P0 |
| 5 | Codex | Add source status dashboard truth | V2 dashboard source panel | Fresh/stale/error visible | False confidence | P0 |
| 6 | Harel | Register FRED/BLS keys if Politics/Macro is selected | `FRED_API_KEY`, `BLS_API_KEY` available by key name | Keys exist; values not printed | Manual signup delay | P1 |
| 7 | Harel | Pick one sports source if Sports is selected | TheSportsDB/API-Football/balldontlie decision | Provider documented | Coverage mismatch | P1 |
| 8 | Codex | Wire qwen3:4b local triage | Ollama transport + cache-first tests | AI unavailable falls back safely | Latency/model quality | P1 |
| 9 | Codex | Add Claude escalation guard | Budget/cache/prompt-version ledger | No key means no cloud call; budget enforced | Cost leak | P1 |
| 10 | Codex | Run DATA_ONLY source smoke | Docker test + endpoint evidence report | Runtime healthy, no live creds, source rows real | Rate-limit/source errors | P1 |

## 17. Final Subsystem Status Table

| Area | Status | Recommendation |
|---|---|---|
| Runtime safety | GREEN | Continue DATA_ONLY/PAPER development |
| Source architecture | YELLOW | Add source status/freshness/reliability before source sprawl |
| Polymarket-native data | GREEN/YELLOW | Gamma active; CLOB/Data API read-only next |
| News | YELLOW | Choose one provider; prefer GDELT or GNews |
| Official macro | YELLOW | FRED/BLS/Federal Register are good next sources |
| Sports | YELLOW | Choose provider after sports family scope |
| Social | YELLOW/RED | Reddit only with caution; no X/Twitter yet |
| Whale/activity | YELLOW | Use Polymarket-native activity before Etherscan |
| AI local | YELLOW | qwen3:4b enough for triage, not final authority |
| AI cloud | YELLOW | Claude useful only with cache/budget/escalation controls |
| Paper/live | YELLOW/RED | Paper later; live no |

## 18. Final Recommendation

Status for starting source connectivity phase: YELLOW.

POLYBOT can safely begin a narrow source connectivity phase on this server, provided the first implementation is read-only, DATA_ONLY/PAPER-only, source-status-visible, cache-aware, and test-isolated.

Recommended next phase:

V2.21-source-prep: Polymarket CLOB/Data API read-only + source status dashboard + source reliability foundation.

Do not begin social/news sprawl or live execution work before this foundation is in place.
