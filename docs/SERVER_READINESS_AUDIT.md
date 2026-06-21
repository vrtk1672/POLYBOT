# POLYBOT Server Readiness Audit

Date: 2026-05-20  
Phase: SERVER_READINESS_AUDIT  
Scope: repository, runtime, dependencies, environment, Docker setup, data flows, and permanent 24/7 server readiness.  
Rule: no live trading was enabled, no secrets were printed, no packages were installed, and no feature code was changed.

## 1. Executive Summary

This machine is **not ready to run POLYBOT 24/7 now**.

The repository itself is strong: FastAPI runtime code exists, V2.0-V2.20 modules are present, 57 migrations exist, safety tests pass, the Python dependency set imports successfully, and the new Polymarket Gamma -> CLOB `/book` smoke report is GREEN. The server/runtime layer is not yet stable enough: Docker Desktop is installed but the Docker daemon is not reachable, no API runtime is currently listening on port 8000, Postgres/Redis containers could not be verified, and the machine hardware detected by Windows does not match the provided dedicated-server hardware profile.

Current readiness score: **57 / 100**

### GREEN

- POLYBOT repo structure is present and complete across runtime, events, data foundation, neurons, memory, strategy, risk, execution, exits, no-trade, learning, dashboard, scripts, docs, and tests.
- Python 3.11 is installed and `python -m uv` works.
- Project dependency import smoke passed for FastAPI, psycopg, httpx, Anthropic, uvicorn, and Pydantic.
- Polymarket public data smoke is GREEN: `run_reports/polymarket_orderbook_smoke.json` reports 10 usable orderbooks and 0 errors.
- Gamma -> markets -> `clobTokenIds` -> CLOB `/book` path exists in `app/tools/polymarket_orderbook_smoke.py`.
- Best bid and best ask are calculated from orderbook depth, not last price.
- Safety/runtime tests passed.
- `.env` is ignored by `.gitignore`.
- Live guard code blocks live orders when kill switch is enabled, live trading is false, whitelist is absent, or `--armed` is missing.

### YELLOW

- Actual detected hardware differs from the provided target-server profile. Windows reports a Lenovo machine with Intel i3-1005G1, 2 cores / 4 threads, 8GB RAM, Intel UHD graphics, and only C: visible.
- 8GB RAM is workable for core DATA_ONLY but not comfortable for 24/7 Docker plus Postgres, Redis, API, dashboard, scans, and optional local AI. Upgrade to 16GB remains recommended.
- `uv` is available through `python -m uv`, but `uv` is not on PATH.
- Node and npm are installed, but pnpm/yarn are not.
- Ollama appears installed as a client/process, but localhost API is unreachable.
- AI model router currently references `qwen3:8b`, `qwen3:14b`, and `deepseek-r1:14b`; the server hardware plan should prefer `qwen3:4b`, but that model is not currently referenced by the router.
- News/social/whale source freshness is not proven in this audit.
- Main runtime start remains PowerShell/local Python, not a deterministic Docker app service.

### RED

- Docker daemon is not reachable: Docker CLI reports missing `dockerDesktopLinuxEngine` pipe.
- No Docker containers could be listed; Postgres, Redis, Grafana, and app containers could not be verified.
- No service is listening on API port 8000; `/healthz`, `/runtime/state`, and `/dashboard/api/v2/overview` fail to connect.
- Postgres and Redis readiness cannot be verified until Docker is running.
- There is no main Docker Compose file for the POLYBOT API/runtime. Only `docker-compose.grafana.yml` exists.
- Runtime endpoints are not currently live, so dashboard truth cannot be verified on this machine right now.
- PAPER readiness is blocked until persisted/fresh orderbook snapshots and DB-backed runtime are verified.
- LIVE readiness is explicitly NO.

### Top 10 Things To Do Next

1. Confirm this is the intended dedicated server. Hardware detected locally does not match the provided i3-10105F / GT 710 profile.
2. Start Docker Desktop and verify `docker ps` works.
3. Create or verify deterministic Postgres and Redis containers with restart policy.
4. Create a deterministic POLYBOT runtime startup path for this server, preferably a main Compose/service wrapper or a Windows service/task that runs the canonical script.
5. Verify `POLYBOT_DATABASE_URL` points to the actual local Postgres and do not expose the password.
6. Run `scripts/migrate_runtime.ps1` after Docker/Postgres are reachable.
7. Start runtime and verify `/healthz`, `/runtime/state`, `/runtime/health`, and `/dashboard/api/v2/overview`.
8. Verify orderbook snapshots persist to Postgres, not only to `run_reports/polymarket_orderbook_smoke.json`.
9. Install/repair Ollama only if local AI is desired, then test lightweight `qwen3:4b`; do not rely on 14B models on this hardware.
10. Add boot/restart/log rotation/backup policy, then run a 30-minute DATA_ONLY soak before PAPER.

