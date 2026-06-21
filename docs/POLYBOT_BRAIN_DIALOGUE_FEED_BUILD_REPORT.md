# POLYBOT Brain Dialogue Feed Build Report

## Purpose

Implement a factual Brain Dialogue Feed and System Life Screen so operators can
see POLYBOT components speaking from real runtime evidence.

## Current Reality Found

- SYSTEM ON/OFF exists and runtime was ON.
- Run/source records exist for MarketService, DataFoundation, Brain Mesh
  Activation, Evidence Refresh, Side Evidence, Downstream Recompute, Post-Side
  Risk/Exit Recovery, Risk, Exit, Eligibility, Paper Intent, Paper Execution,
  Paper Exit, PnL, and No-Trade.
- Runtime before migration had `brain_dialogue_events=0`.
- Runtime paper truth before smoke: `paper_intents=3`, `paper_orders=3`,
  `paper_fills=3`, `paper_positions=3`, `live_orders=0`, `real_orders=0`.
- `service_health` contains decorative RUNNING rows, so System Life activity
  must not trust service registry alone.

## Files Created

- `app/db/migrations/0094_brain_dialogue_feed_system_life.sql`
- `app/services/brain_dialogue.py`
- `tests/brain_dialogue_fixtures.py`
- `tests/test_brain_dialogue_service.py`
- `tests/test_brain_dialogue_materialization.py`
- `tests/test_dashboard_brain_dialogue_api.py`
- `tests/test_system_life_screen_api.py`
- `tests/test_brain_dialogue_on_off_safety.py`
- `tests/test_component_silence_detection.py`
- `docs/POLYBOT_BRAIN_DIALOGUE_FEED.md`
- `docs/POLYBOT_BRAIN_DIALOGUE_FEED_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/services/system_power.py`
- `tests/test_dashboard_system_power_truth.py`

## DB Changes

Added `brain_dialogue_events` with:

- source record linkage
- component/event/status/message fields
- candidate/risk/exit/eligibility/paper linkage fields
- evidence and next-required-evidence JSON
- duplicate guard on `source_table + source_record_id + event_type`

## Runtime Integration

`MarketService.refresh()` invokes `BrainDialogueService.materialize_recent()` at
the end of the safe cycle after Paper Exit Loop / PnL. The service checks
SYSTEM power and materializes normal component dialogue only when SYSTEM ON is
active.

## API / Dashboard

- `GET /dashboard/api/v2/brain-dialogue`
- `GET /dashboard/api/v2/system-life`
- `GET /dashboard/api/v2/brain-dialogue/{candidate_id}`

All return `mock_data=false` and are read-only.

## Components Supported

- SystemPower
- MarketService
- DataFoundation
- Brain Mesh Activation
- Evidence Refresh
- Side Evidence
- Downstream Evidence Recompute
- Risk Exit Readiness Recovery
- Risk Gate
- Exit Cortex
- Eligibility Gate
- Paper Intent Gate
- Paper Execution
- Paper Exit Loop
- PnL Ledger
- No-Trade Ledger

## Components Not Yet Supported

- Dashboard Truth dialogue is not independently wired because no dashboard-run
  source table exists. The System Life endpoint reports it as `wired=false`
  instead of inventing activity.

## Tests Added

Six focused test files covering service materialization, dedupe, APIs, ON/OFF
safety, read-only behavior, and silence detection.

## Tests Run

- New dialogue tests: `12 passed`.
- System/runtime regressions: `24 passed`.
- Brain/evidence/downstream regressions: `16 passed`.
- Side/risk/eligibility regressions: `18 passed`.
- Paper execution/exit/PnL regressions: `22 passed`.

One earlier broad regression command timed out and produced no usable result.
One outdated system-power expectation was updated from `brain_dialogue_feed.wired=false`
to `true` after this feature wired the feed.

## Runtime Smoke

- Rebuilt and restarted `migrate` + `api` without wiping volumes.
- `GET /healthz`: 200.
- `GET /runtime/health`: 200.
- `GET /dashboard/api/v2/brain-dialogue`: 200.
- `GET /dashboard/api/v2/system-life`: 200.
- OFF observation: `brain_dialogue_events` stayed at 0 normal events.
- ON observation: dialogue materialized automatically during scheduler cycles.
- Final runtime: `brain_dialogue_events=878`.
- Dashboard read duplicate check: count stayed `878 -> 878`.
- Recent dialogue: `431` events from `15` components in the last 10 minutes.
- System Life: `active_components=15`, `silent_components=2`, `stale_components=1`.

## Sample Real Dialogue

- MarketService: runtime cycle status and stage flags.
- DataFoundation: persisted DB-backed market/completeness event.
- Brain Mesh Activation: evidence, brain outputs, coordinator decisions, thesis counts.
- Evidence Refresh: markets checked, orderbooks, bindings, sides.
- Side Evidence: links/candidates checked and sides recovered/rejected.
- Risk Gate: APPROVE from real `risk_decisions`.
- Exit Cortex: COMPLETE from real `exit_plans`.
- Eligibility Gate: ELIGIBLE from real `paper_eligibility_candidates`.
- Paper Intent Gate: run summary from `paper_intent_runs`.
- Paper Execution: run summary from `paper_execution_runs`.
- Paper Exit Loop: open-position check from `paper_exit_loop_runs`.
- PnL Ledger: daily PnL from `paper_daily_pnl`.
- No-Trade Ledger: blocker reasons from `no_trade_log`.

## Safety Confirmation

- No live orders created.
- No real orders created.
- No paper artifacts are created by dialogue.
- Dashboard reads are read-only.
- SYSTEM OFF blocks normal dialogue generation.
- Component activity is based on real source records, not decorative service health.

## Remaining Risks

- The API response includes raw source payloads and can be large at high limits.
- Dashboard Truth needs an independent source/run record before it can speak.
- PnL Ledger can appear stale if no paper PnL update occurred recently.

## Next Recommended Step

Paper Dashboard + Regression + Soak Readiness.
