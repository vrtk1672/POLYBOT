# V2.8 Build Report

## Summary

V2.8 Market / Orderbook / Liquidity / Time / Fees Neurons implemented as a non-trading technical truth layer.

The implementation persists five technical signal types, builds combined `TechnicalMarketTruth`, publishes V2.8 event types, exposes `/market-neuron/*` APIs, and adds dashboard technical truth fields.

## Files Created

- `app/market_neuron/*`
- `app/repositories/market_technical_signal_repository.py`
- `app/repositories/orderbook_signal_repository.py`
- `app/repositories/liquidity_signal_repository.py`
- `app/repositories/time_signal_repository.py`
- `app/repositories/fee_reward_signal_repository.py`
- `app/api/market_neuron_routes.py`
- `app/db/migrations/0046_v2_8_market_technical_neurons.sql`
- `tests/test_v2_8_*.py`
- `docs/V2_8_MARKET_TECHNICAL_NEURONS.md`

## Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration

`0046_v2_8_market_technical_neurons.sql`

## API Routes Added

- `GET /market-neuron/health`
- `GET /market-neuron/market/{market_id}`
- `GET /market-neuron/signals/recent`
- `GET /market-neuron/blocked/recent`
- `GET /market-neuron/top`
- `POST /market-neuron/analyze`

## Dashboard Changes

Added real DB-backed `market_technical` overview fields. Missing data is reported as empty, disabled, or error truth.

## Events Published

- `market.technical_signal.created`
- `orderbook.signal.created`
- `liquidity.signal.created`
- `time.signal.created`
- `fee_reward.signal.created`
- `market.technical_truth.created`
- `market.technical_truth.blocked`

## Tests Added

- `tests/test_v2_8_market_analyzer.py`
- `tests/test_v2_8_orderbook_analyzer.py`
- `tests/test_v2_8_liquidity_analyzer.py`
- `tests/test_v2_8_time_analyzer.py`
- `tests/test_v2_8_fee_reward_analyzer.py`
- `tests/test_v2_8_technical_signal_builder.py`
- `tests/test_v2_8_market_neuron_service.py`
- `tests/test_v2_8_market_neuron_api.py`
- `tests/test_v2_8_market_neuron_safety_guards.py`

## Test Results

Targeted V2.8 no-DB result:

`python -m uv run pytest (Get-ChildItem tests/test_v2_8_*.py).FullName -q`

Result: `11 passed, 5 skipped`

Skipped tests require `POLYBOT_DATABASE_URL`.

DB-backed V2.8 subset:

`$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_8_market_neuron_service.py tests/test_v2_8_market_neuron_api.py tests/test_v2_8_market_neuron_safety_guards.py -q`

Result: `5 passed`

Full suite no-DB/default environment:

`python -m uv run pytest`

Result: `212 passed, 357 skipped`

## Runtime Verification

Runtime migration applied:

`powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`

Result: `Applied migrations: 0046_v2_8_market_technical_neurons.sql`

Runtime startup was verified by launching the canonical `scripts/start_runtime.ps1` in the background, then checking endpoints on `127.0.0.1:8000`.

Verified:

- `/healthz`
- `/runtime/state`
- `/runtime/health`
- `/events/lag`
- `/data/coverage`
- `/whales`
- `/market-neuron/health`
- `/market-neuron/signals/recent`
- `/market-neuron/blocked/recent`
- `/market-neuron/top`

Manual smoke:

- `POST /market-neuron/analyze` for market `2169995` with safe manual orderbook payload.
- Rows created in all five V2.8 signal tables.
- `market.technical_truth.created` and component events published.
- Runtime stayed `DATA_ONLY`.
- Live permissions stayed false.
- No order/order-intent/exit tables were created by V2.8.

## Safety Checklist

- No order path added.
- No order-intent path added.
- No exit path added.
- Missing bid/ask/depth blocks technical readiness.
- Missing exit liquidity blocks entry readiness.
- Wide spread blocks or penalizes.
- Low depth blocks or penalizes.
- Fees reduce net edge.
- Dashboard uses real DB-backed values only.
- State Governor collection permission gates analysis jobs.

## Remaining Risks

- External orderbook ingestion remains dependent on V2.2 data availability; V2.8 handles missing data honestly.

## Recommendation

V2.8 is GREEN. Move to V2.9 only after accepting this build report.
