# POLYBOT Paper Dashboard + Regression + Soak Readiness

## Scope

This phase adds a unified Paper dashboard truth surface, Paper technical regression coverage, and a guarded 4h Paper soak runner.

This is Paper-only. It does not enable live trading, shadow trading, real orders, capital allocation, strategy changes, or fake paper data.

## API

- `GET /dashboard/api/v2/paper`
- `GET /dashboard/api/v2/paper/positions`
- `GET /dashboard/api/v2/paper/pnl`
- `GET /dashboard/api/v2/paper/soak-readiness`

All responses are DB-backed and include `mock_data=false`.

## Regression Suite

Added focused tests for:

- paper dashboard truth
- runtime Paper safety regression
- soak readiness response
- PnL reconciliation
- orphan and duplicate checks
- no-live safety

## Soak Runner

- `scripts/run_4h_technical_paper_soak.py`
- `scripts/run_4h_technical_paper_soak.ps1`

The runner samples every five minutes by default, writes a line-delimited JSON log, writes a Markdown report, and turns SYSTEM OFF on critical stop conditions.

## Definition Of Done

- Unified Paper endpoints exist.
- Required regression tests pass.
- Soak readiness endpoint returns GREEN before a soak is started.
- Baseline safety counts are captured.
- A started soak has log and report paths.
- No live or real execution state mutates.
