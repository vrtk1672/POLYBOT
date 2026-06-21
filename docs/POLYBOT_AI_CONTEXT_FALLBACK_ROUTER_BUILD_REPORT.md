# POLYBOT AI Context Fallback Router Build Report

## Current Reality Found

V3.9 source-to-neuron wiring already produced source-backed events through provider, neuron, neural event, mesh session, shared awareness, brain opinion, and coordinator paths. Ollama model discovery and endpoint reachability existed, but local generation could time out and leave the phase YELLOW. OpenAI and Anthropic credentials/model readiness were previously validated but generation was not wired into source-to-neuron fallback.

## Ollama Root Cause

Ollama was reachable, but `/api/generate` could exceed the runtime smoke timeout. The problem was generation latency, not endpoint discovery. The router keeps the local prompt bounded and caps Ollama output to 48 predicted tokens, then falls through to cloud providers if enabled.

## Router Design

`AIContextRouterService` tries providers in order and stops on the first successful source-backed response. Each provider attempt is audited with status, reason, latency, model, and hashes. Prompt and response bodies are bounded/redacted; secrets are not stored.

If every provider fails, it emits `AI_CONTEXT_UNAVAILABLE` and runtime continues. No fake AI context is created.

## Provider Order

Default: `ollama,openai,anthropic`

Cloud fallback can be disabled with `AI_CONTEXT_ENABLE_CLOUD_FALLBACK=false` or by passing `include_cloud_ai_generation=false`.

## Timeout Settings

- Provider timeout default: 15 seconds
- Total timeout default: 45 seconds
- Prompt cap default: 2000 chars
- Response token cap default: 300
- Ollama predicted-token cap: 48

## Files Created

- `app/services/ai_context_router.py`
- `app/db/migrations/0109_ai_context_fallback_router.sql`
- `tests/test_ai_context_router.py`
- `docs/POLYBOT_AI_CONTEXT_FALLBACK_ROUTER.md`
- `docs/POLYBOT_AI_CONTEXT_FALLBACK_ROUTER_BUILD_REPORT.md`

## Files Changed

- `app/source_to_neuron/service.py`
- `app/api/routes.py`
- `app/neural_bus/types.py`
- `app/shared_awareness/types.py`

## Tests Run

- `docker compose --profile test run --rm test_migrate` -> applied `0109_ai_context_fallback_router.sql`
- `docker compose --profile test run --rm test python -m pytest tests/test_ai_context_router.py -q` -> 10 passed, 1 warning
- `docker compose --profile test run --rm test python -m pytest tests/test_v3_source_to_neuron_ingestion_wiring.py tests/test_source_to_neuron_yellow_fixes.py -q` -> 12 passed, 1 warning

## Sample Fallback Trace

Expected sanitized trace when Ollama times out and OpenAI succeeds:

1. Ollama attempt: `OLLAMA_TIMEOUT`
2. OpenAI attempt: `COMPLETED`
3. Anthropic attempt: not called
4. Final status: `OK`
5. Selected provider: `openai`
6. Event: `AI_CONTEXT_UPDATED`

Expected sanitized trace when all fail:

1. Ollama attempt: provider-specific timeout/error
2. OpenAI attempt: provider-specific timeout/auth/error or skipped if cloud disabled
3. Anthropic attempt: provider-specific timeout/auth/error or skipped if cloud disabled
4. Final status: `AI_CONTEXT_UNAVAILABLE`
5. Event: `AI_CONTEXT_UNAVAILABLE`
6. Runtime continues

## Runtime Smoke

Runtime smoke was run on the rebuilt API container after applying migration `0109_ai_context_fallback_router.sql`.

Pre-smoke:

- SYSTEM power: `OFF`
- Read-only dashboard route: `GET /dashboard/api/v2/ai-context-router` returned `mock_data=false`
- SYSTEM OFF source-to-neuron call returned `SYSTEM_POWER_OFF`

Bounded ON smoke:

- Prompt: tiny AI context smoke prompt
- Provider order: `ollama,openai,anthropic`
- Provider timeout: 15 seconds
- Total timeout: 45 seconds
- Max prompt chars: 500
- Max response tokens: 64

Actual sanitized trace:

1. Ollama `http://localhost:11434`: `OLLAMA_ERROR`
2. Ollama `http://host.docker.internal:11434`: `OLLAMA_TIMEOUT`
3. OpenAI: `OPENAI_ERROR` due provider `429 Too Many Requests`
4. Anthropic: `ANTHROPIC_ERROR` due provider `404 Not Found`
5. Final status: `AI_CONTEXT_UNAVAILABLE`
6. Event: `AI_CONTEXT_UNAVAILABLE`
7. `runtime_continues=true`

Post-smoke:

- SYSTEM power: `OFF`
- Safety counts unchanged
- Router dashboard `mock_data=false`
- Router dashboard `secrets_exposed=false`
- Explicit secret scan against the latest dashboard payload returned `secrets_exposed=false`

Provider outcome means the router safety behavior is proven, but cloud fallback success still needs operator/provider action for OpenAI quota/rate limit and Anthropic endpoint/model configuration.

## Safety Checklist

- Live not enabled.
- Shadow not enabled.
- No real orders created.
- No paper intents, orders, fills, positions, or capital rows created by router tests.
- No fake AI response created on failure.
- No secrets printed or returned.
- Source-to-neuron still blocks while SYSTEM is OFF.
- Direct router calls while SYSTEM is OFF return `SYSTEM_POWER_OFF` without provider calls or router audit-row writes.

## Remaining Risks

- Real cloud fallback depends on valid provider credentials, provider availability, and model availability.
- Runtime smoke can prove routing behavior only for currently configured providers.
- The implementation uses direct HTTP provider calls; if a provider API contract changes, the provider-specific adapter may need adjustment.
- Current runtime smoke returned OpenAI `429 Too Many Requests` and Anthropic `404 Not Found`; no provider succeeded in that smoke.

## Overnight Observation Readiness

The router removes Ollama timeout as a hard blocker by falling back or degrading safely. Overnight observation should not start from this result alone because the live smoke ended in `AI_CONTEXT_UNAVAILABLE`; operator/provider action is needed for cloud success if GREEN preflight requires an AI context update.