### What Should Not Be Done On This Machine

- Do not enable live trading.
- Do not add wallet private keys for live use.
- Do not run heavy 14B local LLMs as routine infrastructure on 8GB RAM.
- Do not expose Postgres, Redis, Grafana, Ollama, or the API publicly without a deliberate network/security plan.
- Do not run PAPER until DB, runtime, orderbook persistence, and no-live safety checks are verified.
- Do not claim 24/7 readiness from a one-off smoke report.

## 2. Hardware Readiness

### Provided Server Profile

| Item | Provided |
|---|---|
| CPU | Intel i3-10105F |
| Cores / Threads | 4 / 8 |
| RAM | 8GB now, planned 16GB |
| GPU | NVIDIA GeForce GT 710, 985MB |
| Storage | C: 500GB SSD, D: 111GB additional drive |
| OS | Windows 11 64-bit |
| Motherboard | H410M S2H V3 |

### Detected Local Machine Profile

| Item | Detected |
|---|---|
| CPU | Intel Core i3-1005G1 @ 1.20GHz |
| Cores / Threads | 2 / 4 |
| RAM | 8,355,045,376 bytes, about 7.8GB |
| GPU | Intel UHD Graphics, 1GB reported adapter RAM |
| Disk | C: about 173.8GB used, 63.4GB free |
| OS | Microsoft Windows 11 Home, 10.0.26200, 64-bit |
| Last boot | 2026-05-18 22:40:12 |
| WSL | default distribution `docker-desktop`, WSL2 |

This mismatch is a readiness blocker until confirmed. The audit can only certify the machine it can inspect.

### Hardware Ratings

| Area | Rating | Notes |
|---|---|---|
| Core bot runtime | YELLOW | Adequate for light DATA_ONLY if Docker and DB are healthy; detected CPU is weaker than expected. |
| Docker readiness | RED | Docker CLI installed, daemon unreachable. |
| Database readiness | RED | Postgres cannot be verified while Docker is down. |
| AI local readiness | RED/YELLOW | Ollama client/process exists but API unreachable; heavy local AI not suitable. |
| 24/7 stability | RED | No verified Docker daemon, DB, runtime, or restart policy. |

## 3. Operating System and Runtime

| Tool | Status | Version / Evidence |
|---|---|---|
| Windows | PRESENT | Windows 11 Home, version 10.0.26200, build 26200 |
| PowerShell | PRESENT | 5.1.26100.8457 |
| Python | PRESENT | Python 3.11.0 |
| pip | PRESENT | pip 25.3 |
| uv | PARTIAL | `python -m uv --version` works: uv 0.11.7; `uv` command is not on PATH |
| Git | PRESENT | 2.52.0.windows.1 |
| Docker CLI | PRESENT | Docker 29.2.0 |
| Docker Compose | PRESENT | v5.0.2 |
| Docker daemon | RED | Not reachable; missing `dockerDesktopLinuxEngine` pipe |
| WSL | PRESENT | Docker Desktop WSL2 default |
| Node | PRESENT | v24.13.1 |
| npm | PRESENT | 11.8.0 |
| pnpm | MISSING | Not installed |
| yarn | MISSING | Not installed |

## 4. Repository Structure

Top-level folders/files detected:

- `app/`: main Python FastAPI application.
- `app/api/`: API route modules for runtime, events, data foundation, AI, news, rules, social, whale, market neuron, memory, brains, opportunity, strategy, capital, risk, execution, exits, no-trade, learning, and dashboard.
- `app/runtime/`: State Governor, runtime modes, health truth, safe startup, cycle orchestration.
- `app/events/`: Event bus, event types, event store/replay/consumer logic.
- `app/data_foundation/`: market registry, snapshots, orderbook snapshotter, liquidity, completeness, staleness.
- `app/ingestion/`: Gamma client and market service refresh path.
- `app/ai_brain/`: hybrid AI brain, router, local/cloud workers, cache, budget/cost/decision tracking.
- `app/news_neuron/`, `app/social_neuron/`, `app/whale_neuron/`, `app/rules_neuron/`: intelligence neurons.
- `app/market_neuron/`: technical/orderbook/liquidity/time/fee signal builders.
- `app/market_memory/`: V2.9 memory.
- `app/brains/`: context and capital brains.
- `app/opportunity/`, `app/strategy/`, `app/capital/`, `app/risk/`: opportunity, routing, allocation, and risk layers.
- `app/execution_v2/`: internal paper/shadow execution layer.
- `app/exit_cortex/`: exit planning and internal exit-intent layer.
- `app/no_trade/`: canonical no-trade logging/review/regret.
- `app/learning/`: feedback and learning loop.
- `app/repositories/`: Postgres repository pattern.
- `app/db/migrations/`: SQL migrations, 57 files.
- `scripts/`: runtime, migration, V2.20 smoke, verification, and audit scripts.
- `tests/`: 267 Python test files.
- `docs/`: phase docs and reports.
- `run_reports/`: generated runtime/smoke/audit reports.
- `artifacts/`: previous runtime and closeout artifacts.

Main entrypoints:

- API/runtime: `app/main.py`
- Console command: `polybot = app.main:run`
- Canonical runtime script: `scripts/start_runtime.ps1`
- Migration script: `scripts/migrate_runtime.ps1`
- Polymarket smoke: `app/tools/polymarket_orderbook_smoke.py`

## 5. Programming Languages

| Language / Format | Where | Use | Server Tooling Needed |
|---|---|---|---|
| Python | `app/`, `tests/` | Runtime, services, repositories, tests, tools | Python 3.11, uv/pip |
| PowerShell | `scripts/` | Windows runtime ops, migrations, smoke checks | PowerShell 5.1+ |
| SQL | `app/db/migrations/` | Postgres schema | Postgres |
| Markdown | `docs/`, README | Documentation/reports | None |
| YAML | `docker-compose.grafana.yml` | Grafana Compose | Docker Compose |
| TOML | `pyproject.toml` | Python project config | uv/pip |
| JSON/JSONL | `run_reports/`, artifacts | Reports and runtime artifacts | None |
| HTML | `app/api/routes.py` embedded dashboard | FastAPI-served dashboard | Browser |
| JavaScript | minimal generated/venv/artifact presence | Not a primary app stack | Node only if future frontend tooling is added |

## 6. Python Project Audit

| Item | Result |
|---|---|
| Python requirement | `>=3.11` |
| Package manager | uv lock present; `python -m uv` works |
| Virtual environment | `.venv/` exists |
| Dependency lock | `uv.lock` exists |
| Main dependencies | `anthropic`, `fastapi`, `httpx`, `pydantic`, `pydantic-settings`, `psycopg[binary]`, `py-clob-client`, `rich`, `uvicorn[standard]` |
| Dev/test dependencies | `pytest`, `pytest-asyncio`, `ruff` |
| Import smoke | PASS: `fastapi`, `psycopg`, `httpx`, `anthropic`, `uvicorn`, `pydantic` |
| Suspicious/missing | `uv` not on PATH; local Ollama integration is not a real transport yet; no main Docker app service |

Python dependency command run:

```powershell
python -m uv run python -c "import fastapi, psycopg, httpx, anthropic, uvicorn, pydantic; print('imports_ok')"
```

Result: `imports_ok`.

## 7. Docker Audit

Compose files:

- `docker-compose.grafana.yml` only.

There is no detected main Compose file for the API, Postgres, Redis, and runtime.

Docker commands:

- `docker --version`: Docker 29.2.0
- `docker compose version`: v5.0.2
- `docker ps -a`: failed
- `docker volume ls`: failed
- `docker network ls`: failed

Failure:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

Docker readiness: **RED**

Impact:

- Cannot verify Postgres container.
- Cannot verify Redis container.
- Cannot verify Grafana container.
- Cannot verify restart policies, volumes, healthchecks, networks, or old containers.
- Permanent server startup is not deterministic.

Grafana Compose note:

- `docker-compose.grafana.yml` uses `grafana/grafana:latest`.
- It exposes `3001:3000`.
- It contains default `admin/admin`, which is acceptable only for local testing and should be changed before any persistent monitoring exposure.

## 8. Database and Redis Readiness

