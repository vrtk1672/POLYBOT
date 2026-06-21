# V2.20B-1 POLYBOT Operating Requirements Audit

Date: 2026-05-18

This is a readiness audit, not a feature phase. POLYBOT is treated as a neural mesh. No providers, trading logic, order intents, live orders, live exits, or external balance mutations were added.

## Overall Status

Status: **YELLOW**

The audit completed deeply enough to map operating requirements, source reality, env/model needs, mesh connectivity, and run blockers. POLYBOT can proceed to a **30m DATA_ONLY smoke** based on V2.20B runtime evidence. It should not proceed to PAPER or long-run stages until persisted orderbook freshness and stale source gaps are fixed or explicitly accepted as degraded.

## Domain Audit Matrix

| Domain | Should Exist | Current Repo Truth | Runtime/Data Evidence | Safe Degrade | DATA_ONLY Blocker | PAPER Blocker | 24h+ Blocker | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| News sources | breaking, scheduled, official, market-specific, aggregator, verification sources | V2.4 News Neuron, manual/RSS collector, source registry | `news_sources=0`; one stale manual/raw row | stale/no-data | no | only for markets needing confirmation | stale sources | PARTIAL |
| Social sources | fast social, community, KOL, hype/noise, native social, verification | V2.6 Social Neuron, manual/RSS/public-trend shells, platform source types | `social_sources=0`; one stale row | stale/no-data | no | only if engine/source requires social | stale sources | PARTIAL |
| Official sources | gov/court/sports/weather/macro/company official confirmation | source types/docs only | no configured official source rows | insufficient_data | no | yes for official-dependent markets | yes | DOCS_ONLY/PARTIAL |
| Market data | active market list, metadata, price/liquidity | Gamma client, Data Foundation | Gamma fetched 2500 events; `markets_v2` fresh | no-data/stale | no now | no if fresh | monitor rate/stability | GREEN for DATA_ONLY |
| Orderbook/liquidity/fees | best bid/ask/depth/slippage/fees | CLOB book read path, V2.8 analyzers, DB tables | CLOB book logs 200; `orderbook_snapshots=0`; liquidity/fees fresh | block execution | no | **yes** | yes | RED for PAPER |
| Whale data | wallets, large trades, profiles, follow value | V2.7 shell/history, source registry/scanner | `whale_sources=0`; stale whale events/profiles | stale/no-data | no | no unless engine requires | stale source | PARTIAL |
| AI/models | local-first models, cache, budget, cost | V2.3 Hybrid AI, legacy Anthropic services | Ollama missing; local models missing; no AI request rows | `UNAVAILABLE`/blocked | no | no if AI-degraded accepted | AI-full run blocked | YELLOW |
| API keys/env | DB/runtime/safety/provider keys | `.env`, `.env.example`, settings, scripts | DB URL set by scripts; provider keys mostly absent in audit process | many optional | DB URL needed | DB URL/orderbook source needed | provider decisions needed | YELLOW |
| Event Bus/mesh | DB/event/API links between nodes | V2.1 event bus, typed events, dashboard | `event_log=6160`, failed/DLQ zero in V2.20B | no consumers is visible | no | no | lag/consumer coverage | YELLOW |
| Scheduler/runner | periodic mesh refresh, smoke/long-run scripts | `RefreshScheduler`, V2.20 scripts | runtime refresh completed; endpoints responsive | blocked-by-mode | no | no if orderbook fixed | needs 30m/24h evidence | YELLOW |
| Runtime services | FastAPI/Postgres/Docker/Redis/ports | FastAPI, Postgres, scripts | Postgres OK, 57 migrations, Docker timeout, Redis not required | Docker optional for current local DB if DB running | no if Postgres running | no if Postgres running | Docker/restart risk | YELLOW |
| Modes | DATA_ONLY/PAPER/SHADOW/SMALL_LIVE/ATTACK/KILL/DEGRADED | State Governor and mode checks | tests pass; runtime scripts force live false | missing data blocks | no | orderbook blocks | mode soak needed | YELLOW |
| Data freshness | stale/no-data/insufficient states | dashboard envelopes, service health | market fresh, source stale, orderbook no rows | explicit stale/no-data | no | yes for orderbook | yes | YELLOW |
| Risk/safety | gate/governor/kill/manual override/live off | V2.14, stage4 guards | tests pass; live disabled | blocks | no | no | verify during smoke | GREEN static |
| Paper execution | risk+exit+orderbook-based simulation | V2.15 | stale paper rows; no fresh orderbook DB | blocked | n/a | **yes** | yes | BLOCKED |
| Exit readiness | exit plans/intents/failures/orphans | V2.16 | stale exit rows; orphan count visible | failures/orphans visible | no | requires fresh orderbook | yes | PARTIAL |
| No-Trade | log every block/reason/review/regret | V2.17 | rows exist; dashboard stale but real | insufficient_data | no | no | review evidence sparse | YELLOW |
| Learning | trade/no-trade/source/engine/AI learning | V2.19 | rows exist; no fresh closed-trade flow | pending/insufficient | no | no | sparse outcomes | YELLOW |
| Dashboard truth | all node pages, stale truth, no mock | V2.18 plus V2.20B fast paths | truth script `ok=true`, no violations | stale/no-data | no | no | monitor slow pages | GREEN for DATA_ONLY |
| Long-run readiness | 30m/24h/72h/7d scripts/checkpoints | V2.20 scripts exist | no 30m or 24h completed | n/a | 30m DATA_ONLY yes | PAPER no | long-run no | YELLOW |

