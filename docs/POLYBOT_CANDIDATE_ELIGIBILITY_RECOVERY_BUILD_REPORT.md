# POLYBOT Candidate Eligibility Recovery Build Report

Phase: Candidate Eligibility Root Cause Fix: SIDE + RISK + EXIT READINESS RECOVERY

## Purpose

Build a controlled recovery pass that consumes refreshed evidence and attempts to move candidates from blocked to eligible only when real SIDE, Risk, Exit, and Eligibility evidence supports it.

This phase also exposes exact candidate-level root cause when candidates remain blocked.

## Current Reality Found

Runtime before ON smoke:

- `paper_eligibility_candidates=3930`
- `eligible=0`
- `blocked=3930`
- candidates with `market_id=1990`
- candidates with `side=0`
- `lineage_trusted=3930`
- trusted bindings visible to candidates: `1456`
- candidates with fresh orderbook evidence: `39`
- complete thesis profiles: `0`
- `risk_approved=0`
- `exit_ready=0`
- `paper_intents=0`
- executable paper intents: `0`
- `paper_orders=0`
- `paper_fills=0`
- `paper_positions=0`
- open paper positions: `0`
- `live_orders=0`
- `orders_v2=1` historical row
- `fills_v2=1` historical row
- `positions=0`
- `candidate_eligibility_recovery_runs=0`

Top blockers before recovery:

- `EXIT_NOT_READY=3930`
- `MISSING_SIDE=3930`
- `RISK_BLOCKED=3930`
- `RISK_NOT_APPROVED=3930`
- `THESIS_NOT_COMPLETE=3930`
- `MISSING_FRESH_ORDERBOOK=2494`
- `MISSING_SIGNAL_MARKET_BINDING=2494`
- `MISSING_MARKET_ID=1940`

Root cause inspection:

- trusted `signal_market_links` with `matched_side`: `0`
- coordinator decisions with explicit side: `0`
- brain outputs with explicit side: `0`
- thesis profiles missing side: `4222`
- complete thesis profiles: `0`

## Files Created

- `app/db/migrations/0091_candidate_eligibility_recovery.sql`
- `app/services/candidate_eligibility_recovery.py`
- `tests/test_candidate_eligibility_recovery_service.py`
- `tests/test_dashboard_eligibility_recovery_truth.py`
- `tests/test_paper_simulation_permission_alignment.py`
- `docs/POLYBOT_CANDIDATE_ELIGIBILITY_RECOVERY.md`
- `docs/POLYBOT_CANDIDATE_ELIGIBILITY_RECOVERY_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/ingestion/market_service.py`
- `app/runtime/modes.py`
- `app/services/system_power.py`
- `app/services/paper_execution.py`
- `app/services/paper_intents.py`
- `app/repositories/paper_eligibility_repository.py`
- `app/services/paper_eligibility.py`
- `tests/test_downstream_evidence_recompute_scheduler.py`

## DB Migration

Applied migration:

- `0091_candidate_eligibility_recovery.sql`

New table:

- `candidate_eligibility_recovery_runs`

The table records run identity, cycle identity, SYSTEM power, candidate/risk/exit/eligibility counts, side recovery counts, paper intent/execution counts, safety deltas, top blockers, metadata, and errors.

## Runtime Integration Point

`MarketService.refresh()` now runs `CandidateEligibilityRecoveryService.run_recovery(...)` after `DownstreamEvidenceRecomputeService.run_recompute(...)` and before Paper Intent / Paper Execution / Paper Exit stages.

SYSTEM OFF blocks recovery before any recompute or paper-stage work.

## API / Dashboard Changes

Added:

- `GET /dashboard/api/v2/eligibility-recovery`
- `GET /dashboard/api/v2/paper-intent-recovery`

The eligibility recovery endpoint reports DB/runtime truth with `mock_data=false`.

## Recovery Contract

The recovery service:

