# POLYBOT Control Center V1.5 Live Data Root Cause Report

Date: 2026-06-08

## 1. Short Summary

The Control Center looks loaded but not alive because `http://127.0.0.1:8000` is being served by a local Python `uvicorn app.main:app` process with no database URL, while the healthy Docker API has database config but is running a stale image that does not contain the Control Center V1.5 backend modules/routes.

## 2. Evidence Matrix

| Area | Finding | Evidence | Impact |
| ---- | ------- | -------- | ------ |
| UI serving | `/control-center` is currently served as the built React app on host port 8000. | `Invoke-WebRequest /control-center`: status 200, title `POLYBOT Control Center Components`, has `<div id="root"></div>`, placeholder false. | Frontend shell is loading correctly. |
| Frontend API base | Frontend uses same-origin read-only paths. | `controlCenterEndpoints.ts` maps to `/dashboard/api/v2/control/*`; client uses `method: "GET"`. | Browser calls the same process serving `/control-center`. |
| Host port 8000 owner | IPv4 `127.0.0.1:8000` is owned by local Python PID 7388. | `Get-CimInstance`: `"python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. | Operator traffic hits local Python first, not Docker API. |
| Docker port 8000 | Docker also publishes 8000 through `com.docker.backend`/`wslrelay`. | `docker compose ps`: `polybot_api` maps `0.0.0.0:8000->8000`; `Get-NetTCPConnection` shows Docker listeners plus local Python listener. | Multiple processes conflict/confuse diagnosis. |
| Local DB config | Local repo/runtime has no DB URL configured. | `.env` names do not include `POLYBOT_DATABASE_URL` or `DATABASE_URL`; local `.venv` diagnostic says `enabled=False`, `has_database_url=False`. | Local Control Center APIs truthfully return "database is not configured." |
| Docker DB config | Docker API has DB env names. | `docker compose exec api python -c ...` lists `['DATABASE_URL', 'POLYBOT_DATABASE_URL']`; settings check says `enabled=True`, `has_database_url=True`. | Docker API should be DB-capable. |
| Docker code freshness | Docker API image is stale and lacks Control Center V1.5 code. | `docker compose exec api python`: `/app/app/control_center` does not exist; `/app/app/api/routes.py` does not contain `dashboard/api/v2/control`; container-local requests return 404. | Docker API cannot serve Control Center V1.5 endpoints despite having DB config. |
| DB schema | Docker Postgres schema is present and broad. | `\dt` shows 323 public tables. Required tables mostly exist. | The database itself is not the primary blocker. |
| Runtime data | Important tables are populated. | `event_log=506279`, `service_health=30`, `system_state=1`, `paper_positions=12`, `no_trade_log=11622`, `risk_evidence_mesh_evaluations=1596`. | Once the right API process reaches this DB, UI should become much more alive. |
| Full Monitor Run | Status is available but no current/latest in local process. | `/full-monitor-run`: `available=True`, `current=null`, `latest=null`, warning "No Full Monitor Run has been started in this process." | In-memory run store has no run for this local process. |

## 3. Process / Port Analysis

Port 8000 is conflicted.

- `polybot_api` is up and healthy in Docker, exposing `0.0.0.0:8000->8000`.
- Windows also has a local Python process on `127.0.0.1:8000`.
- Exact local process: PID 7388, command line `"C:\Users\harel\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Docker-related listeners are `com.docker.backend.exe` and `wslrelay.exe`.
- Since the operator opens `http://127.0.0.1:8000/control-center`, the local Python listener is the process returning the new React UI and the `database is not configured` envelopes.

Container-local evidence proves the Docker API is not the same application version:

- From inside `polybot_api`, `http://127.0.0.1:8000/dashboard/api/v2/control/overview` returns 404.
- `/app/app/control_center` does not exist inside the container.
- `/app/app/api/routes.py` inside the container does not contain the Control Center V1.5 route text.

## 4. DB Config Analysis

Expected DB env keys from code:

- `POLYBOT_DATABASE_URL`
- `DATABASE_URL`
- optional `POLYBOT_DATABASE_SCHEMA`
- optional `DATABASE_SCHEMA`
- `POLYBOT_PHASE1_PERSISTENCE_ENABLED` or `PHASE1_PERSISTENCE_ENABLED`
- `POLYBOT_PHASE1_AUTO_MIGRATE` or `PHASE1_AUTO_MIGRATE`

