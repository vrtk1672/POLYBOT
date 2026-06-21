# POLYBOT Phase 5 - Eligible To Intent Bridge Report

## 1. Purpose

Phase 5 closes the visibility gap between `ELIGIBLE` paper candidates and `paper_intents`.

The phase does not make Paper Ready, activate runtime trading, or force intent creation. It adds source-backed bridge truth so every eligible candidate is accounted for as already having an intent, ready, waiting, blocked, no-trade, or unknown with an explicit explanation.

## 2. Current Reality Found

Current active runtime remains safe/stopped:

- System power: `OFF`
- Runtime life: `STOPPED`
- Paper simulation: `OFF`
- Paper readiness: `BLOCKED`
- Candidate explanation ledger: `STALE`
- Eligible candidates: `2,940`
- Paper intents: `20`
- Eligible without intent: `2,926`

The active bridge endpoint explains all `2,926` eligible candidates without intent and reports `0` unexplained.

## 3. Existing Sources Reused

- `paper_eligibility_candidates`
- `paper_intents`
- `no_trade_log`
- `orderbook_snapshots`
- `risk_decisions`
- `exit_plans`
- `lifecycle_governance_decisions`
- `paper_accounts`
- `paper_positions`
- `system_state`
- `RuntimeReadinessService`
- `StateGovernor`
- Existing `PaperIntentGateService` blocker logic

## 4. Where The Gap Was Found

The existing bridge was implicit in `PaperIntentGateService.build_intents()`.

Gaps found:

- No dedicated bridge truth endpoint.
- No dashboard-visible eligible-to-intent outcome ledger.
- System-power OFF returned before candidate selection, recording a blocked run but no per-candidate no-trade bridge outcomes.
- Existing no-trade rows did not carry canonical bridge outcome metadata.
- Eligible candidates with no intent were visible in Phase 4 but not assigned bridge outcomes.

## 5. Bridge Model

Bridge outcomes exposed:

- `PAPER_INTENT_CREATED`
- `ALREADY_HAS_INTENT`
- `NO_TRADE_WITH_REASON`
- `WAITING_FOR_REFRESH`
- `BLOCKED_BY_GOVERNOR`
- `BLOCKED_BY_RUNTIME`
- `BLOCKED_BY_PAPER_SIMULATION`
- `BLOCKED_BY_PRICE`
- `BLOCKED_BY_CAPITAL`
- `BLOCKED_BY_LIFECYCLE`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_EXIT`
- `BLOCKED_BY_DATA`
- `BLOCKED_BY_DUPLICATE`
- `UNKNOWN_WITH_EXPLANATION`

Bridge states exposed:

- `RESOLVED`
- `WAITING`
- `BLOCKED`
- `READY_FOR_INTENT`
- `UNKNOWN`

Read-only API mode computes bridge outcomes without writes. Normal paper-intent gate mode now records bridge outcome metadata on created intent evidence and no-trade evidence.

## 6. Files Inspected

- `AGENTS.md`
- `docs/POLYBOT_CONTEXT_INDEX.md`
- `docs/POLYBOT_V2_MASTER_CONTEXT.md`
- `docs/POLYBOT_SAFETY_RULES.md`
- `docs/POLYBOT_AGENT_WORKFLOW.md`
- `docs/POLYBOT_ULTIMATE_FORENSIC_AUTOPSY.md`
- `docs/TRUTH_HARDENING_REPORT.md`
- `docs/CURRENT_RUNTIME_READINESS_REPORT.md`
- `docs/CURRENT_PAPER_READINESS_REPORT.md`
- `docs/CANDIDATE_EXPLANATION_LEDGER_REPORT.md`
- `app/services/paper_intents.py`
- `app/repositories/paper_intent_repository.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/runtime_readiness.py`
- `app/control_center/truth_contract.py`
- `app/runtime/state_governor.py`
- `app/services/system_power.py`
- `app/services/candidate_eligibility_recovery.py`
- `app/services/paper_execution.py`
- `app/services/paper_capital.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- Existing paper intent, no-trade, paper readiness, candidate explanation, and read-only API tests

## 7. Files Changed