| Item | Status | Evidence |
|---|---|---|
| Postgres container | UNKNOWN/RED | Docker daemon unreachable; port not listening in checked common ports |
| Redis container | UNKNOWN/RED | Docker daemon unreachable; port not listening in checked common ports |
| Migration scripts | GREEN | 57 SQL migrations under `app/db/migrations/` |
| Migration runner | GREEN/PARTIAL | `scripts/migrate_runtime.ps1` calls `python -m uv run app/db/migrate.py` |
| DB URL config | PRESENT | `.env.example` and scripts use `POLYBOT_DATABASE_URL`; value not printed here |
| Redis usage | PARTIAL/UNKNOWN | Redis service not verified; event mesh appears Postgres-backed in current V2 code |
| Schema drift risk | YELLOW | Migrations exist, but DB cannot be queried while Docker/Postgres are down |

Next DB verification:

1. Start Docker Desktop.
2. Verify Postgres container and port.
3. Run `scripts/migrate_runtime.ps1`.
4. Query migration status with the migration tool, not by dumping tables.
5. Verify `event_log`, market tables, orderbook snapshots, and runtime state exist.

## 9. Environment Variables

`.env` exists and is ignored by `.gitignore`. Values were not printed.

### Present In `.env`

| VAR_NAME | Present | Secret | Purpose | Risk If Missing |
|---|---|---|---|---|
| ANTHROPIC_API_KEY | YES | YES | Cloud AI / legacy Anthropic paths | Cloud AI unavailable; some legacy lite narrators may raise if invoked |
| LIVE_KILL_SWITCH | YES | NO | Live safety | Must default true |
| LIVE_MARKET_WHITELIST | YES | NO | Live market allowlist | Live must not run without it |
| LIVE_MAX_ORDER_USD | YES | NO | Live cap | Live unsafe if absent in live mode |
| LIVE_MIN_CONFIDENCE | YES | NO | Live confidence gate | Live unsafe if absent in live mode |
| LIVE_OPTIONAL_WHITELIST_MODE | YES | NO | Live whitelist behavior | Live unsafe if misconfigured |
| LIVE_TRADING_ENABLED | YES | NO | Live master switch | Must remain false |
| LIVE_USE_ADAPTIVE_SELECTOR | YES | NO | Live selector behavior | Future live only |
| POLY_API_KEY | YES | YES | Polymarket API credential | Not needed for DATA_ONLY public reads |
| POLY_API_PASSPHRASE | YES | YES | Polymarket API credential | Not needed for DATA_ONLY public reads |
| POLY_API_SECRET | YES | YES | Polymarket API credential | Not needed for DATA_ONLY public reads |
| POLY_FUNDER | YES | YES | Wallet/funder | Not needed now |
| POLY_PRIVATE_KEY | YES | YES | Private key | High sensitivity; should not be on this machine until live is explicitly certified |
| POLYBOT_EXECUTION_BACKEND | YES | NO | Backend mode | Misconfig can affect runtime behavior |
| POLYBOT_RUNTIME_MODE | YES | NO | Runtime mode | Must not silently enable live |

### Present In `.env.example`

Includes DB/runtime/paper/live settings:

- `POLYBOT_DATABASE_URL`
- `POLYBOT_RUNTIME_MODE`
- `POLYBOT_EXECUTION_BACKEND`
- `POLYBOT_API_HOST`
- `POLYBOT_API_PORT`
- `POLYBOT_INTELLIGENCE_*`
- `ANTHROPIC_API_KEY`
- paper capital limits
- live caps and live credentials placeholders

Security note: `.env` contains live credential variable names. The audit did not print values. For a 24/7 DATA_ONLY/PAPER server, live private keys should be absent or encrypted/off-machine until live certification.

## 10. Polymarket Market Data Readiness

Evidence:

- `app/tools/polymarket_orderbook_smoke.py`
- `run_reports/polymarket_orderbook_smoke.json`
- `app/ingestion/gamma_client.py`
- `app/data_foundation/orderbook_snapshotter.py`
- `app/market_neuron/orderbook_analyzer.py`
- `app/repositories/orderbook_snapshot_repository.py`

Smoke result:

- status: GREEN
- rows_count: 10
- errors_count: 0
- best bid / best ask present
- spread present
- bids/asks count present
- min order size present
- tick size present

Correct path is implemented in the smoke tool:

```text
Gamma live events -> markets[] -> clobTokenIds -> CLOB /book -> best bid / best ask / spread / depth
```

Best bid / ask correctness:

- Smoke tool uses `max(bids.price)` for best bid.
- Smoke tool uses `min(asks.price)` for best ask.
- Data foundation `orderbook_snapshotter.py` uses the same max/min logic.

Remaining gaps before real Data Foundation/PAPER:

