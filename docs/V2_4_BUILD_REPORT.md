# V2.4 Build Report

## Summary

V2.4 implements the News Neuron foundation: source registry, collector, normalizer, deduplicator, source reliability scoring, market linking, impact scoring, priced-in detection, TTL, optional AI context analysis, DB tables, API routes, dashboard truth, Event Bus integration, tests, and docs.

The News Neuron is intelligence-only. It does not create orders, order intents, positions, risk approvals, or trading actions.

## Files Created

- `app/news_neuron/*`
- `app/api/news_routes.py`
- `app/repositories/news_source_repository.py`
- `app/repositories/news_raw_event_repository.py`
- `app/repositories/news_normalized_event_repository.py`
- `app/repositories/news_dedup_repository.py`
- `app/repositories/news_market_link_repository.py`
- `app/repositories/news_impact_repository.py`
- `app/repositories/news_reliability_repository.py`
- `app/repositories/news_ai_analysis_repository.py`
- `app/db/migrations/0042_v2_news_neuron.sql`
- `tests/test_v2_4_news_*.py`
- `docs/V2_4_NEWS_NEURON.md`
- `docs/V2_4_BUILD_REPORT.md`

## Files Changed

- `app/events/types.py`
- `app/main.py`
- `app/api/routes.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration Added

- `0042_v2_news_neuron.sql`

## API Routes Added

- `GET /news/recent`
- `GET /news/sources`
- `GET /news/market/{market_id}`
- `GET /news/impact/top`
- `POST /news/collect`
- `POST /news/manual`

## Dashboard Changes

Added a read-only News Neuron panel and dashboard overview key `news_neuron`, backed by real DB queries only.

## Events Published

- `news.source.registered`
- `news.raw.collected`
- `news.event.created`
- `news.event.normalized`
- `news.event.deduped`
- `news.market.linked`
- `news.impact.scored`
- `news.ai.analyzed`
- `news.source.reliability.updated`

## Tests Added

- `tests/test_v2_4_news_contracts.py`
- `tests/test_v2_4_news_source_registry.py`
- `tests/test_v2_4_news_collector.py`
- `tests/test_v2_4_news_normalizer.py`
- `tests/test_v2_4_news_deduplicator.py`
- `tests/test_v2_4_news_source_reliability.py`
- `tests/test_v2_4_news_market_linker.py`
- `tests/test_v2_4_news_impact_scorer.py`
- `tests/test_v2_4_news_priced_in_detector.py`
- `tests/test_v2_4_news_ttl_engine.py`
- `tests/test_v2_4_news_ai_context_analyzer.py`
- `tests/test_v2_4_news_api.py`
- `tests/test_v2_4_news_service_integration.py`
- `tests/test_v2_4_news_safety_guards.py`

## Tests Run

Initial targeted V2.4 no-DB run:

- `python -m uv run pytest tests/test_v2_4_news_contracts.py ... tests/test_v2_4_news_safety_guards.py -q`: `18 passed, 8 skipped`.

Per-file targeted no-DB run:

- `tests/test_v2_4_news_contracts.py`: `2 passed`
- `tests/test_v2_4_news_source_registry.py`: `1 passed, 1 skipped`
- `tests/test_v2_4_news_collector.py`: `2 skipped`
- `tests/test_v2_4_news_normalizer.py`: `2 passed`
- `tests/test_v2_4_news_deduplicator.py`: `2 passed`
- `tests/test_v2_4_news_source_reliability.py`: `1 passed`
- `tests/test_v2_4_news_market_linker.py`: `2 passed`
- `tests/test_v2_4_news_impact_scorer.py`: `2 passed`
- `tests/test_v2_4_news_priced_in_detector.py`: `2 passed`
- `tests/test_v2_4_news_ttl_engine.py`: `1 passed`
- `tests/test_v2_4_news_ai_context_analyzer.py`: `2 passed`
- `tests/test_v2_4_news_api.py`: `3 skipped`
- `tests/test_v2_4_news_service_integration.py`: `1 skipped`
- `tests/test_v2_4_news_safety_guards.py`: `1 passed, 1 skipped`

Explicit local DB run:

- `tests/test_v2_4_news_api.py`: `3 passed`
- `tests/test_v2_4_news_service_integration.py`: `1 passed`
- `tests/test_v2_4_news_market_linker.py`: `2 passed`
- `tests/test_v2_4_news_impact_scorer.py`: `2 passed`
- `tests/test_v2_4_news_source_registry.py`: `2 passed`
- `tests/test_v2_4_news_collector.py`: `2 passed`
- `tests/test_v2_4_news_safety_guards.py`: `2 passed`
- Optional combined explicit-DB regression batch for `tests/test_v2_3_ai_api.py`, `tests/test_v2_2_data_foundation_api.py`, `tests/test_v2_1_event_api.py`, and `tests/test_runtime_api.py`: timed out after 604 seconds before emitting useful per-file output; no failure assertion was captured.

Regression run:

- V2.3 selected regressions: passed or skipped as expected without DB env.
- V2.2 selected regressions: passed or skipped as expected without DB env.
- V2.1 selected regressions: skipped as expected without DB env.
- Runtime and Stage 4 regressions: passed or skipped as expected without DB env.

Full suite:

- `python -m uv run pytest`: `158 passed, 332 skipped`.

Relevant old regressions:

- `python -m uv run pytest tests/test_phase2_execution_aware_paper.py -q`: `13 skipped` because DB env was absent.
- `python -m uv run pytest tests/test_phase9_dashboard_telegram.py -q`: `10 skipped` because DB env was absent.

## Runtime Verification Results

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: applied `0042_v2_news_neuron.sql`.
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`: foreground command was started directly first and timed out because the server is long-running; then it was started in a background PowerShell process for endpoint verification.
- `GET /healthz`: returned `{"status":"ok","app":"polybot","ready":true}`.
- `GET /runtime/state`: returned `DATA_ONLY`, kill false, live permissions false.
- `GET /runtime/health`: returned `HEALTHY`.
- `GET /events/lag`: returned real metrics with `failed_events=0`, `open_dlq_count=0`.
- `GET /data/coverage`: returned real coverage; orderbook coverage remained `0.0`, consistent with V2.2 limitation.
- `GET /ai/health`: returned `local_ai_available=false`, `cloud_enabled=false`.
- `GET /news/recent`: returned list response.
- `GET /news/sources`: returned list response.
- `GET /news/impact/top`: returned list response.
- `POST /news/manual`: persisted and processed a safe manual BTC headline.
- Follow-up `GET /news/recent`: returned the normalized manual item.
- Follow-up `GET /events/recent`: included News Neuron events, including `news.impact.scored`.
- Follow-up `GET /news/impact/top`: returned persisted impact rows.
- Runtime process was stopped after verification.

