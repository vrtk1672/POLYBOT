# Canonical Runtime

## Purpose

This is the one true local runtime path for POLYBOT. Use it to remove startup drift, DB drift, and mode ambiguity.

## Canonical Local Runtime

- Canonical DB target: `postgresql://polybot:polybot@127.0.0.1:55432/polybot`
- Canonical dashboard URL: `http://127.0.0.1:8000/dashboard`
- Canonical docs URL: `http://127.0.0.1:8000/docs`
- Canonical health URL: `http://127.0.0.1:8000/dashboard/api/health`
- Canonical default mode: `paper_safe`
- Canonical execution backend: `paper`

## Required Environment

Minimum local runtime variables:

- `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
- `PHASE1_PERSISTENCE_ENABLED=true`
- `POLYBOT_RUNTIME_MODE=paper_safe`
- `POLYBOT_EXECUTION_BACKEND=paper`
- `LIVE_TRADING_ENABLED=false`
- `LIVE_KILL_SWITCH=true`

`DATABASE_URL` is non-canonical for local operation and should be unset to avoid target drift.

## Official Local Ritual

Migration:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
```

Startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1
```

Smoke check:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_runtime.ps1
```

## Paper vs Live Discipline

- Local runtime defaults to `paper_safe`
- `paper_safe` means dashboard/API runtime with live trading disabled
- Live is not a separate architecture in this repo
- Live differs only through Stage 4 execution settings and explicit CLI flags
- No server startup path should silently enable live behavior
- Any future live action must require both explicit Stage 4 flags and `LIVE_TRADING_ENABLED=true`

## Telegram

- Command endpoint: `POST http://127.0.0.1:8000/telegram/command`

## Deprecated / Non-Canonical Paths

- `python -m uv run polybot` directly: still works, but non-canonical for operators because it does not force the safe runtime env
- `python -m uv run app/db/migrate.py` directly: still works, but non-canonical for operators because it does not force the canonical DB target
- `gamma_crawler.py`: standalone scanner path, not the canonical runtime for the integrated system
- `brain.py` mode flags: phase-specific operator tooling, not the canonical local app runtime
- `DATABASE_URL`: accepted for compatibility only; not the canonical local DB selector
