# Stage 26B Ollama Router Timeout Tuning Report

## Status

GREEN.

Stage 26B tuned POLYBOT's local Ollama routing path so `qwen3:4b` can complete through the production AI Context Router instead of failing on the short router/client timeout path.

## Dispatch Classification

- Executor: Codex
- Task mode: `CONTROLLED_AI_INTEGRATION_FIX`
- Risk level: MEDIUM
- Codex review: required
- ChatGPT review: required
- Safety posture: no trading activation, no execution changes, no Governor bypass

## Context

Stage 26A showed that direct Ollama calls to `qwen3:4b` completed, but POLYBOT's AI Context Router failed with `OLLAMA_TIMEOUT`. The direct benchmark showed medium prompts around `33-41s`, while the router path had tighter effective timeouts.

Stage 26B found two timeout layers:

- `AIContextRouter` provider/total timeout defaults.
- `HttpxSourceClient.post_json()` default `10s` timeout when Source-to-Neuron injected the HTTP client into the router.

## Changes

- Added bounded Ollama timeout configuration:
  - `OLLAMA_TIMEOUT_SECONDS=90`
  - `OLLAMA_TIMEOUT_FAST_SECONDS=60`
  - `OLLAMA_TIMEOUT_PRIMARY_SECONDS=90`
  - `OLLAMA_TIMEOUT_REASONING_SECONDS=120`
- Raised bounded router defaults:
  - `AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS=90`
  - `AI_CONTEXT_TOTAL_TIMEOUT_SECONDS=120`
- Capped timeout values at `120s`.
- Routed per-model Ollama timeout values into `/api/generate` calls.
- Allowed `SourceHttpClient.post_json()` and `HttpxSourceClient.post_json()` to accept per-request `timeout_seconds`.
- Added `think: false` to the Ollama payload.
- Tightened the bounded prompt to require compact final JSON only and forbid trades, orders, fills, positions, fake opportunities, and fake PnL.
- Added cleanup for visible reasoning preambles and JSON extraction before storing/parsing operator AI output.
- Added tests for timeout defaults, env overrides, bounding, prompt cleanup, Ollama payload shape, and Source-to-Neuron timeout propagation.

## Validation

### AI Router Smoke

- Artifact: `run_reports/ollama_ai_diagnostic/stage26b_ai_router_smoke.md`
- Source status: `OK`
- Router status: `OK`
- Selected provider: `ollama`
- Final reason: `AI_CONTEXT_UPDATED`
- Latency: `6069 ms`
- Provider latency: `6054 ms`
- Model: `qwen3:4b`
- Errors: none

Historical timeout counters remain in the dashboard because prior runs are retained. The Stage 26B post-fix smoke itself completed without a new `OLLAMA_TIMEOUT`.

### Monitoring Run

- Artifact: `run_reports/ollama_ai_diagnostic/stage26b_monitoring_run_summary.md`
- Run id: `full_monitor_run_eb417cf47a9a4f57b5abe3b19352f369`
- Status: `COMPLETED`
- Mode: `DATA_ONLY_MONITORING`
- Duration: `3 minutes`
- Cycles completed: `4`
- Errors: none
- Execution enabled: `false`
- Orders/fills/positions created by run: `0/0/0`

Canonical count check after the run:

- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `orders_v2=1`
- `fills_v2=1`
- `positions=0`

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_ai_context_router.py -q`
  - Result: `5 passed, 16 skipped`
- `.venv\Scripts\python.exe -m pytest tests/test_v2_3_local_ai_worker.py tests/test_v2_3_ai_model_router.py -q`
  - Result: `7 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_actions.py tests/test_control_center_full_monitor_run.py -q`
  - Result: `25 passed`
- `.venv\Scripts\python.exe -m pytest @<control-center-test-file-list> -q`
  - Result: `49 passed`
- `.venv\Scripts\python.exe -m py_compile app/services/ai_context_router.py app/source_to_neuron/service.py`
  - Result: passed
- `docker compose build api`
  - Result: passed
- `docker compose build test`
  - Result: passed
- `docker compose run --rm test python -m pytest tests/test_ai_context_router.py -q`
  - Result: `21 passed, 1 warning`
- Host endpoint sanity:
  - `/health`: HTTP `200`
  - `/control-center`: HTTP `200`

## Migrations

None.

## Rollback

Revert the Stage 26B changes in:

- `app/services/ai_context_router.py`
- `app/source_to_neuron/service.py`
- `.env.example`
- `docker-compose.yml`
- `tests/test_ai_context_router.py`

Then rebuild the Docker services:

```powershell
docker compose build api
docker compose build test
docker compose up -d api
```

## Risks

- Local AI responses can still be slow under host load; bounded timeouts prevent indefinite hangs.
- Historical AI timeout counts are cumulative and will continue to display old failures unless the dashboard adds a recent-window metric.
- `qwen3:4b` may still emit reasoning-like text despite `think: false`; cleanup now strips common visible preambles and extracts the first JSON object.

## Definition of Done

- POLYBOT AI Context Router completes through local Ollama without `OLLAMA_TIMEOUT`: complete.
- Timeout tuning is bounded and configurable: complete.
- Prompt/output cleanup prevents reasoning preambles from polluting parsed JSON: complete.
- Safe monitoring run completes with no execution artifacts: complete.
- Targeted tests and Docker tests pass: complete.
- Documentation and run artifacts written: complete.

Safe to proceed: YES, for continued DATA_ONLY/local AI monitoring. Not approval for live trading.
