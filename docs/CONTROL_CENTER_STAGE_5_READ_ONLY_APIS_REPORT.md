# Control Center V1.5 Stage 5 - Read-Only APIs Report

## Purpose

Create real read-only backend API surfaces for future Control Center screens using the Stage 4 Truth Contract. No frontend UI, control actions, DB writes, migrations, runtime activation, paper execution, shadow/live behavior, orders, fills, or positions were added.

## Current Reality Found

- Stage 4 Truth Contract exists in `app/control_center/truth_contract.py`.
- `/dashboard` and `/control-center` are served from `app/api/routes.py`.
- Existing Dashboard V2 routes remain in `app/api/routes.py`.
- Existing Dashboard V2 query envelopes use `status`, `updated_at`, `stale`, `stale_reason`, `data_source`, `data_confidence`, `errors`, and `data`.
- `HealthTruthService.get_health_truth()` refreshes heartbeat rows, so Stage 5 does not call it.
- `MeshBlockersService` and `MeshDashboardService` can reach runtime health truth, so Stage 5 avoids them for Control Center reads.
- Safe reusable read-only services include paper PnL/positions reads, no-trade summary, risk evidence dashboard summary, lifecycle governance dashboard summary, AI context router dashboard summary, and truth-state dashboard summary.
- Missing or unavailable sources are represented as `MISSING` or `PARTIAL`.

## Files Created

- `app/control_center/query_service.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/CONTROL_CENTER_STAGE_5_READ_ONLY_APIS_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/control_center/__init__.py`

## Endpoints Added

- `GET /dashboard/api/v2/control/overview`
- `GET /dashboard/api/v2/control/organs`
- `GET /dashboard/api/v2/control/live-flow`
- `GET /dashboard/api/v2/control/decision-xray`
- `GET /dashboard/api/v2/control/blockers`
- `GET /dashboard/api/v2/control/closest-actionable`
- `GET /dashboard/api/v2/control/truth-state`
- `GET /dashboard/api/v2/control/risk-evidence`
- `GET /dashboard/api/v2/control/lifecycle-governance`
- `GET /dashboard/api/v2/control/mesh-dialogues`
- `GET /dashboard/api/v2/control/pnl-ledger`
- `GET /dashboard/api/v2/control/positions`
- `GET /dashboard/api/v2/control/no-trade`
- `GET /dashboard/api/v2/control/ai`
- `GET /dashboard/api/v2/control/logs`

Preserved:

- `GET /dashboard/api/v2/control/truth-contract`
- `GET /dashboard`
- `GET /control-center`
- Existing `/dashboard/api/*`
- Existing `/dashboard/api/v2/*`

## Source Mapping

| Endpoint | Source table/service/file | REAL/PARTIAL/MISSING/NOT_IMPLEMENTED | Notes |
|---|---|---|---|
| `/overview` | `runtime_state`, `service_health`, `event_log`, source table counts | `PARTIAL` or `MISSING` | Direct read-only probes only; no runtime health refresh |
| `/organs` | `service_health` heartbeat rows | `REAL` or `MISSING` | Health source guard enforced |
| `/live-flow` | `event_log` via `EventStoreRepository.list_recent_events` | `REAL` or `MISSING` | Event source guard enforced |
| `/decision-xray` | `RiskEvidenceMeshService.dashboard_summary` | `REAL`, `PARTIAL`, `MISSING`, or `ERROR` | Decision evidence guard enforced; no approval claimed |
| `/blockers` | `no_trade_log` + `risk_evidence_mesh_evaluations` summaries | `REAL`, `PARTIAL`, `MISSING`, or `ERROR` | Avoids `MeshBlockersService` because it can refresh heartbeat rows |
| `/closest-actionable` | risk evidence closest subjects | `PARTIAL`, `MISSING`, or `REAL` | Candidate `truth_state` normalized/enforced |
| `/truth-state` | `TruthStateService.dashboard_summary` / `truth_state_registry` | `REAL`, `MISSING`, or `ERROR` | Reuses existing persisted truth-state vocabulary |
| `/risk-evidence` | `risk_evidence_mesh_evaluations` | `REAL`, `MISSING`, or `ERROR` | Does not claim Risk Gate approval |
| `/lifecycle-governance` | `LifecycleGovernanceGateService.dashboard_summary` | `REAL`, `MISSING`, or `ERROR` | Read-only; no lifecycle changes triggered |
| `/mesh-dialogues` | `brain_dialogue_events` direct read | `REAL` or `MISSING` | No dialogue materialization or invention |
| `/pnl-ledger` | `PaperDashboardTruthService.get_pnl` / paper PnL ledger | `REAL`, `MISSING`, or `ERROR` | PnL source guard enforced; fake PnL false |
| `/positions` | `PaperDashboardTruthService.get_positions` / `paper_positions` | `REAL`, `MISSING`, or `ERROR` | Canonical position source guard enforced |
| `/no-trade` | `PaperIntentGateService.get_no_trade_dashboard_summary` | `REAL`, `MISSING`, or `ERROR` | NO_TRADE surfaced as first-class decision |
| `/ai` | `AIContextRouterService.dashboard_summary` | `REAL`, `MISSING`, or `ERROR` | Interpretation-only; no execution authority |
| `/logs` | `runtime_incidents`, `event_delivery_attempts`, `event_log` | `REAL` or `MISSING` | Recent incident/DLQ/event-like read-only feed |

