# V2.3 Build Report

## V2.3.1 Follow-Up

V2.3.1 Runtime Startup Responsiveness Fix completed: YES.

Final V2.3 status: GREEN. Canonical runtime endpoint verification passed after removing blocking startup refresh and delaying the first scheduler refresh until after readiness.

See `docs/V2_3_1_RUNTIME_STARTUP_RESPONSIVENESS_FIX.md`.

## Summary

V2.3 implements the Hybrid AI Brain foundation: typed AI contracts, compact V2.2-backed case files, local-first model routing, budget gates, cache, prompt versions, local/cloud worker abstractions, request/response ledger, cost ledger, decision log, model performance tracking, AI API routes, dashboard truth fields, and redacted Event Bus events.

The implementation is infrastructure-only. It does not create orders, order intents, positions, risk approvals, opportunity scores, or trading events.

## Files Created

- `app/ai_brain/__init__.py`
- `app/ai_brain/contracts.py`
- `app/ai_brain/model_router.py`
- `app/ai_brain/budget_governor.py`
- `app/ai_brain/cache.py`
- `app/ai_brain/cost_ledger.py`
- `app/ai_brain/prompt_versions.py`
- `app/ai_brain/case_file_builder.py`
- `app/ai_brain/local_ai_worker.py`
- `app/ai_brain/cloud_escalation_worker.py`
- `app/ai_brain/decision_log.py`
- `app/ai_brain/model_performance.py`
- `app/ai_brain/ai_errors.py`
- `app/ai_brain/redaction.py`
- `app/ai_brain/service.py`
- `app/repositories/ai_prompt_repository.py`
- `app/repositories/ai_cache_repository.py`
- `app/repositories/ai_request_repository.py`
- `app/repositories/ai_cost_repository.py`
- `app/repositories/ai_decision_repository.py`
- `app/repositories/ai_model_performance_repository.py`
- `app/api/ai_routes.py`
- `app/db/migrations/0041_v2_hybrid_ai_brain.sql`
- `tests/test_v2_3_ai_contracts.py`
- `tests/test_v2_3_ai_case_file_builder.py`
- `tests/test_v2_3_ai_budget_governor.py`
- `tests/test_v2_3_ai_cache.py`
- `tests/test_v2_3_ai_model_router.py`
- `tests/test_v2_3_local_ai_worker.py`
- `tests/test_v2_3_cloud_escalation.py`
- `tests/test_v2_3_ai_cost_ledger.py`
- `tests/test_v2_3_ai_decision_log.py`
- `tests/test_v2_3_ai_api.py`
- `tests/test_v2_3_ai_safety_guards.py`
- `docs/V2_3_HYBRID_AI_BRAIN.md`
- `docs/V2_3_BUILD_REPORT.md`

## Files Changed

- `app/events/types.py`
- `app/main.py`
- `app/runtime/service_registry.py`
- `app/services/query/operator_dashboard_query_service.py`
- `app/api/routes.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration Added

- `app/db/migrations/0041_v2_hybrid_ai_brain.sql`

## API Routes Added

- `GET /ai/health`
- `GET /ai/costs`
- `GET /ai/cache`
- `GET /ai/escalations`
- `GET /ai/decisions`
- `GET /ai/model-performance`
- `POST /ai/analyze`

## Dashboard Changes

Added a read-only AI Brain dashboard panel backed by DB truth:

- local AI status
- cloud AI enabled
- cloud/local calls today
- AI cost today
- cache hit rate
- escalations/errors today
- last AI decision
- top AI task types
- model performance summary

## Events Published

- `ai.request.created`
- `ai.cache.hit`
- `ai.budget.blocked`
- `ai.local.completed`
- `ai.cloud.escalated`
- `ai.cloud.completed`
- `ai.decision.logged`
- `ai.cost.recorded`
- `ai.model.performance.updated`

## Tests Added

V2.3 tests cover contracts, case files, budget gates, cache keys, model routing, local worker behavior, cloud escalation gates, cost ledger, decision log, API routes, and safety guards.

## Test Results

Targeted V2.3 default environment:

- `python -m uv run pytest tests/test_v2_3_ai_contracts.py -q`: `4 passed`.
- `python -m uv run pytest tests/test_v2_3_ai_case_file_builder.py -q`: `3 skipped` because `POLYBOT_DATABASE_URL` was not configured for that command.
- `python -m uv run pytest tests/test_v2_3_ai_budget_governor.py -q`: `4 passed`.
- `python -m uv run pytest tests/test_v2_3_ai_cache.py -q`: `2 passed`.
- `python -m uv run pytest tests/test_v2_3_ai_model_router.py -q`: `4 passed`.
- `python -m uv run pytest tests/test_v2_3_local_ai_worker.py -q`: `3 passed`.
- `python -m uv run pytest tests/test_v2_3_cloud_escalation.py -q`: `3 passed`.
- `python -m uv run pytest tests/test_v2_3_ai_cost_ledger.py -q`: `1 skipped` because `POLYBOT_DATABASE_URL` was not configured for that command.
- `python -m uv run pytest tests/test_v2_3_ai_decision_log.py -q`: `1 skipped` because `POLYBOT_DATABASE_URL` was not configured for that command.
- `python -m uv run pytest tests/test_v2_3_ai_api.py -q`: `3 skipped` because `POLYBOT_DATABASE_URL` was not configured for that command.
- `python -m uv run pytest tests/test_v2_3_ai_safety_guards.py -q`: `2 passed, 2 skipped`.

Targeted V2.3 grouped default run:

- `python -m uv run pytest tests/test_v2_3_ai_contracts.py tests/test_v2_3_ai_case_file_builder.py tests/test_v2_3_ai_budget_governor.py tests/test_v2_3_ai_cache.py tests/test_v2_3_ai_model_router.py tests/test_v2_3_local_ai_worker.py tests/test_v2_3_cloud_escalation.py tests/test_v2_3_ai_cost_ledger.py tests/test_v2_3_ai_decision_log.py tests/test_v2_3_ai_api.py tests/test_v2_3_ai_safety_guards.py -q`: `21 passed, 10 skipped`.

Explicit local Postgres reruns:

- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_3_ai_case_file_builder.py -q`: `3 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_3_ai_cost_ledger.py -q`: `1 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_3_ai_decision_log.py -q`: `1 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_3_ai_api.py -q`: `3 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_3_ai_safety_guards.py -q`: `4 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_2_data_foundation_api.py -q`: `3 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_v2_1_event_api.py -q`: `6 passed`.
- `$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; python -m uv run pytest tests/test_runtime_api.py -q`: `6 passed`.

