# V2.14 Build Report - Risk Gate + Risk Governor

## Summary

V2.14 implements a non-executing risk authority layer with Risk Gate, Risk Governor, conservative limits, breach detection, cooldown records, audited overrides, attack mode eligibility, DB persistence, API routes, dashboard truth, tests, and docs.

No orders, order intents, exits, live requests, external balance mutations, or live trading behavior were added.

## Files Created

- `app/risk/__init__.py`
- `app/risk/contracts.py`
- `app/risk/risk_errors.py`
- `app/risk/risk_gate.py`
- `app/risk/risk_governor.py`
- `app/risk/risk_limit_manager.py`
- `app/risk/risk_breach_detector.py`
- `app/risk/correlation_checker.py`
- `app/risk/exposure_checker.py`
- `app/risk/cooldown_manager.py`
- `app/risk/manual_override_auditor.py`
- `app/risk/attack_mode_gate.py`
- `app/risk/service.py`
- `app/repositories/risk_gate_run_repository.py`
- `app/repositories/risk_gate_decision_repository.py`
- `app/repositories/risk_governor_state_repository.py`
- `app/repositories/risk_governor_event_repository.py`
- `app/repositories/risk_limit_repository.py`
- `app/repositories/risk_breach_repository.py`
- `app/repositories/cooldown_event_repository.py`
- `app/api/risk_routes.py`
- `app/db/migrations/0052_v2_14_risk_gate_governor.sql`
- `tests/test_v2_14_risk_gate.py`
- `tests/test_v2_14_risk_governor.py`
- `tests/test_v2_14_risk_limits.py`
- `tests/test_v2_14_breach_detector.py`
- `tests/test_v2_14_correlation_checker.py`
- `tests/test_v2_14_exposure_checker.py`
- `tests/test_v2_14_cooldown_manager.py`
- `tests/test_v2_14_manual_override.py`
- `tests/test_v2_14_attack_mode_gate.py`
- `tests/test_v2_14_risk_service.py`
- `tests/test_v2_14_risk_api.py`
- `tests/test_v2_14_risk_safety_guards.py`
- `docs/V2_14_RISK_GATE_GOVERNOR.md`
- `docs/V2_14_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

- `app/db/migrations/0052_v2_14_risk_gate_governor.sql`

Tables:

- `risk_gate_runs`
- `risk_gate_decisions`
- `risk_governor_state`
- `risk_governor_events`
- `risk_limits`
- `risk_breaches`
- `cooldown_events`

Migration results:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- First DB-backed run: `Applied migrations: - 0052_v2_14_risk_gate_governor.sql`
- Final rerun: `No pending migrations.`

## API Routes

- `GET /risk/health`
- `GET /risk/governor`
- `GET /risk/limits`
- `GET /risk/breaches/recent`
- `GET /risk/cooldowns`
- `GET /risk/gate/recent`
- `GET /risk/gate/{run_id}`
- `POST /risk/governor/rebuild`
- `POST /risk/gate/evaluate`
- `POST /risk/override`

## Dashboard Changes

Added DB-backed `risk` overview with:

- `risk_status`
- `governor_status`
- `kill_switch_active`
- `attack_mode_allowed`
- `cooldown_active`
- `gate_runs_today`
- `approved_today`
- `blocked_today`
- `breaches_today`
- `active_cooldowns`
- `max_daily_loss`
- `daily_loss`
- `max_weekly_loss`
- `weekly_loss`
- `open_positions_count`
- `open_exposure`
- `recent_gate_decisions`
- `recent_breaches`
- `recent_cooldowns`
- `latest_manual_override`
- `insufficient_data_count`
- `errors`

Dashboard smoke returned real DB-backed risk truth: `risk_status=OK`, `governor_status=BLOCKED` after the intentional HUNT engine-loss smoke, `gate_runs_today=4`, `approved_today=1`, `blocked_today=3`, `breaches_today=1`, and `active_cooldowns=1`.

## Events Published

- `risk.gate.run.started`
- `risk.gate.approved`
- `risk.gate.blocked`
- `risk.gate.reduced`
- `risk.gate.insufficient_data`
- `risk.governor.state.updated`
- `risk.governor.blocked`
- `risk.limit.created`
- `risk.limit.updated`
- `risk.breach.detected`
- `risk.cooldown.created`
- `risk.cooldown.expired`
- `risk.manual_override.created`
- `risk.attack_mode.allowed`
- `risk.attack_mode.blocked`

## Tests Added

V2.14 unit, service, API, and safety tests were added under `tests/test_v2_14_*.py`.

## Tests Run

Targeted V2.14 no-DB:

- `$files = (Get-ChildItem tests\test_v2_14_*.py).FullName; python -m uv run pytest $files -q`
- Result: `17 passed, 4 skipped in 19.00s`

Targeted V2.14 DB-backed:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $files = (Get-ChildItem tests\test_v2_14_*.py).FullName; python -m uv run pytest $files -q`
- Result: `21 passed in 834.21s (0:13:54)`

