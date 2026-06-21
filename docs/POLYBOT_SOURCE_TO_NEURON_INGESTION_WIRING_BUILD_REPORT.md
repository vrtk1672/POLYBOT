# POLYBOT V3.9 Source-to-Neuron Ingestion Wiring Build Report

## Current Reality Found

- V3.8 already proved a real CLOB orderbook path through `ORDERBOOK_REFRESHED`, mesh sessions, shared awareness, multi-brain opinions, mesh coordinator decisions, and dialogue.
- News tables existed but were empty before the V3.9 smoke: `news_sources=0`, `news_raw_events=0`, `news_normalized_events=0`.
- Orderbook truth already existed in `orderbook_snapshots`.
- Whale table existed with `whale_events=0`.
- AI request/response/cache tables existed.
- Neural bus, mesh sessions, shared awareness, multi-brain consumption, mesh coordinator, capital brain, position awareness, and brain dialogue were already wired.

## Implementation

Created `app/source_to_neuron/SourceToNeuronIngestionService` with a bounded `run_once()` worker behind SYSTEM ON. It wires configured sources to their organs and publishes source-backed neural events only after real provider/source records exist.

Added API routes:

- `GET /dashboard/api/v2/source-to-neuron-flow`
- `POST /source-to-neuron/run`

## Source-to-Neuron Mapping

| Source | Neuron / Brain | Event | Storage Path | Status |
| --- | --- | --- | --- | --- |
| RSS | News Neuron | `NEWS_DETECTED` | `news_sources`, `news_raw_events`, `news_normalized_events`, `neural_events` | Wired |
| NewsAPI | News Neuron | `NEWS_DETECTED` | `news_sources`, `news_raw_events`, `news_normalized_events`, `neural_events` | Wired |
| Gamma public market data | Market Neuron | `MARKET_REPRICING` | `source_status`, `neural_events` | Wired |
| CLOB book | Orderbook Neuron | `ORDERBOOK_REFRESHED` | `orderbook_snapshots`, `neural_events` | Wired |
| CLOB spread/depth | Liquidity Neuron | `SPREAD_CHANGED`, `LIQUIDITY_CHANGED` | `orderbook_snapshots`, `neural_events` | Wired |
| CLOB trades/activity | Whale Neuron | `WHALE_DETECTED` | `whale_events`, `neural_events` | Wired |
| Ollama local context | AI Context Brain | `AI_CONTEXT_UPDATED` | `ai_requests`, `ai_responses`, `neural_events` | Wired, degraded in runtime smoke |
| OpenAI / Anthropic | AI Context Brain | None by default | Provider status | Auth-only |
| Paper PnL | PnL Neuron | `PNL_CHANGED` | `paper_trade_ledger`, `neural_events` | Wired |

## Files Created

- `app/source_to_neuron/__init__.py`
- `app/source_to_neuron/service.py`
- `tests/test_v3_source_to_neuron_ingestion_wiring.py`
- `docs/POLYBOT_SOURCE_TO_NEURON_INGESTION_WIRING.md`
- `docs/POLYBOT_SOURCE_TO_NEURON_INGESTION_WIRING_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`

## DB Migration

No migration was required. Existing source, neuron, event, mesh, awareness, brain, coordinator, dialogue, orderbook, whale, AI, and paper truth tables were reused.

## Runtime Smoke

SYSTEM OFF:

- `POST /source-to-neuron/run` returned `SYSTEM_POWER_OFF`.
- Events created: `0`.

SYSTEM ON bounded pass:

- Events created: `8`.
- Event counts: `NEWS_DETECTED=2`, `MARKET_REPRICING=1`, `ORDERBOOK_REFRESHED=1`, `SPREAD_CHANGED=1`, `LIQUIDITY_CHANGED=1`, `WHALE_DETECTED=1`, `PNL_CHANGED=1`.
- Sessions updated: `8`.
- Awareness source updates: `102`.
- Brain opinions created: `26`.
- Mesh coordinator decisions created: `5`.
- Dashboard returned `mock_data=false`.
- Dialogue materialized News, Orderbook, Liquidity, Whale, and PnL messages.
- SYSTEM was returned to OFF.

Final source-status truth pass:

- Ran a second bounded pass with `include_ollama_generation=false`.
- Events created: `6`.
- Event counts: `NEWS_DETECTED=2`, `MARKET_REPRICING=1`, `ORDERBOOK_REFRESHED=1`, `SPREAD_CHANGED=1`, `LIQUIDITY_CHANGED=1`.
- V3.9 source-status rows were written for `rss_source_to_neuron` and `newsapi_source_to_neuron`.
- Trading mutation detected: `false`.
- SYSTEM was returned to OFF.

Ollama:

- Model discovery was active.
- Tiny local generation timed out and was reported as degraded.
- No fake `AI_CONTEXT_UPDATED` was created.

## Before / After Counts

| Table / Metric | Before | After |
| --- | ---: | ---: |
| `neural_events` | 12 | 26 |
| `mesh_sessions` | 15 | 21 |
| `mesh_shared_awareness` | 15 | 21 |
| `mesh_brain_opinions` | 41 | 71 |
| `mesh_coordinator_decisions` | 5 | 11 |
| `brain_dialogue_events` | 55599 | 55804 |
| `news_sources` | 0 | 2 |
| `news_raw_events` | 0 | 4 |
| `news_normalized_events` | 0 | 4 |
| `orderbook_snapshots` | 25881 | 25883 |
| `whale_events` | 0 | 1 |
| `ai_requests` | 2 | 2 |
| `ai_responses` | 2 | 2 |

## Safety Counts

Unchanged after smoke:

- `live_orders=0`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `paper_intents=6`
- `paper_capital_ledger=1`
- `risk_decisions=10332`
- `exit_plans=10332`
- legacy `coordinator_decisions=10636`
- `brain_outputs=10672`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- paper account current/available/locked/exposure remained `1000/1000/0/0`

## Tests Run

- `python -m py_compile app\source_to_neuron\service.py app\api\routes.py` -> passed.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v3_source_to_neuron_ingestion_wiring.py -q` -> `8 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v2_21_source_status.py tests/test_v3_neural_event_bus.py -q` -> `15 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v3_mesh_sessions_foundation.py -q` -> `11 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v3_shared_awareness_layer.py tests/test_v3_multi_brain_consumption_layer.py tests/test_v3_mesh_coordinator_evolution.py -q` -> `38 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v3_capital_brain_upstream.py tests/test_v3_position_awareness.py -q` -> `33 passed, 1 warning`.
- `docker-compose run --rm --no-deps test python -m pytest tests/test_v3_intelligence_source_readiness.py -q` -> `11 passed, 1 warning`.

Test infrastructure note: the test Postgres container initially exhausted shared lock memory during schema teardown. `max_locks_per_transaction` was raised to `512` for the test container and leftover isolated test schemas were cleaned one schema per transaction. Reruns then passed.

## Source-Backed Flow Traces

- RSS -> News Neuron -> `NEWS_DETECTED` -> neural event -> dialogue.
- NewsAPI -> News Neuron -> `NEWS_DETECTED` -> market-linked neural event -> dialogue.
- Gamma -> Market Neuron -> `MARKET_REPRICING` -> market mesh session.
- CLOB `/book` -> Orderbook Neuron -> `ORDERBOOK_REFRESHED` -> orderbook awareness.
- CLOB spread/depth -> Liquidity Neuron -> `SPREAD_CHANGED`, `LIQUIDITY_CHANGED` -> liquidity awareness.
- CLOB activity -> Whale Neuron -> `WHALE_DETECTED` when threshold was met.
- Ollama -> AI Context Brain remained degraded on generation timeout; no fake AI context was emitted.

## Providers Still Missing

- CryptoPanic
- X/Twitter
- Reddit
- Telegram
- Discord

## Remaining Risks

- Ollama generation can time out with the currently configured local model; model/prompt timeout policy should be tuned before relying on runtime AI context.
- NewsAPI source status now has V3.9-specific rows, while the legacy `news_provider` status remains intentionally disabled by older V2.21 validation logic.
- The worker is bounded and manual/API-triggered; scheduler integration is intentionally not enabled in this phase.

## Phase Status

YELLOW.

The configured working sources are wired and real source-backed events were created. Dashboard truth, dialogue, sessions, awareness, multi-brain, and coordinator effects are visible. No trading mutation occurred and tests passed. The phase is YELLOW because real Ollama context generation timed out during smoke, so AI context runtime proof is partial.

## Next Recommended Phase

Full News Neuron / Whale Neuron / AI Context expansion can proceed after deciding whether to tune Ollama generation timeout/model routing or keep local AI context as validation/auth-only until the model is faster.
