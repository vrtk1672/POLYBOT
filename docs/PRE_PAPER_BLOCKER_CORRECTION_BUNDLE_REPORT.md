# Pre-Paper Blocker Correction Bundle Report

## Purpose

Correct stale and false pre-paper blockers found by `PRE_PAPER_BLOCKER_DEEP_TRUTH_AUDIT.md` without enabling Paper Simulation or creating execution artifacts.

## Current Reality Found

The active system already had candidate-scoped event production in prior reports, but after API restart this smoke produced fresh market-scoped orderbook events only. Runtime Supervisor was `REGISTERED_NOT_RUNNING`, with `supervisor_cycles_completed_since_system_on=0`.

The duplicate intent and open position blockers were false positives caused by stale truth queries:

- duplicate intent logic used `status` instead of `intent_status` and fallback historical market/side counts.
- open position logic counted `closed_at IS NULL`, including quarantined or excluded rows.

## Capital Freshness Correction

Lifecycle governance now accepts fresh event-native capital brain output as current capital truth when the historical `capital_brain_evaluations` source is stale. The replacement is bounded by a 600 second TTL and does not reserve, allocate, or mutate capital.

If event-native capital is fresh:

- `CAPITAL_OK` clears `STALE_CAPITAL_EVALUATION`.
- `CAPITAL_BLOCKED` replaces stale capital with current capital blockers.
- missing/partial/unknown capital becomes `CAPITAL_SOURCE_MISSING`.

## Lifecycle Re-Evaluation Result

`orderbook_mesh_consumer` now records capital output before lifecycle and invokes lifecycle governance for candidate-scoped orderbook events. In this smoke, no candidate-scoped events were produced, so the new lifecycle re-evaluation path could not be exercised against live candidate-scoped bundles.

Latest lifecycle rows still show historical `STALE_CAPITAL_EVALUATION` rows, with no fresh candidate-scoped lifecycle row during the smoke.

## Duplicate Intent Truth Correction

Added shared pre-paper active truth logic that:

- uses `intent_status` when present.
- counts only active statuses: `CREATED`, `PENDING`, `ACTIVE`, `READY`, `SUBMITTED`, `OPEN`.
- excludes consumed intents referenced by fills or paper position payloads.
- leaves historical intents intact.

Smoke result: `duplicate_active_intent_risk=0`.

## Open Position Truth Correction

Added shared open position truth logic that:

- counts active current statuses only.
- excludes `excluded_from_active_paper_truth=true`.
- excludes closed and quarantined historical rows.
- leaves historical positions intact.

Smoke result: `open_paper_positions=0`.

## Candidate-Scoped Surface Consistency

Corrected active truth is consistent between paper actionability and pre-paper safety:

- `duplicate_active_intent_risk=0`
- `open_paper_positions=0`

Candidate-scoped surfaces disagree with prior expected runtime state because the active smoke produced no candidate-scoped events:

- `candidate_event_scoped=0`
- `linked_to_candidate=0`
- `market_event_only=25`
- `token_side_mismatch=25`

## Coordinator / No-Trade Second-Layer Result

Paper actionability re-evaluated with corrected duplicate/open-position truth. Remaining states are specific:

- `BLOCKED_BY_LIFECYCLE`
- `MISSING_CANDIDATE_EVENT_LINK`
- `MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE`
- `WAITING_FOR_PRICE_REFRESH`
- `BLOCKED_BY_DATA`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_EXIT`

Generic `NO_PAPER_ACTIONABILITY` still appears in pre-paper safety because no candidate-actionable bundle exists after this smoke.

## Files Inspected

- `app/control_center/paper_actionability.py`
- `app/control_center/pre_paper_safety.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/candidate_scoped_events.py`
- `app/control_center/candidate_event_correlation.py`
- `app/services/paper_capital.py`
- `app/services/lifecycle_governance.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/capital_brain/service.py`
- `app/capital_brain/repository.py`
- `app/services/trade_lifecycle.py`
- `app/services/freshness_governance.py`

## Files Changed

- `app/control_center/pre_paper_active_truth.py`
- `app/control_center/paper_actionability.py`
- `app/control_center/pre_paper_safety.py`
- `app/services/lifecycle_governance.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `tests/test_pre_paper_blocker_correction.py`