Exact code path:

- `app/db/config.py` defines `DatabaseSettings.database_url` with alias choices `POLYBOT_DATABASE_URL` and `DATABASE_URL`.
- `DatabaseSettings.enabled` is `phase1_persistence_enabled and bool(database_url)`.
- `app/control_center/query_service.py` returns "database is not configured" when `DatabaseConnectionFactory.enabled` is false.

Actual env names inside Docker API:

- `DATABASE_URL`
- `POLYBOT_DATABASE_URL`

Actual `.env` DB key names, names only:

- `.env`: no `POLYBOT_DATABASE_URL`, no `DATABASE_URL`, no `POSTGRES_*`, no `DB_*`.
- `.env.example`: includes `POLYBOT_DATABASE_URL`, `PHASE1_PERSISTENCE_ENABLED`, `PHASE1_AUTO_MIGRATE`.

Compose DB config:

- `api` service passes both `POLYBOT_DATABASE_URL` and `DATABASE_URL`.
- `migrate` service also passes both keys.
- Docker API should connect to `postgres:5432`.
- Host/local Python should connect to `127.0.0.1:55432`.

Expected connection strings with placeholders:

- Docker API: `postgresql://<user>:<password>@postgres:5432/<database>`
- Host Python: `postgresql://<user>:<password>@127.0.0.1:55432/<database>`

Exact mismatch:

The fresh host process has the new Control Center code but no DB env. The Docker process has the DB env but stale code. The operator is using the host process.

## 5. DB Schema Analysis

| Table | Exists? | Count if checked | Notes |
| ----- | ------- | ---------------- | ----- |
| `service_health` | YES | 30 | Organ Health source table exists and has rows. |
| `event_log` | YES | 506279 | Live Flow/log source exists and is heavily populated. |
| `runtime_state` | NO | N/A | Not present; Control Center overview currently reads `system_state`, not `runtime_state`. |
| `system_state` | YES | 1 | Runtime/system state source exists. |
| `paper_positions` | YES | 12 | Canonical paper positions exist. |
| `paper_capital_ledger` | YES | 38 | Capital ledger exists. |
| `no_trade_log` | YES | 11622 | No-Trade source exists and is populated. |
| `risk_evidence_mesh_evaluations` | YES | 1596 | Risk evidence source exists and is populated. |
| `paper_daily_pnl` | YES | 3 | PnL page service uses paper PnL/ledger source. |
| `lifecycle_governance_decisions` | YES | 10747 | Lifecycle source exists and is populated. |
| `truth_state_registry` | YES | 8816 | Truth State source exists and is populated. |
| `runtime_incidents` | YES | 0 | Logs can still be MISSING if incident rows are empty. |
| `event_delivery_attempts` | YES | 0 | Delivery attempt source exists but empty. |
| `brain_dialogue_events` | YES | 134289 | Mesh dialogue source exists and is populated. |

Schema/tables are not the first blocker. The API process being hit is not connected to this DB.

## 6. Control Center Endpoint Analysis

Observed against `http://127.0.0.1:8000`, which is the local Python process:

| Endpoint | Status | Source | Warning/Error | Meaning |
| -------- | ------ | ------ | ------------- | ------- |
| `/dashboard/api/v2/control/overview` | MISSING | `runtime_state_service_health_event_log` | `Overview sources are unavailable because the database is not configured.` | Local API has no DB URL. |
| `/dashboard/api/v2/control/organs` | MISSING | `service_health_heartbeat` | `Service heartbeat source is unavailable because the database is not configured.` | Local API cannot read `service_health`. |
| `/dashboard/api/v2/control/live-flow` | MISSING | `event_log` | `Event source is unavailable because the database is not configured.` | Local API cannot read `event_log`. |
| `/dashboard/api/v2/control/full-monitor-run` | MISSING | `control_center:full_monitor_run` | `No Full Monitor Run has been started in this process.` | In-process run store is empty. |
| `/dashboard/api/v2/control/logs` | MISSING | `runtime_incidents_event_log_dlq` | `Log-like sources are unavailable because the database is not configured.` | Local API cannot read logs/events. |
| `/dashboard/api/v2/control/pnl-ledger` | MISSING | `paper_pnl_ledger` | `PnL requires paper_daily_pnl/paper ledger source; no fake PnL is supplied.` | Local service returns honest missing/withheld PnL. |
| `/dashboard/api/v2/control/positions` | MISSING | `paper_positions` | `Positions require canonical paper_positions source.` | Local service cannot surface DB-backed positions. |
| `/dashboard/api/v2/control/no-trade` | REAL | `no_trade_log` | none observed | This service can return a real summary shape despite the broader DB mismatch; it does not disprove the DB config issue shown by overview/organs/live-flow/logs. |
| `/dashboard/api/v2/control/risk-evidence` | MISSING | `risk_evidence_mesh_evaluations` | `Risk evidence is read-only and does not claim approval.` | Not enough evidence surfaced through the local process. |

