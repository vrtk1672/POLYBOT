# V2.20 Paper Full System Run

V2.20 is a verification and evidence-gathering phase. It does not add strategy, capital, risk, execution, exit, or learning behavior. It verifies that the existing V2.0-V2.19 chain can run as one safe system with real DB/runtime truth and no live mutation.

## Purpose

V2.20 answers whether POLYBOT can run end to end without real money:

- DATA_ONLY observes and analyzes without paper/live execution mutation.
- PAPER may create only internal paper/shadow records through the certified V2.15/V2.16 boundaries.
- Dashboard V2 reflects real runtime/DB truth.
- Failures, stale data, duplicates, or orphans are reported instead of hidden.

## Run Stages

Required staged runs:

1. 24h DATA_ONLY
2. 24h PAPER
3. 72h PAPER
4. 7d PAPER

Short smoke runs are allowed when the current environment cannot stay alive for long durations, but they are not substitutes for the required long-duration evidence.

## Scripts

Smoke scripts:

- `scripts/run_v2_20_data_only_smoke.ps1`
- `scripts/run_v2_20_paper_smoke.ps1`

Long-run wrappers:

- `scripts/run_v2_20_24h_data_only.ps1`
- `scripts/run_v2_20_24h_paper.ps1`
- `scripts/run_v2_20_72h_paper.ps1`
- `scripts/run_v2_20_7d_paper.ps1`

Verification scripts:

- `scripts/verify_v2_20_system_truth.ps1`
- `scripts/verify_v2_20_no_live_mutation.ps1`
- `scripts/verify_v2_20_duplicates_orphans.ps1`
- `scripts/verify_v2_20_dashboard_truth.ps1`
- `scripts/verify_v2_20_ai_cost_cache.ps1`

The scripts force `LIVE_TRADING_ENABLED=false`, `LIVE_EXECUTION_ENABLED=false`, and `LIVE_KILL_SWITCH=true`. Runtime mode changes are requested through `/runtime/mode/request` with actor and reason; scripts do not edit State Governor tables directly.

## Run Commands

Targeted smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_data_only_smoke.ps1 -DurationSeconds 600 -IntervalSeconds 60
powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_paper_smoke.ps1 -DurationSeconds 600 -IntervalSeconds 60
```

Long-duration evidence:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_24h_data_only.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_24h_paper.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_72h_paper.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_v2_20_7d_paper.ps1
```

Standalone checks:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_v2_20_system_truth.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_v2_20_dashboard_truth.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_v2_20_duplicates_orphans.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_v2_20_ai_cost_cache.ps1
```

## Expected Metrics

Each checkpoint captures:

- runtime endpoint health
- dashboard endpoint truth
- table counts for live orders, paper orders, orders_v2, fills_v2, exit plans/intents, no-trade, learning, model adjustments, and events
- pipeline table row counts by module
- event count, latest event timestamp, lag, and DLQ state
- AI cost, request count, cache entries, and cache hit rate
- duplicate active order groups
- orphan internal V2 orders missing exit plans

Reports are written to `run_reports/v2_20/*.json`.

## Safety Boundaries

V2.20 verification must never:

- enable live trading
- send live orders
- create live exits
- mutate external balances
- bypass State Governor
- bypass Risk Governor
- hide duplicate/orphan findings
- fake long-run completion

DATA_ONLY fails if paper execution records grow. PAPER permits only internal paper/shadow records and still fails on live order mutation.

## Dashboard Checks

Dashboard checks call:

- `/dashboard/api/v2/overview`
- `/dashboard/api/v2/events`
- `/dashboard/api/v2/risk`
- `/dashboard/api/v2/capital`
- `/dashboard/api/v2/execution`
- `/dashboard/api/v2/exits`
- `/dashboard/api/v2/no-trade`
- `/dashboard/api/v2/learning`

Responses are accepted when they are real DB/runtime truth. Stale, NO_DATA, DEGRADED, and INSUFFICIENT_DATA are valid when honestly labeled. Any `mock_data=true` response is a failure.

## Duplicate And Orphan Checks

Duplicate detection groups active `orders_v2` by `market_id`, `side`, and `engine`.

Orphan detection checks active `orders_v2` against `exit_plans` by `exit_plan_id` or `order_id`. Legacy `paper_positions` are reported separately because legacy positions do not have a canonical V2 exit-plan linkage.

## AI Cost And Cache Checks

The AI check reads `ai_cost_ledger`, `ai_requests`, and `ai_cache` when present. Missing AI tables are reported as `NO_DATA`. Cost must remain bounded during smoke and long runs.

## What Actually Ran

See `docs/V2_20_BUILD_REPORT.md` for the latest executed evidence. Long-duration 24h/72h/7d runs must not be marked complete until their scripts finish and reports are saved.

## Remaining Risks

- Long-duration evidence is required before Shadow Live can be considered.
- PAPER mode depends on State Governor accepting an audited transition.
- Legacy `paper_positions` have limited exit-plan linkage and must be treated as partial truth.

## Next Recommended Phase

Do not start V2.21 Shadow Live until V2.20 has at least 24h DATA_ONLY, 24h PAPER, 72h PAPER, and preferably 7d PAPER evidence with no safety violations.
