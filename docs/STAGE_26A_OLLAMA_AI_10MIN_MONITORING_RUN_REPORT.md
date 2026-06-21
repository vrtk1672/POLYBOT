# Stage 26A Ollama AI 10-Minute Monitoring Run Report

## 1. Short Summary

Stage 26A completed the Ollama host diagnostic, direct model benchmarks, Docker-to-Ollama connectivity check, POLYBOT AI config inspection, a source-to-neuron AI smoke, and a safe 10-minute Control Center monitoring run.

Final status: `YELLOW`.

Ollama is healthy and Docker can reach it. The 10-minute `DATA_ONLY_MONITORING` run completed safely with zero orders, fills, or position updates. POLYBOT's AI Context Router still times out on Ollama generation under the current bounded timeout settings, so local AI is reachable but not fully optimized for POLYBOT runtime use yet.

## 2. System RAM / Resource Snapshot

- Total RAM: `31.87 GB`
- Free RAM: `20.74 GB`
- Ollama process: running
- Ollama version: `0.30.6`

## 3. Ollama Host Health

- Host API health: `OK`
- Host endpoint checked: `http://127.0.0.1:11434/api/tags`
- Installed model visible: `qwen3:4b`

## 4. Installed Models

- `qwen3:4b`

No `qwen3:8b` or larger model was installed or tested in this phase.

## 5. Model Benchmark Results

Direct host benchmark results for `qwen3:4b`:

| Test | Seconds | Timed Out | Response Chars |
|---|---:|---|---:|
| quick_health | 5.33 | false | 179 |
| polybot_role | 33.03 | false | 1281 |
| json_summary | 34.99 | false | 1062 |
| no_trade_explanation | 34.09 | false | 1159 |
| market_monitoring_summary | 40.67 | false | 1355 |

Artifacts:

- `run_reports/ollama_ai_diagnostic/ollama_model_benchmarks.json`
- `run_reports/ollama_ai_diagnostic/ollama_model_benchmarks.md`

## 6. Docker-to-Ollama Connectivity

- Docker API to Ollama: `YES`
- Endpoint: `http://host.docker.internal:11434/api/tags`
- Models visible from Docker: `qwen3:4b`
- Docker sees Ollama env names: `YES`
- Secrets printed: `NO`

Artifact:

- `run_reports/ollama_ai_diagnostic/docker_to_ollama_check.md`

## 7. POLYBOT AI Config Inspection

POLYBOT has active Ollama/local AI integration points:

- `app/services/ai_context_router.py`
- `app/source_to_neuron/service.py`
- `app/services/source_status.py`
- `app/control_center/query_service.py`
- `app/api/routes.py`

Answers:

1. POLYBOT uses Ollama through source status and AI Context Router paths.
2. `AIContextRouterService` calls `/api/generate`; `SourceToNeuronIngestionService` invokes the router.
3. Yes, `AIContextRouterService` is the provider router.
4. Yes, provider and total timeouts are configured.
5. Yes, model names are read from env.
6. Yes, Docker API receives the Ollama env names.
7. Yes, AI router attempts are recorded in `ai_context_router_runs`.
8. Yes, Control Center AI shows Ollama timeout/failure truth.
9. Full Monitor Run reads the AI panel; it does not itself trigger new AI generation.
10. Missing: timeout tuning for local `qwen3:4b` runtime generation and possibly an AI queue/backpressure layer.

## 8. AI Optimization Recommendation

Current model routing should remain:

- FAST: `qwen3:4b`
- PRIMARY: `qwen3:4b`
- REASONING: `qwen3:4b`

Recommended after review:

- Increase local provider timeout from current bounded default to at least `60s` for quick/medium Ollama calls.
- Keep total timeout bounded; do not allow unbounded AI waits.
- Keep local AI concurrency at `1`.
- Optionally install and benchmark `qwen3:8b`; do not configure it until it is installed and tested.

## 9. Config Changes Made

None.

No `.env`, Docker, runtime code, tests, or migrations were changed.

## 10. 10-Minute Monitoring Run Setup

- Started through Control Center action API wrapper.
- Actor: `harel`
- Reason: `10 minute local ai monitoring validation`
- Duration: `10` minutes
- Interval: `60` seconds
- Mode: `DATA_ONLY`
- Safety mode: `DATA_ONLY_MONITORING`
- Execution enabled: `false`

## 11. 10-Minute Monitoring Run Result

