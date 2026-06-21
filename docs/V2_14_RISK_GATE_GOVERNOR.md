# V2.14 Risk Gate + Risk Governor

## Purpose

V2.14 adds the system risk authority. It creates two non-executing layers:

- Risk Gate: evaluates one proposed route/allocation/contract before it can ever become executable.
- Risk Governor: evaluates global risk state, limits, cooldowns, breaches, KILL behavior, attack mode eligibility, and audited overrides.

Risk Gate approval is not an order, not an order intent, and not an execution instruction.

## Architecture

- `app/risk/contracts.py`: Risk Gate, Governor, limits, breach, cooldown, and reproducibility contracts.
- `app/risk/risk_gate.py`: deterministic route/allocation risk evaluation.
- `app/risk/risk_governor.py`: global governor state builder.
- `app/risk/risk_limit_manager.py`: conservative default limits.
- `app/risk/risk_breach_detector.py`: daily/weekly loss, exposure, and position breach detection.
- `app/risk/correlation_checker.py`: market-family exposure checks.
- `app/risk/exposure_checker.py`: total exposure and open-position checks.
- `app/risk/cooldown_manager.py`: breach-to-cooldown and active cooldown checks.
- `app/risk/manual_override_auditor.py`: mandatory actor/reason/scope audit validation.
- `app/risk/attack_mode_gate.py`: attack mode eligibility only, no activation.
- `app/risk/service.py`: DB integration, State Governor guard, events, and read APIs.
- `app/api/risk_routes.py`: read endpoints plus safe rebuild/evaluate/override endpoints.

## DB Tables

Migration: `app/db/migrations/0052_v2_14_risk_gate_governor.sql`

- `risk_gate_runs`
- `risk_gate_decisions`
- `risk_governor_state`
- `risk_governor_events`
- `risk_limits`
- `risk_breaches`
- `cooldown_events`

These are risk authority and audit tables only. They are not execution tables.

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

## Events

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

## Risk Gate Logic

Risk Gate evaluates one route/allocation with:

- max loss
- liquidity
- slippage
- wording risk
- correlation
- exposure
- engine budget
- confidence
- exit plan
- governor state
- runtime state
- data completeness

Hard blocks include KILL, missing exit plan, NO_TRADE/BLOCKED route, blocked allocation, bad liquidity, and missing capital allocation.

Manual override can only clear eligible soft blocks and is always audited. It cannot bypass KILL, missing exit plan, or live-disabled runtime boundaries.

## Risk Governor Logic

Risk Governor tracks:

- global status
- kill switch
- attack mode eligibility
- cooldown state
- daily and weekly loss
- open positions and exposure
- active breaches
- active cooldowns
- manual overrides
- data confidence and insufficient data

Default limits are conservative and seeded into `risk_limits`.

## Attack Mode Boundary

V2.14 may mark `attack_mode_allowed=true` only when:

- Governor status is `OK`
- no active major breaches exist
- daily and weekly loss are clean
- Attack Bank is available
- explicit governor approval is present

It does not activate live trading or execute anything.

## Dashboard Fields

The dashboard query service exposes real DB-backed `risk` overview fields:

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

No fake dashboard data is introduced.

## Safety Boundaries

- Risk Gate cannot create orders.
- Risk Gate cannot create order intents.
- Risk Gate cannot create exits.
- Risk Governor cannot create orders.
- Risk Governor cannot create order intents.
- Risk Governor cannot mutate external balances.
- Gate approval is not executable.
- KILL blocks all.
- Missing exit plan blocks.
- Manual override requires audit and cannot bypass KILL.
- Attack mode requires Governor approval.

## Known Limitations

- Real exposure and PnL quality depend on existing paper/live truth tables.
- V2.14 provides authority records for future V2.15 execution, but does not yet enforce an end-to-end executable path because execution remains out of scope.

## Next Phase

V2.15 Execution Cortex V2 may consume Risk Gate/Governor decisions after V2.14 is verified GREEN.