- consumes refreshed binding, orderbook, thesis, risk, exit, and eligibility evidence
- recovers side only from trusted deterministic evidence
- reruns Risk Core, Exit Foundation, Paper Eligibility, Paper Intent Gate, and Safe Paper Execution
- records before/after blocker counts and safety deltas
- emits candidate-level root-cause traces

It does not fabricate side, risk approval, exit readiness, eligibility, paper intents, paper orders, fills, positions, or live actions.

## Side Recovery Rules

Valid side sources:

- trusted `signal_market_links.link_evidence_json.matched_side` of `YES` or `NO`
- explicit runtime coordinator metadata side/direction of `YES` or `NO`

Rejected side sources:

- missing side
- ambiguous side
- weak binding confidence
- stale/blocked binding
- fuzzy title matching alone
- dry-run evidence
- defaulting to `YES` or `NO`

## Runtime Smoke Results

Health after rebuild/restart:

- `GET /healthz`: `200`, ready true

OFF smoke:

- `POST /system/power/off`: `200`, power `OFF`
- observed one scheduler interval
- recovery runs stayed `0`
- `paper_intents=0`
- `paper_orders=0`
- `paper_fills=0`
- `paper_positions=0`
- `orders_v2=1` unchanged
- `fills_v2=1` unchanged
- `positions=0`
- `live_orders=0`

ON smoke:

- `POST /system/power/on`: `200`, power `ON`
- observed runtime cycle
- `candidate_eligibility_recovery_runs=1`
- latest recovery run status `OK`
- `candidates_checked=100`
- `sides_recovered=0`
- `risk_approved_before=0`, `risk_approved_after=0`
- `exit_ready_before=0`, `exit_ready_after=0`
- `eligible_before=0`, `eligible_after=0`
- `paper_intents_before=0`, `paper_intents_after=0`
- `paper_orders_delta=0`
- `paper_fills_delta=0`
- `paper_positions_delta=0`
- `live_orders_delta=0`
- `real_orders_delta=0`
- `no_valid_paper_intents_reason=MISSING_SIDE`
- `GET /dashboard/api/v2/eligibility-recovery`: `200`, `mock_data=false`

Runtime after ON smoke:

- `paper_eligibility_candidates=3938`
- `eligible=0`
- `blocked=3938`
- candidates with `side=0`
- trusted bindings visible to candidates: `1459`
- candidates with fresh orderbook evidence: `36`
- `risk_approved=0`
- `exit_ready=0`
- `paper_intents=0`
- executable paper intents: `0`
- `paper_orders=0`
- `paper_fills=0`
- `paper_positions=0`
- open paper positions: `0`
- `live_orders=0`
- `orders_v2=1` unchanged
- `fills_v2=1` unchanged
- `positions=0`

Top blockers after recovery:

- `EXIT_NOT_READY=3938`
- `MISSING_SIDE=3938`
- `RISK_BLOCKED=3938`
- `RISK_NOT_APPROVED=3938`
- `THESIS_NOT_COMPLETE=3938`
- `MISSING_FRESH_ORDERBOOK=2499`
- `MISSING_SIGNAL_MARKET_BINDING=2499`
- `MISSING_MARKET_ID=1944`

## Candidate Trace Summary

The latest trace inspected ten blocked candidates.

Common findings:

- all inspected candidates had `side=null`
- no inspected candidate had a paper intent
- some candidates had `market_id`, trusted binding, and fresh orderbook
- those candidates still remained blocked by `MISSING_SIDE`, `RISK_BLOCKED`, `RISK_NOT_APPROVED`, `THESIS_NOT_COMPLETE`, and `EXIT_NOT_READY`
- other candidates also lacked market, orderbook, or binding evidence

Smallest valid upstream fix:

- persist deterministic `matched_side=YES|NO` from trusted market/token-side evidence, or emit explicit coordinator/brain side metadata from real evidence

## Tests Added

- `tests/test_candidate_eligibility_recovery_service.py`
- `tests/test_dashboard_eligibility_recovery_truth.py`
- `tests/test_paper_simulation_permission_alignment.py`

