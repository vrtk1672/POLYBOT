# POLYBOT Capital Efficiency Model Build Report

Date: 2026-06-03

Executor: Codex

Task mode: `CONTROLLED_RUNTIME_FEATURE + CAPITAL_EFFICIENCY_REASONING + ECONOMIC_OPTIMIZATION`

Risk: VERY HIGH

ChatGPT review: REQUIRED

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Current Reality Found

Paper account:

- current_balance: `996.84932200`
- available_balance: `996.68932200`
- locked_balance: `0.16000000`
- open_exposure: `0.16000000`
- realized_pnl: `-3.15067800`
- unrealized_pnl: `-0.04000000`

Current open Paper position:

- paper_position_id: `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- market_id: `598936`
- side: `YES`
- cost_basis / locked notional: `0.16`
- current exit value: `0.08`
- current unrealized PnL: `-0.04`
- exit-now PnL: `-0.08`
- hold-to-resolution profit if win: `9.84`
- time_to_resolution: available from Exit/Hold
- exit/hold decision: `HOLD_REVIEW`

Before this phase:

- capital lock duration could be computed from position/ledger timestamps, but no model used it.
- reward per hour and reward per dollar-hour did not exist.
- opportunity cost did not exist and was not fabricated in this phase.
- Capital Brain consumed payout/odds and exit-hold visibility observationally, but not a dedicated capital efficiency table.
- Coordinator did not see capital efficiency.

Exact missing links:

- no `capital_efficiency_evaluations`
- no reward-per-dollar-time metric
- no capital efficiency dashboard/API
- no forensics capital efficiency fields
- no dialogue materializer for dollar-time capital use

## Files Created

- `app/db/migrations/0121_capital_efficiency_model.sql`
- `app/services/capital_efficiency.py`
- `tests/test_capital_efficiency.py`
- `docs/POLYBOT_CAPITAL_EFFICIENCY_MODEL.md`
- `docs/POLYBOT_CAPITAL_EFFICIENCY_MODEL_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/paper_trade_forensics.py`
- `app/capital_brain/service.py`
- `app/services/exit_foundation.py`
- `app/mesh_coordinator/service.py`
- `app/services/exit_hold_reasoning.py`
- `app/services/open_position_watchdog.py`
- `app/services/brain_dialogue.py`

## DB Migration

`0121_capital_efficiency_model.sql` creates:

- `capital_efficiency_evaluations`
- `capital_efficiency_sources`

No trading/capital balance tables were modified.

## Runtime Smoke

SYSTEM state before and after smoke:

- power: `OFF`
- live_allowed: `false`
- shadow_allowed: `false`

Bounded evaluation:

- subjects checked: `141`
- evaluations created: `141`
- recommendations: `CAPITAL_WATCH=71`, `CAPITAL_REDUCE_REVIEW=10`, `CAPITAL_BLOCK=4`, `CAPITAL_INSUFFICIENT_DATA=56`

Open position sample:

- evaluation_id: `capital_efficiency_f6d0c1bee17751a4a7657fd48e439e6a`
- paper_position_id: `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- market_id: `598936`
- side: `YES`
- capital_locked: `0.16000000`
- time_locked_seconds: `12129`
- time_to_resolution_seconds: `2313254`
- current_exit_pnl: `-0.080000000000`
- potential_reward: `9.840000000000`
- risk_amount: `0.160000000000`
- reward_per_locked_dollar: `61.5000`
- reward_per_hour: `0.01531349345986216818386567147`
- reward_per_dollar_hour: `0.09570933412413855114916044670`
- current_return_pct: `-0.5000`
- hold_return_pct: `61.5000`
- liquidity_exit_quality: `GOOD`
- rules_risk: `HIGH`
- risk_of_reversal: `HIGH`
- capital_efficiency_score: `0.5500`
- recommendation: `CAPITAL_WATCH`
- missing_inputs_json: `[]`
- confidence: `null`

Missing-time sample:

