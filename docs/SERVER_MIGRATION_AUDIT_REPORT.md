# POLYBOT Server Migration Audit Report

Generated: 2026-05-21

## 1. Summary

POLYBOT's new-server Docker runtime is now wired to the existing repository migration system. The original startup blocker was missing Postgres schema tables (`service_health`, `system_state`). Those tables already existed in the repository migrations, but Docker startup did not run migrations before the API started.

Repair completed:

- Added a one-shot `migrate` service to `docker-compose.yml`.
- Made `api` wait for `migrate` to complete successfully.
- Removed API `env_file: .env` loading from Docker so local secrets are not injected or exposed by `docker compose config`.
- Pinned Docker safety defaults to PAPER/paper with live disabled and kill switch enabled.
- Verified Postgres, Redis, API, docs, health, runtime health, dashboard, and migration idempotency.

Final status: **YELLOW** because Docker/runtime is healthy, but Stage 4 safety-test collection is blocked on this Windows server by Application Control policy for a compiled dependency DLL. Core runtime/schema targeted tests passed.

## 2. Current Server Path

`C:\Server\apps\polybot`

## 3. Docker Runtime Status

Services present:

- `polybot_postgres`: running, healthy, published on host port `55432`.
- `polybot_redis`: running, healthy, published on host port `56379`.
- `polybot_migrate`: one-shot migration service, completed successfully.
- `polybot_api`: running, healthy, published on host port `8000`.

Docker commands verified:

- `docker compose config`: passed after sanitizing API secret handling.
- `docker compose build`: passed.
- `docker compose up -d`: passed.
- `docker compose ps`: API/Postgres/Redis healthy.
- `docker compose run --rm migrate`: returned `No pending migrations.`

## 4. Files Created Or Changed

Changed:

- `docker-compose.yml`
- `SERVER_RUNTIME_README.md`

Created:

- `docs/SERVER_MIGRATION_AUDIT_REPORT.md`

No Git status is available because this server directory is not currently a Git working tree (`.git` is absent). Per migration instruction, no GitHub pull/push/overwrite operation was performed.

## 5. DB / Migration Status

Existing migration mechanism:

- `app/db/migrate.py`
- `app/db/migrations/*.sql`
- `schema_migrations` table

Migration result:

- First Docker migration run applied 57 migration files, `0001_phase1_cycles.sql` through `0056_v2_19_feedback_learning_loop.sql`.
- Idempotency check returned `No pending migrations.`
- `schema_migrations` count: `57`.

Verified required tables:

- `service_health`
- `system_state`
- `system_state_history`
- `runtime_cycles_v2`
- `runtime_incidents`
- `event_log`
- `event_consumers`

Current persisted runtime state:

- `system_state.current_mode`: `DATA_ONLY`
- runtime cycle completed in `DATA_ONLY`
- latest checked cycle status: `COMPLETED`
- cycle errors: `0`
- cycle warnings: `0`

## 6. API Status

API status: healthy.

Verified endpoints:

- `GET /docs`: `200`
- `GET /healthz`: `status=ok`, `ready=True`
- `GET /runtime/health`: `overall_status=HEALTHY`, `current_mode=DATA_ONLY`
- `GET /dashboard`: `200`
- `GET /dashboard/api/v2/overview`: `status=OK`, `mock_data=false`, `system_mode=DATA_ONLY`

Startup log after repair:

- `v2_runtime_startup status=OK current_mode=DATA_ONLY`
- `execution_mode=PAPER`
- `execution_backend=paper`
- `anthropic_key_present=False`
- `live_enabled=False`
- `live_kill_switch=True`

## 7. Redis Status

Redis container is healthy.

Notes:

- Current code/docs indicate Redis is not required by the Postgres-backed event bus yet.
- Redis remains available as a server runtime dependency for future queue/cache use.

## 8. Postgres Status

Postgres container is healthy.

Notes:

- Pre-repair Postgres logs contained the expected missing-table errors for `system_state` and `service_health`.
- After the migration service ran and the API restarted, API startup completed successfully and required tables are present.
- No volume-destructive command was run.

## 9. Env Status

Local `.env` key audit only, values not printed.

Required keys present in `.env`:

