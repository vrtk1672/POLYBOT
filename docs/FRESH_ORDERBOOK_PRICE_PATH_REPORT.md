# Fresh Orderbook / Price Path Report

## Purpose

Phase 7 adds current, trusted, explainable orderbook and price readiness before any paper execution path can be considered executable.

The rule remains: no trusted fresh price, no trade.

## Current Reality Found

At implementation start, current paper readiness and bridge truth were blocked by stale orderbook evidence:

- `STALE_ORDERBOOK`
- `STALE_TRUSTED_ORDERBOOK`
- `MISSING_FRESH_ORDERBOOK`
- `MISSING_TRUSTED_ORDERBOOK`
- `REFRESH_REQUIRED_BEFORE_EXECUTION`

Production DB snapshot before controlled smoke:

- `orderbook_snapshots`: 50,712, latest `2026-06-14 14:37:36.851471+00`
- `trusted_orderbook_evidence_links`: 3,995, latest `2026-06-14 14:38:25.949427+00`
- `paper_eligibility_candidates`: 20,192
- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `live_orders`: 0

The default eligible candidate sample used market `691547`, side `YES`, token `34626184950254225208692030156208941308358060420950772251072421141618169142241`, and stale trusted orderbook evidence from June 10-11, 2026.

## Existing Sources Reused

- `orderbook_snapshots`
- `trusted_orderbook_evidence_links`
- `paper_eligibility_candidates`
- `paper_intents`
- `markets_v2`
- `live_orderbook_watcher_runs`
- `clob_token_book_verification_runs`
- `LiveOrderbookWatcherService`
- Runtime Supervisor
- Paper Readiness
- Candidate Explanation Ledger
- Eligible-to-Intent Bridge

No duplicate orderbook truth table was introduced.

## Why Orderbook Was Stale Or Missing

The system had trusted orderbook evidence, but the candidate-linked evidence was older than the 180 second execution TTL. SYSTEM ON candidate refresh was working from Phase 6B, but orderbook refresh was not part of the supervisor life path before this phase.

## Files Inspected

- `app/control_center/candidate_producer_freshness.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/runtime_supervisor.py`
- `app/services/orderbook_snapshots.py`
- `app/services/trusted_orderbook.py`
- `app/services/paper_execution.py`
- `app/services/paper_intents.py`
- `app/services/paper_eligibility.py`
- `app/services/live_orderbook_watcher.py`
- `app/services/clob_token_book_verification.py`
- `app/data_foundation/orderbook_snapshotter.py`
- `app/runtime/state_governor.py`
- `app/api/routes.py`
- Control Center frontend query and page files
- Related paper readiness, candidate explanation, bridge, and read-only API tests

## Files Changed

- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/runtime_supervisor.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_orderbook_price_readiness.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/FRESH_ORDERBOOK_PRICE_PATH_REPORT.md`

## APIs Added Or Changed

Added:

- `GET /dashboard/api/v2/control/orderbook-price-readiness`
- `GET /dashboard/api/v2/control/orderbook-price-readiness/{candidate_id}`

Extended:

- `GET /dashboard/api/v2/control/paper-readiness`
- `GET /dashboard/api/v2/control/candidate-explanations`
- `GET /dashboard/api/v2/control/eligible-intent-bridge`

## Frontend Changes

Control Center now fetches and displays Orderbook Price Readiness:

- trusted fresh/stale orderbook counts
- price-ready and waiting-for-refresh counts
- candidate, market, side, token
- entry price source and value
- exit liquidity state/source
- best bid, best ask, spread, depth
- orderbook age and execution TTL
- refresh-before-execution state
- exact blockers

Paper Readiness also shows price path and refresh-before-execution state.

## Tests Added

Added `tests/test_orderbook_price_readiness.py` covering:

- missing orderbook
- stale orderbook
- fresh trusted orderbook
- missing token
- missing side
- explicit entry price source
- exit liquidity state
- paper readiness price path integration
- candidate explanation and bridge integration
- read-only artifact safety
- supervisor orderbook refresher blockers

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_orderbook_price_readiness.py -q`
  - Result: `9 skipped in 2.32s`
- `.venv\Scripts\python.exe -m pytest tests/test_candidate_producer_freshness.py tests/test_paper_readiness.py tests/test_candidate_explanations.py tests/test_eligible_intent_bridge.py tests/test_control_center_read_only_apis.py -q`
  - Result: `5 passed, 50 skipped in 6.35s`