Docker API container-local result:

| Endpoint | Status | Source | Warning/Error | Meaning |
| -------- | ------ | ------ | ------------- | ------- |
| `/dashboard/api/v2/control/overview` | HTTP 404 | N/A | route missing | Docker image is stale and lacks V1.5 Control Center routes. |
| `/dashboard/api/v2/control/organs` | HTTP 404 | N/A | route missing | Same. |
| `/dashboard/api/v2/control/live-flow` | HTTP 404 | N/A | route missing | Same. |
| `/dashboard/api/v2/control/full-monitor-run` | HTTP 404 | N/A | route missing | Same. |

## 7. Full Monitor Run Analysis

- Available? YES on the local API: `available: true`.
- Current/latest? Both null on the local API.
- Why null? Stage 16 stores current/latest in `DEFAULT_FULL_MONITOR_RUN_STORE`, an in-process memory store. No run has been started in the local process currently serving `127.0.0.1:8000`.
- Does it write data? No durable DB write for the run ledger. It creates an in-memory run record and summarizes existing read-only Control Center envelopes.
- Will it populate source tables? No. It does not create event rows, positions, fills, orders, PnL, risk evaluations, or source data. It only reads/summarizes what existing endpoints return.
- Can START FULL MONITOR RUN make current/latest non-null? YES, if the action is accepted by actor/reason/duration and State Governor/live safety checks. It will populate in-process `latest` until that API process restarts.
- What can it populate today? Only the in-memory Full Monitor Run status envelope and module result summary.
- What can it not populate today? It cannot repair DB config, create source rows, enable skipped monitor modules, create paper/live execution artifacts, or create a durable run history.
- Are orderbook/news/whale/social skipped intentionally? YES. Stage 16 explicitly marks them `SKIPPED` because safe Control Center read-only monitor endpoints do not exist for those modules.

## 8. Root Cause

Primary root cause:

1. Process/config skew: the operator is hitting a local Python FastAPI process that has the new Control Center UI/routes but no `POLYBOT_DATABASE_URL`/`DATABASE_URL`, so DB-backed visibility endpoints return honest MISSING.

Secondary root causes:

2. Docker image skew: `polybot_api` has the correct DB env but is stale and does not contain the Control Center V1.5 backend package/routes.
3. Port conflict: Docker and local Python both have listeners related to port 8000, making it easy to think the healthy Docker API is serving the UI when it is not.
4. Full Monitor Run has not been started in the currently-served process, and its state is memory-only.
5. Docker API logs show `refresh_cycle_blocked_by_runtime_mode`, so even the stale Docker runtime is not actively refreshing new live data in its current mode.

Non-root causes:

- Postgres health is not the root cause; container is healthy.
- Schema absence is not the root cause; required tables mostly exist and are populated.
- Frontend API path is not the root cause; it correctly calls same-origin `/dashboard/api/v2/control/*`.
- The Control Center truth components are not faking failure; they are accurately exposing the backend envelopes they receive.

## 9. Fix Plan

Step 1: Choose one canonical API process for `/control-center`.

- File/config: operational process state, no source code change required.
- Action: stop the local `python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` if Docker should own port 8000, or intentionally run local Python with the host DB URL if local should own it.
- Risk: LOW/MEDIUM operational risk because stopping the wrong process could interrupt the currently visible UI.
- Test command: `Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess`
- Expected result: one intended owner for `127.0.0.1:8000`.

Step 2: Make the chosen API process have both fresh Control Center code and DB config.

