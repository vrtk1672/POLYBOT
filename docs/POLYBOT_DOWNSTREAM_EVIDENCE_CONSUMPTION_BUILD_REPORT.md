# POLYBOT Downstream Evidence Consumption Build Report

Phase: Step 3.5 of POLYBOT Life Injection

## Current Reality Found

Step 3 produced fresh orderbooks and trusted bindings, but downstream records did not consume the refreshed evidence. Before this phase, the dashboard reported no downstream recompute runs.

Baseline before OFF/ON smoke:

- orderbook_snapshots: 562
- signal_market_links: 101
- neuron_signal_bindings: 487
- coordinator_decisions: 488
- position_thesis_profiles: 194
- risk_decisions: 100
- exit_plans: 100
- paper_eligibility_candidates: 100
- no_trade_log: 100
- downstream_evidence_recompute_runs: 0
- paper_orders: 0
- paper_fills: table absent, treated as 0
- paper_positions: 0
- orders_v2: 1 historical row, unchanged
- live_orders: 0
- fills_v2: 1 historical row, unchanged
- positions: 0

Baseline blocker dashboard:

- MISSING_FRESH_ORDERBOOK: 485
- MISSING_SIGNAL_MARKET_BINDING: 530
- MISSING_SIDE: 870
- MISSING_MARKET_LINK: 0
- MISSING_MID_PRICE: 200
- THESIS_BLOCKED: 576
- RISK_NOT_APPROVED: 300
- EXIT_NOT_READY: 200

## Files Created

- `app/services/downstream_evidence_recompute.py`
- `app/db/migrations/0088_polybot_downstream_evidence_recompute.sql`
- `tests/test_downstream_evidence_recompute_service.py`
- `tests/test_downstream_evidence_recompute_scheduler.py`
- `tests/test_dashboard_downstream_recompute_truth.py`
- `docs/POLYBOT_DOWNSTREAM_EVIDENCE_CONSUMPTION.md`
- `docs/POLYBOT_DOWNSTREAM_EVIDENCE_CONSUMPTION_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`

## DB Changes

Added `downstream_evidence_recompute_runs` to record recompute attempts, checked/updated counts, before/after blocker counts, eligibility counts, safety deltas, metadata, and errors.

Migration applied with:

```powershell
docker compose run --rm migrate
```

Result: `0088_polybot_downstream_evidence_recompute.sql` applied.

## Runtime Integration Point

`MarketService.refresh()` now runs `DownstreamEvidenceRecomputeService.run_recompute(...)` after `EvidenceRefreshService.run_refresh(...)` and before paper-stage handling.

## Dashboard/API Changes

Added:

- `GET /dashboard/api/v2/downstream-recompute`

The endpoint reports DB/runtime truth with `mock_data=false`.

## Tests Added

- SYSTEM OFF prevents downstream recompute.
- SYSTEM ON calls thesis, risk, exit, eligibility, and no-trade in order.
- Recompute is idempotent per cycle.
- MarketService runs downstream recompute after evidence refresh.
- Dashboard endpoint exposes real downstream recompute truth.
- No-Trade refresh is called with `write_intents=false`.

## Tests Run

Targeted downstream recompute:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_downstream_evidence_recompute_service.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_dashboard_downstream_recompute_truth.py -q
```

Result: `5 passed, 1 warning in 33.07s`

System Power, Brain Mesh Activation, Evidence Refresh, runtime/state regressions:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py tests/test_evidence_refresh_service.py tests/test_evidence_refresh_scheduler.py tests/test_dashboard_evidence_refresh_truth.py tests/test_runtime_modes.py tests/test_state_governor.py -q
```

Result: `35 passed, 1 warning in 130.93s`

Risk, Exit, Eligibility, No-Trade, orderbook, binding regressions:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_service.py tests/test_v2_no_trade_ledger_service.py tests/test_v2_orderbook_snapshot_service.py tests/test_v2_signal_market_binding_service.py -q
```

Result: `28 passed in 144.94s`

Post-adjustment targeted service check:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_downstream_evidence_recompute_service.py -q
```

