# POLYBOT Paper Session Reset And Restart Report

## Purpose

Stage objective: add an official, non-destructive Paper session reset and deep restart workflow.

The supported operator flow is:

```powershell
.\tools\polybot.ps1 reset-paper-session -balance 1000
.\tools\polybot.ps1 restart-paper-session -balance 1000
.\tools\polybot.ps1 paper-session-status
.\tools\polybot.ps1 paper-session-history
```

Paper reset now means archive the previous simulated session, preserve historical rows, close any open paper positions as reset-closed, create a fresh active Paper session with the requested starting balance, and keep market/event/Mesh/AI history intact.

## Current Problem

The previous restart flow could rebuild and restart the API, but it did not reset Paper ledger state. Operators had no official command to archive the old Paper session and start a fresh simulated account. Manual PowerShell snippets were fragile and risked becoming SQL-level operational hacks.

## Existing Paper Ledger Audit

Canonical Paper truth is Postgres-backed:

- `paper_intents`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_position_closes`
- `paper_daily_pnl`
- `paper_capital_ledger`
- `paper_accounts`
- `paper_runs`
- `paper_signals`
- `paper_trade_ledger`
- `paper_order_events`
- `paper_position_events`

Before this change there was no official session model. Paper balance was stored on `paper_accounts`, while PnL and counts were derived from the ledger tables. Open positions are detected through active/open `paper_positions` rows that are not excluded from active Paper truth.

## Session Model Implemented

Added:

- `paper_sessions`
- `paper_session_resets`

Added nullable session/reset references to canonical Paper ledger tables:

- `paper_session_id`
- `reset_id`

Old rows can be backfilled into a legacy/previous session without deleting history. New Paper rows attach to the active Paper session through repository/service integration.

## Reset Behavior

`reset-paper-session -balance 1000`:

1. Stops POLYBOT through the official control path where available.
2. Refuses to run if live or shadow orders exist.
3. Saves pre-reset status under `run_reports/paper_session_reset_*`.
4. Creates or identifies the previous Paper session.
5. Backfills unscoped historical Paper rows to the previous session.
6. Closes active/open paper positions as `RESET_CLOSED`.
7. Archives pending old paper intents as reset-archived.
8. Marks the previous session `RESET_CLOSED`.
9. Creates a new `ACTIVE` Paper session.
10. Sets the Paper account balance to the requested starting balance.
11. Saves post-reset status and reset result under the report directory.

No market memory, event memory, Mesh results, AI insights, live rows, or shadow rows are reset.

## Deep Restart Behavior

`restart-paper-session -balance 1000` performs a reset, verifies health, and starts POLYBOT in PAPER mode through the existing command path.

## CLI Commands

Added:

- `paper-session-status`
- `paper-session-history`
- `reset-paper-session -balance <amount>`
- `restart-paper-session -balance <amount>`

`status` also shows current Paper session id, starting balance, and previous session archive state when available.

## API Endpoints

Added:

- `GET /dashboard/api/v2/control/paper-session`
- `POST /dashboard/api/v2/control/paper-session/reset`
- `GET /dashboard/api/v2/control/paper-session/history`

The reset endpoint accepts:

```json
{
  "balance": 1000,
  "start_after_reset": false,
  "reason": "manual reset for new test session"
}
```

## Tests Run

Focused:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_session_reset.py tests/test_paper_session_archive.py tests/test_paper_session_cli.py tests/test_paper_session_status_report.py tests/test_paper_session_safety.py -q
```

Result: `9 passed`.

Related:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_runtime_execution_chain.py tests/test_paper_execution_adapter_runtime.py tests/test_system_overview_paper_chain.py -q
```

Result: `5 passed`.

Compile:

```powershell
.venv\Scripts\python.exe -m compileall app tests
```

Result: passed.

## Verification Results

Deployment and verification completed on June 19, 2026.

Deployment:

- `docker compose build api`: passed.
- `docker compose build migrate`: passed.
- `docker compose run --rm migrate`: applied `0146_paper_session_reset.sql`.
- `docker compose up -d --no-deps api`: API restarted.
- `.\tools\polybot.ps1 health`: `/healthz ok`, DB `OK`, runtime health `RUNNING`, execution mode `PAPER`.

Pre-reset Paper ledger totals from `.\tools\polybot.ps1 status`:

- Paper intents: 27
- Paper orders: 18
- Paper fills: 15
- Paper positions: 18
- Open paper positions: 0
- Live orders: 0
- Shadow orders: 0
- Real orders: 0

Reset verification:

- Command: `.\tools\polybot.ps1 reset-paper-session -balance 1000`
- Result: `COMPLETED`
- Previous session: `paper_session_legacy_20260619T140933Z_e9901e8f`
- New session: `paper_session_20260619T140933Z_1976f194`
- Current-session counts: all zero.
- Historical totals remained visible: 27 intents, 18 orders, 15 fills, 18 positions.

Deep restart verification:

- Command: `.\tools\polybot.ps1 restart-paper-session -balance 1000`
- Result: reset completed, health checked, system started in PAPER mode.
- Final active session: `paper_session_20260619T141240Z_e81925e2`
- Starting balance: 1000
- Current-session counts: all zero.
- Historical totals remained visible: 27 intents, 18 orders, 15 fills, 18 positions.
- Open paper positions: 0
- Live/shadow/real orders: 0 / 0 / 0
- Host report directory: `C:\Server\apps\polybot\run_reports\paper_session_reset_cli_20260619T141239Z_976496e6`
- Container report directory: `run_reports/paper_session_reset_20260619T141240Z_49fceecb`

Report files saved in the host directory:

- `pre_paper_session.json`
- `pre_system_overview.json`
- `reset_response.json`
- `post_paper_session.json`
- `post_system_overview.json`

Expected post-reset state:

- New active Paper session exists.
- Starting balance is `1000`.
- Current session counts start at zero.
- Historical totals remain visible.
- Open paper positions are zero after reset.
- Live/shadow/real orders remain untouched.

## Safety Result

This implementation is additive and non-destructive. It preserves old Paper history, blocks reset when live/shadow execution rows exist, and does not touch market intelligence, source events, Mesh memory, AI insights, live orders, or shadow orders.

## Remaining Risks

- Historical rows before this migration are session-scoped by reset-time backfill, not by original runtime session boundaries.
- If an operator runs `restart-paper-session` immediately after `reset-paper-session`, it intentionally archives the fresh reset session and creates another fresh active session before starting PAPER mode.

## Final Status

Implementation and verification status: GREEN for the Paper session reset/restart workflow.
