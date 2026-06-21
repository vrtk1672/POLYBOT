# POLYBOT V3.6 Position Awareness Build Report

## Current Reality Found

- `docs/POLYBOT_VISION_2.md` is not present in this checkout.
- Production `paper_positions=9`.
- Active open positions: `0`.
- Raw open positions: `0`.
- Closed positions: `6`.
- Quarantined legacy positions: `3`.
- Existing `POSITION_SESSION` rows before V3.6 smoke: `0`.
- Existing position-related mesh opinions before V3.6 smoke: `0`.
- Existing position-related mesh coordinator decisions before V3.6 smoke: `0`.
- No `position_awareness`, `position_reactions`, or `position_context_sources` tables existed before migration `0107`.

## Model

V3.6 adds derived position truth:

- `position_awareness`: current position context per position.
- `position_reactions`: source-backed observations such as PnL, liquidity, risk, exit, whale/news, capital pressure, and aging.
- `position_context_sources`: links back to source tables and records.

No source trading truth is overwritten.

## Reaction Rules

- Positive PnL creates `PNL_RISING`.
- Negative or source-event falling PnL creates `PNL_FALLING`.
- Adverse news creates `ADVERSE_NEWS`; non-adverse news creates `POSITIVE_NEWS`.
- Whale exit/sell/outflow creates `WHALE_EXIT`; otherwise whale activity creates `WHALE_ENTRY`.
- Liquidity drop/thin/deteriorated creates `LIQUIDITY_DROP`; otherwise `LIQUIDITY_IMPROVED`.
- Widened/high spread creates `SPREAD_WIDENED`; otherwise `SPREAD_IMPROVED`.
- Risk increase/high/caution/block creates `RISK_INCREASED`; otherwise `RISK_DECREASED`.
- Exit degraded/required/block creates `EXIT_DEGRADED`; otherwise `EXIT_IMPROVED`.
- Capital watch/block/release review creates `CAPITAL_PRESSURE`.
- Age >= 720 minutes creates `POSITION_AGING`.
- If no source-backed trigger exists, a source-backed `NO_REACTION` observation is recorded from `paper_positions`.

## Files Created

- `app/db/migrations/0107_v3_position_awareness.sql`
- `app/position_awareness/__init__.py`
- `app/position_awareness/types.py`
- `app/position_awareness/repository.py`
- `app/position_awareness/service.py`
- `tests/test_v3_position_awareness.py`
- `docs/POLYBOT_POSITION_AWARENESS.md`
- `docs/POLYBOT_POSITION_AWARENESS_BUILD_REPORT.md`

## Files Changed

