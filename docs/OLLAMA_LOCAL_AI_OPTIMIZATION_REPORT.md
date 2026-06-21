# Ollama Local AI Optimization Report

## Summary

Ollama is healthy on the Windows host and reachable from the Docker API container. The only installed model is `qwen3:4b`, and direct host benchmarks completed without timeouts.

POLYBOT should keep all configured model roles on `qwen3:4b` until `qwen3:8b` is installed and benchmarked. No model-name change was made.

## Current Configuration

- `OLLAMA_BASE_URL=http://host.docker.internal:11434`
- `OLLAMA_MODEL_FAST=qwen3:4b`
- `OLLAMA_MODEL_PRIMARY=qwen3:4b`
- `OLLAMA_MODEL_REASONING=qwen3:4b`
- Docker compose passes the Ollama variables into the API container.
- `.env.example` still defaults `OLLAMA_BASE_URL` to `http://localhost:11434`; Docker runtime correctly overrides through `.env`.

## Host and Docker Health

- Host RAM: `31.87 GB` total, `20.74 GB` free at diagnostic time.
- Ollama process: running.
- Ollama version: `0.30.6`.
- Installed models: `qwen3:4b`.
- Host `/api/tags`: healthy.
- Docker API to `host.docker.internal:11434/api/tags`: healthy.

## Benchmark Result

`qwen3:4b` direct host `/api/generate` tests:

- `quick_health`: `5.33s`, no timeout.
- `polybot_role`: `33.03s`, no timeout.
- `json_summary`: `34.99s`, no timeout.
- `no_trade_explanation`: `34.09s`, no timeout.
- `market_monitoring_summary`: `40.67s`, no timeout.

Quality note: answers were usable text, but Qwen produced verbose reasoning-style preambles even with `think=false`. Prompting should be tightened before using it for operator-facing summaries.

## POLYBOT AI Integration Finding

POLYBOT uses Ollama through:

- `app/services/ai_context_router.py`
- `app/source_to_neuron/service.py`
- Control Center AI readout through `ControlCenterQueryService().ai()`

The AI Context Router reads model names from env and uses bounded timeouts:

- provider timeout default: `AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS`, default `15s`
- total timeout default: `AI_CONTEXT_TOTAL_TIMEOUT_SECONDS`, default `45s`
- keep-alive: `AI_CONTEXT_OLLAMA_KEEP_ALIVE`, default `5m`

During the Stage 26A smoke, `ollama_local_model` tag discovery was `ACTIVE`, but the AI Context Router generation path timed out:

- latest local run: `source_to_neuron_6a3871f17233473a99f1b8b47e84f7a6`
- selected provider: none
- status: `AI_CONTEXT_UNAVAILABLE`
- final reason: `OLLAMA_TIMEOUT`
- cloud fallback: disabled for the smoke

This is consistent with the direct benchmark timings: medium `qwen3:4b` prompts take roughly `33-41s`, while POLYBOT currently gives a provider roughly `10-15s`.

## Recommendation

Keep model routing:

- FAST: `qwen3:4b`
- PRIMARY: `qwen3:4b`
- REASONING: `qwen3:4b`

Recommended next timeout tuning, after ChatGPT/operator approval:

- quick local AI tasks: `60s`
- medium local AI tasks: `180s`
- reasoning tasks: cap at `300s`
- total router timeout: long enough to cover the selected local tier, but never unbounded

Recommended concurrency:

- local AI concurrency: `1` until a queue/backpressure layer exists
- do not run parallel local generations on this host by default

Recommended future test:

- optionally pull and benchmark `qwen3:8b`
- if it completes medium prompts acceptably, use `qwen3:4b` for FAST and `qwen3:8b` for PRIMARY/REASONING
- do not configure uninstalled models

## Config Changes Made

None.

Reason: only `qwen3:4b` is installed and already configured. Timeout changes are recommended but were not applied in this diagnostic phase because the mission only explicitly allowed safe model-name updates.

## Rollback

No rollback required. No runtime code, migrations, or `.env` values were changed.

## Stage 26B Update

Stage 26B implemented the approved timeout tuning and prompt cleanup.

Result: GREEN.

What changed:

- Router provider timeout default raised from `15s` to `90s`.
- Router total timeout default raised from `45s` to `120s`.
- Added bounded Ollama role timeouts:
  - FAST: `60s`
  - PRIMARY: `90s`
  - REASONING: `120s`
- Added global fallback `OLLAMA_TIMEOUT_SECONDS=90`.
- Routed per-request timeout values through `SourceHttpClient.post_json()` so Source-to-Neuron no longer forces the old `10s` HTTP client timeout.
- Added `think: false` to Ollama requests.
- Tightened prompt instructions and added output cleanup for visible reasoning preambles/JSON extraction.

Validation:

- Stage 26B AI Router smoke completed through `ollama` using `qwen3:4b`.
- Router status: `OK`.
- Final reason: `AI_CONTEXT_UPDATED`.
- Latency: `6069 ms`.
- No new `OLLAMA_TIMEOUT` in the successful post-fix smoke.
- Safe monitoring run completed in `DATA_ONLY_MONITORING` with zero orders, zero fills, and zero position updates.

Detailed report: `docs/STAGE_26B_OLLAMA_ROUTER_TIMEOUT_TUNING_REPORT.md`.
