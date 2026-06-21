# POLYBOT Test Isolation Repair Report

Date: 2026-05-21
Server path: `C:\Server\apps\polybot`

## 1. Root Cause

The Docker `test` service was using the same Postgres database as the production/runtime API. Stage4/live-adjacent and dashboard-adjacent tests therefore wrote test rows into runtime tables such as `orders_v2`, `fills_v2`, `execution_quality`, and `ai_*`.

The `test` service also mounted `tests/` read-only but did not mount `scripts/`, so tests that inspect operator scripts could fail inside Docker.

## 2. Files Changed

- `docker-compose.yml`
- `scripts/test_in_docker.ps1`
- `SERVER_RUNTIME_README.md`
- `docs/TEST_ISOLATION_REPAIR_REPORT.md`

## 3. Exact Test DB Design

Docker now has a test profile with an isolated Postgres service:

- Service: `postgres_test`
- Container: `polybot_postgres_test`
- Database: `polybot_test`
- Host port: `55433`
- Volume: `polybot_postgres_test_data`
- Profile: `test`

The normal production/runtime path is unchanged:

- Production API and production `migrate` still use the normal `postgres` service and `polybot` database.
- Test `DATABASE_URL` and `POLYBOT_DATABASE_URL` point to `postgres_test:5432/polybot_test`.
- `test_migrate` runs the normal migration engine against `polybot_test`.
- `test` depends on `postgres_test` healthy, `redis` healthy, and `test_migrate` completed successfully.
- `scripts/` is mounted read-only into `/app/scripts` for tests.

## 4. How Production DB Is Protected

Production and test database endpoints are separated at the Compose service level:

- Production: `postgres:5432/polybot`
- Test: `postgres_test:5432/polybot_test`

The test profile starts and migrates a separate Postgres container before running pytest. Tests no longer point at the production/runtime database.

## 5. Commands Run

Configuration and build:

- `docker compose config` -> passed.
- `docker compose --profile test config` -> passed.
- `docker compose build` -> passed.
- `docker compose --profile test build test` -> passed.

Runtime:

- `docker compose up -d` -> passed.
- `docker compose ps` -> `polybot_api`, `polybot_postgres`, `polybot_postgres_test`, and `polybot_redis` healthy.
- `docker compose run --rm migrate` -> `No pending migrations.`
- `docker compose --profile test run --rm test_migrate` -> `No pending migrations.`

Targeted Docker tests:

- `docker compose --profile test run --rm test python -m pytest tests/test_runtime_integration_guards.py tests/test_stage4_env_isolation.py tests/test_v2_18_dashboard_v2_api.py tests/test_v2_18_dashboard_v2_safety_guards.py tests/test_v2_20_no_live_safety.py tests/test_v2_3_ai_api.py tests/test_v2_15_execution_service.py -q`
  - Result: `33 passed in 43.53s`
- `powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1 tests/test_v2_20_no_live_safety.py tests/test_v2_15_execution_service.py -q`
  - Result: `8 passed in 1.85s`

Endpoint checks:

- `Invoke-RestMethod http://127.0.0.1:8000/healthz`
  - Result: `status=ok`, `ready=True`
- `Invoke-RestMethod http://127.0.0.1:8000/runtime/health`
  - Result: `overall_status=HEALTHY`, `current_mode=DATA_ONLY`, `stale_services=[]`
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview`
  - Result: `status=OK`, `mock_data=false`, `stale=false`

Safety check:

- `docker compose exec -T api python -c "import os; ..."`
  - Result: `MODE=PAPER`, `BACKEND=paper`, `LIVE=false`, `KILL=true`

Test DB checks:

- `docker compose --profile test exec -T postgres_test psql -U polybot -d polybot_test -c "select current_database() as db, count(*) as migrations from schema_migrations;"`
  - Result: `db=polybot_test`, `migrations=57`
- `docker compose --profile test exec -T postgres_test psql -U polybot -d polybot_test -c "...row counts..."`
  - Result: `orders_v2=2`, `fills_v2=2`, `execution_quality=2`, `schema_migrations=57`

Production DB checks:

- Production counts before isolated test runs:
  - `orders_v2=1`
  - `fills_v2=1`
  - `execution_quality=1`
  - `ai_requests=2`
  - `ai_responses=2`
  - `ai_cache=1`
  - `ai_cost_ledger=1`
- Production counts after isolated test runs:
  - `orders_v2=1`
  - `fills_v2=1`
  - `execution_quality=1`
  - `ai_requests=2`
  - `ai_responses=2`
  - `ai_cache=1`
  - `ai_cost_ledger=1`

Script mount check:

- `docker compose --profile test run --rm test sh -c 'ls /app/scripts | head -5; mount | grep /app/scripts || true'`
  - Result: script files are visible under `/app/scripts`; mount is read-only.

## 6. Test Results

Targeted Docker tests pass through the isolated test database:

- Stage4/environment/safety/dashboard/execution targeted group: `33 passed`
- Wrapper smoke group through `scripts/test_in_docker.ps1`: `8 passed`

## 7. Production DB Verification

The production business/test-contaminated table counts remained unchanged after the isolated Docker tests. The `event_log` table continues to receive normal runtime scheduler events, so it was not used as proof of test pollution isolation.

## 8. Runtime Health Verification

Current runtime status after the repair:

- API: healthy
- Postgres: healthy
- Redis: healthy
- Runtime health endpoint: `HEALTHY`
- Dashboard overview: `OK`, `mock_data=false`, `stale=false`

## 9. Safety Verification

Safety environment inside the API container remains:

- `POLYBOT_RUNTIME_MODE=PAPER`
- `POLYBOT_EXECUTION_BACKEND=paper`
- `LIVE_TRADING_ENABLED=false`
- `LIVE_KILL_SWITCH=true`

No trading, scoring, execution, State Governor, or live-safety logic was changed.

## 10. Remaining Risks

- The isolated test database uses a persistent Docker volume, `polybot_postgres_test_data`. This protects production data but means test rows can accumulate across test runs unless tests clean their own rows.
- The repository directory currently is not a Git worktree on this server, so verification used direct file inspection and command outputs instead of `git diff`.
- Existing production rows from the earlier audit contamination remain present. This repair prevents new test writes to production but does not delete prior rows.

## 11. Final Status

GREEN

## 12. Can Continue Development

YES