Regressions:

- V2.2 regression commands: passed or skipped as expected when DB env was absent; pure logic tests passed.
- V2.1 regression commands: passed or skipped as expected when DB env was absent; event type tests passed.
- Runtime and Stage 4 safety regressions: `tests/test_runtime_modes.py` `8 passed`, `tests/test_mode_manager.py` `10 passed`, `tests/test_stage4.py` `30 passed, 1 skipped`, `tests/test_stage4_env_isolation.py` `10 passed`, `tests/test_env_runtime.py` `1 passed`.
- Old paper/dashboard regressions: skipped as expected without DB env.
- Full suite: `136 passed, 324 skipped`.

## Runtime Verification

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: no pending migrations after V2.3.1.
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`: canonical runtime started and became responsive.
- Verified `/healthz`, `/runtime/state`, `/runtime/health`, `/runtime/mode`, `/events/lag`, `/data/coverage`, `/ai/health`, `/ai/costs`, `/ai/cache`, `/ai/escalations`, and `/ai/decisions`.
- Runtime mode remained `DATA_ONLY`; live permissions remained false.

## Fully Implemented

- AI contracts and task taxonomy.
- V2.2-backed case file builder.
- Local-first model router.
- Budget governor.
- Cache keys and DB-backed cache repository.
- Prompt versioning foundation.
- Mockable local and cloud workers.
- Request/response ledger.
- Cost ledger.
- Escalation log.
- Decision log.
- Model performance tracker.
- AI API routes.
- Dashboard AI truth fields.
- Event Bus AI event types and publishing.

## Partial / Deferred

- Real Ollama HTTP transport is not enabled by default.
- Real cloud provider implementation is intentionally absent and disabled by default.
- Specialized prompts remain basic foundation prompts.
- News/rules/social/whale neurons remain future phases.

## Safety Checklist

- KILL blocks AI analysis/cloud: YES
- DATA_ONLY can run safe analysis only: YES
- Live disabled by default: YES
- Cloud disabled by default: YES
- AI cannot create orders: YES
- AI cannot create order intents: YES
- AI cannot bypass State Governor: YES
- AI cannot bypass Risk Gate: YES
- Cache checked before model calls: YES
- Budget checked before model calls: YES
- Low completeness blocks cloud: YES
- Missing orderbook handled honestly: YES
- Missing rules handled honestly: YES
- No secrets printed: YES
- AI events redacted: YES
- Dashboard uses real data only: YES

## Remaining Risks

- Real local model availability depends on future Ollama runtime configuration.
- Cloud provider integration needs a separate reviewed safety gate before any real credentials are used.
- Case-file scoring depends on V2.2 data coverage; runtime orderbook ingestion remains partial.

## Recommendation

V2.3 is GREEN. Proceed to V2.4 News Neuron only when explicitly requested.
