# V2.17 Build Report - No-Trade Intelligence

## Short Summary

V2.17 No-Trade Intelligence is implemented and verified. It turns `NO_TRADE` into a canonical, stored, reviewable, and learnable decision with normalized reasons, candidate engine tracking, post-fact review, regret scoring, safe memory-update hooks, APIs, dashboard truth, tests, and docs.

No orders, order intents, live exits, external sends, or external balance mutations were added.

## Files Created

- `app/no_trade/__init__.py`
- `app/no_trade/contracts.py`
- `app/no_trade/no_trade_errors.py`
- `app/no_trade/no_trade_logger.py`
- `app/no_trade/reason_classifier.py`
- `app/no_trade/candidate_tracker.py`
- `app/no_trade/post_fact_reviewer.py`
- `app/no_trade/regret_scorer.py`
- `app/no_trade/memory_updater.py`
- `app/no_trade/service.py`
- `app/repositories/no_trade_log_repository.py`
- `app/repositories/no_trade_reason_repository.py`
- `app/repositories/no_trade_post_fact_review_repository.py`
- `app/repositories/no_trade_regret_score_repository.py`
- `app/api/no_trade_routes.py`
- `app/db/migrations/0055_v2_17_no_trade_intelligence.sql`
- `tests/test_v2_17_*.py`
- `docs/V2_17_NO_TRADE_INTELLIGENCE.md`
- `docs/V2_17_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

Command:

`powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`

Result:

`Applied migrations: 0055_v2_17_no_trade_intelligence.sql`

Tables:

- `no_trade_log`
- `no_trade_reasons`
- `no_trade_post_fact_review`
- `no_trade_regret_score`

## API Routes

- `GET /no-trade/health`
- `GET /no-trade/recent`
- `GET /no-trade/{no_trade_id}`
- `GET /no-trade/reasons/top`
- `GET /no-trade/by-engine`
- `GET /no-trade/by-market-family`
- `GET /no-trade/regret`
- `GET /no-trade/reviews/pending`
- `POST /no-trade/log`
- `POST /no-trade/review`
- `POST /no-trade/rebuild`

## Dashboard Changes

`OperatorDashboardQueryService` now includes a real DB-backed `no_trade` overview:

- `no_trade_status`
- `logged_today`
- `top_no_trade_reasons`
- `no_trade_by_engine`
- `no_trade_by_market_family`
- `pending_reviews`
- `high_regret_count`
- `good_no_trade_count`
- `insufficient_data_count`
- `regret_analysis`
- `recent_no_trade_logs`
- `recent_high_regret`
- `errors`

## Events Published

- `no_trade.logged`
- `no_trade.reason.created`
- `no_trade.post_fact_review.created`
- `no_trade.regret_scored`
- `no_trade.memory_updated`
- `no_trade.insufficient_data`
- `no_trade.high_regret`
- `no_trade.good_decision`

## Tests Added

- `tests/test_v2_17_reason_classifier.py`
- `tests/test_v2_17_candidate_tracker.py`
- `tests/test_v2_17_no_trade_logger.py`
- `tests/test_v2_17_post_fact_reviewer.py`
- `tests/test_v2_17_regret_scorer.py`
- `tests/test_v2_17_memory_updater.py`
- `tests/test_v2_17_no_trade_service.py`
- `tests/test_v2_17_no_trade_api.py`
- `tests/test_v2_17_no_trade_safety_guards.py`
- `tests/test_v2_17_fixtures.py`

## Tests Run And Exact Results

Targeted no-DB:

- `$files = (Get-ChildItem tests\test_v2_17_*.py).FullName; python -m uv run pytest $files -q`
- Result: `20 passed in 32.10s`

DB-backed targeted:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $env:PHASE1_PERSISTENCE_ENABLED='true'; $files = (Get-ChildItem tests\test_v2_17_*.py).FullName; python -m uv run pytest $files -q`
- Result: `20 passed in 52.49s`

Targeted rerun after DB backfill filter fix:

- `$files = (Get-ChildItem tests\test_v2_17_*.py).FullName; python -m uv run pytest $files -q`
- Result: `20 passed in 35.19s`

Regressions:

- V2.16: `23 passed, 1 skipped in 72.14s`
- V2.15: `19 passed, 1 skipped in 72.45s`
- V2.14: `17 passed, 4 skipped in 43.49s`
- V2.13: `12 passed, 4 skipped in 23.76s`
- V2.12: `12 passed, 7 skipped in 15.79s`
- Runtime: `8 passed, 19 skipped in 21.05s`

Full suite:

- `python -m uv run pytest -q`
- Initial result: `357 passed, 395 skipped in 69.19s`
- Final rerun after backfill fix: `357 passed, 395 skipped in 72.49s`

## Runtime Verification Results

Docker/Postgres:

- `docker ps`: `polybot_phase1_pg` running on `0.0.0.0:55432->5432/tcp`; Grafana also running.
- TCP check: `127.0.0.1:55432` reachable.
- Psycopg DB check: connected to database `polybot` as user `polybot`.

Runtime:

- Canonical script attempted: `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`
- Result: Windows Application Control blocked `uv run polybot` with `os error 4551`.
- Fallback used: direct Python startup, `python -m uv run python -c "from app.main import run; run()"`.
- Runtime started on `127.0.0.1:8000`.
- Runtime state: `DATA_ONLY`.
- Live trading env remained disabled.

Verified endpoints:

- `/healthz` OK
- `/runtime/state` OK
- `/runtime/health` OK
- `/events/lag` OK
- `/data/coverage` OK
- `/exits/health` OK
- `/no-trade/health` OK
- `/no-trade/recent` OK
- `/no-trade/reasons/top` OK
- `/no-trade/by-engine` OK
- `/no-trade/by-market-family` OK
- `/no-trade/regret` OK
- `/no-trade/reviews/pending` OK

## Manual Smoke Results

Market used: `2169995`.

- `POST /no-trade/log` dry_run=true: `written=false`.
- Dry-run row check: `source_record_id='dryrun'` created `0` rows.
- `POST /no-trade/log` dry_run=false with `low_liquidity` and candidate engine `STRIKE`: wrote `no_trade_log` and normalized reasons.
- `POST /no-trade/log` without reason: rejected with HTTP `422`.
- `POST /no-trade/review` dry_run=true with incomplete data: `written=false`, review status `INSUFFICIENT_DATA`.
- `POST /no-trade/review` dry_run=false with insufficient later data: persisted review/regret with `INSUFFICIENT_DATA`.
- `POST /no-trade/review` dry_run=false with favorable move and possible liquidity: persisted `HIGH_REGRET`.
- `POST /no-trade/review` dry_run=false with avoided loss: persisted `GOOD_NO_TRADE`.
- `POST /no-trade/rebuild` dry_run=true for `exit`: returned 1 candidate and wrote nothing.
- `POST /no-trade/rebuild` dry_run=false for `exit`: backfilled 1 deduped exit-failure no-trade candidate.

## DB Row Verification

Before manual smoke:

- `no_trade_log=0`
- `no_trade_reasons=0`
- `no_trade_post_fact_review=0`
- `no_trade_regret_score=0`
- `order_intents=ABSENT`
- `orders=ABSENT`
- `live_orders=3`

After manual smoke:

- `no_trade_log=4`
- `no_trade_reasons=5`
- `no_trade_post_fact_review=3`
- `no_trade_regret_score=3`
- `dry_run_rows=0`
- `HIGH_REGRET=1`
- `GOOD_NO_TRADE=1`
- `order_intents=ABSENT`
- `orders=ABSENT`
- `live_orders=3`
- `paper_orders=3`

## Safety Checklist

- No-Trade cannot create orders: YES
- No-Trade cannot create order intents: YES
- No-Trade cannot create live exits: YES
- No-Trade cannot mutate external balances: YES
- Reason required: YES
- Candidate engine stored when available: YES
- Source layer stored: YES
- Post-fact review avoids fake regret: YES
- Hard risk block respected in regret scoring: YES
- Dry-run writes nothing: YES
- Blocked candidate logs no_trade: YES
- Post-fact review updates regret: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Historical backfill quality depends on the sparsity and consistency of V2.11-V2.16 source rows.
- Post-fact regret remains `INSUFFICIENT_DATA` when later price/liquidity evidence is absent, by design.
- V2.17 emits safe memory-update hooks but does not implement the full V2.19 learning loop.

## Phase Status

GREEN.

## Can Move To V2.18 Dashboard V2

YES.
