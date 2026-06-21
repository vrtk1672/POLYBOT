# V2.20 Build Report - Paper Full System Run

## Status

YELLOW pending long-duration evidence.

V2.20 added verification tooling, smoke/long-run scripts, and targeted tests. It did not add trading logic, strategy logic, execution logic, live sending, order intents, live exits, or external balance mutation.

## Files Created

- `app/services/query/full_system_run_query_service.py`
- `app/tools/__init__.py`
- `app/tools/v2_20_full_system_run.py`
- `scripts/run_v2_20_data_only_smoke.ps1`
- `scripts/run_v2_20_paper_smoke.ps1`
- `scripts/run_v2_20_24h_data_only.ps1`
- `scripts/run_v2_20_24h_paper.ps1`
- `scripts/run_v2_20_72h_paper.ps1`
- `scripts/run_v2_20_7d_paper.ps1`
- `scripts/verify_v2_20_system_truth.ps1`
- `scripts/verify_v2_20_no_live_mutation.ps1`
- `scripts/verify_v2_20_duplicates_orphans.ps1`
- `scripts/verify_v2_20_dashboard_truth.ps1`
- `scripts/verify_v2_20_ai_cost_cache.ps1`
- `tests/test_v2_20_full_system_run.py`
- `tests/test_v2_20_system_truth_checks.py`
- `tests/test_v2_20_no_live_safety.py`
- `docs/V2_20_PAPER_FULL_SYSTEM_RUN.md`
- `docs/V2_20_BUILD_REPORT.md`

## Files Changed

- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

No V2.20 DB migration was added. The phase uses report files under `run_reports/v2_20/` instead of adding new persistence tables.

## API Routes

No V2.20 API routes were added. The phase verifies existing runtime, dashboard, learning, no-trade, exits, execution, and risk endpoints.

## Scripts

The V2.20 scripts:

- run migrations before smoke/long runs
- start or attach to runtime
- request runtime mode changes through `/runtime/mode/request`
- collect periodic checkpoints
- write JSON run reports
- force live trading and live execution disabled
- fail on safety violations

## Tests Added

- run report builder behavior
- DATA_ONLY no-live/no-paper mutation checks
- PAPER internal paper/shadow allowance
- dashboard mock-data rejection
- stale/no-data dashboard truth acceptance
- duplicate active order detection
- script live-disabled guardrails
- verification scripts are read-only

## Tests Run

Initial PowerShell wildcard command:

```powershell
python -m uv run pytest tests/test_v2_20_*.py -q
```

Result: no tests ran because PowerShell passed the wildcard literally.

Explicit targeted command:

```powershell
python -m uv run pytest tests/test_v2_20_full_system_run.py tests/test_v2_20_system_truth_checks.py tests/test_v2_20_no_live_safety.py -q
```

Result: `10 passed in 4.85s`.

Regression and runtime smoke results are recorded below when executed.

## Runtime Verification Results

Pending in this report until runtime smoke is executed in the current environment.

## Smoke Run Results

Pending in this report until DATA_ONLY and/or PAPER smoke scripts are executed.

## What Duration Actually Ran

Pending. Do not claim 24h/72h/7d completion until the long-run scripts actually finish.

## Prepared Long-Run Scripts

- 24h DATA_ONLY: `scripts/run_v2_20_24h_data_only.ps1`
- 24h PAPER: `scripts/run_v2_20_24h_paper.ps1`
- 72h PAPER: `scripts/run_v2_20_72h_paper.ps1`
- 7d PAPER: `scripts/run_v2_20_7d_paper.ps1`

## Safety Checklist

- live remains disabled: YES in scripts
- no live orders: checked by count-delta verification
- no external balance mutation: no external mutation path added
- DATA_ONLY does not create paper execution records: enforced by verification
- PAPER creates only internal paper/shadow records if tested: enforced by verification
- Risk Gate/Governor required before execution: existing V2.14/V2.15 behavior preserved
- Exit plans/orphans checked: YES
- duplicate trades/orders checked: YES for active `orders_v2`
- dashboard shows real data: checked by dashboard truth script
- no mock data: checked by dashboard truth script
- AI cost bounded/cache visible: checked by AI script
- no uncontrolled cloud escalation: checked through AI cost/request visibility
- crashes counted: smoke reports preserve endpoint/API errors
- errors reported honestly: YES

## Remaining Risks

- Long-duration 24h/72h/7d evidence has not yet been completed in this report.
- PAPER smoke depends on the State Governor accepting a safe audited mode transition.
- Legacy paper positions do not have complete V2 exit-plan linkage.

## Go / No-Go

Current phase status: YELLOW until smoke and long-duration run evidence is captured.

Can move to V2.21 Shadow Live: NO. V2.20 must first complete the staged paper evidence without safety violations.