- `app/control_center/eligible_intent_bridge.py`
- `app/api/routes.py`
- `app/services/paper_intents.py`
- `tests/test_eligible_intent_bridge.py`
- `tests/test_control_center_read_only_apis.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/dist/index.html`
- `frontend/control-center/dist/assets/index-B1v7kOAD.css`
- `frontend/control-center/dist/assets/index-D9s9_zrv.js`
- `docs/ELIGIBLE_TO_INTENT_BRIDGE_REPORT.md`

## 8. APIs Changed

Added:

- `GET /dashboard/api/v2/control/eligible-intent-bridge`
- `GET /dashboard/api/v2/control/eligible-intent-bridge/{candidate_id}`

Both are GET-only and return Control Center truth envelopes.

## 9. Frontend Changes

The Control Center cockpit now fetches and displays Eligible To Intent Bridge truth:

- eligible candidates
- paper intents
- eligible without intent
- explained without intent
- unexplained without intent
- top bridge outcomes
- top bridge blockers
- sample eligible candidate bridge explanation
- required conditions to create intent

No new design system was added.

## 10. Tests Added

Added `tests/test_eligible_intent_bridge.py` covering:

- existing intent -> `ALREADY_HAS_INTENT`
- system power OFF -> runtime block
- paper simulation OFF
- Governor denial
- stale orderbook
- missing executable price
- missing quantity
- capital block
- lifecycle denial
- risk inconsistency
- exit inconsistency
- eligible without intent is explained and counted
- read-only endpoint creates no artifacts
- normal gate records bridge no-trade outcome when power is OFF
- single-candidate endpoint

## 11. Tests Run And Exact Results

Passed:

- `.venv\Scripts\python.exe -m pytest tests/test_eligible_intent_bridge.py -q`
  - `15 passed in 79.90s`
- `.venv\Scripts\python.exe -m pytest tests/test_candidate_explanations.py tests/test_paper_readiness.py tests/test_control_center_read_only_apis.py -q`
  - `34 passed in 159.57s`
- `.venv\Scripts\python.exe -m pytest tests/test_v2_paper_intent_service.py tests/test_v2_paper_intent_safety.py tests/test_v2_paper_intent_repository.py tests/test_v2_paper_intent_contract.py tests/test_v2_no_trade_ledger_service.py tests/test_v2_no_trade_ledger_safety.py tests/test_v2_no_trade_ledger_repository.py tests/test_v2_no_trade_ledger_contract.py -q`
  - `13 passed in 52.70s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - passed
- `npm run typecheck`
  - passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - `3 passed`, `18 tests passed`
- `npm run build`
  - passed

Broad suggested slice, original Phase 5 run:

- `.venv\Scripts\python.exe -m pytest tests -q -k "paper_intent or intent_gate or eligibility"`
  - `46 passed`, `2 failed`, `1850 deselected`
  - Failures:
    - `tests/test_candidate_eligibility_recovery_service.py::test_recovery_recovers_side_recomputes_readiness_and_creates_safe_paper_artifacts`
    - `tests/test_dashboard_eligibility_recovery_truth.py::test_dashboard_eligibility_recovery_truth_is_real`
  - Both failures expected `paper_orders >= 1`; current paper execution returned no orders. This was not loosened because Phase 5 forbids changing execution or lifecycle behavior.

Phase 5 RED fix, 2026-06-14:

- Root cause: candidate eligibility recovery produced three same-market/same-side eligible candidates and paper intents in one batch. Safe paper execution correctly blocked all of them with `SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW`.
- Fix: `PaperIntentGateService` now deduplicates same-batch `(market_id, side)` candidates before intent creation. The first safe candidate may proceed through the existing gates; duplicate same-market/same-side candidates receive explicit no-trade bridge evidence with `SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW` / `BLOCKED_BY_DUPLICATE`.
- `.venv\Scripts\python.exe -m pytest tests\test_candidate_eligibility_recovery_service.py::test_recovery_recovers_side_recomputes_readiness_and_creates_safe_paper_artifacts tests\test_dashboard_eligibility_recovery_truth.py::test_dashboard_eligibility_recovery_truth_is_real -q`
  - `2 passed in 17.56s`
- `.venv\Scripts\python.exe -m pytest tests -q -k "paper_intent or intent_gate or eligibility"`
  - `48 passed`, `1850 deselected`, `235.09s`
- `.venv\Scripts\python.exe -m pytest tests\test_eligible_intent_bridge.py tests\test_candidate_explanations.py tests\test_paper_readiness.py -q`
  - `44 passed in 235.84s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - passed

