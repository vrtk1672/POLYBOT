# POLYBOT Post-Side Risk + Exit Readiness Build Report

## Current Reality Found

Before recovery, side evidence existed but Risk and Exit still did not consume it:

- candidates total: 6722
- candidates with side: 2486
- candidates with side and trusted binding: 2486
- candidates with side and fresh orderbook: 2486
- candidates with side and mid price: 2486
- risk approved: 0
- exit ready: 0
- eligible candidates: 0
- paper intents/orders/fills/positions: 0
- live orders: 0
- real `orders_v2`: 1 historical row
- `fills_v2`: 1 historical row
- canonical positions: 0

Root cause: stale thesis blockers (`MISSING_MARKET_LINK`, `THESIS_BLOCKED`) remained after side recovery, and Risk/Exit/Eligibility input readers prioritized `created_at` instead of current `updated_at` evidence.

## Files Created

- `app/services/post_side_risk_exit_readiness.py`
- `app/db/migrations/0093_post_side_risk_exit_readiness_recovery.sql`
- `tests/test_post_side_risk_exit_readiness_service.py`
- `tests/test_dashboard_risk_exit_readiness_truth.py`
- `tests/test_post_side_risk_exit_runtime.py`
- `docs/POLYBOT_POST_SIDE_RISK_EXIT_READINESS.md`
- `docs/POLYBOT_POST_SIDE_RISK_EXIT_READINESS_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/repositories/risk_core_repository.py`
- `app/repositories/exit_foundation_repository.py`
- `app/repositories/paper_eligibility_repository.py`

## DB Changes

Migration `0093_post_side_risk_exit_readiness_recovery.sql` adds `post_side_risk_exit_recovery_runs` for audited recovery runs, before/after counts, blockers, safety deltas, and metadata.

## Runtime Integration

`MarketService.refresh()` now runs Post-Side Risk + Exit Readiness Recovery after Downstream Evidence Recompute and before Candidate Eligibility Recovery.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/risk-exit-readiness`

Dashboard response is DB-backed and returns `mock_data=false`.

## Tests Run

- `tests/test_post_side_risk_exit_readiness_service.py tests/test_dashboard_risk_exit_readiness_truth.py tests/test_post_side_risk_exit_runtime.py`: 6 passed
- Post-side + Risk/Exit/Eligibility service band: 19 passed
- Side recovery + candidate eligibility + paper execution/exit safety band: 34 passed, 1 warning
- System power/runtime/4C consolidated band: 70 passed, 1 warning

## Runtime Smoke

OFF smoke:

- `POST /system/power/off`: 200
- post-side runs stayed unchanged across scheduler interval
- paper intents/orders/fills/positions stayed unchanged
- `orders_v2=1`, `fills_v2=1`, `positions=0`

ON smoke:

- `POST /system/power/on`: 200
- post-side recovery ran automatically
- final latest run: `status=OK`
- candidates checked: 100
- thesis recovered: 100
- risk approved before/after in latest run: 109 -> 112
- exit ready before/after in latest run: 109 -> 112
- eligible before/after in latest run: 109 -> 112
- post-side service paper intents before/after: 0 -> 0
- candidate eligibility recovery paper intents after: 3
- paper orders/fills/positions: 3/3/3 through existing safe paper path
- live orders: 0
- real orders: 0 live rows, `orders_v2=1` historical
- `fills_v2=1` historical
- canonical positions: 0

Final runtime counts:

- candidates total: 6850
- candidates with side: 2534
- candidates with side and trusted binding: 2534
- candidates with side and fresh orderbook: 2534
- candidates with side and mid price: 2534
- risk approved: 112
- exit ready: 112
- eligible candidates: 112
- paper intents: 3
- paper orders: 3
- paper fills: 3
- paper positions: 3
- live orders: 0

## Blockers Before / After

Before:

- `RISK_NOT_APPROVED`: 2486
- `RISK_BLOCKED`: 2486
- `EXIT_NOT_READY`: 2486
- `MISSING_FRESH_ORDERBOOK`: 3
- `MISSING_MID_PRICE`: 4239
- `THESIS_NOT_COMPLETE`: 2486
- `MISSING_SIGNAL_MARKET_BINDING`: 3
- `NO_VALID_PAPER_INTENTS`: 1

After:

- `RISK_NOT_APPROVED`: 2422
- `RISK_BLOCKED`: 2422
- `EXIT_NOT_READY`: 2422
- `MISSING_FRESH_ORDERBOOK`: 3
- `MISSING_MID_PRICE`: 4319
- `THESIS_NOT_COMPLETE`: 2422
- `MISSING_SIGNAL_MARKET_BINDING`: 3
- `NO_VALID_PAPER_INTENTS`: 0

## Candidate Trace Summary

The final trace found 10 side-bearing candidates with:

- trusted binding: YES
- orderbook fresh: YES
- mid price: 0.115
- thesis status: COMPLETE
- risk status: APPROVE
- exit status: COMPLETE
- eligibility status: ELIGIBLE
- paper intent id: not yet present on those trace rows
- next blocker: `READY_FOR_PAPER_INTENT_GATE`

## Safety Confirmation

- SYSTEM OFF blocked recovery.
- Recovery did not call Paper Intent or Paper Execution directly.
- Paper artifacts appeared only later through existing safe eligibility/intent/execution handoff.
- Live orders stayed 0.
- Real orders stayed blocked.
- Canonical `orders_v2` and `fills_v2` remained historical unchanged counts.
- No secrets printed.
- No destructive DB action used.

## Remaining Risks

- 2422 side-bearing candidates remain blocked by thesis/risk/exit evidence.
- `MISSING_MID_PRICE` remains present on older exit-plan rows and should be interpreted by current candidate linkage, not raw table total alone.
- Dashboard endpoint is now optimized, but the trace should stay bounded to avoid heavy scans as runtime volume grows.

## Next Recommended Step

Move to Paper Dashboard + Regression + Soak Readiness with close attention to paper position lifecycle, intent/execution idempotency, and no-live safety.