- `POLYBOT_RUNTIME_MODE`
- `POLYBOT_EXECUTION_BACKEND`
- `LIVE_TRADING_ENABLED`
- `LIVE_KILL_SWITCH`
- `LIVE_MAX_ORDER_USD`
- `ANTHROPIC_API_KEY`
- `POLY_PRIVATE_KEY`
- `POLY_FUNDER`
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`

Required keys missing from `.env` but supplied safely by Docker compose defaults:

- `DATABASE_URL`
- `POLYBOT_DATABASE_URL`
- `REDIS_URL`
- `OLLAMA_BASE_URL`

Other `.env.example` keys missing from `.env`:

- `ALLOW_SCALING`
- `LIVE_MAX_CONCURRENT_POSITIONS`
- `LIVE_MAX_DAILY_LOSS`
- `LIVE_MAX_SAME_MARKET_EXPOSURE`
- `PAPER_MAX_ALLOC_PER_TRADE_PCT`
- `PAPER_MAX_TOTAL_DEPLOYMENT_PCT`
- `PAPER_MIN_CASH_RESERVE_PCT`
- `PAPER_SAFE_MAX_CONCURRENT_POSITIONS`
- `PAPER_STARTING_CAPITAL_USD`
- `PHASE1_AUTO_MIGRATE`
- `PHASE1_PERSISTENCE_ENABLED`
- `POLYBOT_API_HOST`
- `POLYBOT_API_PORT`
- `POLYBOT_INTELLIGENCE_AI_ENABLED`
- `POLYBOT_INTELLIGENCE_NEWS_ENABLED`
- `POLYBOT_INTELLIGENCE_REFRESH_INTERVAL_SECONDS`
- `POLYBOT_INTELLIGENCE_WHALE_REFRESH_INTERVAL_SECONDS`
- `POLYBOT_LOG_LEVEL`
- `POLYBOT_REFRESH_INTERVAL_SECONDS`
- `POLYBOT_TOP_N`

Docker API environment intentionally does not load `.env` by default after this repair. This avoids accidental secret exposure and avoids `.env` silently enabling live behavior.

## 10. Tests Run And Exact Results

Passed:

```powershell
C:\Server\tmp\polybot-test-venv\Scripts\python.exe -m pytest tests/test_state_governor.py tests/test_mode_manager.py tests/test_runtime_cycle_orchestrator.py tests/test_runtime_api.py tests/test_v2_1_event_store.py tests/test_v2_1_event_consumers.py tests/test_v2_20_no_live_safety.py -q
```

Result:

```text
39 passed in 143.17s (0:02:23)
```

Blocked:

```powershell
C:\Server\tmp\polybot-test-venv\Scripts\python.exe -m pytest tests/test_runtime_integration_guards.py ...
C:\Server\tmp\polybot-test-venv\Scripts\python.exe -m pytest tests/test_stage4_env_isolation.py ...
```

Result:

```text
ImportError: DLL load failed while importing _regex: An Application Control policy has blocked this file.
```

Interpretation:

- This is a server environment policy block while importing `regex._regex` through `eth_account` / Stage 4 dependencies.
- The failure occurs during test collection before POLYBOT assertions run.
- No test failure indicated live trading was enabled.

## 11. Logs Reviewed

Reviewed:

- `docker compose logs --tail=150 api`
- `docker compose logs --tail=120 migrate`
- `docker compose logs --tail=80 postgres`
- `docker compose logs --tail=80 redis`

Key findings:

- `migrate` applied all migrations on first run.
- API starts cleanly after migration.
- Postgres missing-table errors in logs are pre-repair entries from the previous failing API startup.
- Redis started normally and is accepting connections.

## 12. Safety Checklist

- Live trading enabled: **false in Docker API**
- Live kill switch: **true in Docker API**
- Docker runtime mode: **PAPER**
- Persisted system state: **DATA_ONLY**
- API startup triggered no live orders.
- DATA_ONLY runtime cycle blocked paper engine by mode.
- No GitHub pull/push was performed.
- No Docker volume deletion was performed.
- No Grafana service was added.
- No fake dashboard data was created.
- No safety checks were bypassed.

## 13. Remaining Problems

- Stage 4/live-related tests cannot currently collect on this Windows server because Application Control blocks a compiled `regex` dependency DLL.
- Local `.venv` copied from the old machine is stale and points to an old Python path; tests were run using a temporary venv at `C:\Server\tmp\polybot-test-venv`.
- Docker API no longer receives `.env` secrets by default. This is safer for server startup, but any future approved cloud AI or venue-auth run must wire secrets deliberately and separately.
- Redis exists and is healthy, but current code paths remain primarily Postgres-backed.

## 14. Recommended Next Steps

1. Decide how to handle the server Application Control policy for Python compiled wheels so Stage 4 tests can run.
2. Replace or recreate the stale repo `.venv` if operators want local non-Docker test commands from this checkout.
3. Keep Docker API `.env` injection disabled unless a specific approved task requires scoped secrets.
4. Add a documented operator-only path for AI credentials if cloud AI is needed.
5. Continue with V2.20 evidence collection only in DATA_ONLY or PAPER after the Stage 4 test environment blocker is resolved or explicitly waived for non-live work.

## 15. Final Status

**YELLOW**

Reason:

- Docker builds.
- Postgres is healthy.
- Redis is healthy.
- API starts and stays running.
- Required DB schema exists.
- Missing-table startup errors are repaired.
- Live trading remains disabled in Docker.
- Core targeted runtime/schema/safety tests pass.
- Stage 4/live-adjacent tests are blocked by server policy before assertions run.
