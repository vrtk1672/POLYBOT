# POLYBOT Exit Now vs Hold-to-Resolution Reasoning

Status: implemented as a derived, observational reasoning layer.

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`.

## Purpose

The Exit/Hold model compares the source-backed economics of selling now against holding to binary-market resolution. It does not close positions, alter exit thresholds, create intents, create paper artifacts, mutate balances, or call order/write endpoints.

Allowed outputs:

- `EXIT_NOW`
- `HOLD_TO_RESOLUTION`
- `PARTIAL_EXIT_REVIEW`
- `HOLD_REVIEW`
- `EMERGENCY_EXIT_REVIEW`
- `WAIT`
- `INSUFFICIENT_DATA`

## Source Rules

For open Paper positions:

- `exit_now_value = current_best_bid * quantity`
- `exit_now_pnl = exit_now_value - cost_basis`
- `hold_to_resolution_value` and `hold_to_resolution_profit_if_win` come from `payout_odds_evaluations`
- `time_to_resolution_seconds` comes from `markets_v2` close/resolution time, then `market_rules.deadline_at`, then `rules_analysis.deadline_at`
- `rules_risk` comes from `rules_analysis` and `market_rules`
- `liquidity_exit_quality` and `spread_risk` come from the latest non-stale `orderbook_snapshots` row
- missing data is recorded in `missing_inputs_json`; it is not inferred

The model leaves `confidence` null. It does not fake confidence, fair probability, expected value, or PnL.

## Decision Rules

- `INSUFFICIENT_DATA`: payout/odds or basic subject data is missing.
- `EMERGENCY_EXIT_REVIEW`: an open Paper position has no current exit price.
- `EXIT_NOW`: exit PnL is positive, exit liquidity is good, and remaining hold upside is small.
- `PARTIAL_EXIT_REVIEW`: profit exists, hold upside remains, and risk is rising.
- `HOLD_TO_RESOLUTION`: time to resolution is short, rules risk is low or medium, liquidity is available, and hold value exceeds exit-now value.
- `HOLD_REVIEW`: current bid is not profitable but no emergency signal exists.
- `WAIT`: source-backed values exist but the evidence does not support a stronger decision.

## Database

Migration `0120_exit_now_hold_resolution_reasoning.sql` creates:

- `exit_hold_evaluations`
- `exit_hold_sources`

Rows are derived truth only. Idempotency is based on subject, latest source evidence, and decision.

## API

Added:

- `GET /dashboard/api/v2/exit-hold`
- `GET /dashboard/api/v2/exit-hold/{evaluation_id}`
- `POST /exit-hold/evaluate`

The evaluator creates only `exit_hold_*` records.

## Integrations

- Paper Forensics shows exit-now value, exit-now PnL, hold-to-resolution value, hold profit, time to resolution, decision, reason, and missing inputs.
- Capital Brain, Exit Foundation, and Mesh Coordinator expose latest Exit/Hold evaluations as `observational_only`.
- Brain Dialogue has an `Exit/Hold` materializer that speaks from `exit_hold_evaluations` when normal dialogue materialization is allowed by the existing SYSTEM power convention.

## Safety

This layer is not an exit executor. It does not:

- create orders, fills, positions, closes, intents, or ledger rows
- mutate paper balances
- enable live or shadow
- alter stop-loss/take-profit/max-hold logic
- call write/order endpoints
