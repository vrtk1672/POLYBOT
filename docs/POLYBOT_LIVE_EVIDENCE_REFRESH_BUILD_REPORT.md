# POLYBOT Live Evidence Refresh Build Report

Phase: Step 3 of POLYBOT Life Injection

## Current Reality Found

Step 1 and Step 2 were present: SYSTEM ON/OFF existed, Brain Mesh Activation was wired into SYSTEM ON, and no execution path was enabled. Before this phase, orderbook evidence was stale, binding and side blockers remained, and evidence refresh was not part of the autonomous runtime cycle.

Baseline runtime counts before the ON smoke:

- orderbook_snapshots: 22
- latest orderbook_snapshot timestamp: 2026-05-28 23:10:16.549568+00
- signal_market_links: 20
- neuron_signal_bindings: 271
- neuron_signals: 307
- coordinator_decisions: 272
- position_thesis_profiles: 86
- risk_decisions: 100
- exit_plans: 100
- paper_eligibility_candidates: 100
- no_trade_log: 100
- evidence_refresh_runs: 0
- paper_orders: 0
- paper_fills: table absent, treated as 0
- paper_positions: 0
- orders_v2: 1 historical row, unchanged
- live_orders: 0
- fills_v2: 1 historical row, unchanged
- positions: 0

## Files Created

- `app/services/evidence_refresh.py`
- `app/db/migrations/0087_polybot_live_evidence_refresh.sql`
- `tests/test_evidence_refresh_service.py`
- `tests/test_evidence_refresh_scheduler.py`
- `tests/test_dashboard_evidence_refresh_truth.py`
- `docs/POLYBOT_LIVE_EVIDENCE_REFRESH.md`
- `docs/POLYBOT_LIVE_EVIDENCE_REFRESH_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`

## DB Changes

Added `evidence_refresh_runs` to record autonomous evidence refresh attempts, counts, blocker deltas, safety deltas, metadata, and error truth.

Migration applied with:

```powershell
docker compose run --rm migrate
```

Result: `0087_polybot_live_evidence_refresh.sql` applied.

## Runtime Integration Point

`MarketService.refresh()` now runs `EvidenceRefreshService.run_refresh(...)` after Brain Mesh Activation and before paper-stage safety handling. The service checks SYSTEM ON/OFF and StateGovernor before doing work.

## Dashboard/API Changes

Added:

- `GET /dashboard/api/v2/evidence-refresh`

The endpoint reports real DB/runtime truth with `mock_data=false`.

## Tests Added

- SYSTEM OFF prevents EvidenceRefreshService from running.
- SYSTEM ON allows EvidenceRefreshService to run.
- EvidenceRefreshService calls orderbook and binding refresh services.
- EvidenceRefreshService records a run summary.
- Trusted side evidence can recover side.
- Weak or missing side evidence does not default to YES/NO.
- MarketService invokes evidence refresh after Brain Mesh Activation.
- Dashboard endpoint returns real evidence refresh truth.

## Tests Run

Targeted evidence refresh:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_evidence_refresh_service.py tests/test_evidence_refresh_scheduler.py tests/test_dashboard_evidence_refresh_truth.py -q
```

Result: `6 passed, 1 warning in 40.53s`

Orderbook, binding, risk, exit, eligibility, runtime/state regressions:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_runtime_modes.py tests/test_state_governor.py tests/test_v2_orderbook_snapshot_service.py tests/test_v2_signal_market_binding_service.py tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py -q
```

Result: `38 passed in 184.13s`

System Power and Brain Mesh Activation regressions:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py -q
```

Result: `14 passed, 1 warning in 90.38s`

## Runtime Smoke Results

SYSTEM OFF smoke:

- Posted `/system/power/off`.
- Observed one scheduler window.
- Counts remained unchanged.
- evidence_refresh_runs stayed 0.
- orderbook_snapshots stayed 22.
- signal_market_links stayed 20.
- orders/fills/positions stayed unchanged.

SYSTEM ON smoke:

- Posted `/system/power/on`.
- Observed scheduler runtime.
- Evidence refresh ran automatically twice.
- Latest dashboard status: `OK`.
- Latest run checked 10 markets.
- Latest run created 20 orderbook snapshots.
- Latest run created 3 trusted binding links and rejected 47 weak/missing links.
- Latest run recovered 0 sides because no unambiguous trusted side evidence was available.
- Safety deltas all remained 0.

Counts after ON smoke:

- orderbook_snapshots: 62
- latest orderbook_snapshot timestamp: 2026-05-29 22:41:20.068851+00
- signal_market_links: 26
- neuron_signal_bindings: 287
- neuron_signals: 323
- coordinator_decisions: 288
- position_thesis_profiles: 94
- risk_decisions: 100
- exit_plans: 100
- paper_eligibility_candidates: 100
- no_trade_log: 100
- evidence_refresh_runs: 2
- paper_orders: 0
- paper_fills: table absent, treated as 0
- paper_positions: 0
- orders_v2: 1 historical row, unchanged
- live_orders: 0
- fills_v2: 1 historical row, unchanged
- positions: 0

## Blocker Counts

Before runtime refresh, dashboard blocker counts were:

- MISSING_FRESH_ORDERBOOK: 256
- MISSING_SIGNAL_MARKET_BINDING: 340
- MISSING_SIDE: 546

Latest run recorded:

- MISSING_FRESH_ORDERBOOK: 260 before, 260 after
- MISSING_SIGNAL_MARKET_BINDING: 355 before, 355 after
- MISSING_SIDE: 570 before, 570 after

The blocker counts did not decrease during this phase because downstream Risk, Exit, and Eligibility records were not re-evaluated in this step. Evidence refresh produced fresh snapshots and trusted links; downstream recomputation remains a later safe phase.

## Safety Confirmation

- SYSTEM OFF blocked autonomous evidence refresh.
- SYSTEM ON ran evidence refresh automatically.
- No paper orders were created.
- No live orders were created.
- No fills were created.
- No positions were created.
- Historical orders/fills stayed unchanged.
- Weak bindings were rejected.
- Side was not defaulted or invented.
- Dashboard used DB/runtime truth only.

## Remaining Risks

- Downstream Risk, Exit, and Eligibility still need a safe recomputation phase to consume the refreshed evidence.
- Side recovery remains blocked until trusted links provide unambiguous YES/NO side evidence.
- Binding refresh still rejects most candidates because evidence is weak, missing, stale, or ambiguous.

## Next Recommended Step

Step 4 should wire the Brain Dialogue Feed or a controlled downstream re-evaluation phase that consumes refreshed orderbook, binding, and side evidence without enabling execution.
