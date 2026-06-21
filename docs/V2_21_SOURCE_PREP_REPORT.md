# V2.21 Source Prep Report

## 1. Executive Summary

V2.21 Source Prep is implemented as a read-only source connectivity and observability foundation.

Final status: **GREEN**

POLYBOT now has a real Dashboard V2 source-status endpoint backed by safe GET-only checks and a small operational `source_status` table. Gamma, CLOB orderbook-derived price/spread/depth truth, Data API trade/activity discovery, and Ollama tag visibility are represented as source truth. News and social remain intentionally disabled placeholders for later phases.

No trading, order placement, cancellation, signing, private-key usage, paper execution, news, social, whale profiling, Claude routing, or live logic was added.

## 2. Existing Source Connector Audit

Existing assets preserved:

- `app/ingestion/gamma_client.py`: active async Gamma ingestion client used by runtime market refresh.
- `app/tools/polymarket_orderbook_smoke.py`: existing read-only Gamma to CLOB `/book` smoke path.
- `app/data_foundation/orderbook_snapshotter.py`: orderbook normalization and depth/spread math.
- `app/market_neuron/orderbook_analyzer.py`: orderbook signal analysis logic.
- `app/repositories/orderbook_snapshot_repository.py`: canonical `orderbook_snapshots` persistence.
- `app/stage4/execution_client.py`: Stage4 CLOB client contains public and authenticated methods, but it imports Stage4 auth/private-key paths and was not used for V2.21.
- Dashboard V2 routes already existed under `/dashboard/api/v2/*`.

Existing gaps:

- CLOB source status was not visible as dashboard truth.
- CLOB read-only checks were not represented in an operational source status table.
- Data API trades/activity discovery was not surfaced in source health.
- Optional source placeholders were not represented explicitly.

Official API references reviewed:

- Polymarket API overview: https://docs.polymarket.com/api-reference/introduction
- CLOB orderbook endpoint: https://docs.polymarket.com/api-reference/market-data/get-order-book
- Data API trades endpoint: https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets

## 3. What Was Added / Changed

Files changed:

- `app/db/migrations/0057_v2_21_source_status.sql`
- `app/repositories/source_status_repository.py`
- `app/services/source_status.py`
- `app/api/routes.py`
- `tests/test_v2_21_source_status.py`
- `tests/test_v2_18_dashboard_v2_api.py`
- `docs/V2_21_SOURCE_PREP_REPORT.md`

The new service avoids the Stage4 authenticated CLOB client and uses direct bounded GET-only HTTP checks.

## 4. Polymarket Gamma Status

Source: `polymarket_gamma`

Runtime result:

- Status: `ACTIVE`
- Endpoint: `https://gamma-api.polymarket.com/events`
- Auth/key required: no
- Read-only: true
- Mutation allowed: false
- Real runtime check passed with active event discovery.

## 5. Polymarket CLOB / Data Read-Only Status

Sources:

- `polymarket_clob_orderbook`
- `polymarket_clob_prices`
- `polymarket_clob_spreads`
- `polymarket_activity_readonly`

Runtime result:

- CLOB `/book`: `ACTIVE`
- CLOB price truth: `ACTIVE`, derived from read-only `/book` best bid/ask/last trade fields.
- CLOB spread/depth truth: `ACTIVE`, derived from read-only `/book` bid/ask depth.
- Data API `/trades`: `ACTIVE`

The CLOB checker uses a bounded set of Gamma-discovered token candidates. During verification, the first two token candidates returned `404`, the third returned `200`, and source status remained accurate instead of crashing.

## 6. Activity / Trades Read-Only Discovery Status

Source: `polymarket_activity_readonly`

Runtime result:

- Status: `ACTIVE`
- Endpoint: `https://data-api.polymarket.com/trades`
- Auth/key required: no
- Read-only: true
- Mutation allowed: false
- Runtime sample returned one trade item with `limit=1`.

No whale profiling or wallet attribution logic was implemented.

## 7. Source Reliability Model

New table: `source_status`

Tracked fields include:

- `source_name`
- `source_type`
- `configured`
- `key_required`
- `key_present`
- `key_name`
- `endpoint_url`
- `runtime_status`
- `freshness_status`
- `read_only`
- `mutation_allowed`
- `success_count`
- `error_count`
- `last_success_at`
- `last_error_at`
- `last_latency_ms`
- `details_json`
- `notes`

Safety constraint:

- `read_only = TRUE`
- `mutation_allowed = FALSE`

This is operational source health, not the long-term learning/memory model in `source_reliability_memory`.

## 8. Dashboard Endpoint Details

New endpoint:

`GET /dashboard/api/v2/source-status`

Runtime result:

- `status`: `OK`
- `mock_data`: `false`
- `stale`: `false`
- degraded sources: empty

