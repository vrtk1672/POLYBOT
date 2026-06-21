# POLYBOT V2.0 Core Runtime Foundation

## Purpose

V2.0 introduces a single runtime authority for POLYBOT mode, permission, health, and cycle truth. It is intentionally a foundation layer: it does not rewrite the existing pipeline, does not enable live trading, and does not delete legacy controls.

## Architecture

The runtime foundation lives under `app/runtime`.

- `modes.py`: canonical modes, actions, and permissions.
- `mode_manager.py`: legal transition rules.
- `state_governor.py`: current mode authority and permission checks.
- `cycle_orchestrator.py`: V2 cycle ledger and stage guards.
- `service_registry.py`: current service status registry.
- `health_truth.py`: runtime health snapshot.
- `safe_startup.py`: startup initialization and fail-safe policy.

Persistence is Postgres-backed through the existing `DatabaseConnectionFactory` and repository style.

## Runtime Modes

- `DATA_ONLY`: collect, score, and run intelligence only. No order or position creation.
- `PAPER`: paper orders and paper positions only. No live orders.
- `SHADOW_LIVE`: live-like simulated decisions only. No live orders.
- `SMALL_LIVE`: requires explicit transition certification. No automatic live enablement in V2.0.
- `ATTACK_MODE`: blocked unless `governor_approved=true` is supplied.
- `COOLDOWN`: collect, score, intelligence, and close-position permission only. New entries blocked.
- `KILL`: blocks trading, signal generation, orders, positions, cloud AI, attack, and runtime engines.

## Permission Matrix

| Mode | Data | Intelligence | Paper | Shadow | Live | Attack |
| --- | --- | --- | --- | --- | --- | --- |
| DATA_ONLY | Yes | Yes | No | No | No | No |
| PAPER | Yes | Yes | Yes | No | No | No |
| SHADOW_LIVE | Yes | Yes | No | Yes | No | No |
| SMALL_LIVE | Yes | Yes | No | Yes | Yes, mode-permitted only | No |
| ATTACK_MODE | Yes | Yes | No | No | No | Yes, governor-approved only |
| COOLDOWN | Yes | Yes | No new entries | No | No | No |
| KILL | No runtime actions | No | No | No | No | No |

## DB Tables

Migration: `app/db/migrations/0038_v2_runtime_foundation.sql`

- `system_state`: single current runtime state truth.
- `system_state_history`: audit trail for allowed and blocked transitions.
- `runtime_cycles_v2`: V2 cycle ledger with stage start/finish flags.
- `service_health`: current service health truth.
- `runtime_incidents`: runtime incident tracking.

## API Routes

- `GET /runtime/state`
- `GET /runtime/health`
- `GET /runtime/mode`
- `POST /runtime/mode/request`
- `POST /runtime/kill`
- `POST /runtime/resume`

All mode mutations require `actor` and `reason`.

## Integration Points

- `app/main.py`: safe startup, service registration, runtime routes.
- `app/scheduler.py`: checks `COLLECT_DATA`; KILL blocks scheduled refresh.
- `app/ingestion/market_service.py`: V2 cycle ledger and scanner/intelligence/paper stage guards.
- `app/services/runtime_paper_trading.py`: paper order/position creation blocked outside PAPER.
- `app/services/live_runtime.py`: live order path blocked unless `SEND_LIVE_ORDER` is permitted.
- `app/services/operator_control.py`: kill/resume/pause mapped to governor where feasible.
- `app/services/telegram_bot.py`: `/kill`, `/resume`, `/pause` now flow through runtime control.
- `app/services/query/operator_dashboard_query_service.py`: dashboard overview includes runtime truth.
- `app/api/routes.py`: dashboard HTML includes a small Runtime panel.

## Safety Guarantees

- Missing state never enables trading.
- KILL blocks all runtime trading actions.
- DATA_ONLY blocks orders and positions.
- PAPER blocks live orders.
- SHADOW_LIVE blocks live orders.
- ATTACK_MODE requires explicit governor approval metadata.
- SMALL_LIVE transition from SHADOW_LIVE requires certification metadata.
- Every allowed and blocked mode transition is persisted in `system_state_history`.
- Live trading is not enabled by this phase.

## How To Test

Unit and integration tests:

```powershell
python -m uv run pytest tests/test_runtime_modes.py -q
python -m uv run pytest tests/test_mode_manager.py -q
python -m uv run pytest tests/test_state_governor.py -q
python -m uv run pytest tests/test_runtime_cycle_orchestrator.py -q
python -m uv run pytest tests/test_runtime_api.py -q
python -m uv run pytest tests/test_runtime_integration_guards.py -q
```

Runtime verification:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1
Invoke-RestMethod http://127.0.0.1:8000/runtime/state
Invoke-RestMethod http://127.0.0.1:8000/runtime/health
Invoke-RestMethod http://127.0.0.1:8000/runtime/mode
```

## How To Operate

Start in `DATA_ONLY`. Move to `PAPER` only with an actor and reason:

```json
{"to_mode":"PAPER","actor":"operator","reason":"paper validation","metadata":{}}
```

Use `/runtime/kill` for emergency stop and `/runtime/resume` to resume to `DATA_ONLY`.

## Limitations

- V2.0 does not replace `MarketService.refresh()`.
- V2.0 does not enable live trading.
- Stage 4 live cage logic still exists and remains an additional legacy safety layer.
- Some dashboard services are registered as `STOPPED` until deeper service heartbeats are wired.

## V2.1 Remaining Work

- Risk Governor with explicit SMALL_LIVE live caps.
- Formal incident lifecycle and alerting.
- Broader service heartbeat coverage.
- Shadow-live mode wiring independent of legacy env branches.
- Dashboard V2 controls with authenticated operator workflow.
