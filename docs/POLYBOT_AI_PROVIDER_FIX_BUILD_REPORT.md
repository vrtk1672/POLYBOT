# POLYBOT AI Provider Fix Build Report

Generated: 2026-06-02T07:05Z
Executor: Codex
Task mode: DEEP_DIAGNOSTIC + SAFE_FIX_IF_CONFIRMED
Risk: HIGH
ChatGPT review: REQUIRED

## Summary

Root causes were found for the reported provider issues and the 4h observation concern.

- The 4h observation run completed GREEN; it did not fail.
- Ollama timeout was caused by cold/warmup latency, wrong container-local localhost first hop, forced `keep_alive=0s`, and qwen3 returning content in `thinking`.
- Anthropic 404 was caused by stale model ids. Auth, endpoint, version, and body shape are valid.
- OpenAI 429 is specifically `insufficient_quota`.

## Files Changed

- app/services/ai_context_router.py
- scripts/run_overnight_observation.py
- tests/test_ai_context_router.py
- tests/test_overnight_observation_runner.py
- .env.example
- docker-compose.yml

## Files Created

- docs/POLYBOT_AI_PROVIDER_ROOT_CAUSE_ANALYSIS.md
- docs/POLYBOT_OBSERVATION_RUN_FAILURE_ANALYSIS.md
- docs/POLYBOT_AI_PROVIDER_FIX_BUILD_REPORT.md

## DB Migrations

None.

## Fixes Applied

### Ollama

- Added configurable keep-alive:
  - `AI_CONTEXT_OLLAMA_KEEP_ALIVE`
  - fallback `OLLAMA_KEEP_ALIVE`
  - default `5m`
- Prefer `host.docker.internal:11434` before localhost when running in Docker and the configured base URL is localhost.
- Extract Ollama output from `response`, falling back to `thinking`.

### Anthropic

- Added current available fallback models:
  - `claude-haiku-4-5-20251001`
  - `claude-sonnet-4-6`
- Kept env model override first.
- Updated `.env.example` with `ANTHROPIC_MODEL=claude-haiku-4-5-20251001`.

### OpenAI

- Classify 429 `insufficient_quota` as `OPENAI_QUOTA_EXCEEDED`.
- Keep other 429/rate-limit cases as `OPENAI_RATE_LIMITED`.
- Treat `OPENAI_QUOTA_EXCEEDED` as safe-yellow only when AI is optional.

## Tests Run

Compile:

- `python -m py_compile app/services/ai_context_router.py scripts/run_overnight_observation.py`
  - Result: passed

Standard Docker pytest path:

- `docker compose --profile test run --rm --no-deps test python -m pytest tests/test_ai_context_router.py tests/test_overnight_observation_runner.py -q`
  - Result: failed before collection with `OSError: [Errno 12] Cannot allocate memory: '/app/tests'`.
  - Classification: environment/bind-mount failure, not a test assertion failure.

Copy-based Docker test path:

- `python -m pytest /tmp/tests/test_ai_context_router.py /tmp/tests/test_overnight_observation_runner.py -q`
  - Result: 28 passed, 1 warning in 150.22s
- `python -m pytest /tmp/tests/test_v3_source_to_neuron_ingestion_wiring.py /tmp/tests/test_source_to_neuron_yellow_fixes.py /tmp/tests/test_v2_21_source_status.py -q`
  - Result: 20 passed, 1 warning in 127.72s

## Runtime Diagnostics

No production `route_context()` smoke was run after the patch to avoid writing AI/neural/mesh audit rows.

Direct provider diagnostics:

- Ollama host:
  - tags OK, `qwen3:4b` present
  - `keep_alive=0s` call: 18.278s
  - `keep_alive=5m` calls: 10.774s, then 6.000s
- Ollama API container:
  - localhost refused
  - host.docker.internal tags OK
  - patched-like warmed calls: 3.498s and 3.453s
- Anthropic:
  - model list OK
  - old fallback models 404
  - `claude-haiku-4-5-20251001` tiny call OK in 1.001s
- OpenAI:
  - tiny call returned 429 `insufficient_quota`

## Observation Forensics

The run `overnight_observation_20260602T002301Z` completed GREEN:

- started_at: 2026-06-02T00:23:01.877177+00:00
- finished_at: 2026-06-02T04:23:04.733257+00:00
- samples: 48
- stop_reason: NONE
- final report: docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md

## Safety Before/After

Before and after this phase:

- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0
- paper_intents: 6
- paper_orders: 9
- paper_fills: 6
- paper_positions: 9
- paper_capital_ledger: 1
- risk_decisions: 10332
- exit_plans: 10332
- coordinator_decisions: 10636

SYSTEM power after phase: OFF.

## Secret Exposure Check

- `.env` was inspected with masked output only.
- Provider diagnostics printed only status codes and sanitized provider error bodies.
- API dashboard reports `secrets_exposed=false`.
- No secret values were printed.

## Remaining Operator Actions

- OpenAI: fix quota/billing/plan for the configured key if OpenAI fallback is desired.
- Anthropic: optionally set `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` in real `.env`; code now has this fallback even if env is unset.
- Ollama: consider setting `OLLAMA_BASE_URL=http://host.docker.internal:11434` for API container clarity, or leave router fallback in place.

## Remaining Engineering Actions

- Consider a read-only Ollama warmup/status endpoint if future observation preflight should verify warm latency before an AI smoke.
- Consider surfacing `OPENAI_QUOTA_EXCEEDED` separately in the dashboard summary after a new router run records that reason.
- Consider making the runner-owned final report path clearer in the starter report to avoid PID/report confusion.

## Phase Status

GREEN.

Root causes are identified, confirmed safe fixes were applied, tests pass through the non-flaky container path, no safety mutation occurred, no secrets were exposed, and the reported 4h run actually completed GREEN.

Can start a new 4h observation after review: YES, subject to normal GREEN or safe-yellow preflight.
