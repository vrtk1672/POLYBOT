# Stage4 Test Environment Blocker Report

Date: 2026-05-21
Server path: `C:\Server\apps\polybot`

## 1. Root Cause

Stage4/live-adjacent pytest collection is blocked on the Windows host by Windows Application Control while importing the compiled `regex` extension used indirectly by Web3/Ethereum signing dependencies.

The failure is host test environment policy, not a POLYBOT runtime failure. The same targeted tests collect and pass inside Docker's Linux Python environment.

## 2. Exact Blocked File / Module

Blocked file:

`C:\Server\tmp\polybot-test-venv\Lib\site-packages\regex\_regex.cp311-win_amd64.pyd`

Blocked module:

`regex._regex`

Import chain observed:

`pytest` -> Stage4/dashboard tests -> `app.stage4.auth` -> `eth_account` -> `eth_abi` -> `parsimonious` -> `regex` -> `regex._regex_core` -> `from regex import _regex`

Host traceback failure:

`ImportError: DLL load failed while importing _regex: An Application Control policy has blocked this file.`

## 3. Tests Affected

The host-side collection block affected this targeted Stage4/live-adjacent set:

- `tests/test_runtime_integration_guards.py`
- `tests/test_stage4_env_isolation.py`
- `tests/test_v2_18_dashboard_v2_api.py`
- `tests/test_v2_18_dashboard_v2_safety_guards.py`

Host result before Docker runner repair:

`collected 0 items / 4 errors`

## 4. Whether Docker Test Runner Passes

Yes. Docker-based targeted tests passed:

`22 passed in 24.11s`

The Docker test image uses Linux Python and does not hit the Windows Application Control block on `regex._regex`.

## 5. Files Changed

- `Dockerfile`
  - Added `ARG INSTALL_DEV=false`.
  - Keeps production runtime install as the default.
  - Allows the dedicated test service to install `.[dev]`, including `pytest-asyncio`.
- `docker-compose.yml`
  - Added a profiled `test` service.
  - Test service pins safe runtime variables: `POLYBOT_RUNTIME_MODE=PAPER`, `POLYBOT_EXECUTION_BACKEND=paper`, `LIVE_TRADING_ENABLED=false`, `LIVE_KILL_SWITCH=true`.
  - Test service depends on healthy Postgres, healthy Redis, and successful migrations.
  - Test service mounts `tests/` read-only.
- `scripts/test_in_docker.ps1`
  - Added a PowerShell wrapper for Docker-based pytest runs.
- `SERVER_RUNTIME_README.md`
  - Documented the canonical Docker test runner for Stage4/live-adjacent tests on this Windows server.
- `docs/STAGE4_TEST_ENV_BLOCKER_REPORT.md`
  - This report.

## 6. Scripts Added

`scripts/test_in_docker.ps1`

Usage:

```powershell
.\scripts\test_in_docker.ps1 tests/test_stage4_env_isolation.py -q
```

Default behavior with no arguments:

```powershell
.\scripts\test_in_docker.ps1
```

Runs:

```powershell
docker compose run --rm test python -m pytest <args>
```

## 7. Commands Run and Exact Results

Host blocked collection command:

```powershell
$venv='C:\Server\tmp\polybot-test-venv'
$env:POLYBOT_DATABASE_URL='<set locally, value not printed>'
$env:LIVE_TRADING_ENABLED='false'
$env:LIVE_KILL_SWITCH='true'
& "$venv\Scripts\python.exe" -m pytest tests/test_runtime_integration_guards.py tests/test_stage4_env_isolation.py tests/test_v2_18_dashboard_v2_api.py tests/test_v2_18_dashboard_v2_safety_guards.py -vv --tb=long
```

Result:

`collected 0 items / 4 errors`

Exact blocker:

`ImportError: DLL load failed while importing _regex: An Application Control policy has blocked this file.`

Docker compose validation:

```powershell
docker compose config
docker compose --profile test config
```

Result:

Both commands completed successfully.

Docker test image build:

```powershell
docker compose --profile test build test
```

Result:

`polybot_server-test Built`

Targeted Docker tests:

```powershell
docker compose run --rm test python -m pytest tests/test_runtime_integration_guards.py tests/test_stage4_env_isolation.py tests/test_v2_18_dashboard_v2_api.py tests/test_v2_18_dashboard_v2_safety_guards.py -q
```

Result:

`22 passed in 24.11s`

Script verification:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1 tests/test_stage4_env_isolation.py -q
```

Result:

`10 passed in 2.90s`

Production image build:

```powershell
docker compose build
```

Result:

`polybot_server-api Built`

`polybot_server-migrate Built`

Runtime restart:

```powershell
docker compose up -d
```

Result:

API recreated and started after migrations completed successfully.

Runtime status:

```powershell
docker compose ps
```

Result:

- `polybot_api`: `Up ... (healthy)`
- `polybot_postgres`: `Up ... (healthy)`
- `polybot_redis`: `Up ... (healthy)`

Migration check:

```powershell
docker compose run --rm migrate
```

Result:

`No pending migrations.`

Health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

Result:

`status=ok`, `ready=True`

Runtime health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/runtime/health
```

Result:

`overall_status=HEALTHY`, `current_mode=DATA_ONLY`, `stale_services=[]`, `warnings=[]`

Dashboard overview:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview
```

Result:

`status=OK`, `mock_data=false`, `stale=false`, `overall_runtime_health=HEALTHY`

Container safety env:

```powershell
docker compose exec -T api python -c "import os; print('MODE=', os.getenv('POLYBOT_RUNTIME_MODE')); print('BACKEND=', os.getenv('POLYBOT_EXECUTION_BACKEND')); print('LIVE=', os.getenv('LIVE_TRADING_ENABLED')); print('KILL=', os.getenv('LIVE_KILL_SWITCH'))"
```

Result:

- `MODE= PAPER`
- `BACKEND= paper`
- `LIVE= false`
- `KILL= true`

API logs reviewed:

```powershell
docker compose logs --tail=120 api
```

Result:

- FastAPI startup completed.
- `execution_mode=PAPER`
- `execution_backend=paper`
- `live_enabled=False`
- `live_kill_switch=True`
- `v2_runtime_startup status=OK current_mode=DATA_ONLY warnings=[]`

## 8. Safety Verification

- Live trading was not enabled.
- Docker API env remains `LIVE_TRADING_ENABLED=false`.
- Docker API env remains `LIVE_KILL_SWITCH=true`.
- Docker API env remains `POLYBOT_RUNTIME_MODE=PAPER`.
- Docker API env remains `POLYBOT_EXECUTION_BACKEND=paper`.
- Persisted runtime mode remains `DATA_ONLY`.
- No trading, scoring, strategy, or execution logic was changed.
- No Docker volumes were deleted.
- No global Windows security policy was disabled or weakened.
- No secrets were printed in this report.

## 9. Recommendation: Host Tests vs Docker Tests

Use Docker as the canonical test runner for Stage4/live-adjacent tests on this Windows server:

```powershell
.\scripts\test_in_docker.ps1 tests/test_runtime_integration_guards.py tests/test_stage4_env_isolation.py tests/test_v2_18_dashboard_v2_api.py tests/test_v2_18_dashboard_v2_safety_guards.py -q
```

The Windows host can still be used for tests that do not import the blocked compiled dependency chain.

If host-side Stage4 collection is required later, the least-risk operator-controlled path is:

1. Keep using the fresh venv at `C:\Server\tmp\polybot-test-venv`.
2. Reinstall dependencies cleanly if needed.
3. If policy still blocks the extension, ask the operator/security owner to approve an exclusion scoped only to the fresh test venv folder or to the exact signed package path.

Do not disable Windows security globally.

## 10. Final Status

YELLOW

Reason: Docker-based targeted Stage4/live-adjacent tests pass, runtime remains healthy, and safety remains preserved. The Windows host pytest collection remains blocked by Application Control policy for the compiled `regex` extension, so Docker is the documented canonical runner for this test class on this server.

Can we continue development on this server: YES