- Smoke writes to `run_reports/polymarket_orderbook_smoke.json`, not directly to Postgres.
- Previous V2.20B audit found `orderbook_snapshots=0`; this audit could not re-query DB because Docker/Postgres are down.
- PAPER should remain blocked until fresh orderbook/depth snapshots are persisted and visible through `/data/markets/{market_id}/orderbook/latest`.

## 11. AI / Hybrid AI Brain Readiness

Detected:

- Ollama client exists: version 0.19.0.
- Ollama process names were visible.
- Ollama API is not reachable at `http://localhost:11434/api/tags`.
- No installed model list could be retrieved.

Current model router references:

- `qwen3:8b`
- `qwen3:14b`
- `deepseek-r1:14b`
- `cloud-critical-reasoner`

Server hardware recommendation:

- Recommended local first model: `qwen3:4b`
- Optional controlled test: `qwen3:8b`
- Not recommended for routine use on this server: `qwen3:14b`, `deepseek-r1:14b`
- Heavy reasoning should use cloud escalation later, under AI budget guard.

AI code readiness:

- `app/ai_brain/local_ai_worker.py` supports `UNAVAILABLE` when transport/model is missing.
- `app/ai_brain/cache.py`, budget/cost/decision/performance modules exist.
- `HybridAIBrainService` uses cache, budget governor, cost ledger, decision log, and redaction.
- Some legacy services still raise if `ANTHROPIC_API_KEY` is missing when those paths are invoked, for example cognition/event interpreter code paths.

AI readiness rating: **YELLOW/RED**

Can bot continue without AI:

- Core deterministic/runtime paths can continue in degraded AI mode if AI is not invoked as required truth.
- Any path requiring local model output must return `AI_UNAVAILABLE` / `INSUFFICIENT_DATA`, not fake output.

Must install/verify only if local AI is desired:

```powershell
ollama serve
ollama pull qwen3:4b
ollama list
```

Do not install 14B models for routine operation on 8GB RAM.

## 12. Runtime Modes and Safety

Modes in code:

- `DATA_ONLY`
- `PAPER`
- `SHADOW_LIVE`
- `SMALL_LIVE`
- `ATTACK_MODE`
- `COOLDOWN`
- `KILL`

Safety evidence:

- `app/runtime/modes.py` defines mode permissions.
- `DATA_ONLY` can collect/score/intelligence but cannot open paper/live positions.
- `PAPER` can open paper positions and run paper engine.
- `SHADOW_LIVE` can create shadow orders but not live orders.
- `COOLDOWN` blocks opening new positions.
- `KILL` returns no permissions.
- `app/runtime/safe_startup.py` keeps persisted state as authority and records downgrade if env requests elevated mode.
- `app/stage4/live_guard.py` blocks live order if live kill switch is enabled, live trading is false, whitelist is missing, market not whitelisted, or `--armed` is missing.
- V2.14-V2.16 code enforces risk approval, exit plans, internal paper/shadow-only execution, and no live exits.

Safety uncertainty:

- The legacy `app/config.py` `canonical_runtime_mode()` maps unknown modes to `PAPER`; newer State Governor is authoritative, but this legacy helper should be treated carefully in operations.
- `.env` contains live credential variables. Their presence alone did not enable live in inspected guard code, but they should not be used on the server until certification.

## 13. API and Dashboard Audit

FastAPI app entrypoint: `app/main.py`.

Health-critical endpoints:

- `/healthz`
- `/health`
- `/runtime/state`
- `/runtime/health`
- `/events/lag`
- `/data/coverage`

Major V2 endpoints:

- `/ai/*`
- `/news/*`
- `/rules/*`
- `/social/*`
- `/whales/*`
- `/market-neuron/*`
- `/market-memory/*`
- `/brains/*`
- `/opportunities/*`
- `/strategy/*`
- `/capital/*`
- `/risk/*`
- `/execution/*`
- `/exits/*`
- `/no-trade/*`
- `/learning/*`

Dashboard V2 endpoints:

- `/dashboard/api/v2/overview`
- `/dashboard/api/v2/events`
- `/dashboard/api/v2/risk`
- `/dashboard/api/v2/engines`
- `/dashboard/api/v2/ai`
- `/dashboard/api/v2/no-trade`
- `/dashboard/api/v2/learning`
- `/dashboard/api/v2/memory`
- `/dashboard/api/v2/market`
- `/dashboard/api/v2/opportunities`
- `/dashboard/api/v2/capital`
- `/dashboard/api/v2/execution`
- `/dashboard/api/v2/exits`
- `/dashboard/api/v2/news`
- `/dashboard/api/v2/social`
- `/dashboard/api/v2/whales`
- `/dashboard/api/v2/live-flow`
- `/dashboard/api/v2/settings`