The endpoint returns real source records and remains safe if individual source checks fail.

## 9. DB / Migration Changes

Migration added:

- `0057_v2_21_source_status.sql`

Production migration result:

- `docker compose run --rm migrate`: `No pending migrations.`
- `source_status` exists in production DB.

Test migration result:

- First run after rebuilding test migration image applied `0057_v2_21_source_status.sql`.
- Later run: `No pending migrations.`

## 10. Tests Added / Updated

Added:

- `tests/test_v2_21_source_status.py`

Updated:

- `tests/test_v2_18_dashboard_v2_api.py`

Coverage:

- Source status endpoint returns `mock_data=false`.
- Gamma source maps to `ACTIVE` when check succeeds.
- CLOB orderbook/prices/spreads map to `ACTIVE` with read-only checks.
- Optional news key missing does not crash.
- Optional social key missing does not crash.
- No live/private key is required.
- Only GET-style read calls are used in source tests.
- Source failure becomes `DEGRADED`, not an exception.
- Dashboard route remains stable.
- Persistence uses Docker test DB `polybot_test`.

## 11. Commands Run and Exact Results

Configuration/build:

- `docker compose config`: passed.
- `docker compose --profile test config`: passed.
- `docker compose build`: passed.
- `docker compose build api migrate`: passed after connector refinement.
- `docker compose --profile test build test`: passed.
- `docker compose --profile test build test_migrate`: passed.

Runtime:

- `docker compose up -d`: passed.
- `docker compose ps`: api/postgres/postgres_test/redis healthy.
- `docker compose run --rm migrate`: `No pending migrations.`
- `docker compose --profile test run --rm test_migrate`: `No pending migrations.` after applying `0057`.

Tests:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_21_source_status.py tests/test_v2_18_dashboard_v2_api.py -q`: `11 passed in 5.61s`
- `.\scripts\test_in_docker.ps1 tests/test_v2_21_source_status.py -q`: `6 passed in 3.28s`

Runtime endpoints:

- `Invoke-RestMethod http://127.0.0.1:8000/healthz`: `status=ok`, `ready=True`
- `Invoke-RestMethod http://127.0.0.1:8000/runtime/health`: `overall_status=HEALTHY`
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview`: `status=OK`, `mock_data=false`, `stale=false`
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/source-status`: `status=OK`, `mock_data=false`, `stale=false`

Safety:

- API env check: `MODE=PAPER`, `BACKEND=paper`, `LIVE=false`, `KILL=true`

DB source-status sample:

- `polymarket_gamma`: `ACTIVE`
- `polymarket_clob_orderbook`: `ACTIVE`
- `polymarket_clob_prices`: `ACTIVE`
- `polymarket_clob_spreads`: `ACTIVE`
- `polymarket_activity_readonly`: `ACTIVE`
- `ollama_local_model`: `ACTIVE`
- `news_provider`: `DISABLED`
- `reddit_or_social_provider`: `DISABLED`

## 12. Safety Verification

Confirmed:

- No live trading was enabled.
- No private key was used.
- No authenticated CLOB trading client was used.
- No order placement endpoint was called.
- No cancel endpoint was called.
- New source checks are read-only.
- New table enforces `read_only=true` and `mutation_allowed=false`.
- `/runtime/health` remains `HEALTHY`.
- Dashboard overview remains real (`mock_data=false`).

## 13. What Remains Missing

Not implemented by design:

- Persistent orderbook snapshot ingestion loop.
- Paper trading.
- News provider.
- Social provider.
- Whale profiling.
- Claude routing.
- Live execution.
- Source freshness scheduler.
- Complex reliability learning.

Known notes:

- `source_status` currently updates when `/dashboard/api/v2/source-status` is requested. A future scheduler can refresh it periodically.
- CLOB `/book` can return `404` for some Gamma token candidates; the checker handles this by bounded candidate fallback.

## 14. Next Recommended Phase

Recommended Phase 2:

1. Add a scheduled read-only orderbook snapshot refresh for selected active markets.
2. Persist CLOB orderbook snapshots into `orderbook_snapshots`.
3. Connect source freshness to Dashboard V2 market/source panels.
4. Add source stale thresholds and source-history trend view.
5. Only after source persistence is stable, move to Paper readiness.

## 15. Final Status

Final status: **GREEN**

Can continue to Phase 2: **YES**

Reason:

- Docker runtime healthy.
- Migrations clean.
- `/runtime/health` healthy.
- Dashboard overview OK.
- `/dashboard/api/v2/source-status` works with `mock_data=false`.
- Gamma active.
- CLOB read-only orderbook/prices/spreads active.
- Data API activity read-only active.
- No live mutation path introduced.
- Tests pass in isolated Docker test DB.
- Safety env remains `LIVE=false`, `KILL=true`.
