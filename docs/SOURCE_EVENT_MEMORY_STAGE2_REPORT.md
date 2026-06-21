# Source Event Memory Stage 2 Report

## Purpose

Stage 2 adds Source Event Memory and Event-to-Market Recall for POLYBOT Money Machine Core. It remembers recent world/source events, normalizes them into a canonical DATA_ONLY memory table, links them to Stage 1 Market Universe Memory, and exposes recall visibility to control endpoints.

This stage does not create execution candidates, paper artifacts, paper orders, shadow orders, live orders, or targeted revalidation jobs.

## Money Machine Fit

Stage 1 answered: which markets exist?

Stage 2 answers: what happened, and which remembered markets may be affected?

The output is a recall layer for future Stage 3 Targeted Market Revalidation from Event Recall.

## Existing Source Audit

Existing source rows are available across:

- `news_normalized_events`, `news_market_links`, `news_impact_scores`
- `external_events_normalized`, `external_event_enrichments`
- `whale_events`
- `orderbook_signals`, `market_technical_signals`
- `payout_odds_evaluations`
- `neuron_signals`
- `brain_outputs`

Stage 2 reads these tables and normalizes recent rows. No AI-generated source facts or links are introduced.

## Architecture

Added `SourceEventMemoryService` as the canonical DATA_ONLY source-event layer:

- reads recent source rows from existing source tables
- normalizes source type, text, event time, direction, freshness, entities/topics/keywords
- deduplicates by source type, source id/url, headline, raw hash, and timestamp bucket
- links each event to `market_universe_memory`
- records refresh-run metadata and safety counts
- exposes endpoint summaries, per-event recall, and by-market recall

The service is wired into `SourceRefreshOrchestrator` at a conservative cadence and into read-only control surfaces.

## Data Model

Migration `0133_source_event_memory.sql` adds:

- `source_event_memory`
- `event_to_market_recall`
- `source_event_memory_refresh_runs`

The schema is append/update DATA_ONLY and non-destructive.

## Normalization

Canonical source types:

- `NEWS`
- `RSS`
- `CRYPTOPANIC`
- `WHALE`
- `WALLET_FLOW`
- `ORDERBOOK_MOVEMENT`
- `MARKET_MOVEMENT`
- `SIGNAL`
- `PAYOUT_ODDS`
- `AI_SUMMARY`
- `UNKNOWN`

Entity/topic/keyword extraction is deterministic and local. Existing stored entities/topics are reused when present.

## Direction

Event direction supports:

- `YES`
- `NO`
- `NEUTRAL`
- `MIXED`
- `UNKNOWN`

Per-market direction is stored on recall rows. Unknown direction remains unknown when evidence is insufficient.

## Recall Logic

Market links are scored from:

- exact linked market id
- title/slug/question keyword overlap
- entity overlap
- topic/tag overlap
- keyword overlap

Link types:

- `DIRECT_LINK`
- `LIKELY_LINK`
- `WEAK_LINK`
- `CONTEXT_ONLY`
- `NO_LINK`

Only `DIRECT_LINK` and high-confidence `LIKELY_LINK` are marked eligible for future targeted revalidation. Stage 2 does not execute that revalidation.

## Already Priced In

Already-priced-in state is populated only from existing impact/movement evidence when available:

- `YES`
- `NO`
- `UNKNOWN`
- `NOT_EVALUATED`

Missing evidence remains `NOT_EVALUATED` or `UNKNOWN`.

## Contradiction / Support

Contradiction hints are populated from existing source metadata when available. Existing-thesis support remains `NOT_EVALUATED` unless safe evidence exists.

## API Endpoints

Added:

- `GET /dashboard/api/v2/control/source-event-memory`
- `POST /dashboard/api/v2/control/source-event-memory/refresh`
- `GET /dashboard/api/v2/control/source-event-memory/recall?source_event_id=...`
- `GET /dashboard/api/v2/control/source-event-memory/by-market?market_id=...`

Updated:

- `GET /dashboard/api/v2/control/market-universe-memory`
- `GET /dashboard/api/v2/control/trade-opportunity-score`
- `GET /dashboard/api/v2/control/paper-actionability`
- `GET /dashboard/api/v2/control/decision-propagation-trace`

## Integration Surfaces

Market memory samples now include recent linked-event summary when available.

Opportunity score and paper actionability expose:

- `recent_source_event_count`
- `strongest_event_link_type`
- `strongest_event_link_confidence`
- `recent_directional_event_state`
- `recent_source_event_link_state`
- `direct_event_link_count`
- `likely_event_link_count`
- `source_event_memory_ids`
- `event_to_market_link_ids`

