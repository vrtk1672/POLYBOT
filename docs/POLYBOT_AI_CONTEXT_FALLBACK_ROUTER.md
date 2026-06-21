# POLYBOT AI Context Fallback Router

## Purpose

The AI Context fallback router prevents slow or unavailable AI providers from blocking POLYBOT runtime.

AI remains supporting evidence only. It cannot create trades, create paper artifacts, bypass Risk, bypass Exit, bypass Capital, bypass Coordinator, or bypass the State Governor.

## Provider Order

Default order:

1. `ollama`
2. `openai`
3. `anthropic`

Configurable env:

- `AI_CONTEXT_PROVIDER_ORDER=ollama,openai,anthropic`
- `AI_CONTEXT_PROVIDER_TIMEOUT_SECONDS=15`
- `AI_CONTEXT_TOTAL_TIMEOUT_SECONDS=45`
- `AI_CONTEXT_MAX_PROMPT_CHARS=2000`
- `AI_CONTEXT_MAX_RESPONSE_TOKENS=300`
- `AI_CONTEXT_ENABLE_CLOUD_FALLBACK=true`

Ollama local generation is additionally capped to 48 predicted tokens to preserve the timeout-safe smoke path.

## Success

On first successful provider the router:

- writes `ai_requests`
- writes `ai_responses`
- writes `ai_decision_logs`
- writes `ai_context_router_runs`
- publishes `AI_CONTEXT_UPDATED`
- updates `source_status` for `ai_context_router`

Stored data is redacted. Full secrets are never stored or returned.

## Failure

If all configured providers fail, the router:

- writes `ai_context_router_runs`
- writes an `AI_CONTEXT_UNAVAILABLE` decision log
- publishes `AI_CONTEXT_UNAVAILABLE`
- updates `source_status` as degraded
- returns `runtime_continues=true`

It does not fake a response.

## Dashboard

Read-only route:

`GET /dashboard/api/v2/ai-context-router`

Returns provider order, latest status, selected provider, provider attempt status, fallback counts, timeout counts, success counts, unavailable counts, latest runs, and `mock_data=false`.

## Source-To-Neuron

`SourceToNeuronIngestionService.run_once()` now calls `AIContextRouterService.route_context()` instead of the previous Ollama-only generation path.

System OFF blocks runtime generation. Read-only dashboards remain available.

## Safety

The router does not write to:

- `live_orders`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_intents`
- `paper_capital_ledger`
- `risk_decisions`
- `exit_plans`
- `coordinator_decisions`
- `orders_v2`
- `fills_v2`
- canonical `positions`