Runtime endpoint check now:

- `/healthz`: FAIL, unable to connect
- `/runtime/state`: FAIL, unable to connect
- `/dashboard/api/v2/overview`: FAIL, unable to connect

Dashboard truth rating: **YELLOW/RED until runtime and DB are running on this machine**.

## 14. Tests Audit

Test framework:

- pytest
- pytest-asyncio

Test files:

- 267 Python test files under `tests/`.

Targeted tests run in this audit:

```powershell
python -m uv run pytest tests/test_env_runtime.py tests/test_runtime_modes.py tests/test_state_governor.py tests/test_stage4_env_isolation.py -q
```

Result:

```text
19 passed, 7 skipped in 15.47s
```

```powershell
python -m uv run pytest tests/test_gamma_client.py tests/test_market_service.py -q
```

Result:

```text
4 passed in 10.68s
```

```powershell
python -m uv run pytest tests/test_v2_20b_runtime_readiness.py -q
```

Result:

```text
1 passed in 3.59s
```

```powershell
python -m uv run pytest tests/test_v2_20a_neural_mesh_readiness.py -q
```

Result:

```text
4 passed in 3.48s
```

Combined V2.20A/V2.20B command initially timed out:

```powershell
python -m uv run pytest tests/test_v2_20b_runtime_readiness.py tests/test_v2_20a_neural_mesh_readiness.py -q
```

Result:

```text
timed out after about 124 seconds
```

The split commands passed, so this looks like a test-process/environment timing issue, not a failing assertion.

Critical tests before server deployment:

1. Runtime/safety tests.
2. V2.20A/B readiness tests.
3. Market/Gamma tests.
4. Data foundation/orderbook snapshot tests.
5. V2.14 risk tests.
6. V2.15 execution safety tests.
7. V2.16 exit safety tests.
8. V2.18 dashboard API tests.
9. V2.20 no-live safety tests.

Missing for permanent server:

- A deterministic Docker/boot smoke test.
- Postgres/Redis live container health test.
- Orderbook persistence end-to-end smoke.
- Windows startup/restart recovery test.
- Log rotation/backup tests.

## 15. Scripts and Operations

Important scripts:

- `scripts/load_env.ps1`: loads `.env` safely.
- `scripts/check_env_runtime.ps1`: summarizes env runtime state without printing secret values.
- `scripts/migrate_runtime.ps1`: runs migrations against local Postgres URL.
- `scripts/start_runtime.ps1`: canonical runtime startup on 127.0.0.1:8000.
- `scripts/run_v2_20_data_only_smoke.ps1`: DATA_ONLY smoke.
- `scripts/run_v2_20_paper_smoke.ps1`: PAPER smoke.
- `scripts/run_v2_20_24h_data_only.ps1`: 24h DATA_ONLY run.
- `scripts/run_v2_20_24h_paper.ps1`: 24h PAPER run.
- `scripts/run_v2_20_72h_paper.ps1`: 72h PAPER run.
- `scripts/run_v2_20_7d_paper.ps1`: 7d PAPER run.
- `scripts/verify_v2_20_no_live_mutation.ps1`: no-live mutation check.
- `scripts/verify_v2_20_dashboard_truth.ps1`: dashboard truth check.
- `scripts/verify_v2_20_runtime_readiness.ps1`: runtime readiness check.

