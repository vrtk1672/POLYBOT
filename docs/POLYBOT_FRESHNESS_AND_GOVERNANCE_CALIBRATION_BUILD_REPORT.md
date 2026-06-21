# POLYBOT Freshness Gate + Governance Blocker Calibration Build Report

Date: 2026-06-04

Security governance status: `YELLOW_ACCEPTED_BY_OPERATOR`

## Summary

Implemented a source-backed freshness governance layer and calibrated lifecycle governance blockers.

Stale sources can no longer authorize Paper. Old paper intents require refresh before execution. Optional missing context remains non-fatal by itself. Same-market guard now distinguishes active exposure from stale historical artifacts.

## Current Reality Found

Initial production counts:

- `lifecycle_governance_decisions`: 7693
- `trade_lifecycle_plans`: 7693
- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `paper_capital_ledger`: 38
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- canonical positions table count: 0

Initial actionability:

- `HARD_BLOCK`: 7393
- `WATCH_FOR_CONFIRMATION`: 300
- `ACTIONABLE_SMALL_PAPER`: 0
- `ACTIONABLE_STANDARD_PAPER`: 0
- `COMPLETE_HIGH_CONFIDENCE`: 0

Initial top blockers:

- `RISK_BLOCKED`: 4566
- `SAME_MARKET_OPPOSING_SIDE_BLOCK`: 2977
- `CAPITAL_BLOCKED`: 4

Initial top optional missing inputs:

- `MEMORY_CONTEXT_MISSING`: 7693
- `WHALE_CONTEXT_MISSING`: 7693
- `FAIR_PROBABILITY_MISSING`: 7593
- `NEWS_CONTEXT_MISSING`: 4283

Paper capital state:

- current balance: 996.81932200
- available balance: 996.81932200
- locked balance: 0
- open exposure: 0
- realized PnL: -3.18067800
- unrealized PnL: 0

## Root Findings

Freshness:

- Lifecycle plans and governance decisions were source-backed but did not enforce TTLs.
- Latest orderbook/trusted book/risk/exit/capital/economic reasoning records from the 4h run were historical by audit time.
- Old decisions could explain history but should not authorize Paper.

Old intents:

- 14 `CREATED` paper intents were old enough to require refresh before any execution.
- Several old same-market opposite-side intent pairs existed and could pollute same-market decisions if treated as active indefinitely.

Blockers:

- No plans were blocked only by optional missing context in the sampled audit.
- Most blocks were true critical blockers or stale/refresh-required after the new freshness pass.
- Same-market guard needed precision so old historical artifacts do not behave like fresh active exposure.

## Files Created

- `app/db/migrations/0125_freshness_and_governance_calibration.sql`
- `app/services/freshness_governance.py`
- `docs/POLYBOT_FRESHNESS_AND_GOVERNANCE_CALIBRATION.md`
- `docs/POLYBOT_FRESHNESS_AND_GOVERNANCE_CALIBRATION_BUILD_REPORT.md`

## Files Changed

- `app/services/lifecycle_governance.py`
- `app/services/same_market_side_guard.py`
- `app/services/paper_intents.py`
- `app/services/paper_execution.py`
- `app/services/paper_trade_forensics.py`
- `app/services/brain_dialogue.py`
- `app/api/routes.py`
- `tests/test_lifecycle_governance.py`
- `tests/test_same_market_side_guard.py`
- `tests/test_paper_execution_service.py`

Note: `scripts/run_active_30m_observation.py` had pre-existing local changes from the prior controlled-run phase and was not part of this freshness implementation.

## DB Migration

Migration: `0125_freshness_and_governance_calibration.sql`

Created:

- `freshness_governance_checks`
- `governance_blocker_calibration_runs`
- `governance_blocker_calibration_traces`