## Truth Contract Enforcement

- Every endpoint returns `status`, `source`, `last_updated`, `stale_after_seconds`, `truth_state`, `data`, `warnings`, and `errors`.
- All responses are built through `truth_envelope()`.
- `REAL`, `STALE`, and `PARTIAL` always include a source.
- Safe degraded states return HTTP 200 with `MISSING`, `PARTIAL`, or `STALE`.
- `ERROR` is reserved for code/query failures and includes errors.
- `data` is always a dict/object.
- `warnings` and `errors` are always arrays.
- Domain guards are used for runtime overview, organs/health, live-flow/events, decision-xray, closest-actionable candidates, PnL ledger, and positions.
- No endpoint calls a mutating route, POST endpoint, runtime refresh, scheduler, paper execution, shadow/live path, or mode/system-power transition.

## Tests Added

- `tests/test_control_center_read_only_apis.py`
  - all 15 Stage 5 endpoints return HTTP 200
  - all 15 responses match Truth Contract shape
  - all 15 responses use valid status and truth_state values
  - arrays/dict shape is preserved
  - control routes are GET-only
  - no mutating control terms are exposed
  - fake green/runtime claims are avoided
  - PnL, health, decision, and candidate guard behavior is reflected
  - Stage 4 truth-contract endpoint remains preserved

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_control_center_read_only_apis.py -q`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_truth_contract.py tests/test_control_center_route.py -q`
- `.venv\Scripts\python.exe -m py_compile app\control_center\query_service.py app\control_center\truth_contract.py app\api\routes.py tests\test_control_center_read_only_apis.py tests\test_control_center_truth_contract.py tests\test_control_center_route.py`

## Exact Results

- Stage 5 API tests: `5 passed in 6.91s`
- Stage 4 + Stage 3 regression tests: `12 passed in 6.61s`
- Python compile check: passed

## Safety Checklist

- `/dashboard` preserved: YES
- `/control-center` preserved: YES
- Truth-contract endpoint preserved: YES
- Full UI built: NO
- Frontend dependencies installed: NO
- Package/lockfile changed: NO
- DB writes: NO
- Migrations: NO
- Runtime started: NO
- Paper/shadow/live activated: NO
- Orders/fills/positions created: NO
- Secrets printed: NO
- Only GET read-only endpoints added: YES
- Dangerous controls exposed: NO
- Fake green introduced: NO
- Fake PnL introduced: NO
- Fake runtime status introduced: NO

## Remaining Risks

- In environments without a configured DB, many endpoints honestly return `MISSING`.
- Some endpoints are intentionally `PARTIAL` because unified Control Center-specific source tables do not exist yet.
- Existing service summaries may evolve; future Stage 6/7 UI work should keep tests around the Truth Contract shape.
- No frontend components exist yet.

## Next Recommended Phase

Stage 6, Design System + Truth Components.