How to start today:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1
```

Current blocker: Docker/Postgres are not reachable, so migration/runtime startup cannot be certified now.

Missing for 24/7:

- Main app Docker Compose/service definition.
- Docker Desktop startup verification.
- Windows scheduled task or service wrapper.
- Restart policy.
- Log rotation policy.
- Backup/restore script for Postgres.
- Monitoring loop that writes run reports.

## 16. Ports and Local Services

Checked ports:

- 3000
- 3001
- 5432
- 55432
- 6379
- 8000
- 11434
- 5050
- 9090

No listeners were returned for these ports at audit time.

Expected local-only ports:

| Port | Service | Status | Exposure Recommendation |
|---|---|---|---|
| 8000 | POLYBOT FastAPI | DOWN | Local-only |
| 55432 | Postgres mapped port in scripts | UNKNOWN/DOWN | Local-only |
| 6379 | Redis | UNKNOWN/DOWN | Local-only |
| 3001 | Grafana | DOWN | Local-only unless secured |
| 11434 | Ollama | DOWN/UNREACHABLE | Local-only |

## 17. Security and Secrets

Findings:

- `.env` exists.
- `.env` is included in `.gitignore`.
- `.env` values were not printed.
- `.env` contains live credential variable names including `POLY_PRIVATE_KEY`, `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE`, and `POLY_FUNDER`.
- `rg --files` did not show committed `*.pem`, `*.key`, `*.crt`, or `*.p12` files outside ignored paths.
- Live guard code requires explicit live enablement and blocks under kill switch / missing armed / whitelist failures.

Security rating: **YELLOW**

Risk:

- Secret material may be present locally. That is acceptable only if this machine is physically and network-secured and never used for untrusted workloads. For DATA_ONLY/PAPER, live private keys are not needed and should ideally be absent.

## 18. 24/7 Server Readiness Checklist

### Hardware

- [ ] Confirm this is the intended dedicated server hardware.
- [ ] Upgrade RAM to 16GB.
- [ ] Keep at least 100GB free on the primary SSD if logs/DB grow locally.
- [ ] Disable sleep/hibernate for 24/7 operation.
- [ ] Configure Windows updates for controlled maintenance windows.
- [ ] Use a UPS if possible.

### Software

- [ ] Start Docker Desktop and verify daemon.
- [ ] Ensure Docker Desktop starts at boot.
- [ ] Create deterministic Postgres container with restart policy.
- [ ] Create deterministic Redis container if used.
- [ ] Keep Python 3.11 and `python -m uv`.
- [ ] Add `uv` to PATH or standardize all scripts on `python -m uv`.
- [ ] Optional: install/repair Ollama service.
- [ ] Optional: install `qwen3:4b`.

### Network

- [ ] Stable internet.
- [ ] DNS reliable.
- [ ] Keep DB/Redis/Ollama local-only.
- [ ] Decide remote access plan: Tailscale/SSH/RDP/VPN.
- [ ] Do not expose API/dashboard publicly without auth and firewall rules.

### Operations

- [ ] Define startup command.
- [ ] Define shutdown command.
- [ ] Define health check command.
- [ ] Define backup plan.
- [ ] Define logs directory and retention.
- [ ] Define run_reports retention.
- [ ] Define failure recovery plan.
- [ ] Run 30-minute DATA_ONLY smoke before 24h.

## 19. Recommended Installation List

### Must Have

- Docker Desktop running and daemon reachable.
- Git.
- Python 3.11.
- uv tooling, preferably available as `uv` or consistently through `python -m uv`.
- Postgres via Docker.
- Redis via Docker if event/queue usage requires it.
- Project dependencies from `uv.lock`.

### Recommended

- Ollama, if local degraded AI is desired.
- `qwen3:4b` as first local model test.
- Grafana, only if monitoring dashboards are needed and secured.
- Tailscale or another secure remote access plan.
- Windows scheduled task/service wrapper for runtime.

### Optional

- `qwen3:8b` for controlled tests.
- Anthropic/Claude API key for cloud escalation.
- OpenAI API key if future code uses it.
- External monitoring.

### Not Recommended Now

- `qwen3:14b` as routine local model.
- `deepseek-r1:14b` as routine local model.
- Heavy local AI on 8GB RAM.
- Live trading keys on the server before live certification.
- Wallet private keys before explicit live readiness.

## 20. Final Action Plan

1. **Confirm machine identity**
   - Command:
     ```powershell
     Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors
     Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model,TotalPhysicalMemory
     ```
   - GREEN: hardware matches intended server.
   - RED: hardware mismatch unresolved.

2. **Start Docker Desktop**
   - Command:
     ```powershell
     docker ps
     docker info
     ```
   - GREEN: daemon responds.
   - RED: daemon unreachable.

3. **Verify Postgres and Redis**
   - Command:
     ```powershell
     docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
     ```
   - GREEN: Postgres and Redis containers running with restart policy.
   - RED: missing/down.

4. **Verify env without printing secrets**
   - Command:
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\scripts\check_env_runtime.ps1
     ```
   - GREEN: runtime mode safe, live disabled, kill switch true.
   - RED: live enabled or kill switch false.

