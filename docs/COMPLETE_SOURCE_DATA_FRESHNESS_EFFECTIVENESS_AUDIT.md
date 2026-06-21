# Complete Source Data Freshness & Effectiveness Audit

## 1. Purpose

Audit every source POLYBOT consumes or is expected to consume, measuring whether it exists, refreshes, is fresh, links to candidates, produces directional evidence, reaches Full Mesh, reaches the Source-Backed Edge Engine, reaches Risk, and can support Phase 10 readiness.

This was an audit-first pass. No Paper Simulation, Full Monitor Run, Shadow, Live, execution action, paper action, paper intent, order, fill, position, live order, or shadow order was created.

## 2. Full Source Inventory

Audited sources:

- Polymarket market data: `markets_v2`
- CLOB orderbook: `orderbook_snapshots`
- Candidate price path: `paper_eligibility_candidates`, `fresh_candidate_seeds`
- Liquidity: `brain_outputs`, `orderbook_snapshots`
- Market movement / technicals: `market_technical_signals`, `orderbook_signals`
- Signals: `neuron_signals`, `neuron_signal_bindings`, `signal_quality_evaluations`
- News/RSS/NewsAPI/CryptoPanic: `news_raw_events`, `news_normalized_events`, `news_impact_scores`, `news_market_links`, source registry/credential status rows
- Whale/wallet flow: `whale_events`, `whale_scan_runs`, `whale_market_scores`, `whale_profiles`, `whale_categories`
- Payout/odds: `payout_odds_evaluations`, `payout_odds_sources`
- Cross-market: expected `external_market_prices`, `cross_market_discrepancies`, `external_odds`
- Memory/history: `market_memory_v2`, `market_family_memory`, `no_trade_memory`
- Social: `social_raw_events`, `social_normalized_events`, `social_market_links`, `social_hype_scores`
- AI/model surfaces: source registry entries for OpenAI, Anthropic, Ollama, and internal budget/cache; no dedicated AI decision rows found in the audited table set
- Control/truth: `truth_state_registry`, `runtime_cycles_v2`, `risk_evidence_mesh_evaluations`, `lifecycle_governance_decisions`, `coordinator_decisions`, `no_trade_log`

## 3. Source Existence Table

| Source | Code/Registry | DB tables | Runtime endpoint visibility |
|---|---|---|---|
| Polymarket market data | Present | `markets_v2` | Indirect through candidates/orderbook |
| CLOB orderbook | Present | `orderbook_snapshots` | Mesh/orderbook/actionability |
| Candidate price path | Present | `paper_eligibility_candidates`, `fresh_candidate_seeds` | Candidate price/path readiness |
| Liquidity | Present | `brain_outputs`, `orderbook_snapshots` | Mesh bundles |
| Market movement | Registered | `market_technical_signals`, `orderbook_signals` | Full Mesh source organ, no rows |
| Signals | Registered | `neuron_*`, `signal_quality_evaluations` | Full Mesh source organs |
| News | Registered | `news_*` | Full Mesh source organ |
| Whale | Registered | `whale_*` | Full Mesh source organ |
| Payout | Registered | `payout_odds_*` | Full Mesh source organ |
| Cross-market | Registered | no tables found | Full Mesh source organ reports no connector |
| Memory | Registered | memory tables exist | Full Mesh source organ reports no data |
| Social | Registered | social tables exist | Full Mesh source organ reports missing/no data |
| AI | Registered/passive | source registry rows | Fallback/unavailable in edge reasoning |
| Truth/control | Present | runtime/risk/lifecycle/no-trade tables | Control Center endpoints |

## 4. Source Config Table

Config key names surfaced by source registry/credential status, without values:

