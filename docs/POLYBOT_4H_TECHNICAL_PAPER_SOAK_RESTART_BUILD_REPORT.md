# POLYBOT 4h Technical Paper Soak Restart Build Report

## Current Reality Found

- Existing API stack healthy on `http://127.0.0.1:8000`.
- No old soak runner was active before preflight.
- SYSTEM OFF was set before validation.
- Runtime mode is PAPER.
- Preflight dashboard endpoints returned 200.
- Dashboard endpoints reported `mock_data=false`.
- Active paper lineage was clean.
- Raw legacy paper rows remain quarantined and visible for audit.

## Small In-Scope Fix

The soak runner was hardened before restart:

- Added `/dashboard/api/v2/system-life` endpoint sampling.
- Added mock dashboard data hard-stop detection.
- Added raw quarantine growth hard stops.
- Added raw quarantine counts to the runner baseline so stable quarantined rows do not trigger false RED.
- Added tests for raw quarantine guard behavior.

## Files Changed

- `scripts/run_4h_technical_paper_soak.py`
- `tests/test_soak_runner_paper_consistency_guards.py`

## Files Created

- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_RESTART.md`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_RESTART_BUILD_REPORT.md`
- `logs/soak/4h_paper_soak_20260531T073303Z.log`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260531T073303Z.md`

Launcher smoke artifacts also exist and are not active soak reports:

- `logs/soak/4h_paper_soak_20260531T072619Z.log`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260531T072619Z.md`
- `logs/soak/4h_paper_soak_20260531T072645Z.log`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260531T072645Z.md`

## Preflight Endpoint Result

- `/healthz`: 200
- `/runtime/health`: 200
- `/system/power`: 200
- `/dashboard/api/v2/paper`: 200, `mock_data=false`
- `/dashboard/api/v2/paper/positions`: 200, `mock_data=false`
- `/dashboard/api/v2/paper/pnl`: 200, `mock_data=false`
- `/dashboard/api/v2/paper/soak-readiness`: 200, `mock_data=false`
- `/dashboard/api/v2/brain-dialogue`: 200, `mock_data=false`
- `/dashboard/api/v2/neuron-dialogue`: 200, `mock_data=false`
- `/dashboard/api/v2/system-life`: 200, `mock_data=false`

## Preflight Counts

- paper_intents: 3
- paper_orders: 6
- paper_fills: 3
- paper_positions: 6
- open_paper_positions: 0
- active_open_paper_positions: 0
- closed_paper_positions: 3
- paper_position_closes: 3
- paper_trade_ledger: 6
- paper_daily_pnl: 2
- positions_without_fills_count: 0
- raw_positions_without_fills_count: 3
- positions_without_open_ledger_count: 0
- raw_positions_without_open_ledger_count: 3
- quarantined_paper_positions_count: 3
- paper_lineage_consistency_status: OK
- paper_lineage_readiness_status: OK
- soak_readiness_status: GREEN
- can_start_4h_soak: true
- brain_dialogue_events: 12243
- neuron_dialogue_events: 3980
- components_speaking: 1
- components_silent: 16
- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical_positions: 0

## Tests

First required test run failed due invocation only: mounting `tests` alone hid the `scripts` package from the container import path.

Valid test runs:

- `pytest tests/test_soak_runner_paper_consistency_guards.py -q`: 6 passed, 1 warning.
- Full targeted regression command: 61 passed, 2 warnings.

Full targeted command:

```powershell
docker compose run --rm -T -v ${PWD}:/app api python -m pytest tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py tests/test_paper_dashboard_truth.py tests/test_soak_runner_paper_consistency_guards.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_paper_pnl_reconciliation.py tests/test_paper_no_live_safety.py tests/test_paper_no_orphans_duplicates.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_brain_dialogue_service.py tests/test_brain_dialogue_materialization.py tests/test_dashboard_brain_dialogue_api.py tests/test_neuron_dialogue_sources.py tests/test_neuron_dialogue_coverage_service.py tests/test_dashboard_neuron_dialogue_api.py -q
```

## Runtime Soak

- soak_id: `20260531T073303Z`
- pid: `11112`
- status: RUNNING at handoff
- log: `logs/soak/4h_paper_soak_20260531T073303Z.log`
- report: `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260531T073303Z.md`
- first sample: safe

First sample safety:

- endpoint_errors: none
- mock_data_endpoints: none
- paper_lineage_consistency_status: OK
- paper_lineage_readiness_status: OK
- positions_without_fills_count: 0
- positions_without_open_ledger_count: 0
- raw_positions_without_fills_count: 3
- raw_positions_without_open_ledger_count: 3
- quarantined_paper_positions_count: 3
- duplicate_intent_orders_count: 0
- duplicate_order_fills_count: 0
- duplicate_fill_positions_count: 0
- executed_intents_reexecuted_count: 0
- orphan_positions_count: 0
- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical_positions: 0

## Remaining Risks

- The active 4h soak is still running; final status is not known.
- Runtime scheduler health in first sample reported `BLOCKED_BY_MODE` in the paper dashboard latest-runtime field, while SYSTEM ON and PAPER permissions were active. This is a non-stop warning to watch during samples.
- Do not proceed to 12h until this run completes GREEN and is reviewed.
