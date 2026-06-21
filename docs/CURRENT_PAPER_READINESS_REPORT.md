# Current Paper Readiness Report

Date: 2026-06-14

## Purpose

Phase 3 adds a read-only Current Paper Readiness layer that answers:

Can POLYBOT open a Paper trade right now?

The answer is exposed as `READY`, `NOT_READY`, `PARTIAL`, `BLOCKED`, or `UNKNOWN`, with exact blockers. Historical paper ledger health remains separate from current readiness.

## Current Reality Found

In-process verification against the local Postgres DB reports:

- `paper_readiness_state=BLOCKED`
- `paper_execution_readiness_state=BLOCKED_BY_GOVERNOR`
- `paper_simulation_state=OFF`
- `runtime_life_state=STOPPED`
- `system_power_state=OFF`
- `governor_allows_paper=False`
- `market_data_state=STALE`
- `orderbook_state=STALE`
- `trusted_orderbook_state=STALE`
- `candidate_state=STALE`
- `intent_state=ONLY_STALE_INTENTS`
- `risk_state=PARTIAL`
- `exit_state=PARTIAL`
- `capital_state=OK`
- `lifecycle_state=PARTIAL`
- `readiness_state=BLOCKED`

Current blockers:

- `SYSTEM_POWER_OFF`
- `RUNTIME_STOPPED`
- `PAPER_SIMULATION_OFF`
- `GOVERNOR_DENIED_PAPER`
- `STALE_MARKET_DATA`
- `STALE_ORDERBOOK`
- `STALE_TRUSTED_ORDERBOOK`
- `STALE_PAPER_CANDIDATE`
- `ONLY_STALE_PAPER_INTENTS`
- `STALE_PAPER_INTENT`
- `REFRESH_REQUIRED_BEFORE_EXECUTION`
- `RISK_NOT_APPROVED`
- `EXIT_NOT_READY`
- `LIFECYCLE_GOVERNANCE_DENIED`

Current counts:

- eligible candidates: 2940
- blocked candidates: 17222
- fresh intents: 0
- stale intents: 14
- open positions: 0
- paper orders: 12
- paper fills: 9

## Existing Sources Reused

- Runtime readiness: `app/control_center/runtime_readiness.py`
- System power and runtime mode: `system_state`
- Paper simulation switch: `system_state.metadata_json.paper_simulation`
- Governor paper permission: `StateGovernor.can_execute(RUN_PAPER_SIMULATION)`
- Market data: `market_snapshots_v2`, fallback `market_snapshots`
- Orderbook/trusted orderbook: `orderbook_snapshots`
- Candidates: `paper_eligibility_candidates`
- Paper intents: `paper_intents`
- Historical paper ledger: `paper_orders`, `paper_fills`, `paper_positions`
- Risk: `risk_decisions`
- Exit: `exit_plans`
- Capital: `paper_accounts`, paper position exposure
- Lifecycle governance: `lifecycle_governance_decisions`

## Files Inspected

- `AGENTS.md`
- `docs/POLYBOT_CONTEXT_INDEX.md`
- `docs/POLYBOT_AGENT_DISPATCH_PROTOCOL.md`
- `docs/POLYBOT_V2_MASTER_CONTEXT.md`
- `docs/POLYBOT_SAFETY_RULES.md`
- `docs/POLYBOT_AGENT_WORKFLOW.md`
- `docs/POLYBOT_ULTIMATE_FORENSIC_AUTOPSY.md`
- `docs/TRUTH_HARDENING_REPORT.md`
- `docs/CURRENT_RUNTIME_READINESS_REPORT.md`
- `app/control_center/runtime_readiness.py`
- `app/control_center/paper_simulation.py`
- `app/control_center/query_service.py`
- `app/control_center/truth_contract.py`
- `app/control_center/truth_hardening.py`
- `app/services/paper_dashboard_truth.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_intents.py`
- `app/services/paper_execution.py`
- `app/services/paper_capital.py`
- `app/services/risk_core.py`
- `app/services/exit_foundation.py`
- `app/services/lifecycle_governance.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- Existing paper/runtime/truth tests

## Files Changed

- `app/control_center/paper_readiness.py`
- `app/api/routes.py`
- `app/control_center/query_service.py`
- `app/control_center/truth_hardening.py`
- `app/services/paper_dashboard_truth.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `tests/test_control_center_read_only_apis.py`
- `tests/test_paper_readiness.py`
- `docs/CURRENT_PAPER_READINESS_REPORT.md`

