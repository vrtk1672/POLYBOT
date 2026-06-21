# POLYBOT V3.3 Multi-Brain Consumption Build Report

## Current Reality Found

- V3.0 stores immutable neural events in `neural_events` and links consumers through delivery/replay tables.
- V3.1 stores session rooms in `mesh_sessions`, `mesh_session_events`, `mesh_session_participants`, and `mesh_session_state`.
- V3.2 stores derived session awareness in `mesh_shared_awareness` and source refs in `mesh_awareness_sources`.
- Existing coordinator path remains `brain_outputs` -> `coordinator_decisions`.
- Production distribution before V3.3:
  - `brain_outputs=10672`
  - `coordinator_decisions=10636`
  - `source_brain_count`: `1=10624`, `4=12`
  - `conflict_count`: `0=10624`, `2=1`, `3=11`
  - `conflicts_detected`: `false=10624`, `true=12`
  - `brain_outputs` by brain: `runtime_brain_adapter=10624`, `context=12`, `no_trade=12`, `opportunity=12`, `risk=12`
- Existing shared awareness source domains before smoke: `CAPITAL=14`, `ORDERBOOK=3`, `RISK=4`.
- Existing Risk, Exit, Capital, Context, and Coordinator services did not consume `mesh_shared_awareness`.

## Brain Consumption Model

Migration `0104_v3_multi_brain_consumption.sql` adds:

- `mesh_brain_opinions`
- `mesh_brain_consumption_sources`
- `mesh_coordinator_input_bundles`

Opinions are derived from `mesh_shared_awareness` and `mesh_awareness_sources`. They preserve source refs and never overwrite source truth.

## Opinion Rules

- Risk consumes RULES, LIQUIDITY, ORDERBOOK, FEES, TIME, NEWS, CAPITAL.
- Exit consumes EXIT, RISK, LIQUIDITY, ORDERBOOK, TIME, POSITION, PNL.
- Capital consumes CAPITAL, FEES, TIME, PNL, POSITION, RISK, EXIT.
- Context consumes NEWS, WHALE, SOCIAL, RULES, MEMORY, CANDIDATE.
- Position consumes POSITION, PNL, RISK, EXIT, NEWS, LIQUIDITY only when position context exists.
- Coordinator Observer consumes stored opinions only and creates a coordinator input bundle.

Stances are `SUPPORT`, `CAUTION`, `BLOCK`, and `NO_SIGNAL`.

## Conflict Detection

Basic conflict detection records a conflict when any source brain produces `SUPPORT` while another produces `BLOCK`.

Coordinator Evolution is out of scope; conflicts are recorded but not resolved.

## Files Created

- `app/db/migrations/0104_v3_multi_brain_consumption.sql`
- `app/multi_brain_consumption/__init__.py`
- `app/multi_brain_consumption/types.py`
- `app/multi_brain_consumption/repository.py`
- `app/multi_brain_consumption/service.py`
- `tests/test_v3_multi_brain_consumption_layer.py`
- `docs/POLYBOT_MULTI_BRAIN_CONSUMPTION.md`
- `docs/POLYBOT_MULTI_BRAIN_CONSUMPTION_BUILD_REPORT.md`

## Files Changed

- `app/shared_awareness/service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## API Routes

- `GET /dashboard/api/v2/multi-brain-consumption`
- `GET /dashboard/api/v2/multi-brain-consumption/{session_id}`

Both return `mock_data=false`.

## Runtime Integration

`SharedAwarenessService.refresh_session_with_conn()` now invokes `MultiBrainConsumptionService.consume_session_with_conn()` after successful awareness persistence.

SYSTEM OFF still blocks new publishing before sessions, awareness, or opinions can mutate. Dashboard reads remain allowed.

## Tests Added

`tests/test_v3_multi_brain_consumption_layer.py` covers:

- Multiple brain opinions from awareness.
- Risk, Exit, Capital, Context, and Position Brain domain consumption.
- Position Brain gating.
- Coordinator bundle `source_brain_count > 1`.
- Conflict and no-conflict cases.
- Source links to real awareness sources.
- Idempotent rerun.
- Dashboard summary/detail truth.
- SYSTEM OFF mutation block.
- No trading or decision truth mutation.
- Dialogue materialization.

## Tests Run

- `python -m py_compile app\multi_brain_consumption\types.py app\multi_brain_consumption\repository.py app\multi_brain_consumption\service.py app\shared_awareness\service.py app\services\brain_dialogue.py app\api\routes.py`
  - Result: passed.
- `python -m py_compile tests\test_v3_multi_brain_consumption_layer.py`
  - Result: passed.
- `docker compose --profile test run --rm test python -m pytest tests/test_v3_multi_brain_consumption_layer.py -q`
  - Result: `13 passed, 1 warning in 60.51s`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v3_neural_event_bus.py tests/test_v3_mesh_sessions_foundation.py tests/test_v3_shared_awareness_layer.py tests/test_v3_multi_brain_consumption_layer.py -q`
  - Result: `41 passed, 1 warning in 192.81s`.
