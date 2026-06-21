# POLYBOT V3.2 Shared Awareness Layer Build Report

## Dispatch

- Executor: Codex
- Task mode: CORE_ARCHITECTURE + SHARED_AWARENESS + BRAIN_MESH_FOUNDATION
- Risk: HIGH
- ChatGPT review: REQUIRED

## Current Reality Found

Required context was read from repository truth. Prompt-listed
`docs/POLYBOT_VISION_2.md`, `docs/POLYBOT_CURRENT_REALITY_AUDIT.md`, and
`docs/POLYBOT_NEURAL_EVENT_BUS_FOUNDATION*.md` are not present under those exact
paths. Equivalent current files used:

- `docs/POLYBOT_V2_MASTER_CONTEXT.md`
- root `POLYBOT_CURRENT_REALITY_AUDIT.md`
- `docs/POLYBOT_V3_NEURAL_EVENT_BUS_FOUNDATION.md`
- `docs/POLYBOT_V3_NEURAL_EVENT_BUS_FOUNDATION_BUILD_REPORT.md`
- `docs/POLYBOT_MESH_SESSIONS_FOUNDATION.md`
- `docs/POLYBOT_MESH_SESSIONS_FOUNDATION_BUILD_REPORT.md`
- `docs/POLYBOT_NEURON_INTELLIGENCE_PACK1.md`
- `docs/POLYBOT_TRUSTED_ORDERBOOK_EVIDENCE_HARDENING.md`
- `docs/POLYBOT_PAPER_CAPITAL_ACCOUNT_BALANCE_LEDGER.md`

Runtime evidence inspection before implementation:

- `mesh_sessions`: 4
- `mesh_session_events`: 4
- `mesh_session_participants`: 4
- `mesh_session_state`: 4
- `neural_events`: 3
- `neuron_intelligence_evidence`: 600
- `trusted_orderbook_evidence_links`: 266
- `orderbook_snapshots`: 25,881
- `rules_analysis`: 23
- `fee_snapshots`: 105,590
- `news_impact_scores`: 0
- `risk_decisions`: 10,332
- `exit_plans`: 10,332
- `paper_eligibility_candidates`: 10,332
- `paper_accounts`: 1
- `paper_capital_ledger`: 1
- `paper_positions`: 9
- `paper_trade_ledger`: 12
- `brain_dialogue_events`: 55,444
- `whale_events`: 0
- `social_normalized_events`: 0
- `market_memory_v2`: 0
- `paper_daily_pnl`: 2

Safely summarizable now:

- Source-backed: orderbook, trusted orderbook/liquidity, rules, fees, risk,
  exit, eligibility/candidate, paper capital, paper positions, paper trade
  ledger, PnL, Pack 1 neuron evidence.
- Missing in current DB: news impact, whale, social, memory.
- Stale risk: older orderbook neural/source rows can become `STALE` under the
  5-minute orderbook freshness rule.
- Current sessions: existing V3.1 smoke sessions had linked events, but not all
  had source-table refs. They were still usable through real `neural_events`.

## Files Created

- `app/db/migrations/0103_v3_shared_awareness_layer.sql`
- `app/shared_awareness/__init__.py`
- `app/shared_awareness/types.py`
- `app/shared_awareness/repository.py`
- `app/shared_awareness/service.py`
- `tests/test_v3_shared_awareness_layer.py`
- `docs/POLYBOT_SHARED_AWARENESS_LAYER.md`
- `docs/POLYBOT_SHARED_AWARENESS_LAYER_BUILD_REPORT.md`

## Files Changed

