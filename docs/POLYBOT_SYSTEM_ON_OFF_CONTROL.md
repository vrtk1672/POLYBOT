# POLYBOT System ON/OFF Control

Phase: `POLYBOT_SYSTEM_ON_OFF_CONTROL`

## Purpose

This phase adds the operator-facing SYSTEM power contract:

- `SYSTEM ON`: autonomous non-execution runtime work may run through the existing safe runtime path.
- `SYSTEM OFF`: autonomous runtime work is blocked at application level.

The control does not add trading modes, does not enable live trading, and does not create paper orders, order intents, fills, or positions.

## API

- `GET /system/power`
- `POST /system/power/on`
- `POST /system/power/off`
- `GET /dashboard/api/v2/system-power`

POST requests require `actor` and `reason`. Missing values return `400`.

## Persistence

The canonical current power state is stored on `system_state`:

- `system_power`
- `system_power_actor`
- `system_power_reason`
- `system_power_correlation_id`
- `system_power_transition_at`

Every transition is audited in `system_power_transitions` and mirrored to `system_state_history` as `SYSTEM_ON` or `SYSTEM_OFF`.

## Runtime Semantics

`SYSTEM OFF` is enforced above runtime modes. When power is OFF, the State Governor denies runtime permissions, including collection, intelligence, paper, shadow, and live actions. Existing runtime mode remains intact for internal safety.

`SYSTEM ON` allows the existing non-live runtime path to run. It does not override Risk, Exit, Eligibility, Kill, or live-safety constraints.

## Dashboard Truth

The dashboard system power endpoint reports:

- `system_power`
- transition actor, reason, correlation id, timestamp
- runtime, scheduler, market service, data intake, neurons, brains, dialogue, paper, shadow, and live allowed flags
- component `allowed`, `active`, and `wired` truth
- safety fields proving live and execution remain disabled

No mock data is used.

## Safety Contract

- Live trading remains disabled.
- Shadow remains disabled.
- Paper execution remains disabled unless internal runtime mode and future phases explicitly allow it.
- `execution_allowed=false`.
- `orders_allowed=false`.
- No orders, fills, positions, or order intents are created by SYSTEM ON/OFF.
- Missing runtime state does not enable trading.
