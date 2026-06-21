# POLYBOT Runtime Health Repair Report

Generated: 2026-05-21

## 1. Root Cause

`/runtime/health` marked the runtime `DEGRADED` because `service_health.last_heartbeat_at` for required process/dependency rows was written once at startup and never refreshed.

False stale rows observed before repair:

- `fastapi`
- `postgres`

The stale-service calculation itself was not broadly wrong: heartbeat-less static module registrations were not listed as stale, and `STOPPED` optional services were not degrading runtime health. The missing piece was a real refresh path for active process/dependency health.

Dashboard V2 overview also became stale because its overview freshness timestamp was anchored to old `system_state.updated_at` even though `service_health` is part of the overview source tables and now contains fresh runtime dependency truth.

## 2. Files Inspected

- `AGENTS.md`
- `README.md`
- `SERVER_RUNTIME_README.md`
- `docs/SERVER_MIGRATION_AUDIT_REPORT.md`
- `pyproject.toml`
- `docker-compose.yml`
- `app/main.py`
- `app/runtime/health_truth.py`
- `app/runtime/service_registry.py`
- `app/runtime/safe_startup.py`
- `app/api/runtime_routes.py`
- `app/repositories/service_health_repository.py`
- `app/services/query/dashboard_v2_query_service.py`
- `tests/test_runtime_api.py`
- `tests/test_runtime_cycle_orchestrator.py`
- `tests/test_mode_manager.py`
- `tests/test_v2_18_dashboard_v2_api.py`
- `tests/test_v2_18_dashboard_v2_safety_guards.py`

## 3. Files Changed

- `app/runtime/health_truth.py`
- `app/services/query/dashboard_v2_query_service.py`
- `tests/test_runtime_health_truth.py`
- `docs/RUNTIME_HEALTH_REPAIR_REPORT.md`

## 4. Schema / Migration Changes

No schema changes.

No migration files were added or changed.

Existing `service_health.details_json` is used to record the health source and Redis dependency metadata.

## 5. Tests Added / Updated

Added `tests/test_runtime_health_truth.py`.

Coverage added:

- healthy required service heartbeat is not stale
- genuinely stale required service causes stale detection
- `STOPPED` optional service does not become stale
- internal module registration without heartbeat does not become stale
- `/runtime/health` refreshes FastAPI/Postgres/Redis dependency health
- real stale service still causes `DEGRADED`

## 6. Commands Run

Pre-change evidence:

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/runtime/health
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview
docker compose logs --tail=120 api
docker compose exec -T postgres psql -U polybot -d polybot -c "select service_name, service_type, status, last_heartbeat_at, updated_at from service_health order by service_name;"
```

Local tests:

```powershell
C:\Server\tmp\polybot-test-venv\Scripts\python.exe -m pytest tests/test_runtime_health_truth.py tests/test_runtime_api.py tests/test_state_governor.py tests/test_mode_manager.py tests/test_runtime_cycle_orchestrator.py -q
```

Docker verification:

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose run --rm migrate
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/runtime/health
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview
docker compose logs --tail=150 api
docker compose exec -T api python -c "import os; print('MODE=', os.getenv('POLYBOT_RUNTIME_MODE')); print('BACKEND=', os.getenv('POLYBOT_EXECUTION_BACKEND')); print('LIVE=', os.getenv('LIVE_TRADING_ENABLED')); print('KILL=', os.getenv('LIVE_KILL_SWITCH'))"
```

Additional attempted checks:

```powershell
C:\Server\tmp\polybot-test-venv\Scripts\python.exe -m pytest tests/test_v2_18_dashboard_v2_api.py tests/test_v2_18_dashboard_v2_safety_guards.py ...
```

Those dashboard test files could not collect on this Windows server because Application Control blocked the compiled `regex` dependency imported through the existing Stage 4 dependency chain.

## 7. Exact Results

Runtime health tests:

```text
34 passed in 110.08s (0:01:50)
```

Docker:

```text
polybot_api        Up ... (healthy)
polybot_postgres   Up ... (healthy)
polybot_redis      Up ... (healthy)
```

Migrations:

```text
No pending migrations.
```

Health:

```text
/healthz status=ok ready=True
/runtime/health overall_status=HEALTHY current_mode=DATA_ONLY stale_count=0 warnings=0
/dashboard/api/v2/overview status=OK stale=False mock_data=False
```

Safety env inside API:

```text
MODE= PAPER
BACKEND= paper
LIVE= false
KILL= true
```

Service dependency rows after repair:

```text
fastapi  RUNNING  last_heartbeat_at fresh
postgres HEALTHY  last_heartbeat_at fresh
redis    HEALTHY  last_heartbeat_at fresh
```

## 8. Before /runtime/health Status

Before:

```text
overall_status=DEGRADED
current_mode=DATA_ONLY
stale_services=[fastapi, postgres]
warnings=["one or more services are stale"]
```

## 9. After /runtime/health Status

After:

```text
overall_status=HEALTHY
current_mode=DATA_ONLY
stale_services=[]
warnings=[]
```

## 10. Safety Verification

- `POLYBOT_RUNTIME_MODE` inside API: `PAPER`
- `POLYBOT_EXECUTION_BACKEND` inside API: `paper`
- `LIVE_TRADING_ENABLED` inside API: `false`
- `LIVE_KILL_SWITCH` inside API: `true`
- persisted runtime mode: `DATA_ONLY`
- live trading was not enabled
- scoring, strategy, execution, and trading logic were not changed
- Docker volumes were not deleted
- no GitHub pull/push was performed

## 11. Remaining Risks

- Host-side dashboard and Stage 4-adjacent pytest collection remains blocked by Windows Application Control for a compiled `regex` DLL imported through `eth_account`.
- `app/services/query/dashboard_v2_query_service.py` has pre-existing Ruff style violations unrelated to this repair; targeted behavior tests and live endpoint verification were used instead.
- Redis is represented as a checked dependency when `REDIS_URL` is configured, but the current event mesh remains primarily Postgres-backed.

## 12. Final Status

**GREEN**

Reason:

- Docker API/Postgres/Redis are healthy.
- `/healthz` is OK and ready.
- `/runtime/health` is `HEALTHY` and no longer degraded by false stale service rows.
- Tests prove real stale services still degrade runtime health.
- Dashboard overview is `OK`, fresh, and `mock_data=false`.
- Safety environment remains PAPER/paper/live-disabled/kill-switch-enabled.

## 13. Can We Continue Development On This Server

**YES**

Continue server development in DATA_ONLY/PAPER mode. Live-readiness claims still require resolving the host Application Control blocker for Stage 4/live-adjacent tests.