- subject_type: `FRESH_SEED`
- subject_id: `fresh_seed_2169995_YES`
- recommendation: `CAPITAL_WATCH`
- missing_inputs_json: `["TIME_TO_RESOLUTION_MISSING"]`
- confidence: `null`

Dashboard/API checks:

- `GET /dashboard/api/v2/capital-efficiency`: `mock_data=false`, `status=OK`, `total_evaluations=141`
- `GET /dashboard/api/v2/paper/trade-forensics/7668d890-0fe3-5aa3-bc32-996a2f121da2`: includes capital efficiency fields
- `GET /dashboard/api/v2/capital-brain`: includes `capital_efficiency_observational_only=true`
- `GET /dashboard/api/v2/mesh-coordinator`: includes `capital_efficiency_observational_only=true`
- `GET /dashboard/api/v2/exit-hold`: includes `capital_efficiency_observational_only=true`
- `GET /dashboard/api/v2/system-power`: power `OFF`, live/shadow false

## Before / After Counts

Before:

- capital_efficiency_evaluations: `0`
- paper_intents: `20`
- paper_orders: `12`
- paper_fills: `9`
- paper_positions: `12`
- paper_position_closes: `8`
- paper_capital_ledger: `36`
- live_orders: `0`
- orders_v2: `1`
- fills_v2: `1`
- canonical positions: `0`
- capital balances: current `996.84932200`, available `996.68932200`, locked `0.16000000`, open exposure `0.16000000`, realized `-3.15067800`, unrealized `-0.04000000`

After:

- capital_efficiency_evaluations: `141`
- position evaluations: `1`
- candidate evaluations: `100`
- intent evaluations: `20`
- fresh seed evaluations: `20`
- `CAPITAL_SUPPORT`: `0`
- `CAPITAL_WATCH`: `71`
- `CAPITAL_REDUCE_REVIEW`: `10`
- `CAPITAL_RELEASE_REVIEW`: `0`
- `CAPITAL_BLOCK`: `4`
- `CAPITAL_INSUFFICIENT_DATA`: `56`
- missing_time_to_resolution_count: `76`
- avg_capital_efficiency_score: `0.35117647058823529412`
- avg_reward_per_dollar_hour: `280.466696318546957630595305853170987`
- paper_intents: `20`
- paper_orders: `12`
- paper_fills: `9`
- paper_positions: `12`
- paper_position_closes: `8`
- paper_capital_ledger: `36`
- live_orders: `0`
- orders_v2: `1`
- fills_v2: `1`
- canonical positions: `0`
- capital balances unchanged

## Tests Run

- `docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app python - <<'PY' ... run_migrations() ... PY"`: `migrations_ok`
- parse check: `compile_parse_ok`
- `docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest -q tests/test_capital_efficiency.py"`: `12 passed, 1 warning`
- `docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest -q tests/test_payout_odds.py tests/test_exit_hold_reasoning.py tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_paper_exit_capital_release.py tests/test_paper_no_live_safety.py tests/test_paper_execution_safety.py"`: `43 passed, 1 warning`

## Safety Checklist

- No live enabled.
- No shadow enabled.
- No real orders created.
- No Paper orders/fills/positions created.
- No Paper closes created.
- No balance mutation.
- No paper capital ledger mutation.
- No fake PnL.
- No fake expected return.
- No fake opportunity cost.
- No 30m run started.
- SYSTEM remained OFF.

## Remaining Risks

- Many candidate/fresh-seed subjects lack source-backed time-to-resolution or full exit context and are correctly marked missing/watch/insufficient.
- `avg_reward_per_dollar_hour` is skewed by very high-upside low-price Paper intent previews; this is mathematically derived but should be interpreted with source completeness and risk fields.
- The model is observational and does not yet arbitrate full trade lifecycle decisions.

## Phase Status

YELLOW.

The model, metrics, dashboard, forensics, and visibility are working with passing tests and no trading mutation. Status remains YELLOW because security governance is accepted-yellow and many subjects lack complete time/opportunity data.

Can move to Trade Lifecycle Reasoning Mesh: YES.
