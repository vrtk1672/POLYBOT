# POLYBOT Paper Dashboard + Regression + 4h Soak Build Report

## Current Reality Found

Preflight against the running API/DB found:

- SYSTEM power: `ON`
- Runtime mode before Paper activation: `DATA_ONLY`
- Runtime mode for soak: `PAPER`
- Runtime health: `HEALTHY`
- Paper intents/orders/fills/positions before Paper-mode exit loop: `3/3/3/3`
- Open paper positions before Paper-mode exit loop: `3`
- Live orders: `0`
- Real orders / `orders_v2` baseline: `1`
- `fills_v2` baseline: `1`
- Canonical positions baseline: `0`
- Dashboard truth: `mock_data=false`

After switching the Governor to `PAPER`, the safe Paper Exit Loop closed the three open paper positions using existing exit evidence. Runner baseline at soak start:

- Paper intents/orders/fills/positions: `3/3/3/3`
- Open / closed paper positions: `0/3`
- Paper position closes: `3`
- Paper trade ledger rows: `6`
- Paper daily PnL rows: `1`
- Realized PnL: `23.25`
- Live orders: `0`
- Real/order/fill/canonical safety deltas: `0`

## Files Created

- `app/services/paper_dashboard_truth.py`
- `tests/test_paper_dashboard_truth.py`
- `tests/test_paper_runtime_regression.py`
- `tests/test_paper_soak_readiness.py`
- `tests/test_paper_pnl_reconciliation.py`
- `tests/test_paper_no_orphans_duplicates.py`
- `tests/test_paper_no_live_safety.py`
- `scripts/run_4h_technical_paper_soak.py`
- `scripts/run_4h_technical_paper_soak.ps1`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_READINESS.md`
- `docs/POLYBOT_PAPER_DASHBOARD_REGRESSION_SOAK_READINESS.md`

## Files Changed

- `app/api/routes.py`

## DB Migrations

None. This phase uses existing canonical Paper tables and safety tables.

## API Changes

Added:

- `GET /dashboard/api/v2/paper`
- `GET /dashboard/api/v2/paper/positions`
- `GET /dashboard/api/v2/paper/pnl`
- `GET /dashboard/api/v2/paper/soak-readiness`

## Rollback Notes

Remove the added routes from `app/api/routes.py`, delete `app/services/paper_dashboard_truth.py`, and delete the added tests/docs/scripts. No schema rollback is required.

## Safety

- No live execution path was changed.
- No runtime execution thresholds were loosened.
- No fake paper rows are inserted by the new dashboard or readiness code.
- Soak runner stops and posts SYSTEM OFF on critical safety breach.

## Test Results

Targeted Docker regression:

```text
42 passed, 1 warning in 203.18s
```

Command:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_paper_dashboard_truth.py tests/test_paper_runtime_regression.py tests/test_paper_soak_readiness.py tests/test_paper_pnl_reconciliation.py tests/test_paper_no_orphans_duplicates.py tests/test_paper_no_live_safety.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_brain_dialogue_api.py tests/test_dashboard_neuron_dialogue_api.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py
```

## Soak Start

- Started: `2026-05-30T23:39:59Z`
- Expected end: `2026-05-31T03:39:59Z`
- PID: `14268`
- Log: `logs/soak/4h_paper_soak_20260530T233959Z.log`
- Report: `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260530T233959Z.md`
- Status at handoff: `RUNNING`