- `app/mesh_sessions/service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Migration: `0103_v3_shared_awareness_layer.sql`

Tables:

- `mesh_shared_awareness`
- `mesh_awareness_sources`

Idempotency:

- `mesh_shared_awareness.session_id` is unique.
- `mesh_awareness_sources(awareness_id, source_domain, source_table, source_record_id)` is unique.
- Rebuild deletes/reinserts source refs for an awareness row to prevent duplicates.

## Awareness Model

One awareness row per mesh session. Each row includes domain JSON for:

`NEWS`, `WHALE`, `SOCIAL`, `RULES`, `LIQUIDITY`, `ORDERBOOK`, `FEES`, `TIME`,
`RISK`, `EXIT`, `CAPITAL`, `PNL`, `MEMORY`, `POSITION`, `CANDIDATE`.

Each domain includes:

- `status`
- `summary`
- `confidence`
- `source_count`
- `latest_source_at`
- `source_refs`

## Domain Rules

Linked neural events map to domains by event type. Source tables add richer
evidence where entity keys match session `market_id`, `candidate_id`, or
`position_id`.

Domains with no source remain `MISSING`.
Domains with only stale sources are `STALE`.
Domains with fresh and stale/partial sources are `PARTIAL`.
Domains with fresh sources are `PRESENT`.

## Freshness Rules

- Orderbook/liquidity: 5 minutes
- Fees: 6 hours
- Risk/exit/candidate/position/capital/PnL/news/whale/social/time: 24 hours
- Rules/memory: 30 days
- `news_impact_scores.ttl_seconds` overrides the news freshness window when present.

## Runtime Integration

`MeshSessionService.resolve_event_with_conn()` refreshes shared awareness for
sessions that receive a newly linked event. This happens after V3.1 session link
creation and in the same transaction.

SYSTEM OFF blocks new publish and therefore blocks runtime awareness mutation.
Read-only dashboard calls do not mutate awareness.

## API Routes

- `GET /dashboard/api/v2/shared-awareness`
- `GET /dashboard/api/v2/shared-awareness/{session_id}`

Both return `mock_data=false`.

## Dialogue

`BrainDialogueService.materialize_recent()` now materializes source-backed
awareness updates from `mesh_shared_awareness`.

Messages include:

- updated awareness with present evidence domains
- explicit missing-domain messages
- capital attached to position-session message when applicable

## Tests Added

`tests/test_v3_shared_awareness_layer.py`

Coverage:

- orderbook event creates `ORDERBOOK` awareness
- rules evidence creates `RULES` awareness
- missing news remains `MISSING`
- stale orderbook becomes `STALE`
- candidate session attaches risk and exit sources
- position session attaches capital and PnL sources
- source refs point to real records
- idempotent rebuild does not duplicate sources
- dashboard summary returns `mock_data=false`
- detail endpoint returns domains and timeline context
- SYSTEM OFF blocks awareness mutation from runtime publish
- no live/paper/order/fill/position/capital mutation
- dialogue materializes shared awareness messages

## Tests Run

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v3_shared_awareness_layer.py -q"`

Result: `10 passed, 1 warning in 59.36s`

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_v3_neural_event_bus.py tests/test_dashboard_neural_bus_api.py tests/test_v3_mesh_sessions_foundation.py -q"`

Result: `19 passed, 1 warning in 103.79s`

`docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_brain_dialogue_materialization.py tests/test_dashboard_brain_dialogue_api.py tests/test_paper_no_live_safety.py tests/test_paper_execution_safety.py tests/test_v2_risk_core_safety.py tests/test_v2_exit_foundation_safety.py tests/test_v2_paper_eligibility_safety.py tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_safety.py -q"`

Result: `25 passed, 1 warning in 144.17s`

`python -m compileall app\shared_awareness app\mesh_sessions\service.py app\services\brain_dialogue.py app\api\routes.py`

Result: success.

## Runtime Smoke

API rebuilt:

`docker compose up -d --build api`

Health:

`GET /healthz` -> `{"status":"ok","app":"polybot","ready":true}`

Smoke steps:

1. SYSTEM OFF.
2. Attempted publish blocked; awareness count unchanged.
3. SYSTEM ON.
4. Published `ORDERBOOK_REFRESHED` for `market_id=v32-smoke-market`.
5. Published `RISK_CHANGED` for `market_id=v32-smoke-market`, `candidate_id=v32-smoke-candidate`.
6. Processed active sessions.
7. Materialized dialogue.
8. Verified dashboard summary/detail 200 with `mock_data=false`.
9. Verified present, missing, and stale domains are honest.
10. Verified no trading mutation.
11. SYSTEM OFF.