## APIs Changed

Added:

- `GET /dashboard/api/v2/control/paper-readiness`

The endpoint is read-only and returns a Truth Contract envelope plus top-level paper readiness fields.

## Frontend Changes

- Added `paperReadiness` endpoint and query hook.
- Added Control Center cockpit display for:
  - Paper Ready answer: YES / NO / PARTIAL / UNKNOWN
  - execution readiness
  - paper simulation state
  - Governor paper permission
  - market/orderbook/trusted orderbook freshness
  - candidate and intent states
  - risk/exit/capital/lifecycle states
  - main blockers and counts

No new action buttons were added.

## Tests Added

- `tests/test_paper_readiness.py`
  - system power OFF blocker
  - Paper Simulation OFF blocker
  - Governor denial blocker
  - stale orderbook blocker
  - missing trusted orderbook blocker
  - historical paper ledger does not make readiness READY
  - fresh candidate without fresh intent is `PARTIAL` / `WAITING_FOR_REFRESH`
  - fresh intent with stale orderbook is not executable
  - risk blocked
  - exit not ready
  - capital blocked
  - full readiness requires all gates
  - response includes source/truth fields
  - endpoint does not create paper artifacts

## Tests Run And Results

- `$env:POLYBOT_DATABASE_URL='postgresql://...@127.0.0.1:55433/polybot_test'; .venv\Scripts\python.exe -m pytest tests/test_paper_readiness.py -q`
  - Result: `14 passed`
- `$env:POLYBOT_DATABASE_URL='postgresql://...@127.0.0.1:55433/polybot_test'; .venv\Scripts\python.exe -m pytest tests/test_paper_dashboard_truth.py tests/test_truth_hardening.py tests/test_runtime_readiness.py tests/test_control_center_read_only_apis.py -q`
  - Result: `21 passed`
- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed
- `npm run typecheck`
  - Result: passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed`, `18 tests passed`

## GET Verification Results

External running server:

- `GET /healthz`: `status=ok`, `ready=true`
- `GET /runtime/health`: `overall_status=SAFE_STOPPED`, `system_power=OFF`, `readiness_state=BLOCKED`
- `GET /dashboard/api/v2/control/runtime-readiness`: `runtime_life_state=STOPPED`, `system_power_state=OFF`
- `GET /dashboard/api/v2/control/paper-readiness`: `404 Not Found`

The external `:8000` process is serving older code and needs restart/deploy before the new route is available there.

Updated app in-process:

- `GET /dashboard/api/v2/control/paper-readiness`: `200`
- local DB in-process result: `paper_readiness_state=BLOCKED`

## Historical Ledger Health Vs Current Readiness

Historical paper rows are counted and exposed, but they do not contribute to `READY`.

Example from current DB:

- historical paper orders: 12
- historical paper fills: 9
- fresh paper intents: 0
- readiness: `BLOCKED`

## Remaining Paper Truth Risks

- The active external API process must be restarted before it serves the new route.
- Runtime Supervisor and Full Monitor Run remain process-local truth.
- This phase observes lifecycle/capital/risk/exit states from current rows; it does not resolve stale or partial sources.
- No eligible-to-intent bridge was implemented; fresh candidate without fresh intent remains `PARTIAL`.

## Next Recommended Phase

Resolve current freshness blockers without bypassing gates:

1. Fresh orderbook/trusted orderbook evidence.
2. Fresh candidate-to-intent evidence path.
3. Fresh risk/exit/lifecycle evidence alignment.
4. Restart/deploy the API process and repeat GET-only verification.

## Safety Checklist

- Live remained disabled: YES
- Shadow remained disabled: YES
- Paper was not activated: YES
- System ON was not activated: YES
- Full Monitor Run was not started: YES
- No POST action endpoints called: YES
- No paper intents created by readiness endpoint: YES
- No paper orders created by readiness endpoint: YES
- No paper fills created by readiness endpoint: YES
- No positions created by readiness endpoint: YES
- No position closes created by readiness endpoint: YES
- State Governor was not bypassed: YES
- Risk behavior was not changed: YES
- Exit behavior was not changed: YES
- Capital behavior was not changed: YES
- Execution behavior was not changed: YES
- No secrets printed: YES
- No fake dashboard data introduced: YES

## Status

YELLOW.

Current Paper Readiness is clearly exposed and tested, with exact blockers and historical/current separation. The status is YELLOW because the already-running external server has not been restarted and returns 404 for the new route.
