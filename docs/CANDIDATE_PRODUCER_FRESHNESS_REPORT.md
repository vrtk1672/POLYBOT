# Candidate Producer Freshness Report

## 1. Purpose

Phase 6B verifies that SYSTEM ON is not only supervisor heartbeat life, but also feeds safe candidate and readiness freshness. The goal is to make candidate producer life visible under SYSTEM ON without activating Paper Simulation, Shadow, Live, Full Monitor Run, or execution.

## 2. Current Reality Found

Phase 6 showed the supervisor could start, heartbeat, complete cycles, update events, and stop cleanly. It also showed `candidates_updated=false` and `CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON`.

Root cause: `RuntimeSupervisorService` ran read-only Control Center modules and paper simulation modules only when Paper Simulation was explicitly enabled. It did not call `MarketService.refresh()` or any candidate producer. The scheduler/MarketService path could update candidates independently, but short SYSTEM ON smoke did not prove candidate production because scheduler refresh is separate and delayed.

## 3. Why Phase 6 candidates_updated=false Happened

The supervisor cycle path had no safe candidate producer module. Candidate production was effectively outside the supervisor life proof. Full `MarketService.refresh()` was not safe to call directly from the supervisor because that method can continue into paper intent/execution services later in the flow. Phase 6B therefore wires the supervisor to the existing safe eligibility producer only.

## 4. Files Inspected

- `app/control_center/runtime_supervisor.py`
- `app/control_center/supervisor_life_path.py`
- `app/control_center/runtime_readiness.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/query_service.py`
- `app/control_center/truth_contract.py`
- `app/control_center/truth_hardening.py`
- `app/ingestion/market_service.py`
- `app/scheduler.py`
- `app/main.py`
- `app/runtime/state_governor.py`
- `app/runtime/health_truth.py`
- `app/services/system_power.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_intents.py`
- `app/services/paper_dashboard_truth.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_supervisor_life_path.py`
- `tests/test_runtime_readiness.py`
- `tests/test_control_center_runtime_supervisor.py`
- `tests/test_candidate_explanations.py`
- `tests/test_eligible_intent_bridge.py`
- `docs/SUPERVISOR_LIFE_PATH_REPORT.md`

## 5. Files Changed

- `app/control_center/runtime_supervisor.py`
- `app/control_center/candidate_producer_freshness.py`
- `app/control_center/runtime_readiness.py`
- `app/control_center/paper_readiness.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `tests/test_candidate_producer_freshness.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/CANDIDATE_PRODUCER_FRESHNESS_REPORT.md`

## 6. APIs Added/Changed

Added:

- `GET /dashboard/api/v2/control/candidate-producer-freshness`

Changed:

- `POST /dashboard/api/v2/control/actions/system-on` now wires `RuntimeSupervisorService` with the existing safe `PaperEligibilityService` candidate producer.
- `GET /dashboard/api/v2/control/runtime-readiness` now includes candidate producer state and candidate update warning fields.
- `GET /dashboard/api/v2/control/paper-readiness` now classifies Paper Simulation OFF / system/runtime/governor blockers as `BLOCKED`, not `PARTIAL`.

## 7. Frontend Changes

The Control Center now has a Candidate Producer Freshness panel showing producer state, freshness state, update result, after-SYSTEM-ON flags, market refresh/snapshot timestamps, candidate explanation and bridge freshness, paper readiness timestamp, blockers, and warnings. Existing truth/card styling was reused; no new design system or mock data was added.

## 8. Tests Added

- `tests/test_candidate_producer_freshness.py`

Coverage includes:

- supervisor candidate producer path
- no false ALIVE when candidates do not update
- fresh candidate rows after SYSTEM ON
- stale/no-update blockers
- endpoint shape and updated-after-SYSTEM-ON flags
- paper readiness remains blocked when Paper Simulation is OFF
- no paper orders/fills/positions created by the endpoint
- runtime readiness candidate update warning/state

## 9. Tests Run And Exact Results

- `.venv\Scripts\python.exe -m pytest tests/test_candidate_producer_freshness.py -q`
  - Earlier full run: `6 passed in 33.98s`
- `.venv\Scripts\python.exe -m pytest tests/test_supervisor_life_path.py tests/test_runtime_readiness.py tests/test_control_center_runtime_supervisor.py tests/test_candidate_explanations.py tests/test_eligible_intent_bridge.py tests/test_paper_readiness.py -q`
  - `68 passed in 334.16s (0:05:34)`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_read_only_apis.py -q`
  - `5 passed in 10.31s`