- Present: `ANTHROPIC_API_KEY`, `NEWS_API_KEY`, `NEWS_RSS_FEEDS`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL_FAST`, `OLLAMA_MODEL_PRIMARY`, `OLLAMA_MODEL_REASONING`, `OPENAI_API_KEY`, `POLYMARKET_CLOB_API_KEY`, `POLYMARKET_CLOB_HOST`, `POLYMARKET_CLOB_PASSPHRASE`, `POLYMARKET_CLOB_SECRET`
- Missing required: `CRYPTOPANIC_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `TELEGRAM_API_HASH`, `TELEGRAM_API_ID`, `X_BEARER_TOKEN`
- Optional missing: `DISCORD_BOT_TOKEN`, `DISCORD_CHANNELS`, `REDDIT_USER_AGENT`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNELS`

No secret values were printed.

## 5. Source Ingestion / Refresh Table

Controlled SYSTEM ON audit run started at `2026-06-15T20:26:26Z`, ran to six supervisor cycles, and stopped at `2026-06-15T20:33:06Z`.

| Source | Before latest | After latest | New rows during run | Refresh truth |
|---|---|---:|---:|---|
| CLOB orderbook | 2026-06-15T15:10:05Z | 2026-06-15T20:32:54Z | +173 | `REFRESHING_CURRENTLY` |
| Candidate price path | 2026-06-15T15:08:29Z | 2026-06-15T20:32:55Z | +26 | `REFRESHING_CURRENTLY` |
| Liquidity/brain outputs | 2026-06-15T15:10:05Z | 2026-06-15T20:32:54Z | +885 | `REFRESHING_CURRENTLY` |
| Signals | 2026-06-15T15:07:04Z | 2026-06-15T20:31:23Z | +20 | `REFRESHING_CURRENTLY` |
| News | 2026-06-10T22:32:01Z | unchanged | 0 | `REFRESHING_BUT_STALE_BY_TTL` or producer not invoked in this run |
| Whale | 2026-06-07T11:41:05Z | unchanged | 0 | `REFRESHING_BUT_STALE_BY_TTL` or producer not invoked in this run |
| Payout | 2026-06-07T11:44:43Z | unchanged | 0 | `NOT_REFRESHING_PRODUCER_NOT_IN_SUPERVISOR` for candidate DATA_ONLY cycles |
| Market movement | none | none | 0 | `NOT_REFRESHING_NO_PRODUCER` or producer not wired |
| Market memory | none | none | 0 | `NOT_REFRESHING_NO_PRODUCER` |
| Social | none | none | 0 | `NOT_REFRESHING_MISSING_CONFIG` |
| Cross-market | no table | no table | 0 | `NOT_REFRESHING_CONNECTOR_MISSING` |
| AI | registry ready/fallback | no AI rows measured | 0 | `REFRESH_UNKNOWN`; fallback safe |
| Truth/control | 2026-06-15T15:10:05Z | 2026-06-15T20:32:56Z | expected DATA_ONLY rows | `REFRESHING_CURRENTLY` |

## 6. Source Data Counts

After the controlled run:

| Source table | Rows | Latest timestamp | Last 15m |
|---|---:|---|---:|
| `markets_v2` | 13 | 2026-06-04T00:37:55Z | 0 |
| `orderbook_snapshots` | 53816 | 2026-06-15T20:32:54Z | 173 |
| `paper_eligibility_candidates` | 20610 | 2026-06-15T20:32:55Z | 26 |
| `fresh_candidate_seeds` | 22 | 2026-06-04T00:42:49Z | 0 |
| `brain_outputs` | 35192 | 2026-06-15T20:32:54Z | 885 |
| `market_technical_signals` | 0 | none | 0 |
| `orderbook_signals` | 0 | none | 0 |
| `neuron_signals` | 25451 | 2026-06-15T20:31:22Z | 20 |
| `neuron_signal_bindings` | 25393 | 2026-06-15T20:31:22Z | 20 |
| `signal_quality_evaluations` | 22301 | 2026-06-15T20:31:23Z | 20 |
| `news_raw_events` | 83 | 2026-06-10T22:15:43Z | 0 |
| `news_normalized_events` | 295 | 2026-06-10T22:32:01Z | 0 |
| `news_impact_scores` | 391 | 2026-06-10T22:32:01Z | 0 |
| `news_market_links` | 391 | 2026-06-10T22:32:01Z | 0 |
| `whale_events` | 14 | 2026-06-07T11:41:05Z | 0 |
| `whale_scan_runs` | 14 | 2026-06-07T11:41:05Z | 0 |
| `whale_market_scores` | 0 | none | 0 |
| `payout_odds_evaluations` | 1947 | 2026-06-07T11:44:43Z | 0 |
| `payout_odds_sources` | 1947 | no timestamp column | n/a |
| `social_*` tables | 0 | none | 0 |
| `market_memory_*` tables | 0 | none | 0 |
| `truth_state_registry` | 9667 | 2026-06-15T20:32:39Z | 74 |
| `runtime_cycles_v2` | 11776 | 2026-06-15T20:32:26Z | 9 |
| `risk_evidence_mesh_evaluations` | 2425 | 2026-06-15T20:32:39Z | 74 |
| `lifecycle_governance_decisions` | 11728 | 2026-06-15T20:32:39Z | 74 |
| `coordinator_decisions` | 23732 | 2026-06-15T20:32:54Z | 193 |
| `no_trade_log` | 20610 | 2026-06-15T20:32:56Z | 26 |

## 7. Freshness Table

| Source | TTL used for audit | After age | Freshness |
|---|---:|---:|---|
| CLOB orderbook | 180s | 5s | Fresh |
| Candidate price path | 900s | 3s | Fresh |
| Liquidity/brain outputs | 180s | 5s | Fresh |
| Signals | 900s | 96-97s | Fresh |
| News | 5400s | ~424858s | Stale |
| Whale | 5400s | ~723113s | Stale |
| Payout | 900s | ~722895s | Stale |
| Market movement | 900s | no rows | Missing |
| Market memory | 86400s | no rows | Missing |
| Social | 5400s | no rows | Missing |
| Cross-market | 900s | no connector | Missing connector |
| AI | 3600s | no measured runtime row | Fallback / unknown |

## 8. TTL Audit

| Source | TTL result | Evidence |
|---|---|---|
| CLOB orderbook | `TTL_OK_SOURCE_FRESH` | Refreshed during SYSTEM ON. |
| Candidate price path | `TTL_OK_SOURCE_FRESH` | Refreshed during SYSTEM ON. |
| Liquidity | `TTL_OK_SOURCE_FRESH` | Brain outputs refreshed during SYSTEM ON. |
| Signals | `TTL_OK_SOURCE_FRESH` during SYSTEM ON; stale when system off long enough | Short TTL is working. |
| News | `NO_REFRESH_ATTEMPT` or `REFRESH_FAILED` | Data exists but latest is June 10 and no rows appeared during run. |
| Whale | `NO_REFRESH_ATTEMPT` or `REFRESH_FAILED` | Data exists but latest is June 7 and no rows appeared during run. |
| Payout | `NO_REFRESH_ATTEMPT` | Candidate-linked rows exist, but latest is June 7; no DATA_ONLY refresh in six cycles. |
| Market movement | `NO_REFRESH_ATTEMPT` | Tables exist but zero rows. |
| Market memory | `NO_REFRESH_ATTEMPT` | Tables exist but zero rows. |
| Social | `NOT_REFRESHING_MISSING_CONFIG` | Missing required X/Reddit/Telegram keys; zero rows. |
| Cross-market | `NOT_REFRESHING_CONNECTOR_MISSING` | No connector/tables found. |
| AI | `REFRESH_UNKNOWN` | Config rows say OpenAI/Anthropic/Ollama present, but Mesh uses deterministic fallback/unavailable. |

## 9. Candidate-Linking Table

| Source | Candidate/market/side/token link |
|---|---|
| Orderbook | Market, side, token linked; candidate metadata exists on snapshots. |
| Candidate price path | Market/side linked, candidate rows active. |
| Signals | Market-linked; bindings include matched side; latest Mesh responses candidate-side linked. |
| Payout | Subject/candidate, market, side, token support exists; stale. |
| News | Market-linked only; no candidate/side/token direction in current rows. |
| Whale | Market/asset/side columns exist; current rows stale and not decision-useful. |
| Market movement | No rows. |
| Market memory | No rows. |
| Social | No rows. |
| Cross-market | No connector. |
| AI | Candidate identity is available to reasoner, but no live source-backed AI review measured. |

## 10. Directionality Table

| Source | Directional rows / response |
|---|---|
| Signals | 8040 side bindings overall; latest run produced directional Mesh responses. |
| Payout | 189 side rows overall; latest Risk traces used stale YES payout. |
| News | 0 directional rows in audited news impact/link tables. |
| Whale | Side column exists, but audited direction count was 0 because stored values do not map to YES/NO directional source under current query. |
| Market movement | 0 rows. |
| Market memory | Neutral/not directional by design. |
| Social | 0 rows. |
| Cross-market | No connector. |
| AI | No independent direction; must reason only over source records. |

## 11. Mesh Integration Table

| Source | Registry | Full Mesh request | Response state during run |
|---|---|---|---|
| News | Registered | Yes | `UNAVAILABLE_NO_DATA` for current candidate scope |
| Whale | Registered | Yes | `UNAVAILABLE_NO_DATA` for current candidate scope |
| Social | Registered | Yes | `UNAVAILABLE_MISSING_CONFIG` / no data |
| Cross-market | Registered | Yes | `UNAVAILABLE_NO_CONNECTOR` |
| Market memory | Registered | Yes | `UNAVAILABLE_NO_DATA` |
| Market movement | Registered | Yes | `UNAVAILABLE_NO_DATA` |
| Signal quality | Registered | Yes | Candidate-scoped directional |
| Signal processing | Registered | Yes | Candidate-scoped directional |
| Payout | Registered | Yes | Candidate-scoped directional but stale |
| AI reasoner | Registered/passive | Yes | Unavailable/fallback |

Full Mesh during the controlled run, `limit=20`:

- sessions: 20
- blocked: 20
- errors: 0
- source organs active: 60
- missing-config organ count: 20
- no-data organ count: 80
- candidate-scoped source organ count ranged between 20 and 60 depending on latest page composition
- directional source organ count ranged between 20 and 60

## 12. Edge / Risk Consumption Table

After the controlled run, latest 50 Risk Edge Theses:

- `EDGE_SUPPORTED`: 0
- `EDGE_STALE`: 50
- `risk_usable`: 0
- `source_backed`: 0
- source organs queried: 500
- directional sources found: 134

Top traces show Risk consumes:

- fresh `signal_quality`
- fresh `signal_processing`
- stale `payout`

Risk blocks as `RISK_BLOCKED_EDGE_STALE`. This means source data reaches Risk metadata, but stale payout evidence prevents a risk-usable edge.

## 13. Refresh Truth Classification

| Source | Primary classification | Secondary tags | Required action |
|---|---|---|---|
| Polymarket market data | `CONNECTED_BUT_STALE` | market-level, stale | Refresh market metadata or document TTL expectation. |
| CLOB orderbook | `FULLY_DECISION_USEFUL` after SYSTEM ON | candidate-scoped, fresh, watch context | Keep as required context; not edge by itself. |
| Candidate price path | `FULLY_DECISION_USEFUL` after SYSTEM ON | market/side linked | Keep candidate refresh path active. |
| Liquidity | `DECISION_USEFUL_WATCH_ONLY` | fresh, candidate context | Keep; not independent edge. |
| Market movement | `CONNECTED_BUT_NO_DATA` | source-backed capable, needs producer | Wire/restore producer for `market_technical_signals` or `orderbook_signals`. |
| Signals | `DECISION_USEFUL_WATCH_ONLY` | fresh, directional, risk-consumed | Keep; strengthen provenance/independence if intended to support Edge. |
| News | `CONNECTED_BUT_STALE` | market-level, not directional | Restore ingestion and add candidate-direction classification. |
| Whale | `CONNECTED_BUT_STALE` | market/token capable, stale | Restore scanner/profile flow and side normalization. |
| Payout | `CONNECTED_BUT_STALE` | candidate/token/side linked, directional | Refresh/recompute in DATA_ONLY candidate cycles. |
| Cross-market | `NO_CONNECTOR` | external config/connector needed | Add real connector or keep unavailable. |
| Memory | `CONNECTED_BUT_NO_DATA` | producer missing | Populate from outcomes/no-trade history or keep neutral. |
| Social | `MISSING_CONFIG` / `CONNECTED_BUT_NO_DATA` | external config required | Provide X/Reddit/Telegram config or keep unavailable. |
| AI | `UNKNOWN_NEEDS_MANUAL_REVIEW` | configured in registry, fallback used | Verify model router reachability and schema path; do not let AI invent sources. |
| Truth/control | `FULLY_DECISION_USEFUL` | fresh after run | Keep as audit/control truth. |

## 14. Top 20 Candidate Traces

All latest 20 traces were on market `691547`, side `YES`, and token `34626184950254225208692030156208941308358060420950772251072421141618169142241`.

Common result across top 20:

- source organs queried: 10 per candidate
- supporting neurons: `signal_quality`, `signal_processing`, `payout`
- `signal_quality`: YES, confidence 1.0, strength 1.0, freshness about 79-80s
- `signal_processing`: YES, confidence 1.0, strength 1.0, freshness about 79-80s
- `payout`: YES, confidence 0.68, strength 0.6, freshness about 723k seconds
- no-data organs: `market_memory`, `market_movement`, `news`, `whale`
- unavailable organs: `ai_reasoner`, `cross_market`, `social`
- missing config organ: `social`
- edge state: `EDGE_STALE`
- risk result: `RISK_BLOCK`
- risk blocker: `RISK_BLOCKED_EDGE_STALE`
- lifecycle/actionability: blocked by lifecycle/risk chain
- exact missing piece for `EDGE_SUPPORTED`: refresh stale payout or replace it with a fresh independent candidate-linked directional source; then ensure market movement/news/whale/cross-market/memory status is either fresh, explicitly unavailable, or non-blocking.

## 15. Bugs Found

No new code bug was proven in this audit.

The previously fixed bug remains fixed: Full Mesh source organ responses now reach canonical Risk Edge Thesis metadata. Current latest Risk theses show `source_organs_queried > 0` and `directional_sources_found > 0`.

Observed operational gaps:

- payout is candidate-linked and directional but not refreshed in DATA_ONLY candidate cycles
- market movement/technical tables remain empty
- news and whale are stale
- social is missing config
- cross-market has no connector
- AI remains fallback/unavailable despite source registry config readiness

## 16. Fixes Made

No runtime source logic, Risk, Exit, Lifecycle, Capital, Edge threshold, or Paper Actionability behavior was changed.

Added only:

- `tests/test_complete_source_data_audit_contract.py`
- this audit report

## 17. Why EDGE_SUPPORTED Is 0

`EDGE_SUPPORTED` is 0 because every latest sampled Risk Edge Thesis is `EDGE_STALE`.

The candidate-scoped fresh signals are present and consumed, but they are paired with stale payout evidence. Under the existing edge engine rule, stale directional supporting evidence blocks risk usability. News, whale, market movement, market memory, social, cross-market, and AI did not provide fresh candidate-linked independent support during the run.

This is a real current blocker, not a hidden source consumption bug.

## 18. What Exactly Is Needed Per Source

Priority corrections:

1. Payout: add/restore safe DATA_ONLY candidate-specific payout/odds recomputation so latest payout evidence is within 900s TTL.
2. Market movement: wire producer for `market_technical_signals` / `orderbook_signals`, or explicitly declare it passive until implemented.
3. News: restore NewsAPI/RSS ingestion and produce candidate-market directional impact rows when source text supports a side.
4. Whale: restore fresh wallet flow scans and normalize side/token direction to YES/NO when evidence supports it.
5. Cross-market: implement a real connector or keep `NO_CONNECTOR`.
6. Social: provide missing config keys or keep unavailable.
7. Market memory: populate from historical outcomes/no-trade memory or keep neutral/no-data.
8. AI: verify runtime model router reachability and continue deterministic fallback if unavailable; AI must cite existing source records only.

Do not lower edge thresholds. Do not treat orderbook or signals alone as Paper-ready Edge unless repository rules are explicitly changed in a later approved phase.

## 19. READY_FOR_PHASE_10

READY_FOR_PHASE_10 = NO

Exact reason:

- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED = 0`
- `EDGE_SUPPORTED = 0`
- `risk_usable = 0`
- latest Risk edge theses are `EDGE_STALE`
- remaining current blockers are `RISK_BLOCKED_EDGE_STALE`, `BLOCKED_BY_LIFECYCLE`, and expected operational `PAPER_SIMULATION_OFF`

