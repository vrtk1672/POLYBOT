# POLYBOT Control Center V1.5 - Stage 20 Canonical API Owner Fix Report

Date: 2026-06-08

## 1. Short Summary

Stage 20 made Docker `polybot_api` the canonical owner of port 8000, rebuilt it with fresh Control Center code plus built React assets, and verified DB-backed Control Center truth from Docker Postgres.

## 2. Root Cause Confirmed

The Stage 19/Live Data diagnostic root cause was confirmed before fixing:

- Local Python PID `7388` owned `127.0.0.1:8000`.
- Command line: `python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Local Python had fresh Control Center routes but no `POLYBOT_DATABASE_URL` / `DATABASE_URL`.
- Docker `polybot_api` had DB env config but its image was stale and lacked `app/control_center` and `/dashboard/api/v2/control/*` routes.
- Docker Postgres was healthy and populated.

## 3. Fix Implemented

1. Rebuilt the frontend production assets with `npm run build`.
2. Updated `Dockerfile` to bake `frontend/control-center/dist` into the API image.
3. Stopped only the proven local uvicorn owner of `127.0.0.1:8000`.
4. Rebuilt only Docker `api` with `docker compose build api`.
5. Recreated only Docker `api` with `docker compose up -d api`.
6. Verified Docker API now contains fresh Control Center backend code, built frontend assets, DB config, and live DB-backed endpoint responses.

## 4. Files Created

- `docs/CONTROL_CENTER_STAGE_20_CANONICAL_API_OWNER_FIX_REPORT.md`

## 5. Files Changed

- `Dockerfile`

Change: added `COPY frontend/control-center/dist ./frontend/control-center/dist` so Docker API can serve the built Control Center app from `/control-center`.

## 6. Docker/API Ownership Before and After

| State | Owner | Evidence | Result |
| --- | --- | --- | --- |
| Before | Local Python + Docker publishers | PID `7388` command line was local `uvicorn app.main:app --host 127.0.0.1 --port 8000`; Docker also published `0.0.0.0:8000`. | Browser hit local Python, not canonical Docker API. |
| After | Docker publishers only | `Get-NetTCPConnection -LocalPort 8000` shows only Docker/WSL listeners (`wslrelay`, `com.docker.backend`); no `127.0.0.1:8000` local Python listener. | Docker API is canonical public owner. |
| After | `polybot_api` healthy | `docker compose ps` shows `polybot_api` up/healthy with `0.0.0.0:8000->8000/tcp`. | Good. |

## 7. DB Config Verification

| Check | Result |
| --- | --- |
| Docker API DB env names | `['DATABASE_URL', 'POLYBOT_DATABASE_URL']` |
| Docker API DB settings | `enabled=True`, `has_database_url=True`, `phase1=True` |
| Docker API DB connection | `service_health_count=30`, `event_log_count=506353` at check time |
| Secrets printed | NO. Only names/booleans/counts were printed. |

## 8. Endpoint Verification

All checks were run against `http://127.0.0.1:8000` after Docker API rebuild/recreate.

| Endpoint | Status | Source | Evidence | Meaning |
| --- | --- | --- | --- | --- |
| `/dashboard/api/v2/control/overview` | PARTIAL | `runtime_state_service_health_event_log` | `source_counts` includes `system_state=1`, `service_health=30`, `event_log=506355`, `risk_evidence_mesh_evaluations=1596`, `paper_positions=12`, `paper_daily_pnl=3`, `no_trade_log=11622`. | DB-backed overview working. |
| `/dashboard/api/v2/control/organs` | REAL | `service_health_heartbeat` | `count=30`, no DB-not-configured warning. | Service health is visible. |
| `/dashboard/api/v2/control/live-flow` | REAL | `event_log` | `count=50`, no DB-not-configured warning. | Event flow is visible. |
| `/dashboard/api/v2/control/logs` | REAL | `runtime_incidents_event_log_dlq` | Endpoint returned 200 and REAL. | Logs/errors can read DB-backed sources. |
| `/dashboard/api/v2/control/pnl-ledger` | PARTIAL | `paper_pnl_ledger` | Endpoint returned 200 and ledger-only warning, not DB-not-configured. | PnL remains truth-gated/ledger-first. |
| `/dashboard/api/v2/control/positions` | PARTIAL | `paper_positions` | Endpoint returned 200 and positions source warning, not DB-not-configured. | Position visibility reaches DB-backed service. |
| `/dashboard/api/v2/control/no-trade` | REAL | `no_trade_log` | Endpoint returned 200 and REAL. | No-Trade data visible. |
| `/dashboard/api/v2/control/risk-evidence` | REAL | `risk_evidence_mesh_evaluations` | Endpoint returned 200 and REAL. | Risk evidence visible. |
| `/dashboard/api/v2/control/full-monitor-run` | MISSING | `control_center:full_monitor_run` | `available=True`, `current/latest=null`, warning says no run started in this process. | Endpoint exists in Docker API; missing is expected until operator starts a run. |

The universal `database is not configured` failure is resolved.

## 9. UI Serving Verification

| Check | Result |
| --- | --- |
| `/control-center` status | 200 |
| HTML title | `POLYBOT Control Center Components` |
| React root present | YES |
| `/control-center/assets/` references present | YES |
| Browser smoke | `Command Center` loaded at `http://127.0.0.1:8000/control-center`; DB-not-configured warning absent. |

## 10. Tests / Commands Run

- `npm run build`
- `Stop-Process -Id 7388 -Force`
- `docker compose build api`
- `docker compose up -d api`
- `docker compose ps`
- `Get-NetTCPConnection -LocalPort 8000,55432,56379 -ErrorAction SilentlyContinue`
- `docker compose exec api python -c "... control_center_exists / dist_index_exists / routes_has_control_v2 ..."`
- `docker compose exec api python -c "... get_database_settings ..."`
- `docker compose exec api python -c "... service_health/event_log counts ..."`
- `Invoke-WebRequest http://127.0.0.1:8000/control-center`
- `Invoke-RestMethod` for all target Control Center endpoints.
- `$tests = Get-ChildItem -Path tests -Filter 'test_control_center_*.py' | ForEach-Object { $_.FullName }; .venv\Scripts\python.exe -m pytest @tests -q`
- `npm run typecheck`
- In-app browser smoke check against `http://127.0.0.1:8000/control-center`.

## 11. Exact Results

- `npm run build`: PASS; Vite chunk-size warning remains.
- Local uvicorn PID `7388`: stopped.
- `docker compose build api`: PASS.
- `docker compose up -d api`: PASS.
- `docker compose ps`: `polybot_api` up/healthy.
- Docker image freshness: `control_center_exists=True`, `dist_index_exists=True`, `routes_has_control_v2=True`.
- Docker DB settings: `enabled=True`, `has_database_url=True`.
- Docker DB connectivity: `service_health_count=30`, `event_log_count=506353`.
- `/control-center`: HTTP 200, built React root present.
- Key endpoint result: overview `PARTIAL`, organs `REAL`, live-flow `REAL`, logs `REAL`, no-trade `REAL`, risk-evidence `REAL`.
- Backend Control Center tests: `41 passed in 24.90s`.
- Frontend typecheck: PASS.
- Browser smoke: Command Center loaded; `database is not configured` absent.

## 12. Safety Checklist

| Check | YES / NO / UNKNOWN | Notes |
| --- | --- | --- |
| local uvicorn stopped or no longer owns 8000 | YES | PID `7388` stopped; no local `127.0.0.1:8000` Python listener remains. |
| Docker API owns 8000 | YES | Docker publisher is the only remaining public owner. |
| Docker API runs fresh code | YES | `app/control_center` and route text exist inside container. |
| Docker API has DB env config | YES | `DATABASE_URL`, `POLYBOT_DATABASE_URL` names visible. |
| DB data preserved | YES | No destructive command run; row counts remain populated. |
| no secrets printed | YES | Only env names/booleans/counts printed. |
| no DB writes/destructive commands | YES | No deletes/drops/truncates/volume removal. |
| no migrations | YES | No manual migration command was run; compose dependency started existing `migrate` service during recreate and it exited normally. |
| no live/paper/shadow activated | YES | No runtime mode changes; Docker logs show PAPER mode with live disabled. |
| no orders/fills/positions created | YES | No execution commands/actions run. |
| `/control-center` served | YES | HTTP 200, React root present. |
| overview DB connected | YES | Source counts from DB-backed tables. |
| organs DB connected | YES | REAL, count 30. |
| live-flow DB connected | YES | REAL, count 50. |
| tests/checks passed | YES | Backend Control Center tests and frontend typecheck passed. |

## 13. Remaining Risks

- Full Monitor Run remains memory-only and MISSING until started in the Docker API process.
- Some pages remain PARTIAL by truth contract, not by DB config failure.
- Vite bundle chunk-size warning remains.
- Docker `api` depends on baked `frontend/control-center/dist`; future UI changes require `npm run build` before `docker compose build api`.

## 14. Phase Status

GREEN.

Docker API is the canonical owner of port 8000, serves fresh Control Center code/assets, has DB config, and returns DB-backed Control Center truth.

## 15. Can Continue

YES.

## 16. Operator Start Commands

Canonical Docker start:

```powershell
cd C:\Server\apps\polybot
cd frontend\control-center
npm run build
cd C:\Server\apps\polybot
docker compose build api
docker compose up -d api
docker compose ps
Invoke-WebRequest http://127.0.0.1:8000/control-center -UseBasicParsing
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/overview
```

Operator URL:

```text
http://127.0.0.1:8000/control-center
```

