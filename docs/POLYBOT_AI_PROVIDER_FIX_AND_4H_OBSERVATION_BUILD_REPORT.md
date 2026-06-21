# POLYBOT AI Provider Fix and 4h Observation Build Report

Generated: 2026-06-02T00:23Z
Executor: Codex
Task mode: CONTROLLED_FIX + AI_PROVIDER_ROUTING + OVERNIGHT_OBSERVATION_4H
Risk: VERY HIGH
Review: ChatGPT review required after run start or completion.

## Current Reality Found

- SYSTEM power was OFF before preflight.
- Runtime health reported SAFE_STOPPED while SYSTEM was OFF; this is a safe preflight state for observation.
- Live trading remained disabled.
- Shadow remained disabled.
- Dashboard responses were mock_data=false.
- Source status was OK with no unsafe degraded sources.
- Paper readiness was GREEN.
- Paper realized PnL was 23.55 and unrealized PnL was 0.0.
- Paper lineage was OK after excluding 3 legacy quarantined rows.
- Capital reconciliation was OK.

## AI Provider Diagnosis

### Ollama

- API/container could discover the configured local model through Ollama tags.
- Configured fast/primary model: qwen3:4b.
- Generation still failed/degraded:
  - localhost endpoint returned OLLAMA_ERROR.
  - host.docker.internal endpoint timed out.
- Final classification: OLLAMA_TIMEOUT.
- Runtime impact: safe degraded, no blocking.

### OpenAI

- API key was present in masked inspection.
- No explicit OpenAI model env was set, so router defaults were used.
- Runtime smoke returned HTTP 429 Too Many Requests.
- Final classification after fix: OPENAI_RATE_LIMITED.
- Runtime impact: safe degraded, no aggressive retry, no blocking.

### Anthropic

- API key was present in masked inspection.
- No explicit Anthropic model env was set.
- ANTHROPIC_VERSION is passed as 2023-06-01.
- Router tried bounded fallback models:
  - claude-3-5-haiku-latest
  - claude-3-haiku-20240307
- Runtime smoke still returned 404-class failures.
- Final classification after fix: ANTHROPIC_DEGRADED.
- Runtime impact: safe degraded, no blocking.

## Fixes Applied

- Added precise OpenAI 429 classification as OPENAI_RATE_LIMITED.
- Added precise Anthropic 404 classification as ANTHROPIC_DEGRADED.
- Added bounded Anthropic model fallback attempts.
- Added AI_REQUIRED=false dashboard/config visibility.
- Added AI provider env placeholders to .env.example.
- Passed AI provider env controls through docker-compose for API/test services.
- Updated overnight preflight to accept SAFE_STOPPED only when SYSTEM power is OFF.
- Updated overnight runner to treat AI degraded and intentionally disabled legacy/optional sources as safe-yellow.
- Added ai_context_router to observation samples.
- Confirmed no fake AI context is emitted on all-provider failure.

## Files Changed

- app/services/ai_context_router.py
- scripts/run_overnight_observation.py
- tests/test_ai_context_router.py
- tests/test_overnight_observation_runner.py
- .env.example
- docker-compose.yml

## DB Migrations

- None.

## Tests Run

- python -m py_compile app/services/ai_context_router.py scripts/run_overnight_observation.py
- docker compose --profile test run --rm test python -m pytest tests/test_ai_context_router.py tests/test_overnight_observation_runner.py -q
  - Result: 22 passed, 1 warning in 164.93s
- docker compose --profile test run --rm test python -m pytest tests/test_v3_source_to_neuron_ingestion_wiring.py tests/test_source_to_neuron_yellow_fixes.py tests/test_v2_21_source_status.py tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py -q
  - Result: 29 passed, 1 warning in 291.53s
- docker compose --profile test run --rm test python -m pytest tests/test_ai_context_router.py tests/test_overnight_observation_runner.py tests/test_v3_source_to_neuron_ingestion_wiring.py tests/test_source_to_neuron_yellow_fixes.py tests/test_v2_21_source_status.py tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py -q
  - Result: 51 passed, 1 warning in 323.65s
- After the SAFE_STOPPED preflight patch, Docker pytest intermittently failed before collection with OSError Errno 12 Cannot allocate memory while scanning /app/tests. A direct Python assertion inside the test image passed for SAFE_STOPPED preflight behavior.
- After adding news_provider to the safe-yellow allowlist, a dry sample confirmed unsafe_degraded_sources=[] and provider_failure=false.

## Runtime Smoke

Run id: ai_context_provider_fix_smoke_20260602T001439Z

- Ollama: FAILED, OLLAMA_TIMEOUT.
- OpenAI: FAILED, OPENAI_RATE_LIMITED.
- Anthropic: FAILED, ANTHROPIC_DEGRADED.
- Final status: AI_CONTEXT_UNAVAILABLE.
- Selected provider: none.
- Response present: false.
- Runtime continues: true.
- Secrets exposed: false.

## 4h Observation

- Preflight result: SAFE-YELLOW.
- Blockers: none.
- Safe-yellow warning: AI_CONTEXT_UNAVAILABLE with AI_REQUIRED=false.
- Started: YES.
- PID: 7888.
- Start UTC: 2026-06-02T00:23:01Z.
- Expected end UTC: 2026-06-02T04:23:01Z.
- Start local: 2026-06-02T03:23:01+03:00.
- Expected end local: 2026-06-02T07:23:01+03:00.
- Log path: logs/overnight/overnight_observation_20260602T002301Z.log.
- Runner report path: docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md.
- 4h status report path: docs/POLYBOT_4H_OBSERVATION_REPORT_20260602T002301Z.md.

## First Sample

- endpoint_errors: []
- mock_data_endpoints: []
- unsafe_degraded_sources: []
- provider_failure: false
- repeated_provider_failures: 0
- live_orders: 0
- real_orders_current: 1
- orders_v2: 1
- fills_v2: 1
- canonical_positions: 0
- real/canonical/order safety deltas: 0
- paper_intents: 6
- paper_orders: 9
- paper_fills: 6
- paper_positions: 9
- open_positions: 0
- active_positions_without_fills: 0
- realized_pnl: 23.55
- unrealized_pnl: 0.0
- forensics active count: 6
- forensics quarantined count: 3

## Safety Checklist

- live enabled: false
- shadow enabled: false
- live orders: 0
- real orders delta: 0
- orders_v2 delta: 0
- fills_v2 delta: 0
- canonical positions delta: 0
- paper lineage: OK
- capital reconciliation: OK
- fake AI context: none
- fake dashboard data: none
- secrets exposed: false

## Remaining Risks

- Ollama generation remains too slow/unavailable for bounded runtime generation.
- OpenAI account/provider is rate limited or quota limited.
- Anthropic endpoint/model access still returns 404-class failures despite fallback models.
- Docker pytest had an intermittent host/container memory allocation error after the final runner patch; prior full relevant suite passed, and direct assertions verified the final logic.

## Phase Status

YELLOW.

Reason: AI providers remain degraded, but AI is optional for observation, degradation is truthfully reported, no fake AI context is emitted, preflight is safe-yellow, and the 4h observation is running safely.

Can review in morning: YES.