## Tests Added / Changed

Added `tests/test_pre_paper_blocker_correction.py`.

Covered:

- duplicate intent truth uses `intent_status`.
- consumed historical intents do not block.
- active same-market intents still block.
- excluded/quarantined positions do not block.
- true active open positions still block.
- fresh event-native capital truth can replace stale capital in lifecycle.
- stale event-native capital cannot clear stale capital blocker.

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_pre_paper_blocker_correction.py -q`
  - `6 passed in 1.66s`
- `.venv\Scripts\python.exe -m pytest tests/test_paper_actionability_contract.py tests/test_pre_paper_safety_invariants.py tests/test_unified_blocker_shape.py tests/test_paper_certification_plan.py tests/test_candidate_scoped_event_production.py tests/test_mesh_evidence_bundle.py tests/test_eligible_intent_bridge.py tests/test_paper_readiness.py -q`
  - `22 passed, 33 skipped in 3.41s`
- `.venv\Scripts\python.exe -m pytest tests -q -k "pre_paper or paper_actionability or paper_intent or paper_position or capital or lifecycle or blocker"`
  - `60 passed, 165 skipped, 1751 deselected in 5.31s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - passed
- `npm run typecheck`
  - passed

## Deployment / Restart Result

- `docker compose build api`
  - passed
- `docker compose up -d --no-deps api`
  - API container recreated and started
- `GET /healthz`
  - `status=ok`, `ready=true`

No DB migration was added.

## Controlled SYSTEM ON Smoke Procedure

1. Captured baseline DB counts.
2. `POST /system/power/on`
3. Waited 120 seconds.
4. Polled runtime and control endpoints.
5. `POST /system/power/off`
6. Captured final DB counts.

Paper Simulation, Full Monitor Run, Shadow, Live, and paper actions were not activated.

## Before / After Blocker Counts

Before smoke:

- `duplicate_active_intent_risk=0`
- `open_paper_positions=0`
- `candidate_event_scoped=0`
- `linked_to_candidate=0`

During smoke:

- `duplicate_active_intent_risk=0`
- `open_paper_positions=0`
- `candidate_event_scoped=0`
- `linked_to_candidate=0`
- `blocked_by_lifecycle=50`
- `actionable_small_paper=0`
- `actionable_if_paper_enabled=0`

## What Blockers Remain

- `NO_CANDIDATE_SCOPED_EVENT`
- `MISSING_CANDIDATE_EVENT_LINK`
- `MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE`
- `BLOCKED_BY_LIFECYCLE`
- `WAITING_FOR_PRICE_REFRESH`
- `BLOCKED_BY_DATA`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_EXIT`
- `PAPER_SIMULATION_OFF`
- `RUNTIME_STOPPED` after cleanup

## Which Blockers Were Cleared

- stale duplicate intent false-positive
- quarantined/excluded open position false-positive

## Artifact Safety Counts

Before:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`

After:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`

Forbidden artifact counts did not increase.

## Can Phase 10 Start Now

NO.

Minimum blockers before Phase 10:

1. Restore active candidate-scoped event production under SYSTEM ON after API restart.
2. Re-run lifecycle re-evaluation against fresh candidate-scoped bundles.
3. Clear or classify current `BLOCKED_BY_LIFECYCLE`, `BLOCKED_BY_RISK`, `BLOCKED_BY_EXIT`, and price-refresh blockers.
4. Keep corrected duplicate/open-position truth as the canonical source.

## Next Recommended Step

Fix Runtime Supervisor activation after API restart and candidate-targeted event production under SYSTEM ON, then re-run this correction smoke to confirm lifecycle capital freshness clears on live candidate-scoped bundles.
