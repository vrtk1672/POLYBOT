# Phase 9 Dashboard Web + Telegram Control

This phase adds the first operator control room for POLYBOT.

It is intentionally:

- read-first
- advisory and audit oriented
- isolated from broker execution
- safe for remote visibility

It does not:

- submit orders
- cancel orders
- close positions
- mutate live, paper, or shadow exposure state
- wire execution into the dashboard

## Dashboard Views

The dashboard home is served at `/dashboard`.

The backend JSON endpoints are:

- `GET /dashboard/api/overview`
- `GET /dashboard/api/health`
- `GET /dashboard/api/ranking`
- `GET /dashboard/api/positions-orders`
- `GET /dashboard/api/invalidation`
- `GET /dashboard/api/intelligence`
- `GET /dashboard/api/audit`
- `GET /dashboard/api/alerts`

These views summarize persisted data only.

## Dashboard Panels

- System health:
  - DB connectivity
  - last cycle
  - latest snapshot / ranking / invalidation / orchestration metadata
  - pending eligible command intents
  - recent critical alert count
  - warnings
- Scanner / ranking:
  - top ranked opportunities
  - recent ranking policy candidates
  - rejected candidates
  - rejection ledger
- Positions / orders:
  - live positions
  - paper positions
  - shadow positions
  - live orders
  - paper orders
  - shadow orders
  - aggregate PnL snapshot
- Invalidation / exit:
  - invalidation policy records
  - exit advisory records
  - advisory resolution records
  - staged command intent records
- Intelligence:
  - whale scoring rows
  - normalized external news rows
  - cognition summaries
- Audit:
  - decision ledger
  - rejection ledger
  - operator control actions
  - alert events

## Telegram Foundation

The Telegram command surface is exposed through:

- `POST /telegram/command`
- `POST /telegram/webhook`

Supported commands now:

- `/status`
- `/health`
- `/top`
- `/positions`
- `/orders`
- `/pnl`
- `/whales`
- `/news`
- `/pause`
- `/resume`
- `/kill`

## Command Semantics

Read commands are backed by persisted data:

- `/status`
- `/health`
- `/top`
- `/positions`
- `/orders`
- `/pnl`
- `/whales`
- `/news`

Control commands are audited placeholders only:

- `/pause`
- `/resume`
- `/kill`

These commands persist an `operator_control_actions` row with `status_class = PLACEHOLDER`.

They do not:

- pause runtime loops
- resume runtime loops
- kill processes
- mutate any order or position state

## Alerts

Supported alert event classes:

- `CANDIDATE_SELECTED`
- `INVALIDATION_WARNING`
- `FEED_FAILURE`
- `SERVICE_CRASH`
- `RISK_OVERLOAD`
- `CRITICAL_HEALTH_DEGRADATION`

Alerts are persisted in `alert_events` with dedupe support.

If `POLYBOT_TELEGRAM_BOT_TOKEN` and `POLYBOT_TELEGRAM_DEFAULT_CHAT_ID` are configured, alerts may also be delivered to Telegram. Otherwise they remain persisted and queryable only.

## Safety Notes

- No dashboard endpoint executes broker actions.
- No Telegram command executes broker actions.
- All control actions remain explicit and auditable.
- Unsupported or unavailable data surfaces return honest empty or not-yet-available responses.