Runtime smoke results:

- `system_off_publish_blocked`: true
- `mesh_shared_awareness`: `0 -> 7`
- `mesh_awareness_sources`: `0 -> 21`
- `domains_present`: `0 -> 12`
- `domains_missing`: `0 -> 91`
- `domains_stale`: `0 -> 2`
- dashboard summary: 200, `mock_data=false`
- detail endpoint: 200, `mock_data=false`

## Before / After Counts

Before:

- `neural_events`: 3
- `mesh_sessions`: 4
- `mesh_session_events`: 4
- `mesh_shared_awareness`: 0
- `mesh_awareness_sources`: 0
- `domains_present`: 0
- `domains_missing`: 0
- `domains_stale`: 0
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- paper capital: available `1000.00000000`, locked `0.00000000`

After:

- `neural_events`: 5
- `mesh_sessions`: 7
- `mesh_session_events`: 7
- `mesh_shared_awareness`: 7
- `mesh_awareness_sources`: 21
- `domains_present`: 12
- `domains_missing`: 91
- `domains_stale`: 2
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- paper capital: available `1000.00000000`, locked `0.00000000`

Trading/capital mutation: none.

## Sample Awareness Records

`MARKET_SESSION market_id=v32-smoke-market`

- `ORDERBOOK`: `PRESENT`
- `CAPITAL`: `PRESENT`
- `NEWS/WHALE/SOCIAL/RULES/LIQUIDITY/FEES/TIME/RISK/EXIT/PNL/MEMORY/POSITION/CANDIDATE`: `MISSING`

`CANDIDATE_SESSION candidate_id=v32-smoke-candidate`

- `RISK`: `PRESENT`
- `CAPITAL`: `PRESENT`
- missing domains remain `MISSING`

Historical `MARKET_SESSION market_id=smoke-market`

- `ORDERBOOK`: `STALE`
- stale reason is freshness window, source ref preserved.

## Missing / Stale Domains

Current missing domain counts after smoke:

- `NEWS`: 7
- `WHALE`: 7
- `SOCIAL`: 7
- `RULES`: 7
- `LIQUIDITY`: 7
- `ORDERBOOK`: 4
- `FEES`: 7
- `TIME`: 7
- `RISK`: 3
- `EXIT`: 7
- `CAPITAL`: 0
- `PNL`: 7
- `MEMORY`: 7
- `POSITION`: 7
- `CANDIDATE`: 7

Current stale domain counts:

- `ORDERBOOK`: 2
- all other domains: 0

## Sample Dialogue

- `Shared Awareness: Updated MARKET_SESSION awareness with ORDERBOOK/CAPITAL evidence.`
- `Shared Awareness: Updated CANDIDATE_SESSION awareness with RISK/CAPITAL evidence.`
- `Shared Awareness: NEWS, WHALE, SOCIAL, RULES, LIQUIDITY, FEES missing for session; domains remain MISSING.`

## Safety Checklist

- Live not enabled.
- Shadow not enabled.
- SYSTEM OFF blocks publish and runtime awareness mutation.
- Dashboard reads allowed while OFF.
- No orders created.
- No fills created.
- No positions created.
- No paper artifacts created.
- Paper capital balances unchanged.
- Risk, Exit, Eligibility decisions unchanged.
- Source truth not overwritten.
- Missing evidence remains missing.
- No fake news, whale, social, or memory evidence.

## Remaining Risks

- Domain coverage is intentionally sparse until upstream producers publish or
  persist more evidence. Current DB has no news impact scores, whale events,
  social normalized events, or market memory rows.
- Capital is currently attached as global paper account state for active market,
  candidate, position, threat, and opportunity sessions. This is visibility only
  and does not allocate or mutate capital.
- Formal ChatGPT review remains required by project process.

## Next Recommended Phase

Multi-Brain Consumption can read shared awareness, but should remain
read-only/observational first. Do not evolve coordinator or trading decisions
until awareness consumption behavior is reviewed.

## Phase Status

GREEN

## Can Move To Multi-Brain Consumption

YES, after ChatGPT review.
