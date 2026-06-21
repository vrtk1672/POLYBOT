## Extended Paper Truth Run

- Runtime path: canonical `scripts/migrate_runtime.ps1`, `scripts/start_runtime.ps1`, `scripts/smoke_runtime.ps1`
- Artifact root: `artifacts/extended_paper_truth_run_20260422_170653`
- Probe window: `2026-04-22T17:09:44+03:00` to `2026-04-22T17:22:31+03:00`
- Samples captured: `6`

## What Happened

- Runtime stayed alive and all sampled endpoints returned `200` on every pass.
- Refresh cycles continued throughout the run. `runtime_stdout.log` shows `refresh_complete` events through `2026-04-22T17:22:50+03:00`.
- Paper flow stayed active over the whole window. Recent 5-cycle KPI windows consistently showed `paper_would_enter=5`, `paper_orders_created=5`, `paper_orders_filled=5`, and `paper_positions_opened=5`.
- Blocking remained disciplined rather than pathological. The dominant block reason was `same_market_exposure_1_meets_exceeds_live_max_same_market_exposure_1`, which rose from `39` to `68` across the sampled 5-cycle windows.
- Invalidation and advisory activity stayed materially active. `exit_advisory_records_count` and `command_intent_records_count` rose from `44` to `77`.

## Lifecycle Truth

- Direct DB snapshot at the end of the run:
  - `paper_orders_total=20`
  - `paper_positions_total=20`
  - `paper_order_events_total=40`
  - `paper_position_events_total=238`
  - `paper_open_positions=20`
  - `paper_closed_positions=0`
- Recent order events show repeated `CREATED -> FILLED` transitions throughout the run.
- Recent position events show repeated `OPENED` and `MARKED` transitions.
- No `CLOSED` positions were observed in this window.

## Economic Truth So Far

- Provisional paper PnL is available but incomplete for judgment:
  - sample 1 paper unrealized PnL: `0.261775`
  - sample 6 paper unrealized PnL: `0.154275`
  - realized paper PnL: `0.0`
- This run is sufficient to judge flow and lifecycle behavior.
- This run is not sufficient to judge profitability because no paper closes occurred during the window.

## Cold Read

- The system looks operationally credible for paper flow:
  - entries continued over time
  - fills remained immediate and durable
  - positions accumulated coherently
  - advisory/watch activity remained active
- The system is not yet economically interpretable:
  - exits did not fire
  - closes did not occur
  - realized PnL stayed at zero
- Current verdict: `UNCLEAR`
