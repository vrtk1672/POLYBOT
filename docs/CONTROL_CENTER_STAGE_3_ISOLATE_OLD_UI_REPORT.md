# Control Center V1.5 Stage 3 - Isolate Old UI Report

## Purpose

Reserve a safe, read-only `/control-center` path for POLYBOT Control Center V1.5 while preserving the existing legacy `/dashboard` experience.

## Current Reality Found

- `/dashboard` is served from `app/api/routes.py` by `dashboard_home()`.
- Dashboard HTML is embedded in `app/api/routes.py` through `_render_dashboard_html()`.
- Dashboard API routes are defined in `app/api/routes.py` under `/dashboard/api/*` and `/dashboard/api/v2/*`.
- `/control-center` did not already exist before this phase.
- No standalone frontend/static/template system was found.
- The safest file for this route is `app/api/routes.py`, matching the current dashboard route convention.
- Existing dashboard route tests cover `/dashboard` and V2 dashboard route behavior.
- Adding `/control-center` does not conflict with current routing.

## Files Changed

- `app/api/routes.py`

## Files Created

- `tests/test_control_center_route.py`
- `docs/CONTROL_CENTER_STAGE_3_ISOLATE_OLD_UI_REPORT.md`

## Route Added

- `GET /control-center`

## Route Preserved

- `GET /dashboard`
- Existing `/dashboard/api/*`
- Existing `/dashboard/api/v2/*`

## What Was Not Changed

- No frontend stack was created.
- No dependencies were installed or updated.
- No package or lockfile changed.
- No DB schema, migration, or persistence path changed.
- No runtime, scheduler, paper, shadow, live, execution, risk, exit, capital, order, fill, or position logic changed.
- No mutating control was exposed from `/control-center`.

## Tests Added

- `tests/test_control_center_route.py`
  - verifies `GET /control-center` returns 200
  - verifies the page includes `Control Center V1.5`
  - verifies the page includes `ROUTE_RESERVED` and `NOT_IMPLEMENTED`
  - verifies the page avoids fake status claims
  - verifies `GET /dashboard` still returns 200

## Tests Run

- `python -m uv run pytest tests/test_control_center_route.py -q`

## Exact Results

- `3 passed in 5.12s`

## Safety Checklist

- `/dashboard` preserved: YES
- `/control-center` added safely: YES
- Legacy UI deleted: NO
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

- `/control-center` is intentionally only a reserved placeholder.
- Stage 4 must define a Truth Contract before connecting the future Control Center to backend truth APIs.
- Existing mutating backend routes still exist outside this placeholder and must remain isolated from future UI controls until explicitly approved.

## Recommendation

GREEN if the targeted route test passes.

## Next Recommended Phase

Stage 4, Truth Contract.