- Run ID: `full_monitor_run_8e800412951b4f09b62a73feb367476e`
- Status: `COMPLETED`
- Started: `2026-06-10T21:59:52.651714+00:00`
- Ended: `2026-06-10T22:09:54.139141+00:00`
- Elapsed: `601.52s`
- Cycles completed: `11`
- Markets checked: `99`
- Events seen: `550`
- Opportunities found: `220`
- No-trades logged by run counter: `0`
- Paper orders/fills/positions updated by run: `0 / 0 / 0`

Post-run DB counts matched baseline:

- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `orders_v2=1`
- `fills_v2=1`
- `positions=0`

## 12. AI Usage During Run

The monitoring run completed the read-only `ai` module against the Control Center AI panel.

Separate source-to-neuron smoke result:

- `ollama_local_model`: `ACTIVE`, tag check succeeded.
- `ai_context_router`: latest run `source_to_neuron_6a3871f17233473a99f1b8b47e84f7a6`
- selected provider: none
- status: `AI_CONTEXT_UNAVAILABLE`
- final reason: `OLLAMA_TIMEOUT`
- cloud fallback: disabled in smoke

Interpretation: local AI is reachable, but POLYBOT's generation timeout is too tight for current `qwen3:4b` prompt latency.

## 13. Run Report Link

Control Center reported:

- `run_reports/control_center_monitor_runs/full_monitor_run_8e800412951b4f09b62a73feb367476e.md`
- `run_reports/control_center_monitor_runs/full_monitor_run_8e800412951b4f09b62a73feb367476e.json`

Copied host evidence:

- `run_reports/ollama_ai_diagnostic/raw/full_monitor_run_8e800412951b4f09b62a73feb367476e.md`
- `run_reports/ollama_ai_diagnostic/raw/full_monitor_run_8e800412951b4f09b62a73feb367476e.json`

## 14. Control Center / UI Verification

API verification was completed through the real Control Center action and status endpoints from inside the API container because host-to-container port calls returned empty replies during this session.

Playwright/browser screenshot verification was not run. No screenshots were created.

Host port issue observed:

- `curl.exe http://127.0.0.1:8000/health` returned empty reply from server.
- API container-local `http://127.0.0.1:8000/health` returned healthy JSON.

## 15. Tests Run and Exact Results

- `.\.venv\Scripts\python.exe -m pytest tests/test_control_center_actions.py tests/test_control_center_full_monitor_run.py -q`
  - Result: `25 passed in 6.31s`
- `.\.venv\Scripts\python.exe -m pytest @files -q` where `files = tests/test_control_center_*.py`
  - Result: `49 passed in 10.26s`
- Attempted wildcard command:
  - `.\.venv\Scripts\python.exe -m pytest tests/test_control_center_*.py -q`
  - Result: `no tests ran`; PowerShell/Pytest did not expand the wildcard in that form.

## 16. Safety Checklist

- Ollama host healthy: `YES`
- Docker can reach Ollama: `YES`
- Model benchmark completed: `YES`
- No secrets printed: `YES`
- No live trading enabled: `YES`
- No paper execution activated: `YES`
- No orders created by run: `YES`
- No fills created by run: `YES`
- No positions created/updated by run: `YES`
- No fake PnL shown: `YES`
- State Governor not bypassed: `YES`
- KILL protection preserved: `YES`
- 10-minute run stayed DATA_ONLY: `YES`
- Run report created: `YES`
- AI failures reported honestly: `YES`
- Tests passed: `YES`

## 17. Remaining Issues

- POLYBOT AI Context Router times out on Ollama generation with current timeout settings.
- Qwen output quality needs prompt tuning; direct benchmark outputs included reasoning-style preambles.
- Host-to-container API port returned empty replies, while container-local API worked.
- Playwright UI verification and screenshots were not completed.
- Runtime logs showed unrelated `Object of type UUID is not JSON serializable` errors in a background stage during the monitoring window; the FMR itself completed with no recorded errors.

## 18. Recommended Next Step

Run a reviewed Stage 26B timeout-tuning pass:

- set bounded local AI provider timeout to a value that matches measured `qwen3:4b` latency,
- smoke `AIContextRouterService` until Ollama succeeds without cloud fallback,
- then optionally benchmark `qwen3:8b`.

## 19. Phase Status: YELLOW

Ollama and the safe monitoring run passed, but POLYBOT local AI generation is not yet fully usable because runtime router calls still time out.

## 20. Can Continue: YES

Safe to continue to reviewed timeout tuning or optional model expansion. Do not proceed to PAPER, SHADOW_LIVE, SMALL_LIVE, ATTACK_MODE, or any execution activation from this phase.