Post-fix DB-backed service/API/safety slice:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; python -m uv run pytest tests\test_v2_14_risk_service.py tests\test_v2_14_risk_api.py tests\test_v2_14_risk_safety_guards.py -q`
- Result: `5 passed in 780.22s (0:13:00)`

Relevant regressions:

- `python -m uv run pytest tests/test_v2_13_*.py -q` -> `12 passed, 4 skipped in 39.94s`
- `python -m uv run pytest tests/test_v2_12_*.py -q` -> `12 passed, 7 skipped in 16.25s`
- `python -m uv run pytest tests/test_v2_11_*.py -q` -> `10 passed, 7 skipped in 11.98s`
- `python -m uv run pytest tests/test_v2_10_*.py -q` -> `15 passed, 7 skipped in 24.34s`
- `python -m uv run pytest tests/test_v2_9_*.py -q` -> `17 passed, 7 skipped in 13.70s`
- `python -m uv run pytest tests/test_v2_8_*.py -q` -> `11 passed, 5 skipped in 12.74s`
- `python -m uv run pytest tests/test_v2_7_whale_*.py -q` -> `16 passed, 3 skipped in 32.90s`
- `python -m uv run pytest tests/test_runtime_*.py -q` -> `8 passed, 19 skipped in 19.83s`

Full no-DB suite:

- `python -m uv run pytest -q`
- Result: `294 passed, 393 skipped in 62.04s (0:01:02)`

## Runtime Verification

Runtime startup:

- Canonical `scripts/start_runtime.ps1` / `uv run polybot` remains blocked by Windows Application Control, as in prior verified phases.
- Runtime was started with the previously verified direct Python method:
  - `python -m uv run python -c "from app.main import run; run()"`
- Runtime env included:
  - `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
  - `PHASE1_PERSISTENCE_ENABLED=true`
  - `PHASE1_AUTO_MIGRATE=false`
  - `POLYBOT_RUNTIME_MODE=paper_safe`
  - `POLYBOT_EXECUTION_BACKEND=paper`
  - `LIVE_TRADING_ENABLED=false`
  - `LIVE_KILL_SWITCH=true`

Runtime remained safe:

- `system_state.current_mode=DATA_ONLY`
- live permissions remained false.

Endpoint verification:

- `/healthz` -> OK
- `/runtime/state` -> OK
- `/runtime/health` -> OK
- `/events/lag` -> OK
- `/data/coverage` -> OK
- `/capital/health` -> OK, `HEALTHY`
- `/risk/health` -> OK, `HEALTHY`
- `/risk/governor` -> OK, `BLOCKED` after intentional engine-loss smoke
- `/risk/limits` -> OK, `count=9`
- `/risk/breaches/recent` -> OK, `count=2`
- `/risk/cooldowns` -> OK, `count=2`
- `/risk/gate/recent` -> OK, `count=4`

## Manual Smoke

Manual smoke used market `2169995` with explicit safe strategy/allocation payloads.

Results:

- `POST /risk/governor/rebuild` with `dry_run=true` -> `written=false`, status OK.
- `POST /risk/governor/rebuild` with `dry_run=false` -> `written=true`, status OK.
- `POST /risk/gate/evaluate` with `dry_run=true` -> `written=false`, decision `APPROVED`.
- `POST /risk/gate/evaluate` with `dry_run=false` -> `written=true`, decision `APPROVED`.
- `POST /risk/gate/evaluate` missing exit plan -> `BLOCKED`, reason `missing_exit_plan`.
- `POST /risk/gate/evaluate` daily loss/governor blocked payload -> `BLOCKED`, reason `governor_blocked`.
- `POST /risk/gate/evaluate` correlation breach payload -> `BLOCKED`, reason `market_family_exposure_breach`.
- `POST /risk/override` with `dry_run=true` -> `written=false`.
- `POST /risk/override` with `dry_run=false` and actor/reason -> `written=true`, audited override event created.
- `POST /risk/override` attempting `BYPASS_KILL` while governor was KILL -> HTTP `409 Conflict`, rejected as expected.
- `POST /risk/governor/rebuild` with attack bank available but no approval -> `attack_mode_allowed=false`.
- Additional engine-loss smoke -> latest `MAX_ENGINE_LOSS` breach persisted with `cooldown_created=true`, HUNT cooldown persisted active.

## DB Row Verification

Final DB row counts after smoke:

- `risk_gate_runs=4`
- `risk_gate_decisions=4`
- `risk_governor_state=5`
- `risk_governor_events=6`
- `risk_limits=9`
- `risk_breaches=2`
- `cooldown_events=2`
- `paper_orders=3` unchanged from baseline
- `paper_positions=3` unchanged from baseline
- `live_orders=3` unchanged from baseline
- `orders=ABSENT`
- `order_intents=ABSENT`
- `exit_intents=ABSENT`

Latest gate decisions:

- `2169995` -> `APPROVED`
- `2169995-missing-exit` -> `BLOCKED`, `missing_exit_plan`
- `2169995-daily-loss` -> `BLOCKED`, `governor_blocked`
- `2169995-correlation` -> `BLOCKED`, `market_family_exposure_breach`

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Risk Gate cannot create orders: YES
- Risk Gate cannot create order intents: YES
- Risk Gate cannot create exits: YES
- Risk Governor cannot create orders: YES
- Risk Governor cannot create order intents: YES
- Risk Governor cannot mutate external balances: YES
- Gate approval is not executable order: YES
- Trade without exit plan blocked: YES
- Daily loss blocks new trades: YES
- Weekly loss blocks new trades: YES
- Correlation blocks: YES
- Exposure blocks: YES
- Engine loss triggers cooldown: YES
- KILL blocks all: YES
- Manual override audited: YES
- Manual override cannot bypass KILL: YES
- Attack mode requires Governor approval: YES
- Missing risk data becomes insufficient_data: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Real PnL/exposure completeness depends on existing paper/live truth tables; sparse real data is represented conservatively.
- V2.14 creates gate/governor decisions only. V2.15 must consume those decisions before any executable path exists.
- Canonical PowerShell runtime startup remains affected by Windows Application Control, so direct Python startup was used and documented.

## Phase Status

V2.14 status: GREEN.

## Recommendation

Can move to V2.15 Execution Cortex V2: YES.