Phase 10 should not start until at least one candidate has fresh, candidate-linked, directional, source-backed, risk-usable Edge and all non-paper operational gates are clean.

## 20. Safety Result

Forbidden artifact counts:

| Table | Before | After |
|---|---:|---:|
| `paper_intents` | 20 | 20 |
| `paper_orders` | 12 | 12 |
| `paper_fills` | 9 | 9 |
| `paper_positions` | 12 | 12 |
| `paper_position_closes` | 9 | 9 |
| `live_orders` | 0 | 0 |
| `positions` | 0 | 0 |

DATA_ONLY rows changed as expected during SYSTEM ON:

- `orderbook_snapshots`: 53643 -> 53816
- `paper_eligibility_candidates`: 20584 -> 20610
- `brain_outputs`: 34307 -> 35192
- `neuron_signals`: 25431 -> 25451
- `neuron_signal_bindings`: 25373 -> 25393
- `signal_quality_evaluations`: 22281 -> 22301
- `risk_evidence_mesh_evaluations`: 2351 -> 2425
- `lifecycle_governance_decisions`: 11654 -> 11728
- `coordinator_decisions`: 23539 -> 23732
- `no_trade_log`: 20584 -> 20610

SYSTEM OFF cleanup completed. `/runtime/health` after cleanup reported `runtime_state=STOPPED`, `system_power=OFF`, `runtime_life_state=STOPPED`, `supervisor_state=STOPPED`.

## 21. Recommended Next Implementation Bundle

Build a Source Freshness Correction Bundle:

1. Candidate-specific payout/odds refresh in DATA_ONLY.
2. Market movement / orderbook signal producer wiring.
3. News/whale refresh and candidate-direction linking.
4. AI router runtime reachability audit, without source invention.
5. Rerun this audit and require latest Risk Edge Theses to move from `EDGE_STALE` to either `EDGE_SUPPORTED` or a current non-stale blocker.