Result: `3 passed in 19.13s`

## Runtime Smoke Results

Runtime health:

- `GET /healthz`: 200, ready true
- `GET /dashboard/api/v2/downstream-recompute`: 200, `mock_data=false`

SYSTEM OFF smoke:

- Posted `/system/power/off`.
- Observed one scheduler interval.
- downstream_evidence_recompute_runs stayed 0.
- orderbook, signal, risk, exit, eligibility, no-trade, order, fill, and position counts stayed unchanged.

SYSTEM ON smoke:

- Posted `/system/power/on`.
- Observed runtime cycles.
- downstream recompute ran automatically twice.
- Latest run status: `OK`.
- Latest run checked/updated 100 thesis profiles, 100 risk decisions, 100 exit plans, 100 eligibility candidates, and 100 no-trade records.
- Latest downstream timestamps became fresh.
- execution deltas all remained 0.

Counts after ON smoke:

- orderbook_snapshots: 602
- signal_market_links: 107
- neuron_signal_bindings: 503
- coordinator_decisions: 504
- position_thesis_profiles: 202
- risk_decisions: 208
- exit_plans: 208
- paper_eligibility_candidates: 208
- no_trade_log: 208
- downstream_evidence_recompute_runs: 2
- paper_orders: 0
- paper_fills: table absent, treated as 0
- paper_positions: 0
- orders_v2: 1 historical row, unchanged
- live_orders: 0
- fills_v2: 1 historical row, unchanged
- positions: 0

Latest downstream timestamps:

- risk_decisions: 2026-05-29 23:22:49.311013+00
- exit_plans: 2026-05-29 23:22:49.450679+00
- paper_eligibility_candidates: 2026-05-29 23:22:49.746889+00
- no_trade_log: 2026-05-29 23:22:49.881493+00

## Blocker Counts

Latest run before/after:

- MISSING_FRESH_ORDERBOOK: 679 -> 694
- MISSING_SIGNAL_MARKET_BINDING: 582 -> 584
- MISSING_SIDE: 1094 -> 1110
- MISSING_MARKET_LINK: 0 -> 0
- MISSING_MID_PRICE: 328 -> 338
- THESIS_BLOCKED: 692 -> 700
- RISK_NOT_APPROVED: 600 -> 624
- EXIT_NOT_READY: 400 -> 416

## Root Cause If Blockers Did Not Decrease

Downstream recompute did consume refreshed evidence and updated current Risk, Exit, Eligibility, and No-Trade records. Blocker totals increased because Brain Mesh and downstream recompute introduced additional current candidates during the same ON observation window. Those new candidates are honestly blocked by missing side, missing/weak binding, thesis blocked state, missing risk approval, and exit-not-ready evidence.

Eligible candidates remain 0. Paper intents remain skipped by phase.

## Safety Confirmation

- SYSTEM OFF blocked recompute.
- SYSTEM ON ran recompute automatically.
- No paper intents were created by this phase.
- No order intents were created.
- No paper orders were created.
- No live orders were created.
- No fills were created.
- No positions were created.
- DATA_ONLY remained the runtime mode.
- Paper/shadow/live remained disabled.
- Risk/Exit/Eligibility were recomputed through existing gates only.

## Remaining Risks

- Side evidence remains the dominant blocker. It cannot be reduced without trusted unambiguous YES/NO evidence.
- Binding blockers remain where deterministic signal-market links are missing or weak.
- Fresh orderbook evidence exists, but not every active downstream candidate can consume it because some candidates still lack valid market/side/binding lineage.
- Candidate counts continue to grow under SYSTEM ON, so absolute blocker counts can increase even while recompute is working honestly.

## Next Recommended Step

Step 4 should either build the Brain Dialogue Feed or add a narrow side/binding evidence improvement phase that increases trusted YES/NO side evidence without defaulting or fabricating.
