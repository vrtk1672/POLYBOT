# POLYBOT Fresh Seed To Paper Path Build Report

Build date: 2026-06-03

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Current Reality Found

Before this phase, fresh verified market data stopped before the canonical Paper path:

- `fresh_candidate_seeds`: 10
- `BOOK_VERIFIED` seeds: 8
- seeds mapped to `paper_eligibility_candidates`: 0
- seed-derived thesis profiles: 0
- seed-derived risk decisions: 0
- seed-derived exit plans: 0
- seed-derived Paper Intents: 0

The downstream path expected traceable runtime lineage: signal binding, brain output, coordinator decision, thesis, risk, exit, eligibility, then Paper Intent.

## Implementation

Added `FreshSeedPaperCandidateService`.

The service:

- selects source-backed fresh seeds
- rejects missing or untrusted orderbooks
- writes source-backed signal, brain output, coordinator input, and non-executing coordinator decision rows
- calls official downstream services in order
- records exact conversion status and blockers
- stops at Paper Intent

## Files Created

- `app/db/migrations/0116_fresh_seed_paper_candidate_integration.sql`
- `app/services/fresh_seed_paper_path.py`
- `tests/test_fresh_seed_paper_path.py`
- `docs/POLYBOT_FRESH_SEED_TO_PAPER_PATH.md`
- `docs/POLYBOT_FRESH_SEED_TO_PAPER_PATH_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/brain_dialogue.py`
- `scripts/run_active_30m_observation.py`

## DB Migration

`0116_fresh_seed_paper_candidate_integration.sql` adds:

- `fresh_seed_paper_path_runs`
- `fresh_seed_candidate_conversions`

## Runner Invocation Fix

The active 30m runner now calls official HTTP endpoints for the fresh identity, CLOB verification, watcher, fresh seed Paper path, position watchdog, Paper execution, and Paper exits.

It does not manually instantiate legacy runtime services with guessed constructor arguments.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/fresh-seed-paper-path`
- `POST /fresh-seed-paper-path/run`

The dashboard returns `mock_data=false` and exposes conversion counts, blockers, latest traces, and runner invocation status.

## Dialogue

`BrainDialogueService` now materializes source-backed Fresh Seed Paper Path messages for conversion success and blockers.

## Runtime Smoke

Smoke sequence:

1. SYSTEM OFF.
2. Verified mutating bridge run blocked with `SYSTEM_POWER_OFF`.
3. SYSTEM ON.
4. Ran bounded CLOB token book verification.
5. Ran bounded fresh seed Paper path bridge.
6. Materialized dialogue.
7. SYSTEM OFF.

Smoke result:

- OFF blocked status: `BLOCKED`
- CLOB status: `OK`
- CLOB books verified: 20
- CLOB snapshots created: 20
- trusted links created/refreshed: 10 new links
- bridge status: `OK`
- bridge seeds checked: 20
- converted candidates: 20
- Paper Intents created by official gate: 14
- bridge blockers: `MISSING_EXECUTABLE_PRICE=4`, `EXIT_NOT_READY=2`
- final system power: `OFF`

## Before / After Counts

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| fresh_candidate_seeds | 10 | 20 | +10 |
| BOOK_VERIFIED seeds | 8 | 20 | +12 |
| converted_candidates | 0 | 20 | +20 |
| paper_intents | 6 | 20 | +14 |
| paper_orders | 9 | 9 | 0 |
| paper_fills | 6 | 6 | 0 |
| paper_positions | 9 | 9 | 0 |
| paper_capital_ledger | 17 | 17 | 0 |
| live_orders | 0 | 0 | 0 |
| orders_v2 | 1 | 1 | 0 |
| fills_v2 | 1 | 1 | 0 |
| canonical positions | 0 | 0 | 0 |

Post-smoke conversion totals:

- conversions: 20
- thesis_created: 20
- risk_created: 20
- exit_created: 20
- eligibility_created: 20
- paper_intents_created_by_bridge: 14

## Sample Successful Conversion

- seed: `fresh_seed_691547_YES`
- market: `691547`
- side: `YES`
- candidate: `eligibility_exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`
- risk: `risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`
- exit: `exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`
- intent: `paper_intent_eligibility_exit_risk_thesis_fresh_seed_coord_fresh_seed_691547_YES`

## Sample Blocked Conversion

- seed: `fresh_seed_2169995_YES`
- market: `2169995`
- side: `YES`
- candidate created: yes
- risk/exit/eligibility created: yes
- Paper Intent: none
- blocker: `MISSING_EXECUTABLE_PRICE`

## Tests Run

- `tests/test_fresh_seed_paper_path.py -q`: 7 passed.
- `tests/test_v2_thesis_profile_service.py tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_service.py -q`: 23 passed.
- `tests/test_clob_token_book_verification.py tests/test_live_orderbook_watcher.py tests/test_open_position_watchdog.py -q`: 25 passed.
- `tests/test_paper_execution_safety.py tests/test_paper_no_live_safety.py -q`: 2 passed.
- `tests/test_v3_source_to_neuron_ingestion_wiring.py -q`: 8 passed.
- `tests/test_fresh_market_identity_gate.py -q`: 11 passed.

Initial stale test image run without workspace mount failed to import the new file. Rerun with `-v ${PWD}:/app` passed.

## Safety Checklist

- live enabled: no
- shadow enabled: no
- live orders delta: 0
- real orders delta: 0
- orders_v2 delta: 0
- fills_v2 delta: 0
- canonical positions delta: 0
- paper orders delta: 0
- paper fills delta: 0
- paper positions delta: 0
- paper capital ledger delta: 0
- secrets printed: no
- raw `.env` printed: no
- raw `docker compose config` printed: no

## Secret Guard

`scripts/safe_env_audit.py` result:

- status: `OK`
- raw values printed: `false`
- duplicate env keys: none
- dangerous duplicate overrides: none

## Remaining Risks

- The running `polybot_api` container image did not include the new file until rebuild/restart; smoke used a mounted one-off API container.
- Six converted candidates did not create Paper Intents for valid gate reasons.
- New Paper Intents are available for official Paper execution, but this phase did not execute them.

## Phase Status

GREEN.

Fresh verified seeds now enter the canonical Paper decision path, exact blockers are recorded, tests pass, and no direct order/fill/position mutation occurred.

Can run 30m active observation: YES, after rebuilding/restarting the API container so the route and service are available in the live runtime.