## Market Family Source Map

| Family | Required Sources | Official Source Need | Minimum DATA_ONLY | Minimum PAPER | Insufficient / Stale | Engines Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Politics | Gamma market, rules, polls/news, official election/debate sources | election boards, official calendars | market/rules plus stale-aware news optional | orderbook+liquidity+risk+exit; official confirmation for event-driven trades | no official source for resolution/catalyst | SAFE/STRIKE only with confirmation; HUNT requires approval |
| Sports | Gamma, injury/team/league/schedule, odds/news | league/team injury reports | market/rules; news stale tolerated | orderbook plus official injury/game source for injury-driven edge | stale injury/schedule | fast stale risk; avoid HUNT without fresh official |
| Crypto | Gamma, exchange/project status, chain/news/social | project/exchange official pages | market/rules; crypto news optional | orderbook plus fresh source for hacks/unlocks | stale chain/news | CONVEX/HUNT only with attack/risk gates |
| Macro | Gamma, Fed/BLS/BEA/Treasury calendars | Fed/BLS/BEA/Treasury | market/rules and scheduled date | orderbook plus official calendar/release source | no macro official feed | mostly SAFE/STRIKE; news alone insufficient |
| Weather | Gamma, NOAA/weather agencies | NOAA/national weather services | market/rules; weather source missing marked insufficient | orderbook plus official weather data | stale/no weather data | avoid PAPER for weather edge until official feed |
| Legal/Court | Gamma, court docket/rules/news | court/docket official source | market/rules; legal source missing marked insufficient | orderbook plus official docket/source | docs-only court source | high wording/rules risk; SAFE only |
| Entertainment | Gamma, official award/box office trackers/news | official awards/box office | market/rules | orderbook plus event/source confirmation | stale source | small sizes; no HUNT |
| Tech/Company | Gamma, IR/SEC/company news | SEC/company IR | market/rules | orderbook plus official source | no IR/SEC adapter | rules/official confirmation required |
| Geopolitics | Gamma, official gov/security/news | official agencies | market/rules; news stale risky | orderbook plus high-trust confirmation | stale news | high invalidation risk |
| Generic/Unknown | Gamma, rules, orderbook | depends | market/rules only | orderbook, liquidity, risk, exit; otherwise NO_TRADE | unknown family | NO_TRADE valid |

## Event Bus / Mesh Connectivity