- `app/shared_awareness/service.py`
- `app/multi_brain_consumption/repository.py`
- `app/multi_brain_consumption/service.py`
- `app/mesh_coordinator/service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Applied to production:

- `0107_v3_position_awareness.sql`

## Runtime Integration

Current flow:

Neural Event -> Mesh Session -> Shared Awareness -> Capital Brain -> Position Awareness -> Multi-Brain Consumption -> Mesh Coordinator -> Position Awareness coordinator visibility refresh.

Position Awareness public mutation is blocked by SYSTEM OFF.

## API Routes

- `GET /dashboard/api/v2/positions-awareness`
- `GET /dashboard/api/v2/positions-awareness/{position_id}`

Both return `mock_data=false`.

## Tests Added

`tests/test_v3_position_awareness.py` covers:

- awareness creation
- PnL rising/falling
- adverse news
- whale exit
- liquidity drop
- risk increase
- capital pressure
- position aging
- coordinator visibility
- dashboard truth
- source links
- SYSTEM OFF mutation block
- no trading mutation
- runtime publish integration
- dialogue materialization

## Tests Run

- `docker compose --profile test run --rm test python -m pytest tests/test_v3_position_awareness.py -q`
  - Result: `15 passed, 1 warning in 67.59s`
- `docker compose --profile test run --rm test python -m pytest tests/test_v3_neural_event_bus.py tests/test_v3_mesh_sessions_foundation.py tests/test_v3_shared_awareness_layer.py tests/test_v3_multi_brain_consumption_layer.py tests/test_v3_mesh_coordinator_evolution.py tests/test_v3_capital_brain_upstream.py tests/test_v3_position_awareness.py -q`
  - Result: `89 passed, 1 warning in 405.53s`
- `docker compose --profile test run --rm test python -m pytest tests/test_paper_capital_account.py tests/test_dashboard_paper_capital_truth.py tests/test_paper_execution_capital_guards.py tests/test_paper_exit_capital_release.py tests/test_paper_execution_safety.py tests/test_paper_exit_safety.py tests/test_paper_no_live_safety.py tests/test_v2_paper_eligibility_safety.py tests/test_v2_paper_intent_safety.py -q`
  - Result: `19 passed, 1 warning in 96.03s`

## Runtime Smoke

SYSTEM OFF:

- Publishing `PNL_CHANGED` was blocked.
- `position_awareness` remained `0 -> 0`.

SYSTEM ON:

- Published `PNL_CHANGED` for existing paper position `c4e7b2c0-b565-5a6a-9f0b-3bae3bdf11bd`.
- Created `POSITION_SESSION`: `mesh_session_position_session_123596d2cec7987df3493dd5`.
- Created `position_awareness`: `position_awareness_c4e7b2c0-b565-5a6a-9f0b-3bae3bdf11bd`.
- Created reactions: `PNL_RISING`, `PNL_FALLING`, `POSITION_AGING`, `CAPITAL_PRESSURE`.
- Position Brain consumed `POSITION_AWARENESS` and produced `CAUTION`.
- Mesh Coordinator created `EXIT_RECOMMENDED / EXIT_REVIEW`, non-executing.
- Dashboard summary/detail returned HTTP `200` with `mock_data=false`.
- Dialogue materialized 5 Position Awareness messages.
- SYSTEM OFF restored after smoke.

## Before/After Counts

Before smoke:

- `neural_events=10`
- `mesh_sessions=13`
- `mesh_session_events=14`
- `mesh_shared_awareness=13`
- `mesh_brain_opinions=30`
- `mesh_coordinator_input_bundles=6`
- `mesh_coordinator_decisions=3`
- `capital_brain_evaluations=1`
- `position_awareness=0`
- `position_reactions=0`
- `position_context_sources=0`
- `live_orders=0`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `paper_intents=6`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- `paper_capital_ledger=1`
- paper account current/available/locked/exposure = `1000/1000/0/0`

After smoke:

- `neural_events=11`
- `mesh_sessions=14`
- `mesh_session_events=15`
- `mesh_shared_awareness=14`
- `mesh_brain_opinions=36`
- `mesh_coordinator_input_bundles=7`
- `mesh_coordinator_decisions=4`
- `capital_brain_evaluations=2`
- `position_awareness=1`
- `position_reactions=4`
- `position_context_sources=5`
- `live_orders=0`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `paper_intents=6`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- `paper_capital_ledger=1`
- paper account current/available/locked/exposure = `1000/1000/0/0`

## Sample Reaction

`Position Awareness: Position c4e7b2c0-b565-5a6a-9f0b-3bae3bdf11bd received CAPITAL_PRESSURE. Capital Brain produced CAPITAL_RELEASE_REVIEW.`

## Sample Coordinator Visibility

Position session decision:

- final stance: `EXIT_RECOMMENDED`
- final action: `EXIT_REVIEW`
- source brain count: `5`
- safety: `SAFE_NON_EXECUTING`

## Safety Checklist

- No live enabled.
- No shadow enabled.
- No orders created.
- No fills created.
- No positions created.
- No paper intents created.
- No paper capital ledger mutation.
- No paper account balance mutation.
- No risk decision mutation.
- No exit plan mutation.
- No eligibility mutation.
- Legacy `coordinator_decisions` and `brain_outputs` unchanged.

## Remaining Risks

- Production currently has no active open paper positions; smoke used an existing closed paper position to prove source-backed wiring without creating a new position.
- Position reaction semantics are deterministic and conservative; richer side-aware adverse/positive classification should be expanded in a later intelligence phase.
- Position Awareness currently observes and exposes coordinator visibility, but it does not trigger an exit loop and must remain non-executing until an explicit future phase.

## Next Recommended Phase

Full Intelligence Expansion can build richer source interpretation only after human review confirms V3.6 behavior and the lack of active open production positions is acceptable.

## Phase Status

GREEN.
