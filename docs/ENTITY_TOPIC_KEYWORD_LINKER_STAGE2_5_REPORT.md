# Entity / Topic / Keyword Linker Stage 2.5 Report

## 1. Purpose

Stage 2.5 upgrades Source Event Memory recall quality before Stage 3 Targeted Market Revalidation.

The change is DATA_ONLY. It improves how POLYBOT links source events to Market Universe Memory using deterministic identifier, entity, topic, keyword, alias, and token-side evidence. It does not create execution candidates, paper intents, paper orders, paper fills, paper positions, shadow orders, live orders, or real orders.

## 2. Money Machine Fit

Stage 1 taught POLYBOT the remembered market universe.

Stage 2 taught POLYBOT to remember source events and create event-to-market recall rows.

Stage 2.5 improves the meaning layer between those systems so events such as ETF, SEC, BTC, ETH, CPI, Fed, and election updates can recall related markets with auditable confidence and guardrails.

## 3. Existing Linker Audit

The prior linker lived in `app/services/source_event_memory.py`.

Existing tables:

- `source_event_memory`
- `event_to_market_recall`
- `source_event_memory_refresh_runs`
- `market_universe_memory`

Existing recall used source rows from news, RSS, payout/odds, signals, orderbook movement, market movement, and AI summary sources. Link evidence was primarily exact market link, title containment, entity/topic/keyword overlap, and basic confidence thresholds.

Pre-upgrade counts:

- Source events: 259
- Linked events: 167
- Unlinked events: 92
- DIRECT_LINK: 73
- LIKELY_LINK: 25
- WEAK_LINK: 68
- CONTEXT_ONLY: 2
- NO_LINK: 92

False negative risk found: aliases such as BTC/Bitcoin, ETH/Ethereum, SEC, ETF, Fed/FOMC/CPI were not represented as a canonical evidence channel.

False positive risk found: broad political/crypto terms can over-link unless guardrails keep low-confidence links as weak/context only.

## 4. Architecture

Added deterministic linker metadata to every event-to-market recall row:

- `matched_aliases_json`
- `confidence_components_json`
- `semantic_score`
- `token_side_resolution_state`
- `candidate_actionability_hint`
- `guardrail_reason`

The linker now computes and stores component-level evidence:

- identifier score
- title/slug score
- entity score
- topic score
- keyword score
- alias score
- deterministic token-overlap semantic score
- recency boost
- ambiguity penalty
- broadness penalty
- conflict penalty

No external embedding system or AI fact generation was added.

## 5. Evidence Channels

Supported channels:

- Exact identifiers: market id, condition id, token id, slug
- Entity overlap
- Topic overlap and deterministic topic detection
- Keyword overlap
- Alias matching
- Deterministic token overlap as explainable semantic approximation
- Recency boost
- Ambiguity, broadness, and conflict penalties

## 6. Alias System

Added an auditable code-level alias dictionary for common market/event terms:

- BTC / Bitcoin
- ETH / Ethereum
- SEC / Securities and Exchange Commission
- ETF / exchange-traded fund
- spot ETF
- crypto regulation
- Fed / Federal Reserve
- FOMC
- CPI / inflation
- Trump / Donald Trump
- Biden / Joe Biden
- US / USA / United States
- AI / artificial intelligence

Aliases only contribute evidence. They do not by themselves create execution readiness.

## 7. Confidence Formula

The deterministic formula is:

```text
confidence =
  identifier_score
  + title_score
  + entity_score
  + topic_score
  + keyword_score
  + alias_score
  + semantic_score
  + recency_boost
  - broadness_penalty
  - ambiguity_penalty
  - conflict_penalty
```

The score is clamped to `0.0 - 1.0`.

Thresholds:

- DIRECT_LINK: exact identifier, or strong direct/entity-topic confidence
- LIKELY_LINK: confidence >= 0.65
- WEAK_LINK: confidence >= 0.35
- CONTEXT_ONLY: confidence >= 0.20
- NO_LINK: below threshold

## 8. Link Rules

DIRECT_LINK is allowed for exact identifiers or strong concrete evidence.

LIKELY_LINK is allowed for high-confidence but less exact relations.

WEAK_LINK and CONTEXT_ONLY are memory/context only.

NO_LINK remains unlinked.

## 9. Guardrails

Guardrails added:

- Weak links are not targeted revalidation eligible.
- Context-only links are not targeted revalidation eligible.
- Low-confidence links expose `BLOCKED_BY_LOW_CONFIDENCE`.
- Token/side conflict exposes `BLOCKED_BY_CONFLICT`.
- Token/side unknown stays `WATCH_ONLY`.
- Market-level-only evidence stays non-candidate-actionable.
- No Stage 3 targeted revalidation is triggered.
- No execution candidates are created.

## 10. Token / Side Resolution

Supported states:

- `TOKEN_SIDE_DIRECT`
- `TOKEN_SIDE_CONFLICT`
- `MARKET_LEVEL_ONLY`
- `TOKEN_SIDE_UNKNOWN`
- `SIDE_DIRECTIONAL_YES`
- `SIDE_DIRECTIONAL_NO`
- `SIDE_DIRECTIONAL_NEUTRAL`
- `SIDE_DIRECTIONAL_MIXED`

## 11. Candidate Actionability Hints

Added DATA_ONLY hints:

- `REVALIDATION_ELIGIBLE`
- `WATCH_ONLY`
- `CONTEXT_ONLY`
- `NOT_RELEVANT`
- `BLOCKED_BY_LOW_CONFIDENCE`
- `BLOCKED_BY_TOKEN_SIDE_UNKNOWN`
- `BLOCKED_BY_CONFLICT`

These are not trade approvals.

## 12. API Changes

Updated:

- `GET /dashboard/api/v2/control/source-event-memory`
- `GET /dashboard/api/v2/control/source-event-memory/recall`
- `GET /dashboard/api/v2/control/source-event-memory/by-market`
- `GET /dashboard/api/v2/control/market-universe-memory`
- `GET /dashboard/api/v2/control/trade-opportunity-score`
- `GET /dashboard/api/v2/control/paper-actionability`
- `GET /dashboard/api/v2/control/decision-propagation-trace`

Added:

- `GET /dashboard/api/v2/control/source-event-memory/linker-diagnostics`

## 13. Integration Surfaces

Market Universe Memory now exposes recent revalidation-eligible and watch-only linked event counts in samples.

Trade Opportunity Score, Paper Actionability, and Decision Propagation Trace expose:

- `recall_link_state`
- `event_link_actionability_hint`
- `token_side_resolution_state`
- `event_link_guardrail_reason`

## 14. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_entity_topic_keyword_linker.py tests/test_event_linker_guardrails.py tests/test_event_linker_aliases.py tests/test_event_linker_integration_surfaces.py -q
14 passed, 3 skipped
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_source_event_memory.py tests/test_source_event_deduplication.py tests/test_event_to_market_recall.py tests/test_source_event_memory_integration_surfaces.py tests/test_market_universe_memory.py -q
11 skipped
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "entity_topic_keyword_linker or event_linker or source_event_memory or event_to_market_recall or market_universe or opportunity_score or paper_actionability or decision_trace"
49 passed, 14 skipped, 2109 deselected
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
PASS
```

## 15. DATA_ONLY Verification

Deployment:

- `docker compose build api`: PASS
- `docker compose build migrate`: PASS
- `docker compose run --rm migrate`: applied `0134_event_linker_metadata.sql`
- `docker compose up -d --no-deps api`: PASS

Endpoint verification:

- `/healthz`: 200
- `/runtime/health`: 200
- `/dashboard/api/v2/control/source-event-memory`: 200
- `/dashboard/api/v2/control/source-event-memory/linker-diagnostics`: 200
- `/dashboard/api/v2/control/market-universe-memory`: 200
- `/dashboard/api/v2/control/trade-opportunity-score`: 200
- `/dashboard/api/v2/control/paper-actionability?limit=100`: 200
- `/dashboard/api/v2/control/decision-propagation-trace`: 200

Actions:

1. Triggered Source Event Memory refresh.
2. POST SYSTEM ON in DATA_ONLY.
3. Waited four 35-second polls.
4. Triggered Market Universe Memory refresh.
5. POST SYSTEM OFF cleanup.

SYSTEM ON remained DATA_ONLY. Paper Simulation remained OFF.

## 16. Link Counts After Refresh

After upgraded refresh:

- Source events: 432
- Linked events: 281
- Unlinked events: 151
- DIRECT_LINK: 76
- LIKELY_LINK: 153
- WEAK_LINK: 68
- CONTEXT_ONLY: 12
- NO_LINK: 153
- Revalidation eligible links: 109
- Watch-only links: 197
- Token-side unknown links: 301

Token-side resolution:

- MARKET_LEVEL_ONLY: 52
- SIDE_DIRECTIONAL_NEUTRAL: 11
- SIDE_DIRECTIONAL_NO: 17
- SIDE_DIRECTIONAL_YES: 81
- TOKEN_SIDE_UNKNOWN: 301

Top aliases matched in current production refresh: none. The alias path is covered by tests; the current source/market sample did not contain matching alias pairs.

Top topics matched:

- politics: 52
- geopolitics: 34

## 17. Example Links

DIRECT_LINK:

- `source_event_f1208619f1153356bb205175`
- market `691547`
- confidence `1.0`
- hint `REVALIDATION_ELIGIBLE`
- token-side state `SIDE_DIRECTIONAL_NEUTRAL`

LIKELY_LINK:

- `source_event_a79dfb93e47067a52916447e`
- market `691547`
- confidence `0.87`
- hint `REVALIDATION_ELIGIBLE`
- token-side state `SIDE_DIRECTIONAL_YES`

WEAK_LINK:

- `source_event_0d4fa5400d2c3ba6141b9978`
- market `677404`
- confidence `0.4885`
- hint `CONTEXT_ONLY`
- token-side state `MARKET_LEVEL_ONLY`

CONTEXT_ONLY:

- `source_event_536aba599ab9b8ebf24953e1`
- market `2354064`
- confidence `0.3278`
- hint `BLOCKED_BY_LOW_CONFIDENCE`
- token-side state `TOKEN_SIDE_UNKNOWN`

NO_LINK:

- `source_event_e7c990bcf85f9c820f909493`
- no market
- confidence `0.0`
- hint `NOT_RELEVANT`

## 18. Safety Result

Artifact counts before and after DATA_ONLY verification:

- paper_intents: 21 -> 21
- paper_orders: 12 -> 12
- paper_fills: 9 -> 9
- paper_positions: 12 -> 12
- live_orders: 0 -> 0
- positions: 0 -> 0
- shadow_orders: 0 -> 0

No execution candidates were created.

No targeted revalidation was triggered.

No Risk, Capital, Exit, or Lifecycle thresholds were changed.

## 19. Limitations

- Current production market/event sample did not produce alias matches after refresh, though alias behavior is tested and active.
- Semantic scoring is deterministic token overlap only. No external embeddings were added.
- Some pre-migration historical recall rows can still exist with empty metadata if their source event was not reprocessed in the refresh window.

## 20. Recommended Stage 3

Proceed to Stage 3:

Targeted Market Revalidation from Event Recall.

Stage 3 should consume only DIRECT_LINK and high-confidence LIKELY_LINK rows that pass the revalidation eligibility guardrails. It must not treat weak/context links as actionable.
