# V2.3 Hybrid AI Brain

## Purpose

V2.3 adds POLYBOT's controlled AI interpretation layer. It is a semantic reasoning system for summaries, classification, deduplication, contradiction checks, wording-risk prechecks, compact case files, local-first model routing, budget control, caching, cost tracking, decision logging, model performance truth, API visibility, dashboard fields, and Event Bus events.

It is not a trading system. It cannot create orders, order intents, positions, risk approvals, or live execution decisions.

## Architecture

- `app/ai_brain/contracts.py`: strict task, route, request, response, decision, and case-file contracts.
- `app/ai_brain/case_file_builder.py`: builds compact market case files from V2.2 Data Foundation tables.
- `app/ai_brain/model_router.py`: local-first routing across fast, primary, reasoning, and cloud tiers.
- `app/ai_brain/budget_governor.py`: cost and data-quality gate before model calls.
- `app/ai_brain/cache.py`: deterministic cache keys and duplicate-call prevention.
- `app/ai_brain/prompt_versions.py`: prompt defaults and DB-backed prompt registration.
- `app/ai_brain/local_ai_worker.py`: mockable Ollama-compatible local model wrapper.
- `app/ai_brain/cloud_escalation_worker.py`: disabled-by-default cloud escalation abstraction.
- `app/ai_brain/service.py`: orchestration flow tying cache, budget, routing, workers, ledgers, decisions, and events together.

## Local / Cloud Split

Local AI is first choice:

- `qwen3:8b`: classification and dedup.
- `qwen3:14b`: rules summaries, market linking, context summaries, wording prechecks.
- `deepseek-r1:14b`: local reasoning for traps, contradictions, and review prep.

Cloud escalation is disabled by default and only considered when explicitly requested, budget allows it, data completeness is high enough, and local confidence is insufficient.

## AI Task Types

- `MARKET_CLASSIFICATION`
- `RULES_SUMMARY`
- `MARKET_LINKING`
- `NEWS_DEDUP`
- `CONTEXT_SUMMARY`
- `CASE_FILE_BUILD`
- `WORDING_RISK_PRECHECK`
- `CONTRADICTION_CHECK`
- `TRAP_PRECHECK`
- `POST_TRADE_REVIEW_PREP`

News, social, whale, and strategy phases are not implemented here; V2.3 only provides infrastructure.

## Case Files

Case files pull from:

- `markets_v2`
- `market_rules`
- `market_snapshots_v2`
- `orderbook_snapshots`
- `liquidity_snapshots`
- `fee_snapshots`
- `market_family_map`

Missing orderbook and missing rules are represented directly as `orderbook_missing` and `rules_missing`. Low completeness, stale data, closed markets, or incomplete candidate data block cloud-like analysis and return uncertainty.

## Database Tables

Migration: `app/db/migrations/0041_v2_hybrid_ai_brain.sql`

- `ai_prompt_versions`
- `ai_requests`
- `ai_responses`
- `ai_cache`
- `ai_cost_ledger`
- `ai_escalations`
- `ai_decision_logs`
- `ai_model_performance`

## API Routes

- `GET /ai/health`
- `GET /ai/costs`
- `GET /ai/cache`
- `GET /ai/escalations`
- `GET /ai/decisions`
- `GET /ai/model-performance`
- `POST /ai/analyze`

`POST /ai/analyze` requires a reason and either a `market_id` or explicit `input_payload`. It returns structured analysis only.

## Dashboard Truth

The dashboard overview now includes real DB-backed AI fields:

- local AI status
- cloud enabled flag
- cloud/local calls today
- cost today
- cache hit rate
- escalations today
- errors today
- last AI decision time
- top AI task types
- model performance summary

If tables are absent or no calls exist, values are empty/zero truth, not mock data.

## Event Bus Integration

V2.3 adds and publishes AI events:

- `ai.request.created`
- `ai.cache.hit`
- `ai.budget.blocked`
- `ai.local.completed`
- `ai.cloud.escalated`
- `ai.cloud.completed`
- `ai.decision.logged`
- `ai.cost.recorded`
- `ai.model.performance.updated`

Payloads are redacted and do not contain raw secrets or trading instructions.

## State Governor Integration

AI analysis uses `RUN_INTELLIGENCE`. Cloud checks use `CALL_CLOUD_AI`. `KILL` blocks new AI analysis and cloud escalation. AI cannot override runtime mode.

## Safety Guarantees

- AI cannot create orders.
- AI cannot create order intents.
- AI cannot open positions.
- AI cannot approve risk.
- AI cannot bypass State Governor.
- AI cannot bypass data completeness.
- Cloud is disabled by default.
- Budget is checked before model calls.
- Cache is checked before model calls.
- Missing data returns uncertainty or blocked results.
- No trading events are emitted by V2.3.

## Known Limitations

- No real Ollama transport is enabled by default; tests mock workers.
- Cloud escalation is an abstraction only and disabled unless explicitly injected/configured in future.
- Runtime orderbook ingestion remains the V2.2 limitation; missing orderbooks are represented honestly.
- Prompt templates are basic foundation prompts; task-specialized prompt tuning belongs in future neuron phases.

## Future Phases

V2.4 can build the News Neuron on top of this layer. V2.5 can deepen rules/wording interpretation. Strategy, risk, execution, and learning remain future phases.