- File/config for Docker path: `Dockerfile`, `docker-compose.yml`, built image state.
- Action for Docker path: rebuild/recreate `api` so `/app/app/control_center` exists and `/dashboard/api/v2/control/*` routes exist inside the container.
- File/config for local path: `.env` or launch command env.
- Action for local path: provide `POLYBOT_DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:55432/<database>` without printing secrets.
- Risk: MEDIUM. Docker rebuild/recreate is operational; local `.env` changes can expose/alter environment if done carelessly.
- Test command Docker: `docker compose exec api python -c "import pathlib; print(pathlib.Path('/app/app/control_center').exists())"`
- Test command local: `.venv\Scripts\python.exe -c "from app.db.config import get_database_settings; s=get_database_settings(); print(s.enabled, bool(s.database_url))"`
- Expected result: fresh code present and DB settings enabled in the process serving the UI.

Step 3: Verify live-feeling source endpoints before UX polishing.

- File/config: none if Step 1/2 are correct.
- Test command: `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/overview`
- Expected result: `status` becomes `PARTIAL` or `REAL`, `data.source_counts` contains populated source tables, and warnings no longer say `database is not configured`.
- Risk: LOW. Read-only verification.

Step 4: Start Full Monitor Run only after DB-backed endpoints are alive.

- File/config: existing Settings UI/action wrapper.
- Action: use Settings `START FULL MONITOR RUN` with actor, reason, and duration.
- Test command: `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/full-monitor-run`
- Expected result: `latest` is non-null in that same process and module results summarize read-only envelopes.
- Risk: LOW/MEDIUM. It is designed as bounded/read-only, but it is still an action wrapper call and should be done deliberately.

## 10. Immediate Operator Commands

Safe verification commands:

```powershell
docker compose ps
Get-NetTCPConnection -LocalPort 8000,55432,56379 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId = 7388" |
  Select-Object ProcessId,Name,CommandLine
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/overview
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/organs
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/live-flow
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/full-monitor-run
docker compose exec api python -c "import os; print(sorted([k for k in os.environ if any(x in k.upper() for x in ['DATABASE','POSTGRES','DB_','PGHOST','PGPORT','PGDATABASE','PGUSER'])]))"
docker compose exec api python -c "import pathlib; print('control_center_exists', pathlib.Path('/app/app/control_center').exists())"
docker compose exec postgres psql -U polybot -d polybot -At -c "select 'service_health', count(*) from service_health union all select 'event_log', count(*) from event_log union all select 'system_state', count(*) from system_state union all select 'paper_positions', count(*) from paper_positions union all select 'no_trade_log', count(*) from no_trade_log union all select 'risk_evidence_mesh_evaluations', count(*) from risk_evidence_mesh_evaluations;"
```

Fix-phase commands, after approval/intentional choice of Docker as canonical owner:

```powershell
# Rebuild/recreate only after accepting that Docker should own port 8000.
docker compose up -d --build api

# Verify the container now has fresh Control Center code.
docker compose exec api python -c "import pathlib; print(pathlib.Path('/app/app/control_center').exists())"
docker compose exec api python -c "from app.db.config import get_database_settings; s=get_database_settings(); print({'enabled': s.enabled, 'has_database_url': bool(s.database_url)})"

# Verify host UI/API.
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/overview
```

Fix-phase commands, after approval/intentional choice of local Python as canonical owner:

```powershell
# Set a host-safe DB URL without printing the secret value in logs.
# Then restart the local uvicorn process from the same environment.
.venv\Scripts\python.exe -c "from app.db.config import get_database_settings; s=get_database_settings(); print({'enabled': s.enabled, 'has_database_url': bool(s.database_url)})"
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/overview
```

## 11. Safety Checklist

| Check | YES / NO / UNKNOWN |
| ----- | ------------------ |
| no secrets printed | YES |
| no DB writes | YES |
| no migrations run | YES |
| no live trading | YES |
| no orders/fills/positions created | YES |
| no destructive Docker commands | YES |
| root cause identified | YES |
| fix plan clear | YES |

## 12. Status

GREEN.

Root cause is identified with direct process, env, route, endpoint, and table evidence. No unsafe action was performed.

## 13. Can Continue to Fix Phase?

YES.

