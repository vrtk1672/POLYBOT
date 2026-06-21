# Control Center V1.5 Stage 4 - Truth Contract Report

## Purpose

Create the canonical response language for future Control Center data without building UI screens or Stage 5 read-only APIs.

## Current Reality Found

- `/dashboard` remains the existing FastAPI-served dashboard in `app/api/routes.py`.
- `/control-center` remains the Stage 3 reserved placeholder.
- Dashboard V2 uses an existing envelope-like shape from `DashboardV2QueryService`: `status`, `updated_at`, `stale`, `stale_reason`, `data_source`, `data_confidence`, `errors`, `page`, and `data`.
- Existing dashboard tests verify truth envelopes, no mock data, locked advanced controls, and no order-table mutation.
- `app/services/truth_state.py` already contains persisted runtime truth-state vocabulary and DB-backed truth registry behavior, but it is not a Control Center response envelope.
- No existing `app/control_center` package existed before this phase.
- The safest shared model/helper location is `app/control_center/truth_contract.py`.
- The safest optional route location is `app/api/routes.py`, next to the existing dashboard V2 routes.
- The safest test location is `tests/test_control_center_truth_contract.py`.

## Files Created

- `app/control_center/__init__.py`
- `app/control_center/truth_contract.py`
- `tests/test_control_center_truth_contract.py`
- `docs/CONTROL_CENTER_STAGE_4_TRUTH_CONTRACT_REPORT.md`

## Files Changed

- `app/api/routes.py`

## APIs Added

- `GET /dashboard/api/v2/control/truth-contract`

This endpoint is read-only, does not call DB/runtime services, and returns a `NOT_IMPLEMENTED` Truth Contract envelope.

## Contract Fields

- `status`
- `source`
- `last_updated`
- `stale_after_seconds`
- `truth_state`
- `data`
- `warnings`
- `errors`

## Status Values

- `REAL`
- `STALE`
- `MISSING`
- `ERROR`
- `LOCKED`
- `NOT_IMPLEMENTED`
- `PARTIAL`

## Truth State Values

- `ACTIVE_FRESH`
- `LAST_KNOWN`
- `HISTORICAL_ONLY`
- `REFRESH_REQUIRED`
- `UNKNOWN`

## Validation Rules

- `REAL`, `STALE`, and `PARTIAL` require `source`.
- `HISTORICAL_ONLY` truth requires `source`.
- `REAL` cannot use `truth_state=UNKNOWN`.
- `STALE` requires `last_updated` and `stale_after_seconds`.
- `MISSING` requires at least one warning or error.
- `ERROR` requires at least one error.
- `NOT_IMPLEMENTED` must not include data.
- `LOCKED` requires at least one warning or error.
- `warnings` and `errors` must always be arrays.
- `data` must always be an object/dict.

## Domain Guards

- PnL requires a ledger/capital source.
- Health requires a heartbeat/service_health source.
- Decision requires an evidence/source source.
- Candidate requires a truth_state.
- Runtime status requires runtime/source/state source.
- Positions require canonical position source.
- Events require event source.

## Tests Added

- `tests/test_control_center_truth_contract.py`
  - validates a correct `REAL` envelope
  - rejects `REAL` without source
  - rejects `REAL` with `UNKNOWN` truth state
  - rejects `ERROR` without errors
  - verifies `NOT_IMPLEMENTED` does not include data
  - verifies warnings/errors arrays and data object requirements
  - verifies PnL, health, decision, and candidate guards
  - verifies `/dashboard/api/v2/control/truth-contract`
  - verifies `/dashboard` and `/control-center` still load

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_control_center_truth_contract.py -q`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_route.py -q`
- `.venv\Scripts\python.exe -m py_compile app\control_center\truth_contract.py app\api\routes.py tests\test_control_center_truth_contract.py tests\test_control_center_route.py`

## Exact Results

- `tests/test_control_center_truth_contract.py`: `9 passed in 4.56s`
- `tests/test_control_center_route.py`: `3 passed in 5.22s`
- Python compile check: passed

## Safety Checklist

- `/dashboard` preserved: YES
- `/control-center` preserved: YES
- Full UI built: NO
- Frontend dependencies installed: NO
- Package/lockfile changed: NO
- DB writes: NO
- Migrations: NO
- Runtime started: NO
- Paper/shadow/live activated: NO
- Orders/fills/positions created: NO
- Secrets printed: NO
- Dangerous controls exposed: NO
- Fake green introduced: NO
- Fake PnL introduced: NO
- Fake runtime status introduced: NO

## Remaining Risks

- Existing Dashboard V2 endpoints have not been migrated to this contract yet; that belongs to future Stage 5+ work.
- The demo endpoint is intentionally `NOT_IMPLEMENTED` and exposes contract shape only.
- Future domain endpoints must call the domain guards before surfacing PnL, health, decisions, candidates, runtime status, positions, or events.

## Next Recommended Phase

Stage 5, Backend Read-Only Control APIs.
