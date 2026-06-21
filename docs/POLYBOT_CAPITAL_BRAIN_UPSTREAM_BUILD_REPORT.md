# POLYBOT V3.5 Capital Brain Upstream Build Report

## Phase

Mission: V3.5 Capital Brain Upstream

Status: GREEN

Can move to Position-Aware Reactions: YES, after required ChatGPT review.

## Current Reality Found

Paper Capital state before V3.5 smoke:

- `account_id`: `paper_default`
- `current_balance`: `1000.00000000`
- `available_balance`: `1000.00000000`
- `locked_balance`: `0E-8`
- `open_exposure`: `0E-8`
- `daily_pnl`: `0E-8`
- `risk_per_trade_pct`: `1.000000`
- `max_position_size`: `25.00000000`
- `max_daily_loss_pct`: `5.000000`
- `max_open_positions`: `3`
- `max_total_open_exposure_pct`: `15.000000`
- active open positions: `0`
- latest daily PnL row: `2026-05-31`, net PnL `23.55000000`

Current behavior before this phase:

- `PaperCapitalService` blocks or mutates capital only at execution/close time.
- `PaperExecutionService` calls capital precheck before creating paper fills/positions.
- `PaperCapitalService.lock_on_fill()` and `release_on_close()` remain canonical balance mutation methods.
- V3.3 had `CAPITAL_BRAIN` opinions, but they did not have a dedicated upstream evaluation table.
- Coordinator saw Capital only through the prior `mesh_brain_opinions` surface.

## Files Created

- `app/db/migrations/0106_v3_capital_brain_upstream.sql`
- `app/capital_brain/__init__.py`
- `app/capital_brain/types.py`
- `app/capital_brain/repository.py`
- `app/capital_brain/service.py`
- `tests/test_v3_capital_brain_upstream.py`
- `docs/POLYBOT_CAPITAL_BRAIN_UPSTREAM.md`
- `docs/POLYBOT_CAPITAL_BRAIN_UPSTREAM_BUILD_REPORT.md`

## Files Changed