- `docker compose --profile test run --rm test python -m pytest tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_safety.py tests/test_v2_risk_core_safety.py tests/test_v2_exit_foundation_safety.py tests/test_v2_paper_eligibility_safety.py tests/test_v2_paper_intent_safety.py tests/test_paper_no_live_safety.py -q`
  - Result: `11 passed, 1 warning in 69.48s`.

## Runtime Smoke

Steps:

1. SYSTEM OFF.
2. Publish `ORDERBOOK_REFRESHED`: blocked with `SYSTEM_POWER_OFF`.
3. SYSTEM ON.
4. Published source-backed `ORDERBOOK_REFRESHED` with market_id.
5. Published source-backed `RISK_CHANGED` with same market_id and candidate_id.
6. Verified neural events, mesh sessions, shared awareness, brain opinions, source links, and coordinator input bundles.
7. Dashboard summary returned 200 and `mock_data=false`.
8. Detail endpoint returned 200 for `mesh_session_threat_session_76ed80dd55633e522bc67adf`.
9. Dialogue materialized opinion and coordinator observer messages.
10. SYSTEM OFF.

Smoke sample:

- `market_id=v33-smoke-market-1780302127`
- `candidate_id=v33-smoke-candidate-1780302127`
- `source_brain_count=4`
- `conflicts_detected=false`
- No deterministic conflict existed in smoke because no source-backed `BLOCK` stance was present.

## Before / After Counts

Before smoke:

- `neural_events=5`
- `mesh_sessions=7`
- `mesh_session_events=7`
- `mesh_shared_awareness=7`
- `mesh_brain_opinions=0`
- `mesh_brain_consumption_sources=0`
- `mesh_coordinator_input_bundles=0`

After smoke:

- `neural_events=7`
- `mesh_sessions=10`
- `mesh_session_events=10`
- `mesh_shared_awareness=10`
- `mesh_brain_opinions=15`
- `mesh_brain_consumption_sources=30`
- `mesh_coordinator_input_bundles=3`

Safety counts unchanged:

- `live_orders=0`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- `risk_decisions=10332`
- `exit_plans=10332`
- `paper_eligibility_candidates=10332`
- `paper_intents=6`
- `paper_accounts=1`

## Sample Brain Opinions

- Risk Brain: `CAUTION`, consumed `CAPITAL`, missing RULES/LIQUIDITY/ORDERBOOK/FEES/TIME/NEWS.
- Capital Brain: `SUPPORT`, consumed `CAPITAL` and `RISK`.
- Exit Brain: `NO_SIGNAL`, consumed `RISK`, missing exit-relevant domains.
- Context Brain: `NO_SIGNAL`, missing NEWS/WHALE/SOCIAL/RULES/MEMORY/CANDIDATE.
- Coordinator Observer: `SUPPORT`, collected 4 source brains and 4 opinions.

## Sample Coordinator Input Bundle

- `bundle_id=mesh_coordinator_bundle_mesh_session_threat_session_76ed80dd55633e522bc67adf`
- `source_brain_count=4`
- `opinion_count=4`
- `coordinator_ready=true`
- `conflicts_detected=false`
- `conflict_count=0`

## Safety Checklist

- Live trading not enabled.
- Shadow/live actions not created.
- Orders unchanged.
- Fills unchanged.
- Paper positions unchanged.
- Canonical positions unchanged.
- Paper capital balances unchanged.
- Risk decisions unchanged.
- Exit plans unchanged.
- Eligibility outcomes unchanged.
- Paper intents unchanged.
- `brain_outputs` and `coordinator_decisions` untouched by V3.3.

## Remaining Risks

- Opinion rules are intentionally basic and should not be treated as final Coordinator policy.
- Runtime data currently has sparse NEWS/WHALE/SOCIAL/RULES/FEES/TIME domains for new sessions.
- Conflicts are detected when `SUPPORT` and `BLOCK` coexist, but no resolution is implemented in this phase.
- Existing historical coordinator decisions remain mostly single-brain; V3.3 creates new mesh-native bundles in parallel.

## Next Recommended Phase

Coordinator Evolution can consume `mesh_coordinator_input_bundles` after human review confirms V3.3 behavior.