V2.20A static result remains valid: 24/24 nodes present, 20/20 major edges connected. Runtime evidence is narrower:

- `event_log` exists and grows; V2.20B saw `6160` events with failed/DLQ zero.
- Runtime refresh writes market/data foundation events.
- Dashboard consumes all major nodes through `/dashboard/api/v2/*`.
- Several edges are **static connected but runtime sparse**: news/social/whale -> context/opportunity, execution/exit -> learning, learning -> memory.

Important edge statuses:

| Edge | Static | Runtime Evidence | Status |
| --- | --- | --- | --- |
| Market -> Technical/Data Foundation | yes | fresh market/liquidity/fee rows | CONNECTED |
| Market -> Orderbook | yes | CLOB reads only; no persisted rows | PARTIAL |
| News -> Context/Opportunity | yes | stale single row only | PARTIAL |
| Social -> Context/Opportunity | yes | stale single row only | PARTIAL |
| Whale -> Context/Opportunity | yes | stale history, no source rows | PARTIAL |
| Opportunity -> Strategy -> Capital -> Risk | yes | historical rows | CONNECTED static, stale runtime |
| Risk -> Execution | yes | historical rows; safety tests | CONNECTED static |
| Execution -> Exit -> Learning | yes | historical smoke rows | CONNECTED static, sparse runtime |
| All nodes -> Dashboard | yes | runtime dashboard truth verified | CONNECTED |
| Safety paths -> State/Risk Governor | yes | tests/runtime scripts | CONNECTED |

## Scheduler / Runner / Orchestrator

- Runner exists: `RefreshScheduler`.
- Main loop: `MarketService.refresh()` every `POLYBOT_REFRESH_INTERVAL_SECONDS`, default `60`.
- V2.20 smoke/long-run scripts exist.
- Event-driven triggering is partial: events are persisted and replayable, but most nodes are not autonomous event consumers.
- Manual-only or sparse nodes: news source registration/fetch, social source registration/fetch, whale live scanner, learning rebuild/reviews, no-trade rebuild.
- Missing automation before long-run: source freshness checks, persisted orderbook writer proof, automatic no-trade capture coverage from every block path, automated learning after completed cycles.

## Mode Behavior

| Mode | Allowed | Blocked | Current Evidence | Gaps |
| --- | --- | --- | --- | --- |
| DATA_ONLY | ingest, analysis, dashboard, safe memory/no-trade | paper execution records, live orders, order intents, external balance mutation | no-live mutation checker passed with zero deltas | needs 30m smoke |
| PAPER | internal paper/shadow records, paper exits/learnings | live orders/exits/balances | V2.15/V2.16 tests; scripts force live false | blocked by orderbook persistence |
| SHADOW_LIVE | shadow plans only | live send | code boundary exists | not V2.20 target |
| SMALL_LIVE | future certified live | currently not certified | live disabled | out of scope |
| ATTACK_MODE | future governor approved mode | live send in V2.20 | risk/attack gates exist | out of scope |
| KILL | emergency internal planning only | new execution/trading | tests/docs | verify in smoke |
| DEGRADED | stale/no-data/AI unavailable | fake output | dashboard envelopes | source-specific gates incomplete |

## Data Quality / Freshness

Found policies:

- Dashboard V2 envelope marks stale if latest timestamp is older than 20 minutes.
- News/social/whale dashboards show stale when only old rows exist.
- Runtime/data coverage exposes orderbook coverage, rules coverage, liquidity coverage, stale markets.
- AI missing becomes unavailable in Hybrid AI, but legacy Anthropic services raise if directly invoked without key.

Gaps:

- Persisted orderbook freshness is the biggest gap.
- News/social/whale source registries are empty.
- Official source freshness policy is mostly design-level/source-type only.
- Cross-source agreement and contradiction handling exist as AI/logic concepts but lack live source evidence.

## Risk / Safety

Evidence:

- State Governor and Risk Governor exist.
- V2.14 tests passed in prior phases; V2.20B required runtime/V2.18/V2.19 tests passed.
- Live settings stay disabled in scripts.
- Live capital balance call was gated off in V2.20B.
- Dashboard truth is read-only for this audit.