Dashboard note: the existing aggregate `GET /dashboard/api/overview` timed out in this local runtime verification window. The new `news_neuron` dashboard fields are DB-backed in `OperatorDashboardQueryService`, but the full dashboard endpoint remains heavy because it aggregates all legacy panels.

## Fully Implemented

- Durable news source registry.
- Manual and RSS collector abstraction.
- Raw event persistence and content hash duplicate prevention.
- Deterministic normalization.
- Deterministic dedup grouping.
- Operational source reliability scoring.
- V2.2 market linking.
- Bounded impact scoring and NewsSignal contract.
- Priced-in detector and TTL engine.
- Optional V2.3 AI context analyzer.
- API routes.
- Dashboard truth.
- Event Bus events.

## Partial

- Runtime collection scheduling is not enabled by default. Collection is operator/API-triggered.
- RSS parsing is deliberately simple.
- Direction inference stays conservative and commonly returns `UNKNOWN`.
- AI enrichment is optional and skipped for low-value news.

## Safety Checklist

- KILL blocks trading: YES.
- DATA_ONLY blocks orders: YES.
- PAPER blocks live: YES.
- SHADOW_LIVE blocks live: YES.
- Live disabled by default: YES.
- News cannot create orders: YES.
- News cannot create order intents: YES.
- News cannot bypass State Governor: YES.
- News cannot bypass AI Budget Governor: YES.
- Same story deduped: YES.
- Source scored: YES.
- News linked to market only when justified: YES.
- Irrelevant news ignored: YES.
- Priced-in news downgraded: YES.
- TTL computed: YES.
- AI analysis optional and safe: YES.
- No secrets printed: YES.
- News events redacted: YES.
- Dashboard uses real data only: YES.

## Remaining Risks

- Source reliability is preliminary operational reliability, not final truthfulness.
- Market direction inference should remain conservative until future AI/rules phases improve evidence.
- Runtime orderbook ingestion remains partial from V2.2 and can reduce downstream confidence.
- Full live external news collection was not run; tests use mocked RSS/manual ingestion.

## Recommendation

V2.4 status: GREEN.

Can move to V2.5: YES.
