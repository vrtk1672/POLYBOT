# POLYBOT Server Runtime

This is the clean Docker runtime for the new server.

Services:
- polybot_api
- polybot_postgres
- polybot_redis
- polybot_migrate (one-shot schema migration before API startup)

No Grafana.
No legacy stack.
No live trading by default.

Important commands:

docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f api
docker compose down

Docker test runner:
- Use Docker for Stage4/live-adjacent tests on this Windows server because host-side pytest
  collection can be blocked by Windows Application Control when compiled Python extensions
  are imported through Web3 dependencies.
- Command:
  `.\scripts\test_in_docker.ps1 tests/test_runtime_integration_guards.py tests/test_stage4_env_isolation.py -q`
- The `test` service builds with Python dev extras only for pytest. The production API image
  still uses the default runtime install path.
- Tests run against the isolated `polybot_test` database in the `postgres_test` service.
  They do not use the production `postgres` service or production `polybot` database.
- `test_migrate` applies the normal POLYBOT migrations to `polybot_test` before pytest runs.
- `tests/` and `scripts/` are mounted read-only into the test container.

Schema initialization:
- `docker compose up -d` runs the one-shot `migrate` service after Postgres is healthy.
- The API waits for `migrate` to complete successfully.
- Migrations are idempotent and recorded in `schema_migrations`.

Do not run:
docker compose down -v
docker system prune
docker volume prune

Safety defaults:
- Docker pins POLYBOT_RUNTIME_MODE to PAPER.
- Docker pins POLYBOT_EXECUTION_BACKEND to paper.
- Docker pins LIVE_TRADING_ENABLED to false.
- Docker pins LIVE_KILL_SWITCH to true.
- Docker does not load `.env` into the API container by default, so local secrets are not injected just to start the server.