Answers:

- News/social/whale cannot bypass Risk.
- Execution must require strategy route, allocation, risk approval, and exit plan.
- Manual override cannot bypass KILL per V2.14 design/tests.
- Missing orderbook should block paper execution.

## Paper Execution Readiness

Status: **blocked**.

V2.15 logic supports paper/shadow, partial fills, failed fills, slippage, quality, and cancel conditions. But PAPER smoke should not run until the system proves fresh persisted orderbook/depth truth. Current DB evidence shows `orderbook_snapshots=0`.

## Exit Readiness

Status: **partial**.

V2.16 exit plans/intents/failures exist, and dashboard reports orphans/failures. Bad liquidity records failure by design. Exit can create only paper/shadow internal intents. Runtime long-run still needs proof every internal paper order gets an active exit plan or appears as orphan.

## No-Trade Readiness

Status: **partial/good static**.

V2.17 requires reasons, candidate engine when available, source layer, post-fact review without fake regret, and learning feed. Rows exist and dashboard truth is real, but not every possible runtime block path has live no-trade evidence yet.

## Learning Readiness

Status: **partial**.

V2.19 tables and APIs exist. Learning requires evidence and keeps model adjustments recommendation-only. Current completed-trade history is sparse/stale, so 24h+ learning readiness depends on paper cycle outcomes.

## Dashboard Truth

V2.20B evidence:

- Dashboard truth script returned `ok=true`, `violations=[]`.
- `/dashboard/api/v2/overview`, `events`, `risk`, `capital`, `execution`, `exits`, `no-trade`, `learning`, and `market` responded.
- No mock data violations were detected.
- Stale states are explicit.

## Long-Run Readiness

| Run | Decision | Reason |
| --- | --- | --- |
| 30m DATA_ONLY | YES | runtime endpoints responsive; market/liquidity fresh; no-live mutation check passes |
| 30m PAPER | NO | persisted orderbook/depth freshness missing |
| 24h DATA_ONLY | NO | run 30m DATA_ONLY first; Docker timeout/source staleness remain |
| 24h PAPER | NO | PAPER blocker plus no 30m evidence |
| 72h PAPER | NO | no 24h evidence |
| 7d PAPER | NO | no 72h evidence |

## Blockers

Critical:

- None found for DATA_ONLY smoke safety after V2.20B.

High:

- Persisted orderbook snapshots are zero; blocks PAPER.
- News/social/whale live source registries are empty/stale; blocks source-full long-run.
- Docker readiness still times out; blocks confidence for Docker-based long-run operations.

Medium:

- Ollama/local models missing; AI-full run blocked, but AI-degraded DATA_ONLY can run.
- Legacy Anthropic services can raise if invoked without key outside guarded paths.
- Startup remains slower than ideal, roughly 34-39 seconds in V2.20B.
- Event consumers count is zero in event lag output; event bus is store-first, not broadly consumer-driven.

Low:

- Official source adapters are mostly docs-only/source-type shells.
- Telegram/Discord/social provider keys are not modeled in `.env.example`.
- Some dashboard module rows are stale but truthfully reported.

## Recommended Fix Order

1. Prove/fix CLOB orderbook snapshot persistence.
2. Run 30m DATA_ONLY smoke and review event lag/source freshness.
3. Configure one real news RSS source and prove fresh DB rows.
4. Decide AI mode: install Ollama/models or formally mark AI-degraded for V2.20.
5. Address Docker readiness timeout or document a non-Docker local-run requirement.
6. Add social/whale real providers only after explicit provider/key choices.
7. Run 30m PAPER only after orderbook/depth freshness is real.

## Safety Conclusion

DATA_ONLY smoke can start. PAPER and long-run phases cannot be claimed ready. POLYBOT has a strong neural mesh structure, but several input neurons are still configured as shells or stale historical truth rather than fresh live providers.