Migration was applied successfully through the canonical migrate container.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/freshness-governance`
- `GET /dashboard/api/v2/governance-calibration`
- `POST /freshness-governance/evaluate`

Verified:

- `/dashboard/api/v2/freshness-governance` returned `status=OK`, `mock_data=false`
- `/dashboard/api/v2/governance-calibration` returned `status=OK`, `mock_data=false`
- `/healthz` returned OK after API restart warm-up
- system power remained OFF

## Runtime Smoke

No 10m/30m/4h runtime run was started.

Smoke steps:

- Verified SYSTEM OFF.
- Captured safety baseline.
- Applied migration.
- Ran bounded freshness evaluation.
- Ran bounded lifecycle governance evaluation.
- Verified dashboards.
- Verified no trading mutation.
- Verified SYSTEM remained OFF.

Smoke deltas:

- `freshness_governance_checks`: +816
- `lifecycle_governance_decisions`: +100
- Paper intents/orders/fills/positions/closes: unchanged
- Paper capital ledger: unchanged
- live/orders_v2/fills_v2/canonical positions: unchanged
- capital balances: unchanged

Final freshness status counts:

- `EXPIRED`: 816

Final governance actionability:

- `HARD_BLOCK`: 7493
- `WATCH_FOR_CONFIRMATION`: 300
- `ACTIONABLE_SMALL_PAPER`: 0
- `ACTIONABLE_STANDARD_PAPER`: 0
- `COMPLETE_HIGH_CONFIDENCE`: 0

Final top critical blockers after bounded smoke:

- `RISK_BLOCKED`: 4620
- `SAME_MARKET_OPPOSING_SIDE_BLOCK`: 3023
- `STALE_RISK_DECISION`: 100
- `STALE_CAPITAL_EFFICIENCY`: 100
- `STALE_PAYOUT_ODDS`: 100
- `STALE_EXIT_PLAN`: 100
- `STALE_LIFECYCLE_PLAN`: 100
- `STALE_CAPITAL_EVALUATION`: 94
- `STALE_ORDERBOOK`: 94
- `STALE_EXIT_HOLD`: 60
- `RISK_BLOCKED_NO_EDGE`: 50
- `RISK_BLOCKED_LINEAGE`: 50
- `STALE_SAME_MARKET_GUARD`: 46
- `STALE_PAPER_CANDIDATE`: 46
- `STALE_PAPER_INTENT`: 14
- `RISK_BLOCKED_SPREAD`: 4
- `CAPITAL_BLOCKED`: 4

Old intents requiring refresh:

- 14

## Before / After Counts

| Metric | Before | After |
| --- | ---: | ---: |
| freshness_governance_checks | 0 | 816 |
| stale_sources_count | 0 | 816 |
| stale_lifecycle_plans | 7693 | 7693 |
| stale_governance_decisions | 7693 | 7693 |
| stale_risk_decisions | 11432 | 11432 |
| stale_exit_plans | 11432 | 11432 |
| old_intents_requiring_refresh | 14 | 14 |
| HARD_BLOCK | 7393 | 7493 |
| NO_TRADE | 0 | 0 |
| WATCH_FOR_CONFIRMATION | 300 | 300 |
| ACTIONABLE_SMALL_PAPER | 0 | 0 |
| ACTIONABLE_STANDARD_PAPER | 0 | 0 |
| COMPLETE_HIGH_CONFIDENCE | 0 | 0 |
| valid_critical_blockers | 7601 | 8605 |
| optional_misclassified_count | 0 | 0 |
| overblocking_count | 0 | 0 |
| closest_to_actionable_count | 20 | 20 |
| paper_intents | 20 | 20 |
| paper_orders | 12 | 12 |
| paper_fills | 9 | 9 |
| paper_positions | 12 | 12 |
| live_orders | 0 | 0 |
| orders_v2 | 1 | 1 |
| fills_v2 | 1 | 1 |
| canonical positions | 0 | 0 |
| current_balance | 996.81932200 | 996.81932200 |
| available_balance | 996.81932200 | 996.81932200 |
| locked_balance | 0 | 0 |
| open_exposure | 0 | 0 |
| realized_pnl | -3.18067800 | -3.18067800 |
| unrealized_pnl | 0 | 0 |

## Sample Stale Data Block

An old paper intent evaluated for Paper execution produced:

- `STALE_PAPER_INTENT`
- `REFRESH_REQUIRED_BEFORE_EXECUTION`

This blocks execution until fresh lifecycle governance is obtained.

## Sample Valid Critical Blocker

Risk-blocked lifecycle plans remain `HARD_BLOCK`.

New precision blockers include:

- `RISK_BLOCKED_NO_EDGE`
- `RISK_BLOCKED_LINEAGE`
- `RISK_BLOCKED_SPREAD`

## Sample Optional Context Not Hard-Blocking

Optional missing context such as:

- `MEMORY_CONTEXT_MISSING`
- `WHALE_CONTEXT_MISSING`
- `FAIR_PROBABILITY_MISSING`
- `NEWS_CONTEXT_MISSING`

is recorded separately and does not produce `HARD_BLOCK` by itself.

## Sample Closest-To-Actionable Finding

The dashboard calibration summary identified 20 closest-to-actionable records. In the current state they are not actionable because fresh critical inputs are missing or expired, not because optional context alone is missing.

## Tests Run

Compile check:

```text
python -m py_compile app\services\freshness_governance.py app\services\lifecycle_governance.py app\services\same_market_side_guard.py app\services\paper_execution.py app\services\paper_intents.py app\services\paper_trade_forensics.py app\api\routes.py
```

Result: passed.

Targeted tests:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_lifecycle_governance.py"
```

Result: `11 passed, 1 warning`.

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_paper_execution_service.py"
```

Result: `9 passed`.

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_same_market_side_guard.py::test_open_opposite_position_blocks_without_rationale tests/test_same_market_side_guard.py::test_forensics_shape_includes_sample_traces"
```

Result: `2 passed`.

Regression tests:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_trade_lifecycle.py tests/test_capital_efficiency.py tests/test_paper_execution_capital_guards.py tests/test_paper_execution_safety.py"
```

Result: `29 passed, 1 warning`.

One full same-market test run hit an environment/container memory error while scanning migrations:

```text
OSError: [Errno 12] Cannot allocate memory: '/app/app/db/migrations'
```

The failing cases were rerun directly and passed. No assertion failure remained.

## Safety Checklist

- Live trading not enabled.
- Shadow live not enabled.
- No order/write endpoint called.
- No Paper orders created.
- No Paper fills created.
- No Paper positions created.
- No Paper closes created.
- No capital ledger mutation.
- No balance mutation.
- No fake data.
- No fake actionable plan.
- SYSTEM remained OFF.

## Remaining Risks

- Current production reasoning records are stale after the completed 4h run, so no current subject is actionable until fresh runtime cycles rebuild identity/orderbook/risk/exit/capital/lifecycle/governance.
- Several old `CREATED` paper intents remain for audit history and now require refresh before execution.
- Generic `RISK_BLOCKED` remains for compatibility, though precision subtypes are now recorded where source summaries allow it.
- Optional providers such as memory/whale/news are still frequently missing and should continue to reduce completeness rather than hard-block by themselves.

## Phase Status

Status: `YELLOW`

Reason: the calibration and freshness gates work, stale data cannot authorize Paper, old intents require refresh, and no trading mutation occurred. The phase remains YELLOW because current data is stale and no actionable plan exists yet; this is safe but not yet trade-productive.

Can run 10m controlled PAPER validation: `YES`, with normal preflight and fresh runtime source refresh before any Paper intent or execution authorization.