- `app/shared_awareness/service.py`
- `app/multi_brain_consumption/service.py`
- `app/multi_brain_consumption/repository.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Applied:

- `0106_v3_capital_brain_upstream.sql`

Tables:

- `capital_brain_evaluations`
- `capital_brain_sources`

## Capital Brain Model

`CapitalBrainService` creates one idempotent derived evaluation per mesh session. It reads:

- mesh session metadata
- shared awareness
- paper account balances and limits
- latest paper capital ledger record
- linked neural events for estimated required capital and lock time
- position context for position sessions

It writes:

- `capital_brain_evaluations`
- `capital_brain_sources`

It does not write:

- `paper_accounts`
- `paper_capital_ledger`
- paper orders/fills/positions/intents
- risk/exit/eligibility/coordinator legacy truth

## Decision Rules

Candidate and market sessions:

- missing account -> `CAPITAL_INSUFFICIENT_DATA`
- available <= 0 -> `CAPITAL_BLOCK`
- required > available -> `CAPITAL_BLOCK`
- required > max position size -> `CAPITAL_BLOCK`
- daily loss guard active -> `CAPITAL_BLOCK`
- max open positions reached -> `CAPITAL_BLOCK`
- exposure exceeds max -> `CAPITAL_BLOCK`
- exposure near max -> `CAPITAL_WATCH`
- long lock plus poor/missing fees -> `CAPITAL_WATCH`
- poor/stale liquidity -> `CAPITAL_WATCH`
- weak efficiency -> `CAPITAL_WATCH`
- otherwise -> `CAPITAL_SUPPORT`

Position sessions:

- missing position context -> `CAPITAL_INSUFFICIENT_DATA`
- profitable and adverse risk/exit context -> `CAPITAL_RELEASE_REVIEW`
- adverse position context -> `CAPITAL_RELEASE_REVIEW`
- healthy position context -> `CAPITAL_WATCH`

## Runtime Integration

Flow implemented:

Neural event -> Mesh Session -> Shared Awareness -> Capital Brain Evaluation -> Multi-Brain Consumption -> Coordinator Input Bundle -> Mesh Coordinator Decision

Implementation:

- `SharedAwarenessService.refresh_session_with_conn()` invokes `CapitalBrainService.evaluate_session_with_conn()` before Multi-Brain Consumption.
- `MultiBrainConsumptionService` reads the latest `capital_brain_evaluations` row and maps it into the existing `CAPITAL_BRAIN` opinion.
- `CAPITAL_BRAIN` opinion adds `CAPITAL_BRAIN_EVALUATION` to consumed domains and links to the evaluation as a source.
- Mesh Coordinator consumes the capital opinion through the existing bundle/decision flow.

## API Routes

- `GET /dashboard/api/v2/capital-brain`
- `GET /dashboard/api/v2/capital-brain/{evaluation_id}`
- `GET /dashboard/api/v2/capital-brain/session/{session_id}`

Verified with container-local `curl`; all returned HTTP 200 and `mock_data=false`.

## Dialogue

`BrainDialogueService` now materializes Capital Brain dialogue from `capital_brain_evaluations`.

Sample dialogue:

`Capital Brain: Available=1000.00000000, locked=0E-8, exposure=0E-8. I capital support session mesh_session_candidate_session_82e7fdfc5f13b0793b3cec47 because Capital Brain supports upstream review; balance, exposure, and limits fit the session.`

## Tests Added

`tests/test_v3_capital_brain_upstream.py` covers:

- candidate session evaluation
- missing account -> insufficient data
- zero available balance -> block
- required capital greater than available -> block
- max position size exceeded -> block
- daily loss guard -> block
- max open positions reached -> block
- high exposure -> watch/block
- good balance/evidence -> support
- long lock plus poor fees -> watch/block
- profitable adverse position -> release review
- healthy position -> watch
- source links
- dashboard summary/detail/session routes
- System OFF mutation blocking
- no paper/live/order/fill/position/ledger mutation
- multi-brain consumption of capital evaluation
- coordinator visibility
- runtime publish integration
- dialogue materialization

## Tests Run

1. `docker compose --profile test run --rm test python -m pytest tests/test_v3_capital_brain_upstream.py -q`

Initial result: `1 failed, 17 passed` due healthy position being treated as adverse from generic `RISK` wording.

Fix: tightened adverse detection to require explicit adverse/block/caution/worsening wording.

Final result: `18 passed, 1 warning in 81.93s`

2. Targeted compatibility rerun:

`docker compose --profile test run --rm test python -m pytest tests/test_v3_multi_brain_consumption_layer.py::test_coordinator_bundle_records_source_brain_count_gt_one_and_conflicts tests/test_v3_multi_brain_consumption_layer.py::test_brain_dialogue_materializes_multi_brain_opinions tests/test_v3_capital_brain_upstream.py -q`

Result: `20 passed, 1 warning in 93.93s`

3. Full V3 chain:

`docker compose --profile test run --rm test python -m pytest tests/test_v3_neural_event_bus.py tests/test_v3_mesh_sessions_foundation.py tests/test_v3_shared_awareness_layer.py tests/test_v3_multi_brain_consumption_layer.py tests/test_v3_mesh_coordinator_evolution.py tests/test_v3_capital_brain_upstream.py -q`

Result: `74 passed, 1 warning in 334.32s`

4. Paper capital and safety regressions:

`docker compose --profile test run --rm test python -m pytest tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_paper_exit_capital_release.py tests/test_dashboard_paper_capital_truth.py tests/test_v2_runtime_brain_adapter_safety.py tests/test_v2_runtime_coordinator_safety.py tests/test_v2_risk_core_safety.py tests/test_v2_exit_foundation_safety.py tests/test_v2_paper_eligibility_safety.py tests/test_v2_paper_intent_safety.py tests/test_paper_no_live_safety.py -q`

Result: `24 passed, 1 warning in 127.85s`

Warnings were Starlette TestClient/httpx deprecation warnings, not phase failures.

## Runtime Smoke

Commands:

- `docker compose build api migrate`
- `docker compose run --rm migrate`
- `docker compose up -d api`
- Python smoke inside `api` container
- container-local `curl` for dashboard routes

Smoke steps:

1. System OFF.
2. Publish attempt blocked by Neural Event Bus.
3. Verified no counts changed while OFF.
4. System ON.
5. Published `ORDERBOOK_REFRESHED` for `v35-smoke-market` / `v35-smoke-candidate` with estimated required capital `5`.
6. Verified session and shared awareness.
7. Verified `capital_brain_evaluations` created.
8. Verified `CAPITAL_BRAIN` opinion consumed `CAPITAL_BRAIN_EVALUATION`.
9. Verified coordinator bundle/decision includes Capital Brain opinion.
10. Verified dashboard returns `mock_data=false`.
11. Verified Capital Brain dialogue visible.
12. Verified no trading or capital ledger mutation.
13. System OFF.

## Before/After Counts

Before smoke:

- `capital_brain_evaluations`: 0
- `capital_brain_sources`: 0
- `mesh_brain_opinions`: 25
- `mesh_coordinator_input_bundles`: 5
- `mesh_coordinator_decisions`: 2
- `paper account current_balance`: `1000.00000000`
- `available_balance`: `1000.00000000`
- `locked_balance`: `0E-8`
- `open_exposure`: `0E-8`
- `paper_capital_ledger rows`: 1
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `paper_intents`: 6
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- `risk_decisions`: 10332
- `exit_plans`: 10332
- `paper_eligibility_candidates`: 10332
- legacy `coordinator_decisions`: 10636
- `brain_outputs`: 10672

After System ON smoke:

- `capital_brain_evaluations`: 1
- `capital_brain_sources`: 3
- `mesh_brain_opinions`: 30
- `mesh_coordinator_input_bundles`: 6
- `mesh_coordinator_decisions`: 3
- `paper account current_balance`: `1000.00000000`
- `available_balance`: `1000.00000000`
- `locked_balance`: `0E-8`
- `open_exposure`: `0E-8`
- `paper_capital_ledger rows`: 1
- `live_orders`: 0
- `paper_orders`: 9
- `paper_fills`: 6
- `paper_positions`: 9
- `paper_intents`: 6
- `orders_v2`: 1
- `fills_v2`: 1
- canonical `positions`: 0
- `risk_decisions`: 10332
- `exit_plans`: 10332
- `paper_eligibility_candidates`: 10332
- legacy `coordinator_decisions`: 10636
- `brain_outputs`: 10672

After System OFF completion: same as after System ON.

## Sample Evaluation

`capital_eval_mesh_session_candidate_session_82e7fdfc5f13b0793b3cec47`

- decision: `CAPITAL_SUPPORT`
- available: `1000.00000000`
- locked: `0E-8`
- open exposure: `0E-8`
- required: `5.00000000`
- lock minutes: `30`
- efficiency: `0.9858`
- reason: `Capital Brain supports upstream review; balance, exposure, and limits fit the session.`

## Sample Coordinator Influence

Capital opinion:

- brain type: `CAPITAL_BRAIN`
- stance: `SUPPORT`
- consumed domains: `CAPITAL`, `CAPITAL_BRAIN_EVALUATION`
- reasoning: `Capital Brain supports upstream review; balance, exposure, and limits fit the session.`

Coordinator decision:

- final stance: `WATCH`
- final action: `WATCH`
- source brain count: 4
- capital opinion included in supporting opinions

## Safety Checklist

- Live trading not enabled.
- Shadow trading not enabled.
- No live orders created.
- No paper intents created.
- No paper orders created.
- No paper fills created.
- No paper positions created.
- No canonical positions created.
- Paper account balances unchanged.
- Paper capital ledger row count unchanged.
- Risk decisions unchanged.
- Exit plans unchanged.
- Eligibility outcomes unchanged.
- Legacy coordinator decisions unchanged.
- Brain outputs unchanged.
- Capital evaluations are source-linked and derived only.

## Remaining Risks

- Estimated required capital is conservative and simple; it reads explicit event payload fields when present and otherwise defaults from account risk configuration.
- Runtime data currently lacks rich fees/liquidity/time/position evidence for broader real-world capital efficiency decisions.
- Capital Brain decisions are not yet enforced by paper intent or execution gates; this is intentional for V3.5.
- Required ChatGPT review remains outstanding.

## Next Recommended Phase

Position-Aware Reactions.
