# V2.11 Build Report - Opportunity Cortex

## Summary

V2.11 implements a scoring-only Opportunity Cortex. It combines V2.10 Context/Capital outputs, V2.9 memory, V2.8 technical truth, and neuron signals into explainable, reproducible opportunity scores with risk flags, no-trade reasons, and candidate engine suggestions.

No strategy routing, order intents, orders, exits, live trading, risk approval, or balance mutation was added.

## Files Created

- `app/opportunity/__init__.py`
- `app/opportunity/contracts.py`
- `app/opportunity/opportunity_errors.py`
- `app/opportunity/signal_input_builder.py`
- `app/opportunity/opportunity_scorer.py`
- `app/opportunity/risk_flag_builder.py`
- `app/opportunity/candidate_engine_suggester.py`
- `app/opportunity/no_trade_reason_builder.py`
- `app/opportunity/service.py`
- `app/repositories/opportunity_run_repository.py`
- `app/repositories/opportunity_score_repository.py`
- `app/repositories/opportunity_signal_input_repository.py`
- `app/repositories/opportunity_risk_flag_repository.py`
- `app/api/opportunity_routes.py`
- `app/db/migrations/0049_v2_11_opportunity_cortex.sql`
- `tests/test_v2_11_signal_input_builder.py`
- `tests/test_v2_11_opportunity_scorer.py`
- `tests/test_v2_11_risk_flag_builder.py`
- `tests/test_v2_11_candidate_engine_suggester.py`
- `tests/test_v2_11_no_trade_reason_builder.py`
- `tests/test_v2_11_opportunity_service.py`
- `tests/test_v2_11_opportunity_api.py`
- `tests/test_v2_11_opportunity_safety_guards.py`
- `docs/V2_11_OPPORTUNITY_CORTEX.md`
- `docs/V2_11_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

- `app/db/migrations/0049_v2_11_opportunity_cortex.sql`

Tables:

- `opportunity_runs`
- `opportunity_scores_v2`
- `opportunity_signal_inputs`
- `opportunity_risk_flags`

Runtime migration result:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- Result: applied `0049_v2_11_opportunity_cortex.sql`
- Verified tables exist and `schema_migrations` contains the migration.

## API Routes

- `GET /opportunities/health`
- `GET /opportunities/market/{market_id}`
- `GET /opportunities/recent`
- `GET /opportunities/top`
- `GET /opportunities/blocked/recent`
- `GET /opportunities/risk-flags/recent`
- `GET /opportunities/run/{run_id}`
- `POST /opportunities/score`

## Dashboard Changes

Added DB-backed `opportunities` overview:

- opportunity_status
- runs_today
- scores_today
- blocked_today
- watchlist_today
- high_score_today
- latest_score_ts
- top_opportunities
- recent_blocked_opportunities
- common_risk_flags
- average_score
- average_confidence
- insufficient_data_count
- top_candidate_engines
- errors

Dashboard smoke returned real DB-backed opportunity rows after manual scoring.

## Events Published

- `opportunity.run.started`
- `opportunity.score.created`
- `opportunity.blocked`
- `opportunity.watchlist.created`
- `opportunity.high_score.created`
- `opportunity.insufficient_data`

## Tests Added

- Signal input builder tests
- Opportunity scorer tests
- Risk flag tests
- Candidate engine suggestion tests
- No-trade reason tests
- Service persistence/event tests
- API tests
- Safety guard tests

## Tests Run

Targeted V2.11:

- `python -m uv run pytest tests/test_v2_11_opportunity_scorer.py tests/test_v2_11_risk_flag_builder.py tests/test_v2_11_candidate_engine_suggester.py tests/test_v2_11_no_trade_reason_builder.py -q`
  - Result: `9 passed in 5.96s`
- `python -m uv run pytest tests/test_v2_11_signal_input_builder.py -q`
  - Result: `2 passed in 171.39s`
- `python -m uv run pytest tests/test_v2_11_opportunity_service.py -q`
  - Result: `3 passed in 675.67s`
- `python -m uv run pytest tests/test_v2_11_opportunity_api.py -q`
  - Result: `1 passed in 208.19s`
- `python -m uv run pytest tests/test_v2_11_opportunity_safety_guards.py -q`
  - Result: `2 passed in 355.26s`

V2.11 total: `17 passed`.

Regressions:

- V2.10 unit/input tests: `15 passed in 23.82s`
- V2.10 service: `3 passed in 514.15s`
- V2.10 API/safety: `4 passed in 651.20s`
- V2.9 unit builders: `17 passed in 3.94s`
- V2.9 service: `3 passed in 410.36s`
- V2.9 API/safety: `4 passed in 664.46s`
- V2.8 unit analyzers/builders: `11 passed in 5.53s`
- V2.8 service/API/safety: `5 passed in 731.21s`
- V2.7 non-DB: `16 passed, 3 skipped in 37.32s`
- V2.6 non-DB: `9 passed, 11 skipped in 18.04s`
- V2.5 non-DB: `18 passed, 6 skipped in 7.84s`
- V2.4 non-DB: `18 passed, 8 skipped in 18.04s`
- Runtime non-DB: `8 passed, 19 skipped in 24.80s`

Full suite:

- `python -m uv run pytest -q`
  - Result: `254 passed, 378 skipped in 51.88s`

Note: DB-backed tests are migration-heavy on this workstation and broad wildcard batches timed out. Split verification was used. A V2.7 DB-backed wildcard run had one shared-DB duplicate-key failure in `test_performance_history_handles_insufficient_data` because that legacy test writes fixed `whale_performance_id='p1'`; the same V2.7 suite passed without shared DB env.

## Runtime Verification

Docker/Postgres:

- `polybot_phase1_pg` running on `127.0.0.1:55432`.
- TCP `55432` reachable.
- Migration applied and verified.

Runtime:

- Canonical `scripts\start_runtime.ps1` remains blocked locally by Windows Application Control when it invokes `uv run polybot`, as documented in V2.10.
- Direct Python runtime startup used the same verified environment:
  - `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
  - `PHASE1_PERSISTENCE_ENABLED=true`
  - `PHASE1_AUTO_MIGRATE=false`
  - `POLYBOT_RUNTIME_MODE=paper_safe`
  - `POLYBOT_EXECUTION_BACKEND=paper`
  - `LIVE_TRADING_ENABLED=false`
  - `LIVE_KILL_SWITCH=true`
