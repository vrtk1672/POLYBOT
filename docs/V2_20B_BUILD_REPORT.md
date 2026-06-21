# V2.20B Build Report - Critical Mesh Readiness Blockers

Date: 2026-05-18

## Purpose

V2.20B fixed the runtime readiness blockers found by the V2.20A Neural Mesh Readiness Audit. This was not a feature phase. No trading features, live execution, order intents, external balance mutation, or live certification were added.

## Root Cause

The runtime opened port `8000`, but health/dashboard probes timed out because heavy startup and scheduled refresh work could monopolize runtime responsiveness:

- Dashboard overview and market pages called expensive legacy/operator query paths.
- `MarketService.refresh()` performed large scoring, persistence, intelligence, paper-processing, and terminal rendering work on the FastAPI event loop.
- `LiveCapitalSource.snapshot()` could call the external Polymarket CLOB balance endpoint from dashboard/health paths when credentials existed, even while live trading was disabled and kill switch was active.

## Fixes Applied

- `LiveCapitalSource.snapshot()` now returns an internal `DISABLED` snapshot without calling CLOB balance when live trading is disabled or kill switch is active.
- `MarketService.refresh()` now yields during large normalization loops and offloads scoring, DB persistence, data foundation, intelligence, paper cycle processing, and table rendering to worker threads.
- Dashboard V2 overview now uses a direct DB-backed fast truth path for runtime/capital/risk/opportunity/execution/exit/no-trade/learning/event/AI summary.
- Dashboard V2 market page now uses a direct DB-backed fast truth path for market, orderbook, liquidity, and technical freshness.

## Verification

Tests:

- `python -m uv run pytest tests/test_v2_20a_neural_mesh_readiness.py -q` -> `4 passed in 16.64s`
- `python -m uv run pytest tests/test_runtime_*.py -q` via PowerShell file expansion -> `8 passed, 19 skipped in 32.62s`
- `python -m uv run pytest tests/test_v2_19_*.py -q` via PowerShell file expansion -> `21 passed, 8 skipped in 42.62s`
- `python -m uv run pytest tests/test_v2_18_*.py -q` via PowerShell file expansion -> `5 passed, 3 skipped in 32.08s`
- Additional focused check: `python -m uv run pytest tests/test_v2_20b_runtime_readiness.py tests/test_v2_18_dashboard_v2_api.py -q` -> `3 passed, 3 skipped in 16.42s`

Runtime:

- `scripts/migrate_runtime.ps1` -> `No pending migrations.`
- Canonical `scripts/start_runtime.ps1` started runtime with `live_enabled=false`, `live_kill_switch=true`.
- After scheduled refresh began, core endpoint probes stayed responsive:
  - `/healthz` -> `200`, post-refresh `1.004534s`
  - `/runtime/state` -> `200`, post-refresh `1.431978s`
  - `/runtime/health` -> `200`, post-refresh `0.538388s`
  - `/dashboard/api/v2/overview` -> `200`, post-refresh `1.521143s`
  - `/dashboard/api/v2/market` -> `200`, post-refresh `0.683447s`
  - `/dashboard/api/v2/learning` -> `200`, post-refresh `0.625988s`
  - `/data/coverage` -> `200`, post-refresh `0.448585s`
  - `/events/lag` -> `200`, post-refresh `0.350766s`

Dashboard truth:

- `scripts/verify_v2_20_dashboard_truth.ps1` -> `ok=true`, `violations=[]`.
- Dashboard endpoints returned real DB/runtime truth with stale/no-data states where applicable.

Mesh live evidence:

- `event_log` responded with `total_events=6115`, `failed_events=0`, `dlq_count=0`, latest event timestamp `2026-05-18T13:03:17.379482+00:00`.
- Runtime refresh completed after the fix: `refresh_complete events=2500 markets=10590 scored=10590`.
- Logs showed Gamma fetches and CLOB orderbook reads returning `200`.
- No `balance-allowance` CLOB balance call appeared after the live-capital safety fix.

## AI Readiness

`scripts/verify_v2_20_ai_models.ps1` reported:

- Ollama binary not detected.
- Local models missing: `qwen3:8b`, `qwen3:14b`, `deepseek-r1:14b`.
- Script shell did not have `ANTHROPIC_API_KEY`; canonical runtime environment did report `anthropic_key_present=true`.
- Fallback behavior is degraded/unavailable, not fake output.

Install commands if local model runtime is required:

```powershell
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull deepseek-r1:14b
```

## Source Freshness

- Market snapshots: fresh enough for DATA_ONLY smoke, latest `2026-05-18T13:00:27.344494+00:00`.
- Liquidity coverage: `100.0%`.
- Orderbook coverage: `0.0%` in persisted `orderbook_snapshots`; logs show CLOB `book` calls returning `200`, but DB orderbook freshness is not verified.
- News dashboard: `STALE`.
- Social dashboard: `STALE`.
- Whale dashboard: `STALE`.

## Remaining Blockers

High:

- PAPER smoke remains blocked until persisted orderbook/liquidity freshness is verified.
- Docker readiness still times out on `docker info`.
- News/social/whale sources are stale in dashboard truth.

Medium:

- Startup takes roughly 34-39 seconds before Uvicorn is ready.
- Some dashboard module pages are truthfully stale due old records.

## Safety

- Live trading remained disabled.
- Kill switch remained active in Stage4 live settings.
- No live orders, order intents, live exits, or external balance mutation path was added.
- Dashboard/control behavior remains read-only for V2.20B verification.

## Phase Status

V2.20B status: **YELLOW**.

30m DATA_ONLY smoke can start. PAPER smoke and long-run readiness remain blocked pending persisted orderbook freshness and stale source remediation.

## V2.20B-1 Operating Requirements Audit Addendum

V2.20B-1 completed a deeper operating requirements audit for external integrations, sources, secrets, models, runtime, modes, and mesh requirements.

Created:

- `docs/V2_20B_OPERATING_REQUIREMENTS_AUDIT.md`
- `docs/V2_20B_EXTERNAL_INTEGRATIONS_AUDIT.md`
- `scripts/verify_v2_20b_env_keys.ps1`
- `scripts/audit_v2_20b_external_integrations.ps1`

Key audit conclusions:

- News/social/whale modules are structurally present but not configured with fresh live sources.
- Market/Gamma flow is real and fresh enough for DATA_ONLY smoke.
- Persisted `orderbook_snapshots` remain zero, so PAPER remains blocked.
- Local AI models and Ollama are missing; AI-degraded DATA_ONLY is acceptable, AI-full is not.
- `.env` contains several key names, but scripts intentionally report only key presence, never values.
- Dashboard truth remains DB-backed and stale-aware.

V2.20B-1 status: **YELLOW**. Proceed to fixes and 30m DATA_ONLY smoke only; do not proceed to PAPER or long-run.