## Tests Run

Host Python did not have pytest installed:

- `python -m pytest ...`: failed with `No module named pytest`

Docker test image was rebuilt:

- `docker compose --profile test build test test_migrate`

Targeted recovery tests:

- `docker compose --profile test run --rm test python -m pytest tests/test_candidate_eligibility_recovery_service.py tests/test_dashboard_eligibility_recovery_truth.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_paper_simulation_permission_alignment.py -q`
- Result: `10 passed, 1 warning in 52.51s`

Paper/risk/exit/system regressions:

- `docker compose --profile test run --rm test python -m pytest tests/test_paper_execution_service.py tests/test_paper_position_ledger.py tests/test_dashboard_paper_execution_truth.py tests/test_paper_execution_safety.py tests/test_v2_paper_intent_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_risk_core_service.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_runtime_modes.py tests/test_state_governor.py -q`
- Result: `53 passed, 1 warning in 214.10s`

Brain/evidence/downstream/exit-PnL regressions:

- `docker compose --profile test run --rm test python -m pytest tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py tests/test_evidence_refresh_service.py tests/test_evidence_refresh_scheduler.py tests/test_dashboard_evidence_refresh_truth.py tests/test_downstream_evidence_recompute_service.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_dashboard_downstream_recompute_truth.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_dashboard_paper_exit_pnl_truth.py tests/test_paper_exit_safety.py -q`
- Result: `28 passed, 1 warning in 142.30s`

4C/orderbook/binding/no-trade regressions:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_4c_regression_safety.py tests/test_v2_4c_mesh_truth_regression.py tests/test_v2_4c_dashboard_readiness_regression.py tests/test_v2_orderbook_snapshot_service.py tests/test_v2_signal_market_binding_service.py tests/test_v2_no_trade_ledger_service.py -q`
- Result: `57 passed, 1 warning in 164.22s`

Total verified:

- `148 passed`
- warnings were Starlette TestClient deprecation warnings

## Safety Verification

- SYSTEM OFF blocked recovery
- SYSTEM ON ran recovery automatically
- no fake side was created
- no weak side evidence was trusted
- no risk approval was forced
- no exit readiness was forced
- no eligibility was forced
- no paper intents were fabricated
- no paper orders/fills/positions were fabricated
- `paper_orders=0`
- `paper_fills=0`
- `paper_positions=0`
- `orders_v2=1` historical row unchanged
- `fills_v2=1` historical row unchanged
- `positions=0`
- `live_orders=0`

## Blockers Resolved

- Recovery is now automatic under SYSTEM ON.
- Candidate-level root-cause trace exists.
- Paper simulation permission is aligned with the strict paper intent pipeline while legacy paper engine/open paper position actions remain blocked in DATA_ONLY.

## Blockers Remaining

- `MISSING_SIDE`
- `RISK_BLOCKED`
- `RISK_NOT_APPROVED`
- `EXIT_NOT_READY`
- `THESIS_NOT_COMPLETE`
- `MISSING_FRESH_ORDERBOOK` for candidates without matched fresh orderbook
- `MISSING_SIGNAL_MARKET_BINDING` for candidates without trusted binding
- no valid paper intents in runtime

## Remaining Risks

The primary runtime gap is upstream side evidence production. Trusted links exist, and some candidates have fresh orderbook, but no trusted link currently carries deterministic `matched_side`.

Until that is fixed, eligibility should remain blocked.

## Next Recommended Step

Enhance Evidence Refresh / Signal Market Binding to persist deterministic side evidence from real Polymarket token-side mapping when available:

- `matched_side=YES|NO`
- source token/condition fields
- confidence
- timestamp
- evidence payload

Then rerun Candidate Eligibility Recovery and verify `MISSING_SIDE` decreases without defaulting or fabrication.

## Phase Status

YELLOW.

The recovery layer is implemented, tested, integrated, and safe. Runtime candidates remain blocked for a valid root cause: no deterministic side evidence exists yet.
