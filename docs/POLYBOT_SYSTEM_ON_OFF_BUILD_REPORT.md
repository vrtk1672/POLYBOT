# POLYBOT System ON/OFF Build Report

Phase: `POLYBOT_SYSTEM_ON_OFF_CONTROL`

## Current Reality Found

- FastAPI, Postgres, Redis, runtime health, dashboard truth, State Governor, and scheduler were present.
- Internal mode was `DATA_ONLY`.
- No single operator-facing SYSTEM ON/OFF contract existed.
- Scheduler already gated refresh work through `StateGovernor.can_execute(RuntimeAction.COLLECT_DATA)`.

## Files Created

- `app/runtime/system_power.py`
- `app/services/system_power.py`
- `app/api/system_power_routes.py`
- `app/db/migrations/0085_polybot_system_on_off_control.sql`
- `tests/test_system_power.py`
- `tests/test_system_power_api.py`
- `tests/test_system_power_scheduler.py`
- `tests/test_dashboard_system_power_truth.py`
- `docs/POLYBOT_SYSTEM_ON_OFF_CONTROL.md`
- `docs/POLYBOT_SYSTEM_ON_OFF_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/runtime/contracts.py`
- `app/runtime/state_governor.py`
- `app/runtime/health_truth.py`
- `app/repositories/runtime_state_repository.py`

## DB Migration

`0085_polybot_system_on_off_control.sql`

- Adds current power columns to `system_state`.
- Adds `system_power_transitions` audit table.
- Defaults existing systems to `ON` so current runtime behavior is preserved until the operator turns it OFF.

## API Routes

- `GET /system/power`
- `POST /system/power/on`
- `POST /system/power/off`
- `GET /dashboard/api/v2/system-power`

## Dashboard Truth Changes

Dashboard now reports SYSTEM power, transition metadata, runtime allowed flags, component allowed/active/wired truth, and live/execution safety flags with `mock_data=false`.

## Scheduler / Runtime Changes

The scheduler did not need a direct call-site rewrite. It already asks the State Governor before `MarketService.refresh()`. The State Governor now treats `system_power=OFF` as a hard permission block, so scheduler cycles do not call refresh while OFF.

## Safety Checks

- SYSTEM ON does not enable live.
- SYSTEM ON does not enable shadow.
- SYSTEM ON does not create paper orders.
- SYSTEM OFF blocks autonomous runtime work.
- State Governor remains the permission authority.
- Risk, Exit, and Eligibility are not bypassed.

## Tests Added

- System power service tests.
- System power API tests.
- Scheduler gating tests.
- Dashboard system power truth tests.

## Tests Run

- `docker compose --profile test run --rm test python -m pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py -q`
  - Result: `9 passed, 1 warning`
- `docker compose --profile test run --rm test python -m pytest tests/test_runtime_modes.py tests/test_state_governor.py tests/test_v2_20_system_truth_checks.py tests/test_v2_20b_runtime_readiness.py tests/test_v2_18_dashboard_v2_api.py tests/test_v2_18_dashboard_v2_safety_guards.py -q`
  - Result: `27 passed, 1 warning`

Warnings were the existing Starlette TestClient deprecation warning.

## Runtime Smoke

- Built API and test images.
- Applied migration through the normal migrate service.
- Restarted API without wiping volumes.
- `GET /healthz`: `200`
- `GET /runtime/health` while OFF: `200`, `overall_status=SAFE_STOPPED`, `system_power=OFF`, `runtime_work_allowed=false`
- `GET /system/power` while OFF: `200`, `power=OFF`
- `GET /dashboard/api/v2/system-power` while OFF: `200`, `mock_data=false`
- `POST /system/power/off`: `200`, audited `ON -> OFF`
- OFF observation counts stayed unchanged: runtime cycles `9247`, market snapshots `92238/92240`, orderbooks `22`, neuron signals `147`, brain outputs `148`, paper/shadow/live orders `0`, fills `1`, positions `0`
- `POST /system/power/on`: `200`, audited `OFF -> ON`
- ON observation resumed current data path: runtime cycles `9247 -> 9249`, market snapshots `92238/92240 -> 92258/92260`
- Execution safety stayed unchanged: paper/shadow/live orders `0`, fills `1`, positions `0`

## Remaining Risks

- Some service registry rows still show decorative `RUNNING` statuses without heartbeats; this phase reports component truth separately and does not attempt a registry cleanup.
- Brain Dialogue Feed remains allowed when ON but not wired or active.
- Future Brain Mesh wiring must consult System Power before producing autonomous events.

## Next Recommended Step

Step 2: wire Brain Mesh cycle and dialogue feed behind the SYSTEM ON/OFF contract, with OFF remaining a hard autonomous-work block.

## Phase Status

GREEN. SYSTEM ON/OFF is implemented, audited, dashboard-visible, scheduler-enforced, and safety tests pass.