- Runtime log:
  - `startup_complete host=127.0.0.1 port=8000`
  - `v2_runtime_startup status=OK current_mode=DATA_ONLY`
  - `live_enabled=False`
  - `live_kill_switch=True`

Endpoint smoke:

- `/healthz`: OK
- `/runtime/state`: OK, `DATA_ONLY`, live/order permissions false
- `/runtime/health`: OK
- `/events/lag`: OK
- `/data/coverage`: OK
- `/market-neuron/health`: OK
- `/market-memory/health`: OK
- `/brains/health`: OK
- `/opportunities/health`: OK
- `/opportunities/recent`: OK
- `/opportunities/top`: OK
- `/opportunities/blocked/recent`: OK
- `/opportunities/risk-flags/recent`: OK

## Manual Smoke

Market used: `2169995`.

- `POST /opportunities/score` with `dry_run=true`: returned score; opportunity table counts stayed at zero.
- `POST /opportunities/score` with `dry_run=false`: persisted a `STRONG` score:
  - `opportunity_score=0.7196512`
  - `score_band=STRONG`
  - candidate engines: `STRIKE`, `SAFE`, `CONVEX`, `HUNT`
  - explanation states candidate engines are suggestions only.
- Additional blocked smoke with bad orderbook/liquidity persisted:
  - `score_band=BLOCKED`
  - risk flags: `missing_bid_ask`, `low_depth`, `poor_exit_quality`, `missing_exit_liquidity`
  - candidate engines: `NO_TRADE`

## DB Row Verification

Before smoke:

- `opportunity_runs`: `0`
- `opportunity_scores_v2`: `0`
- `opportunity_signal_inputs`: `0`
- `opportunity_risk_flags`: `0`

After dry-run:

- all four counts stayed `0`

After write smoke:

- `opportunity_runs`: `2`
- `opportunity_scores_v2`: `2`
- `opportunity_signal_inputs`: `40`
- `opportunity_risk_flags`: `5`

Events:

- `opportunity.run.started`: `2`
- `opportunity.score.created`: `2`
- `opportunity.blocked`: `1`
- `opportunity.high_score.created`: `1`
- `opportunity.insufficient_data`: `1`

Trading/balance tables:

- `paper_orders`: unchanged at `3`
- `paper_positions`: unchanged at `3`
- `live_orders`: unchanged at `3`
- `orders`: table absent
- `order_intents`: table absent
- `exit_intents`: table absent

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Opportunity Cortex cannot create orders: YES
- Opportunity Cortex cannot create order intents: YES
- Opportunity Cortex cannot create exits: YES
- Opportunity Cortex cannot mutate balances: YES
- High score cannot bypass hard risk flags: YES
- Bad liquidity can block opportunity: YES
- Missing bid/ask/depth can block opportunity: YES
- Missing exit liquidity can block opportunity: YES
- Capital not allowed can block opportunity: YES
- AI context cannot override risk: YES
- Missing data becomes insufficient_data: YES
- Score is explainable: YES
- Score is reproducible: YES
- Candidate engines are suggestions only: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- DB-backed regression tests remain slow because each isolated schema runs migrations.
- One V2.7 shared-DB test uses a fixed primary business key and can collide with prior DB rows; non-DB isolated regression passed.
- Opportunity weights are deterministic and documented but not yet outcome-calibrated.
- Sparse historical inputs can still produce insufficient-data outputs honestly.

## Phase Status

GREEN.

Can move to V2.12 Strategy Router + Engines: YES.