- `.venv\Scripts\python.exe -m pytest tests/test_paper_readiness.py tests/test_candidate_producer_freshness.py -q`
  - `20 skipped in 2.62s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - Passed
- `npm run typecheck`
  - Passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - `3 passed (3), 18 passed (18)`
- `npm run build`
  - Passed with a Vite chunk-size warning for the bundled Control Center JavaScript.

## 10. Deployment/Restart Results

- Confirmed port 8000 owner: `polybot_api`
- Ran `docker compose build api`
- Ran `docker compose up -d --no-deps api`
- No DB deletion, volume reset, or migration was run.

## 11. Controlled SYSTEM ON Smoke Procedure

Before:

- Captured runtime, supervisor life, candidate producer freshness, paper readiness, candidate explanations, and eligible bridge through GET only.
- Captured DB counts for event, market, candidate, no-trade, paper, and live/order tables.

Action:

- Called official `POST /dashboard/api/v2/control/actions/system-on`.
- Did not activate Paper Simulation.
- Did not start Full Monitor Run.
- Waited 135 seconds for supervisor cycles.

During:

- Polled GET endpoints.
- Confirmed supervisor alive, cycles completed, candidate producer running, candidate freshness fresh, and paper readiness blocked.

Cleanup:

- Called official `POST /dashboard/api/v2/control/actions/system-off`.
- Confirmed supervisor stopped and Paper Simulation remained OFF.

## 12. Before/After Counts

Before smoke:

- `event_log`: 550191
- `market_snapshots`: 115478
- `market_snapshots_v2`: 115480
- `paper_eligibility_candidates`: 20182
- `no_trade_log`: 20182
- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- `positions`: 0

During smoke:

- `event_log`: 550240
- `market_snapshots`: 115488
- `market_snapshots_v2`: 115490
- `paper_eligibility_candidates`: 20192
- `no_trade_log`: 20192
- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- `positions`: 0

After SYSTEM OFF:

- `event_log`: 550241
- `market_snapshots`: 115488
- `market_snapshots_v2`: 115490
- `paper_eligibility_candidates`: 20192
- `no_trade_log`: 20192
- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- `positions`: 0

Allowed data/candidate truth moved. Forbidden paper/live/order artifacts did not change.

## 13. Candidate Update Evidence

During smoke:

- `supervisor_life_state`: `ALIVE`
- `cycle_state`: `CYCLE_COMPLETED`
- `cycles_completed_since_system_on`: 3
- `events_updated`: true
- `candidates_updated`: true
- `candidate_producer_state`: `RUNNING`
- `candidate_freshness_state`: `FRESH`
- `candidate_update_result`: `CANDIDATES_UPDATED`
- `supervisor_candidate_path_result`: `PASSED`
- `updated_after_system_on.market_refresh`: true
- `updated_after_system_on.market_snapshots`: true
- `updated_after_system_on.candidates`: true
- `updated_after_system_on.candidate_explanations`: true
- `updated_after_system_on.eligible_bridge`: true
- `updated_after_system_on.paper_readiness`: true

## 14. Candidate Producer Blockers

No candidate producer blockers were present during the successful smoke. In the stopped state, the endpoint correctly reports:

- `SYSTEM_POWER_OFF`
- `SUPERVISOR_STOPPED`
- `CANDIDATES_BLOCKED_BY_RUNTIME`

## 15. Paper Readiness Before/During/After

Before smoke:

- `paper_readiness_state`: `BLOCKED`
- `paper_simulation_state`: `OFF`
- blockers included `SYSTEM_POWER_OFF`, `RUNTIME_STOPPED`, `PAPER_SIMULATION_OFF`, `GOVERNOR_DENIED_PAPER`

During smoke:

- `paper_readiness_state`: `BLOCKED`
- `runtime_life_state`: `ALIVE`
- `paper_simulation_state`: `OFF`
- blockers included `PAPER_SIMULATION_OFF`, stale paper intents, refresh/lifecycle blockers

After cleanup:

- `paper_readiness_state`: `BLOCKED`
- `runtime_life_state`: `STOPPED`
- `paper_simulation_state`: `OFF`
- blockers included `SYSTEM_POWER_OFF`, `RUNTIME_STOPPED`, `PAPER_SIMULATION_OFF`

## 16. SYSTEM OFF Cleanup Result

`POST /dashboard/api/v2/control/actions/system-off` returned `ACCEPTED`. Final GET verification showed:

- system power OFF
- runtime STOPPED
- supervisor STOPPED
- candidate producer STOPPED/BLOCKED_BY_RUNTIME
- paper readiness BLOCKED
- Paper Simulation OFF

## 17. Remaining Risks

- The supervisor candidate path currently uses the existing safe `PaperEligibilityService.evaluate_candidates()` path, not full `MarketService.refresh()`, to avoid paper execution side effects.
- The focused pytest command after the final small paper-readiness classifier change reported skipped tests in this environment, though the earlier full targeted suites passed and active runtime smoke verified the behavior.
- Candidate/no-trade row counts can increase during SYSTEM ON because safe eligibility/no-trade explanation writes are now part of supervisor life. Execution artifact counts remained unchanged.

## 18. Next Recommended Phase

Proceed only after accepting Phase 6B. The next phase should address fresh orderbook/executable pricing or continue hardening the candidate producer path into a broader event/candidate mesh, while keeping Paper Simulation OFF until explicitly certified.

