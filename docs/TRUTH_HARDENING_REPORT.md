# Truth Hardening Report

Date: 2026-06-14

Status: YELLOW

## Mission

Implement visibility-only Truth Hardening across the Control Center, Dashboard APIs, Runtime visibility layer, and Paper visibility layer.

No trading logic, risk logic, eligibility logic, paper execution logic, lifecycle governance logic, order creation, fill creation, position creation, capital allocation, AI routing, or runtime mode activation was changed.

## Current Reality Found

The forensic audit and code inspection confirmed the operator confusion risk:

| Surface | Source | Current State Logic Before | Stale/Missing Weakness Found |
| --- | --- | --- | --- |
| Control Center Overview | `system_state`, `service_health`, `event_log`, paper/truth tables | Source counts and latest rows | Could use latest event/heartbeat as partial comfort while deeper runtime/paper rows were stale. |
| Organ Health | `service_health` | Any service rows could produce `REAL` / `ACTIVE_FRESH` | Registered rows with `RUNNING` labels could look like active services without heartbeat/success proof. |
| Runtime Health | `runtime_cycles_v2`, `service_health`, `system_state` | Active cycle row shown directly | Stale `RUNNING` rows could look active unless separately classified. |
| Runtime Supervisor | process-local supervisor store + Governor state | `RUNNING` meant active process-local supervisor | No persistent cross-process proof; remains process-local truth. |
| Full Monitor Run | process-local monitor store | Current/latest bounded run | Could be confused with normal runtime life; remains labeled diagnostic/read-only. |
| Paper Summary | canonical `paper_*` tables | Readiness derived mostly from safety/lineage warnings | Historical ledger cleanliness could look GREEN while current execution was blocked/stale. |
| Paper Ledger/PnL | `paper_daily_pnl`, closes, positions | Ledger reconciliation | Historical ledger health was not separated from current paper execution readiness. |
| Orderbook Readiness | `orderbook_snapshots` | Indirect through paper execution paths | Missing/stale orderbook was not first-class on `/dashboard/api/v2/paper`. |

## False Green Situations Removed

- Paper summary now separates `paper_ledger_health_status` from `readiness_state`.
- Current paper readiness is `BLOCKED` when system power is off, orderbook source is missing/stale, runtime cycle source is missing/stale, or no current executable paper intents exist.
- Organ Health classifies service rows as `REGISTERED` when they have no heartbeat or success evidence.
- Runtime health classifies stale active cycle rows under `active_cycle_truth` instead of trusting `status='RUNNING'`.

## Historical/Current Separation Added

Canonical classifications added to the Control Center truth contract:

- `truth_state`: `ACTIVE_FRESH`, `LAST_KNOWN`, `HISTORICAL_ONLY`, `REFRESH_REQUIRED`, `UNKNOWN`
- `freshness_state`: `FRESH`, `STALE`, `MISSING`
- `runtime_state`: `RUNNING`, `REGISTERED`, `BLOCKED`, `STOPPED`, `STALE`, `UNKNOWN`
- `readiness_state`: `READY`, `NOT_READY`, `PARTIAL`, `BLOCKED`, `UNKNOWN`

Every Control Center truth envelope can now expose:

- `source`
- `last_updated`
- `age_seconds`
- `freshness_state`
- `runtime_state`
- `truth_state`
- `readiness_state`
- `warnings`
- `errors`

## Files Changed

- `app/control_center/truth_contract.py`
- `app/control_center/truth_hardening.py`
- `app/control_center/query_service.py`
- `app/runtime/health_truth.py`
- `app/services/paper_dashboard_truth.py`
- `frontend/control-center/src/lib/truth-contract.ts`
- `frontend/control-center/src/components/truth/StatusCard.tsx`
- `tests/test_truth_hardening.py`
- `docs/TRUTH_HARDENING_REPORT.md`

## APIs Changed

- `/dashboard/api/v2/control/*` envelopes now include additive truth fields: `age_seconds`, `freshness_state`, `runtime_state`, `readiness_state`.
- `/dashboard/api/v2/control/organs` now includes per-service `freshness_state`, `runtime_state`, `readiness_state`, `truth_state`, `age_seconds`, and `truth_warnings`.
- `/runtime/health` now includes top-level truth classifications plus `active_cycle_truth` and `last_successful_cycle_truth`.
- `/dashboard/api/v2/paper` now includes current paper readiness fields:
  - `source`
  - `last_updated`
  - `age_seconds`
  - `freshness_state`
  - `runtime_state`
  - `truth_state`
  - `readiness_state`
  - `paper_ledger_health_status`
  - `paper_execution_readiness_state`
  - `paper_execution_blockers`
  - `paper_execution_explanation`
  - `market_data_readiness`
  - `orderbook_readiness`

## Dashboard Cards Changed

- Control Center `StatusCard` now displays Freshness, Runtime, and Readiness states directly under the source label.
- Existing status/truth badges remain unchanged for compatibility.

## Tests Added

- `tests/test_truth_hardening.py`
  - Fresh object becomes `ACTIVE_FRESH`.
  - Missing source becomes `MISSING`/`UNKNOWN`.
  - Registered service does not imply running.
  - Stale runtime cycle becomes `STALE`.
  - Historical paper ledger success does not imply current readiness.
  - Current stale paper/orderbook truth overrides historical rows.

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_truth_hardening.py tests/test_control_center_read_only_apis.py tests/test_paper_dashboard_truth.py -q`
  - Result: `7 passed, 6 skipped`
- `.venv\Scripts\python.exe -m pytest tests/test_runtime_health_truth.py tests/test_runtime_api.py tests/test_control_center_runtime_supervisor.py tests/test_control_center_full_monitor_run.py tests/test_control_center_paper_simulation.py tests/test_paper_soak_readiness.py tests/test_paper_lineage_quarantine.py -q`
  - Result: `34 passed, 12 skipped`
- `npm run typecheck`
  - Result: passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx`
  - Result: `2 passed`, `12 tests passed`

Initial unavailable commands:

- `python -m uv run pytest ...` failed because system Python has no `uv` module.
- `python -m pytest ...` failed because system Python has no `pytest` module.
- The local `.venv` interpreter was used successfully.

## Migrations

None.

## Rollback Notes

This phase is read-only visibility hardening. Rollback is limited to reverting the changed source/test/doc/frontend files listed above. No database schema or persisted runtime state was changed.

## Remaining Truth Risks

- `RuntimeSupervisorService` and `FullMonitorRunService` remain process-local truth; after process restart they can only report current-process knowledge.
- Control Center overview still summarizes many sources at a high level; deeper endpoint-specific truth is now better but not exhaustive for every V2 module.
- The paper endpoint now exposes current readiness blockers, but it does not perform or trigger any refresh to resolve them.
- Some legacy tests and operators may still know old `readiness_status`/GREEN language; the new canonical `readiness_state` should be preferred.

## Definition Of Done

- Truth classifications are implemented and exposed.
- Historical/current paper truth is separated.
- Registered/running service truth is separated.
- Stale runtime active-cycle truth is explicit.
- No trading, risk, paper execution, live, shadow, or mode behavior was enabled or loosened.
- Targeted backend and frontend tests passed.

Truth Hardening status: YELLOW.

Can continue to next phase: YES, for further read-only truth hardening and operator UI rollout only. NO for PAPER/SHADOW/LIVE activation based on this phase alone.
