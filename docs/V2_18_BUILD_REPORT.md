# V2.18 Build Report - Dashboard V2

## Short Summary

V2.18 Dashboard V2 is implemented and verified. The repository has no standalone frontend framework, so the phase extends the existing FastAPI-served dashboard into a real operator cockpit with DB/runtime truth envelopes, V2 page APIs, stale-data handling, a dark premium UI shell, live-flow visualization, and locked advanced controls.

No trading logic, orders, order intents, exits, live requests, external sends, or external balance mutations were added.

## Frontend Stack Detected

- No `package.json`.
- No React / Next / Vite / Tailwind frontend.
- Existing dashboard is served from FastAPI via `app/api/routes.py`.
- V2.18 extends the existing embedded HTML/CSS/JavaScript dashboard.

## Files Created

- `app/services/query/dashboard_v2_query_service.py`
- `tests/test_v2_18_dashboard_v2_api.py`
- `tests/test_v2_18_dashboard_v2_safety_guards.py`
- `docs/V2_18_DASHBOARD_V2.md`
- `docs/V2_18_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## API Routes

Added:

- `GET /dashboard/api/v2/overview`
- `GET /dashboard/api/v2/events`
- `GET /dashboard/api/v2/risk`
- `GET /dashboard/api/v2/engines`
- `GET /dashboard/api/v2/ai`
- `GET /dashboard/api/v2/no-trade`
- `GET /dashboard/api/v2/memory`
- `GET /dashboard/api/v2/market`
- `GET /dashboard/api/v2/opportunities`
- `GET /dashboard/api/v2/capital`
- `GET /dashboard/api/v2/execution`
- `GET /dashboard/api/v2/exits`
- `GET /dashboard/api/v2/news`
- `GET /dashboard/api/v2/social`
- `GET /dashboard/api/v2/whales`
- `GET /dashboard/api/v2/live-flow`
- `GET /dashboard/api/v2/settings`

Each endpoint returns `status`, `updated_at`, `stale`, `stale_reason`, `data_source`, `data_confidence`, `errors`, and `data`.

## Pages / Components Added

The existing `/dashboard` page now includes:

- App shell
- Sidebar navigation
- Top status bar
- Status pills
- Stale/degraded banner
- Metric panels
- Flow nodes
- Event/feed rows
- JSON truth panels
- Locked Advanced Control panel
- Reason/confirmation UI for unavailable controls

Pages:

- Overview
- Live Flow
- Markets
- Opportunities
- Engines
- Risk
- Capital
- Positions
- Exits
- News
- Social
- Whales
- AI Brain
- Memory
- No-Trade
- Events
- Advanced Control

## Dashboard Design Notes

The UI uses a dark graphite/black base, cyan/blue/violet accents, compact high-contrast panels, controlled pulse indicators, stale banners, and sharp operational hierarchy. It avoids fake values and shows `NO_DATA`, `STALE`, or `INSUFFICIENT_DATA` where source truth is sparse.

## Advanced Control Behavior

V2.18 does not add write/control endpoints.

The control panel is locked and requires:

- unlock
- actor
- reason
- explicit confirmation
- audit-capable backend endpoint

Trying the visible control without a reason is blocked in the UI. Even with reason/confirmation, Dashboard V2 blocks because no safe write endpoint exists in this phase.

## Tests Run And Exact Results

Targeted no-DB:

- `$files = (Get-ChildItem tests\test_v2_18_*.py).FullName; python -m uv run pytest $files -q`
- Result: `5 passed, 3 skipped in 17.89s`

Targeted DB-backed:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $env:PHASE1_PERSISTENCE_ENABLED='true'; $files = (Get-ChildItem tests\test_v2_18_*.py).FullName; python -m uv run pytest $files -q`
- Result: `8 passed in 55.84s`

Regressions:

- V2.17: `20 passed in 44.85s`
- V2.16: `23 passed, 1 skipped in 52.47s`
- V2.15: `19 passed, 1 skipped in 42.34s`
- V2.14: `17 passed, 4 skipped in 16.85s`
- Runtime: `8 passed, 19 skipped in 24.24s`

Full suite:

- `python -m uv run pytest -q`
- Result: `362 passed, 398 skipped in 77.44s`

