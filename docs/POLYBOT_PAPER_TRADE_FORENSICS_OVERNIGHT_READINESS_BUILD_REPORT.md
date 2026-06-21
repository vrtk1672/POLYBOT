# POLYBOT Paper Trade Forensics + Overnight Readiness Build Report

## Dispatch

- Executor: Codex
- Task mode: CONTROLLED_RUNTIME_FEATURE + READ_ONLY_FORENSICS + SAFE_FIX + OVERNIGHT_OBSERVER_PREP
- Risk: VERY HIGH
- ChatGPT review: REQUIRED

## Summary

Implemented a read-only paper trade forensics layer and a safe overnight observation status/runner. No live, shadow, real-order, paper-order, paper-fill, paper-position, or PnL writer behavior was enabled or loosened.

## Files Created

- `app/services/paper_trade_forensics.py`
- `app/services/overnight_observation_status.py`
- `scripts/run_overnight_observation.py`
- `scripts/run_overnight_observation.ps1`
- `tests/test_paper_trade_forensics.py`
- `tests/test_source_to_neuron_yellow_fixes.py`
- `tests/test_overnight_observation_runner.py`
- `docs/POLYBOT_PAPER_TRADE_FORENSICS_OVERNIGHT_READINESS_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/source_to_neuron/service.py`

## API

- `GET /dashboard/api/v2/paper/trade-forensics`
- `GET /dashboard/api/v2/paper/trade-forensics/{paper_position_id}`
- `GET /dashboard/api/v2/overnight/status`

## DB Migrations

None. Existing Postgres paper, capital, V3 mesh, source, dialogue, and quarantine tables are reused.

## Forensics Behavior

The forensics service traces paper positions through:

`paper_positions -> paper_fills -> paper_orders -> paper_intents -> paper_eligibility_candidates -> risk_decisions -> exit_plans -> paper_position_closes -> paper_trade_ledger -> paper_capital_ledger -> mesh_sessions -> mesh_shared_awareness -> mesh_brain_opinions -> mesh_coordinator_decisions -> brain_dialogue_events -> neural_events`.

Missing links are returned as `MISSING_LINK` objects with exact table and field. Quarantined rows remain visible under `legacy_quarantined` with status `LEGACY_QUARANTINED`.

## Ollama / RSS / NewsAPI

- Ollama generation now tries configured models in `OLLAMA_MODEL_FAST`, `OLLAMA_MODEL_PRIMARY`, `OLLAMA_MODEL_REASONING` order.
- Ollama requests use bounded JSON prompts with `num_predict`, `num_ctx`, `temperature=0`, and `keep_alive=0s`.
- RSS env feed registration remains deterministic/idempotent through `rss_env_<digest>`.
- NewsAPI ingestion remains bounded by `limit_per_source` and persists only source-backed articles returned by the provider.

## Overnight Readiness

Added a safe observer runner that:

- Defaults to 8 hours, samples every 5 minutes.
- Writes logs under `logs/overnight/`.
- Writes final reports under `docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_<timestamp>.md`.
- Refuses start unless preflight is GREEN by default.
- Hard-stops and posts SYSTEM OFF on live/real-order mutation, unsafe paper lineage, active fill-less positions, mock data, repeated provider/API failure, or capital reconciliation RED.

The runner was not started for a full overnight run.

## Runtime Smoke

SYSTEM OFF read-only forensics did not change safety counts. SYSTEM OFF blocked source-to-neuron. A short SYSTEM ON bounded source-to-neuron smoke created source-backed non-trading events and returned SYSTEM OFF after completion.

Smoke result:

- source events created: 6
- event types: `NEWS_DETECTED=2`, `MARKET_REPRICING=1`, `ORDERBOOK_REFRESHED=1`, `SPREAD_CHANGED=1`, `LIQUIDITY_CHANGED=1`
- Ollama: degraded with real `ReadTimeout`; no fake AI context emitted
- trading mutation detected: false
- final system power: OFF

## Safety Counts After Smoke

- `live_orders=0`
- `real_orders_current=1`
- `orders_v2=1`
- `fills_v2=1`
- `canonical_positions=0`
- `paper_intents_total=6`
- `paper_orders_total=9`
- `paper_fills_total=6`
- `paper_positions_total=9`
- `paper_trade_ledger=12`
- `realized_pnl=23.55`
- `unrealized_pnl=0.0`
- `paper_lineage_consistency_status=OK`
- `capital_reconciliation_status=OK`

## Tests

- `python -m py_compile app\services\paper_trade_forensics.py app\services\overnight_observation_status.py app\source_to_neuron\service.py app\api\routes.py scripts\run_overnight_observation.py` passed.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_paper_trade_forensics.py tests/test_source_to_neuron_yellow_fixes.py tests/test_overnight_observation_runner.py -q` -> `16 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v3_source_to_neuron_ingestion_wiring.py -q` -> `8 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_paper_dashboard_truth.py tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q` -> `28 passed, 1 warning`.

## Status

YELLOW.

Forensics, RSS, NewsAPI, overnight readiness, safety tests, and smoke are GREEN. Phase remains YELLOW because real Ollama generation still timed out in runtime smoke and requires operator/provider/model performance action or acceptance of degraded local AI context.