Decision trace exposes the same recall fields.

## Verification Counts

Latest DATA_ONLY refresh:

- total source events: 259
- recent source events: 259
- linked events: 167
- unlinked events: 92
- average link confidence: 0.7028

Source events by type:

- `AI_SUMMARY`: 6
- `MARKET_MOVEMENT`: 10
- `NEWS`: 62
- `ORDERBOOK_MOVEMENT`: 25
- `PAYOUT_ODDS`: 62
- `RSS`: 62
- `SIGNAL`: 32

Link type counts:

- `DIRECT_LINK`: 73
- `LIKELY_LINK`: 25
- `WEAK_LINK`: 68
- `CONTEXT_ONLY`: 2
- `NO_LINK`: 92

Direction counts:

- `YES`: 82
- `NO`: 1
- `NEUTRAL`: 32
- `MIXED`: 0
- `UNKNOWN`: 144

Already-priced-in counts:

- `YES`: 0
- `NO`: 58
- `UNKNOWN`: 0
- `NOT_EVALUATED`: 201

Contradiction/support counts:

- contradicts previous `NO`: 14
- contradicts previous `NOT_EVALUATED`: 245
- supports existing thesis `NOT_EVALUATED`: 259

## Example Linked Event

Example top linked event:

- source event: `source_event_cd37e6cee129e0f34baf85f0`
- type: `SIGNAL`
- source: `polymarket_clob_orderbook`
- headline: `Neuron signal orderbook source_status_observed`
- market: `691547`
- link type: `DIRECT_LINK`
- confidence: 1.0
- direction for market: `NEUTRAL`
- future targeted revalidation eligible: true

## Example Unlinked Event

Example unlinked event:

- source event: `source_event_3a22c90f776727b011241180`
- type: `AI_SUMMARY`
- headline: `AI summary liquidity WATCH`
- direction: `UNKNOWN`
- top link confidence: 0.0

## Tests Run

Focused:

`docker compose --profile test run --rm -e PYTHONPATH=/app test pytest tests/test_source_event_memory.py tests/test_source_event_deduplication.py tests/test_event_to_market_recall.py tests/test_source_event_memory_integration_surfaces.py -q`

Result: `9 passed, 1 warning`.

Related:

`docker compose --profile test run --rm -e PYTHONPATH=/app test pytest tests/test_market_universe_memory.py tests/test_market_identity_normalization.py tests/test_market_memory_refresh.py tests/test_market_memory_integration_surfaces.py tests/test_trade_opportunity_scoring.py -q`

Result: `18 passed, 1 warning`.

Broad:

`docker compose --profile test run --rm -e PYTHONPATH=/app test pytest tests -q -k "source_event_memory or event_to_market_recall or market_universe or market_memory or opportunity_score or paper_actionability or decision_trace"`

Result: `62 passed, 2093 deselected, 1 warning`.

Compile:

`.venv\Scripts\python.exe -m compileall app tests`

Result: passed.

## Deployment

Commands run:

- `docker compose build api`
- `docker compose build migrate`
- `docker compose run --rm migrate`
- `docker compose up -d --no-deps api`

Migration status:

- `0133_source_event_memory.sql` applied.
- Final migration check: no pending migrations.

## DATA_ONLY Verification

Verification sequence:

1. Triggered source event memory refresh.
2. Triggered market universe memory refresh.
3. `POST SYSTEM ON`.
4. Waited through five DATA_ONLY supervisor cycles.
5. Verified source-event endpoint, score/actionability/trace visibility.
6. `POST SYSTEM OFF`.

Final runtime state:

- `overall_status`: `SAFE_STOPPED`
- `runtime_state`: `STOPPED`
- `system_power_state`: `OFF`
- `supervisor_state`: `STOPPED`
- mode: `DATA_ONLY`

## Safety Result

Artifact counts before/after verification:

- `paper_intents`: 21 -> 21
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `live_orders`: 0 -> 0
- `positions`: 0 -> 0
- `shadow_orders`: 0 -> 0

Refresh metadata confirmed:

- `trading_mutation`: false
- `execution_candidates_created`: false
- `targeted_revalidation_triggered`: false

## Limitations

- Stage 2 does not execute targeted market revalidation.
- Stage 2 does not generate candidates.
- Already-priced-in and contradiction states remain conservative where source evidence is missing.
- Weak/context links are memory only and are not actionable.

## Recommended Stage 3

Targeted Market Revalidation from Event Recall:

- consume only `DIRECT_LINK` and high-confidence `LIKELY_LINK`
- refresh market/orderbook/source truth for linked markets
- still avoid execution candidate creation unless a later stage explicitly authorizes it

## Status

GREEN.