## 12. GET Verification Results

Active port: `8000`

Container owner before RED fix:

- `polybot_api`
- container id: `67fa694d9341`
- image: `polybot_server-api`

GET-only verification after Phase 5 implementation:

- `GET /healthz` -> `200`, `ok`
- `GET /runtime/health` -> `200`, runtime `STOPPED`, system power `OFF`
- `GET /dashboard/api/v2/control/runtime-readiness` -> `200`, status `LOCKED`
- `GET /dashboard/api/v2/control/paper-readiness` -> `200`, paper readiness `BLOCKED`
- `GET /dashboard/api/v2/control/candidate-explanations` -> `200`, total candidates `20162`, eligible `2940`, eligible without intent `2926`
- `GET /dashboard/api/v2/control/eligible-intent-bridge` -> `200`, eligible `2940`, eligible without intent `2926`, explained without intent `2926`, unexplained without intent `0`
- `GET /dashboard/api/v2/control/overview` -> `200`, status `PARTIAL`
- `GET /dashboard/api/v2/control/eligible-intent-bridge/{candidate_id}` -> `200`

GET-only verification after Phase 5 RED fix and API-only recreate:

- `GET /healthz` -> `200`, `ok`
- `GET /dashboard/api/v2/control/eligible-intent-bridge` -> `200`, status `STALE`, readiness `BLOCKED`, eligible `2940`, eligible without intent `2926`, explained without intent `2926`, unexplained without intent `0`
- `GET /dashboard/api/v2/control/candidate-explanations` -> `200`, status `STALE`, readiness `BLOCKED`, blocked `17222`, eligible `2940`, unknown `0`
- `GET /dashboard/api/v2/control/paper-readiness` -> `200`, paper readiness `BLOCKED`, execution readiness `BLOCKED_BY_GOVERNOR`, system power `OFF`, runtime `STOPPED`, paper simulation `OFF`

## 13. Eligible-To-Intent Gap Before/After Explanation

Before Phase 5 visibility:

- eligible candidates: `2,940`
- paper intents: `20`
- eligible without intent: `2,926`
- explained without intent: not exposed

After Phase 5 visibility:

- eligible candidates: `2,940`
- paper intents: `20`
- eligible without intent: `2,926`
- explained without intent: `2,926`
- unexplained without intent: `0`

This does not create intents for historical candidates.

## 14. Top Bridge Outcomes

Active server top outcome:

- `BLOCKED_BY_GOVERNOR`

This is expected in the current safe/stopped state because system power is OFF and Governor denies paper simulation.

## 15. Top Blockers

Active server top blocker:

- `STALE_ORDERBOOK`

Sample single-candidate blockers:

- `GOVERNOR_DENIED_PAPER`
- `PAPER_SIMULATION_OFF`
- `RUNTIME_STOPPED`
- `STALE_ORDERBOOK`
- `SYSTEM_POWER_OFF`

## 16. Remaining Bridge Risks

- Historical duplicate eligible candidates can still exist. The normal intent gate now prevents new same-batch duplicate same-market/same-side intent creation and records an explicit duplicate no-trade bridge outcome for duplicates.
- Some bridge truth is stale because the active runtime is stopped.
- Read-only bridge explains current historical candidates; it does not backfill production `no_trade_log` for all historical eligible candidates.
- Normal bridge outcome persistence uses existing `paper_intents.evidence` and `no_trade_log.evidence`, not a new dedicated table.
- `READY_FOR_INTENT` is exposed as bridge state for read-only candidates that pass current checks, but read-only mode never creates the intent.

## 17. Next Recommended Phase

Paper Certification / Safe Paper Cycle Observation should run only after explicit operator activation of SYSTEM ON and PAPER SIMULATION ON, with Governor-approved paper simulation and fresh trusted orderbooks.
