# Full PAPER Runtime 20-Minute Stabilization Report

## Purpose

Stabilize POLYBOT as one autonomous trading machine running with `execution_mode=PAPER`. Paper remains only the execution adapter; analysis, candidate generation, Mesh review, scoring, risk/capital/exit/lifecycle, decision selection, and position management remain the unified runtime path.

## Vision Alignment

The runtime now runs the live-like autonomous loop with the PAPER adapter enabled and LIVE/SHADOW blocked. During monitoring it refreshed sources, triggers, candidates, Mesh reviews, paper decisions, paper execution, exit management, and PnL without creating live/shadow orders.

## Current Fault Summary Before Repair

- Supervisor was `DEGRADED`.
- Repeated error: `Paper simulation cycle failed: TypeError: Object of type Decimal is not JSON serializable`.
- Logs also exposed a Neural Bus publisher failure: `Object of type UUID is not JSON serializable`.
- Paper decisions were concentrated in one market/side: `691547 YES`.
- Duplicate safety was correctly blocking another same market/side entry while a position was open.
- Stale components remained visible: `market_universe_memory` and `targeted_market_revalidation_orderbook`.

## Decimal / UUID JSON Root Cause And Fix

Root cause:

- `runtime_cycles_v2.metadata_json` was written through raw `Jsonb(metadata)` in `RuntimeCycleRepository.finish_cycle`.
- Supervisor paper cycle metadata includes nested PnL/order/position data, which can contain `Decimal`.
- Neural Bus source-backed publishing validated payloads with plain `json.dumps`, so DB rows containing `UUID` or `Decimal` failed before event publication.
- Paper intent/no-trade repository JSONB wrappers were also made safe to prevent the same class of failure.

Fix:

- Added `app.utils.json_safety.json_safe/json_dumps`.
- Sanitizes `Decimal`, `datetime`, `date`, `UUID`, `Enum`, `set`, `tuple`, nested lists/dicts, Pydantic models, and `to_api_dict` objects.
- Applied to runtime cycle metadata, monitor reports, paper simulation truth, paper exit payloads, Neural Bus event payloads/metadata, and paper intent/no-trade JSONB parameters.

## Supervisor DEGRADED Root Cause And Fix

Before the second patch, supervisor degraded on paper-cycle serialization and Neural Bus event serialization. After redeploy, a shortened verification produced completed cycles with `error_count=0`, and the supervisor returned to `RUNNING`.

Latest clean cycles after fix:

- `v2-20260618T155704-8a38bae872`: `COMPLETED`, `error_count=0`
- `v2-20260618T155932-578c030880`: `COMPLETED`, `error_count=0`
- `v2-20260618T160144-02ac13ed1c`: `COMPLETED`, `error_count=0`

## Decision Diversity Audit

Seed diversity exists upstream:

- `691547 YES`: 738 seeds
- `691547 SIDE_UNKNOWN`: 523 seeds
- `597967 NO`: 41 seeds
- `666655 NO`: 27 seeds
- `598936 NO`: 26 seeds
- Additional market/sides exist across `597967`, `666655`, `2365093`, `677404`, `610236`, `597964`, `2354064`, and others.

Mesh-reviewed diversity also exists, but non-691547 market/sides are classified `HARD_BLOCKED`, mostly with `THESIS_WATCH` or `THESIS_MISSING`.

Paper Observation policy eligibility is narrow:

- `691547 YES OBSERVATION_POLICY_ELIGIBLE`: 73
- No other market/side currently has an observation policy review row.

Current PAPER runtime decision:

- `691547 YES`
- decision: `BLOCK`
- blocker: `DUPLICATE_OPEN_PAPER_EXPOSURE`
- warnings include `CAPITAL_WATCH_ALLOWED_FOR_PAPER_LEARNING`, `DATA_ONLY_RESEARCH_ALLOWED_PAPER_ADAPTER_ONLY`, and `DUPLICATE_MARKET_SIDE_SEEDS_SUPPRESSED:67`.

## Why It Was Not Continuing To Other Trades

The final decision selector is already grouped by market/side and duplicate suppression is active. The system is not continuing to other trades because only one market/side currently reaches Paper Observation policy eligibility. Non-691547 candidates reach Mesh, but remain `HARD_BLOCKED` before policy eligibility due to thesis/watch/missing-thesis and strict actionability gaps.

## Paper Position Management Audit

Position manager is active.

During the run, a prior open `691547 YES` position was naturally closed by `MAX_HOLD_TIME` with realized PnL `-0.400000`.

The 20-minute run then created one new natural paper position from the normal decision pipeline. It remains open:

- market: `691547`
- side: `YES`
- status: `OPEN`
- current duplicate blocker is correct for this open same market/side exposure.

## Stale Component Audit

`market_universe_memory`:

- `FRESH`: 1000
- `STALE`: 4
- latest update: `2026-06-18 15:58:52 UTC`

`targeted_market_revalidations.orderbook_refresh_state`:

- `FRESH`: 1234
- `NOT_AVAILABLE`: 544
- `STALE`: 433
- latest update: `2026-06-18 16:03:19 UTC`

These warnings are real diagnostics, not fake freshness. They did not block the current paper entry path because last-mile orderbook refresh and current candidate orderbook state were fresh.

## Files Changed

- `app/utils/json_safety.py`
- `app/repositories/runtime_cycle_repository.py`
- `app/control_center/full_monitor_run_service.py`
- `app/control_center/paper_simulation.py`
- `app/services/paper_exit_loop.py`
- `app/neural_bus/contracts.py`
- `app/repositories/paper_intent_repository.py`
- `app/control_center/runtime_monitoring_report.py`
- `app/services/decision_funnel_diversity.py`
- `tests/test_decimal_json_serialization.py`
- `tests/test_runtime_degraded_diagnostics.py`
- `tests/test_decision_funnel_diversity_audit.py`
- `tests/test_paper_position_management_runtime.py`
- `tests/test_20min_monitoring_report_shape.py`
- `docs/FULL_PAPER_RUNTIME_20MIN_STABILIZATION_REPORT.md`

## Tests Run

- Focused: `8 passed`
- Related: `1 passed, 7 skipped`
- Broad targeted: `19 passed, 29 skipped, 2275 deselected`
- Compile: passed

## Deployment

- `docker compose build api`
- `docker compose up -d --no-deps api`
- No DB migration required.

## 20-Minute Monitoring Snapshots

Snapshot file: `run_reports/full_paper_runtime_20min_20260618_183257.json`

| Minute | Supervisor | Events | Triggers | Seeds | Mesh | Decisions | Intents | Orders | Fills | Positions | Open | Live | Shadow |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | RUNNING | 2465 | 161 | 1672 | 862 | 1 | 24 | 15 | 12 | 15 | 0 | 0 | 0 |
| 5 | DEGRADED | 2529 | 162 | 1677 | 872 | 1 | 24 | 15 | 12 | 15 | 0 | 0 | 0 |
| 10 | DEGRADED | 2529 | 167 | 1691 | 892 | 1 | 25 | 16 | 13 | 16 | 1 | 0 | 0 |
| 15 | DEGRADED | 2529 | 170 | 1706 | 922 | 1 | 25 | 16 | 13 | 16 | 1 | 0 | 0 |
| 20 | DEGRADED | 2529 | 171 | 1711 | 932 | 1 | 25 | 16 | 13 | 16 | 1 | 0 | 0 |

The 20-minute run moved the runtime and produced one natural paper entry, but it also exposed the remaining Decimal/UUID serialization paths. Those were fixed afterward.

## Post-Fix Verification

After the second serialization patch and redeploy, the shortened verification showed:

- supervisor: `RUNNING`
- latest completed cycles: `COMPLETED`
- `error_count=0`
- no `Decimal` or `UUID` serialization errors in recent logs
- source refresh: `ACTIVE`
- paper position remained open
- live/shadow remained zero

## Paper Ledger Before/After 20-Minute Run

- paper intents: `24 -> 25`
- paper orders: `15 -> 16`
- paper fills: `12 -> 13`
- paper positions: `15 -> 16`
- open paper positions: `0 -> 1`
- live orders: `0 -> 0`
- shadow orders: `0 -> 0`
- real orders: `0 -> 0` by runtime status (`orders_v2` has one preexisting non-live baseline row unchanged)

## PnL

Latest `paper_daily_pnl`:

- realized: `-1.40000000`
- unrealized: `-0.40000000`
- net: `-1.80000000`
- closed trades: `3`
- open positions: `1`

## Live / Shadow Safety

- LIVE adapter stayed blocked.
- Shadow stayed disabled.
- No live orders.
- No shadow orders.
- No real runtime orders.
- Paper entries came through the normal decision pipeline.

## Current Final Status

YELLOW / PARTIAL.

POLYBOT is autonomous in PAPER mode for the unified runtime loop, paper adapter, position manager, and PnL path. It is partial because decision diversity remains limited to one policy-eligible market/side, causing valid duplicate-exposure blockers while that market/side is open.

## Exact Remaining Blockers

1. Only `691547 YES` reaches Paper Observation policy eligibility.
2. Current top paper decision is blocked by `DUPLICATE_OPEN_PAPER_EXPOSURE`.
3. Non-691547 Mesh-reviewed seeds remain `HARD_BLOCKED`, commonly due to `THESIS_WATCH` or `THESIS_MISSING`.
4. Stale diagnostics remain for 4 market memory rows and 433 targeted revalidation orderbooks, though current last-mile orderbook path is functioning.

## Recommended Next Action

Broaden the policy-eligible funnel by improving thesis support / observation-policy handling for Mesh-reviewed non-691547 candidates, especially the existing EDGE_SUPPORTED non-691547 market/sides currently hard-blocked at `THESIS_WATCH` or `THESIS_MISSING`.
