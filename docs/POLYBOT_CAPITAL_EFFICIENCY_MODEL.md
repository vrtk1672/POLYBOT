# POLYBOT Capital Efficiency Model

Status: implemented as a derived, observational economic reasoning layer.

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`.

## Purpose

The Capital Efficiency model evaluates whether locked or proposed capital is economically efficient relative to reward, time, liquidity, risk, and account pressure. It does not trade, close positions, create intents, mutate balances, or change Paper Execution/Paper Exit behavior.

## Metrics

For source-backed subjects, the model records:

- `capital_locked`
- `time_locked_seconds`
- `time_to_resolution_seconds`
- `current_exit_pnl`
- `potential_reward`
- `risk_amount`
- `reward_per_locked_dollar`
- `reward_per_hour`
- `reward_per_dollar_hour`
- `current_return_pct`
- `hold_return_pct`
- `open_exposure`
- `available_balance`
- `liquidity_exit_quality`
- `rules_risk`
- `risk_of_reversal`
- `capital_efficiency_score`

No opportunity cost is fabricated. Missing values are stored in `missing_inputs_json`.

## Source Rules

- Position capital lock comes from active `paper_capital_ledger` lock minus release rows.
- Candidate/intent/fresh-seed preview capital uses `payout_odds_evaluations.stake_usd` when available.
- Potential reward and risk come from `payout_odds_evaluations`.
- Exit PnL, time to resolution, liquidity, rules risk, and reversal risk come from `exit_hold_evaluations`.
- Account availability and exposure come from `paper_accounts`.
- If time to resolution is unavailable, dollar-time metrics are left null and `TIME_TO_RESOLUTION_MISSING` is recorded.

## Recommendations

Allowed recommendations:

- `CAPITAL_SUPPORT`
- `CAPITAL_WATCH`
- `CAPITAL_REDUCE_REVIEW`
- `CAPITAL_RELEASE_REVIEW`
- `CAPITAL_BLOCK`
- `CAPITAL_INSUFFICIENT_DATA`

Conservative behavior:

- missing capital/reward -> `CAPITAL_INSUFFICIENT_DATA`
- missing time/rules/liquidity -> `CAPITAL_WATCH`
- positive exit PnL plus weak hold efficiency/risk -> `CAPITAL_RELEASE_REVIEW`
- rising risk with exit liquidity -> `CAPITAL_REDUCE_REVIEW`
- poor liquidity or weak score -> `CAPITAL_BLOCK`
- strong reward per dollar-hour, good liquidity, and low risk -> `CAPITAL_SUPPORT`

`confidence` remains null. The score is deterministic and derived from available source-backed metrics.

## Database

Migration `0121_capital_efficiency_model.sql` creates:

- `capital_efficiency_evaluations`
- `capital_efficiency_sources`

Rows are derived truth only and idempotent by subject plus linked payout/exit-hold evidence.

## API

Added:

- `GET /dashboard/api/v2/capital-efficiency`
- `GET /dashboard/api/v2/capital-efficiency/{evaluation_id}`
- `POST /capital-efficiency/evaluate`

The evaluator writes only `capital_efficiency_*` rows.

## Integrations

- Paper Forensics shows capital efficiency fields and lineage.
- Capital Brain, Exit Foundation, Exit/Hold, Position Watchdog, and Mesh Coordinator expose latest capital efficiency records as observational-only context.
- Brain Dialogue has a source-backed `Capital Efficiency` materializer.

## Safety

This layer does not:

- create orders, fills, positions, closes, intents, or ledger rows
- mutate paper balances
- enable live or shadow
- alter Paper Execution or Paper Exit thresholds
- calculate fake opportunity cost, fake reward, fake PnL, fake EV, or fake confidence