## Frontend Build / Lint / Test Result

No frontend package manager stack exists. There is no `package.json`, so no `npm test`, `npm run lint`, or `npm run build` command is applicable.

Python compile check:

- `python -m uv run python -m py_compile app\api\routes.py app\services\query\dashboard_v2_query_service.py`
- Result: passed.

## Runtime Verification Results

Docker/Postgres:

- `polybot_phase1_pg` running on `127.0.0.1:55432`.
- TCP check to `127.0.0.1:55432` succeeded.

Migration:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- Result: `No pending migrations.`

Runtime:

- Canonical script started the runtime but exceeded the shell timeout while the process continued booting.
- FastAPI became available on `127.0.0.1:8000`.
- A direct Python restart was also used after the final HTML query-param patch.
- Runtime state verified as `DATA_ONLY`.
- Permissions verified: `can_create_live_orders=false`, `can_open_paper_positions=false`, `can_create_shadow_orders=false`, `can_close_positions=false`.

Verified endpoints:

- `/healthz` OK
- `/runtime/state` OK
- `/runtime/health` OK
- `/dashboard/api/v2/overview` OK
- `/dashboard/api/v2/events` OK
- `/dashboard/api/v2/risk` OK
- `/dashboard/api/v2/engines` OK
- `/dashboard/api/v2/ai` OK on retry
- `/dashboard/api/v2/no-trade` OK
- `/dashboard/api/v2/memory` OK
- `/dashboard/api/v2/market` OK
- `/dashboard/api/v2/opportunities` OK
- `/dashboard/api/v2/capital` OK
- `/dashboard/api/v2/execution` OK
- `/dashboard/api/v2/exits` OK
- `/dashboard/api/v2/news` OK
- `/dashboard/api/v2/social` OK
- `/dashboard/api/v2/whales` OK
- `/dashboard/api/v2/live-flow` OK
- `/dashboard/api/v2/settings` OK

Note: one `/dashboard/api/v2/ai` request timed out during a runtime refresh, then returned `200` with `status=NO_DATA`, `stale=true`, and `data_confidence=0.35` on retry.

## Manual Smoke Results

Browser smoke:

- Opened `http://127.0.0.1:8000/dashboard`.
- Overview loaded.
- Sidebar pages rendered.
- Runtime mode displayed as `DATA_ONLY`.
- Live certified displayed as `NO`.
- Stale/degraded states displayed where applicable.
- Opened `http://127.0.0.1:8000/dashboard?page=settings`.
- Advanced Control panel loaded locked.
- Attempted the visible control without reason/confirmation.
- UI blocked the action with: `Blocked: unlock, reason, and explicit confirmation are required.`

DB/order mutation smoke:

- `live_orders=3`
- `paper_orders=3`
- `orders_v2=5`
- `exit_intents=7`
- `no_trade_log=4`
- Dashboard V2 tests confirmed read-only requests did not mutate these tables.

## Safety Checklist

- Dashboard shows real DB/runtime data: YES
- No mock data: YES
- Stale data warning shown: YES
- Missing data shown honestly: YES
- Advanced control requires unlock: YES
- Advanced control requires reason: YES
- Dangerous control requires confirmation: YES
- Control actions audited when tested: N/A, no write control endpoint exists in V2.18
- Kill reflected instantly if tested: N/A, kill control not exposed in V2.18
- Dashboard cannot create orders: YES
- Dashboard cannot create order intents: YES
- Dashboard cannot create live exits: YES
- Dashboard cannot mutate external balances: YES
- Live remains disabled: YES
- State Governor respected: YES
- Risk Governor respected: YES
- UI is readable and operational: YES
- UI is high-quality/futuristic: YES

## Remaining Risks

- The frontend is intentionally an embedded FastAPI shell because that is the actual repository stack; a dedicated SPA can be considered later if the repo adds a frontend toolchain.
- Some dashboard endpoints can be slow while the current single-process runtime performs market refresh work.
- Advanced controls are intentionally non-operational until a future phase exposes safe audited backend endpoints.

## Phase Status

GREEN.

## Can Move To V2.19 Feedback / Learning Loop

YES.