- `.venv\Scripts\python.exe -m pytest tests -q -k "orderbook or price or freshness or paper_execution"`
  - Result: `30 passed, 104 skipped, 1785 deselected in 6.28s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed
- `npm run typecheck`
  - Result: passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed`, `18 passed`
- `npm run build`
  - Result: passed, Vite emitted an existing chunk-size warning

## Deployment And Restart Results

- Confirmed port 8000 is served by Docker forwarding to `polybot_api`.
- Ran `docker compose build api`.
- Ran `docker compose up -d --no-deps api`.
- `/healthz` returned 200 after restart.

## Controlled SYSTEM ON Smoke Procedure

Allowed POST actions used:

- `POST /dashboard/api/v2/control/actions/system-on`
- `POST /dashboard/api/v2/control/actions/system-off`

Forbidden actions were not called:

- Paper Simulation ON
- Full Monitor Run
- Shadow
- Live
- Manual/execution actions

SYSTEM ON was accepted in `DATA_ONLY`. Paper Simulation stayed `OFF`.

## Before And After Orderbook Counts

Before smoke:

- `orderbook_snapshots`: 50,712
- latest orderbook: `2026-06-14 14:37:36.851471+00`
- `live_orderbook_watcher_runs`: 136

After smoke:

- `orderbook_snapshots`: 50,760
- latest orderbook: `2026-06-14 17:38:14.011981+00`
- `live_orderbook_watcher_runs`: 139

SYSTEM ON refreshed orderbooks through the bounded supervisor watcher module.

## Price Path Evidence

Sample candidate:

- candidate: `eligibility_exit_risk_thesis_coord_5def7b952cf540d483b471cd79572e12`
- market: `691547`
- side: `YES`
- token: `34626184950254225208692030156208941308358060420950772251072421141618169142241`
- trusted orderbook state: `TRUSTED_STALE`
- orderbook state: `STALE`
- price path state: `WAITING_FOR_ORDERBOOK_REFRESH`
- entry price source: `BEST_ASK`
- entry price: `0.29`
- exit price source: `BEST_BID`
- exit liquidity state: `EXIT_LIQUIDITY_STALE`
- best bid: `0.28`
- best ask: `0.29`
- spread: `0.01`
- refresh-before-execution: `REQUIRED`
- blocker: `STALE_ORDERBOOK`

The endpoint explains that the candidate has price evidence, but it is not execution-fresh.

## Candidate And Bridge Integration Evidence

Candidate explanations now include orderbook age, TTL, trusted state, price path blockers, and required-to-pass details.

Eligible-to-intent bridge includes price path evidence under `source_evidence.price.price_path` and does not convert stale price evidence into success.

## Paper Readiness Before, During, After

Before restart/smoke:

- `paper_readiness_state`: `BLOCKED`
- `paper_simulation_state`: `OFF`
- `price_path_state`: `WAITING_FOR_ORDERBOOK_REFRESH`
- `refresh_before_execution_state`: `REQUIRED`

During SYSTEM ON:

- runtime became `ALIVE`
- candidate producer became `RUNNING`
- Paper remained `BLOCKED`
- Paper Simulation stayed `OFF`
- price path still required refresh for default eligible candidates

After SYSTEM OFF:

- `system_power_state`: `OFF`
- `runtime_life_state`: `STOPPED`
- `paper_readiness_state`: `BLOCKED`
- `paper_simulation_state`: `OFF`
- `price_path_state`: `WAITING_FOR_ORDERBOOK_REFRESH`
- `refresh_before_execution_state`: `REQUIRED`

## Artifact Safety Counts

Before smoke:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `live_orders`: 0
- `positions`: 0

After smoke:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- `positions`: 0

Forbidden artifact counts did not increase.

## Remaining Risks

- The supervisor orderbook watcher refreshed active watchlist orderbooks, but the default eligible candidate sample still points at older trusted evidence. Candidate-targeted refresh-before-execution remains the next hardening step.
- The static SYSTEM ON component map still labels `orderbook_refresh` as `wired=false`, even though the runtime supervisor now runs the bounded watcher module. This should be reconciled in a later visibility cleanup.
- Local DB-gated tests skipped in this environment; broad related regressions and active runtime smoke covered the deployed behavior.

## Next Recommended Phase

Paper Certification Readiness should verify that when Paper Simulation is explicitly enabled in a controlled safe window, eligible candidates with fresh trusted price evidence still pass all Governor, risk, exit, capital, lifecycle, and execution freshness gates before any paper artifact is created.