5. **Run migrations**
   - Command:
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
     ```
   - GREEN: migrations apply cleanly.
   - RED: DB unavailable or migration fails.

6. **Start runtime**
   - Command:
     ```powershell
     powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1
     ```
   - GREEN: `/healthz` responds.
   - RED: port does not open or endpoints hang.

7. **Verify core endpoints**
   - Command:
     ```powershell
     Invoke-RestMethod http://127.0.0.1:8000/healthz
     Invoke-RestMethod http://127.0.0.1:8000/runtime/state
     Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/overview
     ```
   - GREEN: all return quickly.
   - RED: timeout/fail.

8. **Verify Polymarket smoke**
   - Command:
     ```powershell
     python -m uv run python app/tools/polymarket_orderbook_smoke.py
     ```
   - GREEN: rows > 0 and errors = 0.
   - RED: no orderbooks.

9. **Repair/install light local AI only if needed**
   - Command:
     ```powershell
     ollama serve
     ollama pull qwen3:4b
     ollama list
     ```
   - GREEN: Ollama API responds and `qwen3:4b` appears.
   - YELLOW: AI remains unavailable but bot degrades safely.

10. **Run 30-minute DATA_ONLY soak**
    - Command:
      ```powershell
      powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_data_only_smoke.ps1 -DurationSeconds 1800 -IntervalSeconds 60
      ```
    - GREEN: no crashes, no live mutations, dashboard truth OK, event lag acceptable.
    - RED: runtime crash, DB errors, live mutation, or dashboard failure.

## 21. Final Output

### Short Summary

The repo is technically rich and mostly ready at the code level, and Polymarket public market/orderbook access is verified. The server machine is not ready for permanent 24/7 operation because Docker is currently down, Postgres/Redis cannot be verified, runtime endpoints are not live, no main Docker Compose/service exists for the app, and the detected hardware does not match the provided target-server hardware.

### Current Readiness Score

**57 / 100**

### GREEN Items

- Repo present and complete.
- FastAPI entrypoint present.
- V2 runtime/event/data/risk/execution/exit/no-trade/learning/dashboard modules present.
- 57 migrations present.
- `.venv` exists.
- Python dependency import smoke passed.
- Polymarket Gamma -> CLOB `/book` smoke passed with 10 usable books and 0 errors.
- Safety/runtime targeted tests passed.
- `.env` ignored by `.gitignore`.
- Live guard blocks live by default safety conditions.

### YELLOW Items

- Hardware mismatch between prompt and detected machine.
- 8GB RAM is marginal for 24/7 Docker plus DB plus scans.
- `uv` not on PATH.
- Ollama installed/process exists but API unreachable.
- AI model references are too heavy for this hardware plan.
- News/social/whale source freshness unverified.
- Dashboard truth cannot be checked until runtime is live.
- Runtime scripts are present but not service-managed.

### RED Items

- Docker daemon unreachable.
- Postgres/Redis containers unverified.
- No runtime listening on port 8000.
- No main app Docker Compose.
- No verified restart policy.
- No verified DB backup/log rotation.
- PAPER not ready.
- LIVE not ready.

### Required Installs / Verifications

- Docker Desktop daemon working.
- Postgres container.
- Redis container if required.
- `uv` PATH or script standardization.
- Optional Ollama repair/install.
- Optional `qwen3:4b`.

### Required Fixes

- Resolve hardware identity mismatch.
- Add deterministic startup for API/Postgres/Redis.
- Verify migrations on running Postgres.
- Verify runtime endpoints.
- Persist fresh orderbook snapshots to DB.
- Add/verify backup and log rotation.
- Remove live private keys from DATA_ONLY/PAPER server unless explicitly needed later.

### Recommended Upgrades

- RAM to 16GB.
- Stable UPS/power settings.
- Secure remote access via Tailscale/VPN.
- Monitoring with secured Grafana.
- Use cloud AI escalation for heavy reasoning rather than 14B local models.

### Exact Next 10 Commands

```powershell
Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model,TotalPhysicalMemory
docker ps
docker info
docker compose version
powershell -ExecutionPolicy Bypass -File .\scripts\check_env_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1
Invoke-RestMethod http://127.0.0.1:8000/healthz
python -m uv run python app/tools/polymarket_orderbook_smoke.py
```

### Readiness Decisions

| Question | Answer |
|---|---|
| Ready for 24/7 DATA_ONLY? | NO |
| Ready for PAPER? | NO |
| Ready for LIVE? | NO |

The next legitimate milestone is not PAPER. It is: Docker/DB/runtime up, endpoints verified, then a 30-minute DATA_ONLY smoke.
