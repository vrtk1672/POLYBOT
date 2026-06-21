# POLYBOT Exit Now vs Hold-to-Resolution Reasoning Build Report

Date: 2026-06-03

Executor: Codex

Task mode: `CONTROLLED_RUNTIME_FEATURE + EXIT_REASONING + HOLD_TO_RESOLUTION_MODEL`

Risk: VERY HIGH

ChatGPT review: REQUIRED

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Current Reality Found

- Current open Paper position: `7668d890-0fe3-5aa3-bc32-996a2f121da2`, market `598936`, side `YES`, entry `0.016`, quantity `10`, current best bid `0.008`.
- Current position payout/odds evaluation existed and provided hold-to-resolution economics: payout if win `10`, profit if win `9.84`.
- Current exit value existed from orderbook snapshot `26705`: exit now value `0.08`, exit now PnL `-0.08`.
- Time source existed for market `598936`; rules source existed and carried high rules/reversal risk.
- Existing Paper Exit logic remained fixed target/stop/max-hold based. No hold-to-resolution comparison existed before this phase.
- Paper Forensics did not show exit-now vs hold reasoning before this phase.
- Coordinator/Capital/Exit did not consume exit-now vs hold data before this phase.

## Files Created

- `app/db/migrations/0120_exit_now_hold_resolution_reasoning.sql`
- `app/services/exit_hold_reasoning.py`
- `tests/test_exit_hold_reasoning.py`
- `docs/POLYBOT_EXIT_NOW_VS_HOLD_REASONING.md`
- `docs/POLYBOT_EXIT_NOW_VS_HOLD_REASONING_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/paper_trade_forensics.py`
- `app/capital_brain/service.py`
- `app/services/exit_foundation.py`
- `app/mesh_coordinator/service.py`
- `app/services/brain_dialogue.py`

## DB Migration

`0120_exit_now_hold_resolution_reasoning.sql` creates:

- `exit_hold_evaluations`
- `exit_hold_sources`

No trading or capital tables were modified.

## Runtime Smoke

SYSTEM state before and after smoke:

- power: `OFF`
- live_allowed: `false`
- shadow_allowed: `false`
- paper_execution_allowed: `false`

Bounded evaluation:

- subjects checked: `121`
- evaluations created: `121`
- decisions: `HOLD_REVIEW=10`, `PARTIAL_EXIT_REVIEW=10`, `WAIT=1`, `INSUFFICIENT_DATA=100`

Open position sample:

- evaluation_id: `exit_hold_0c0fcbbaad7554b09620bfd7fa721195`
- paper_position_id: `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- market_id: `598936`
- side: `YES`
- current_exit_price: `0.008`
- exit_now_value: `0.080000000`
- exit_now_pnl: `-0.080000000000`
- hold_to_resolution_value: `10.000000`
- hold_to_resolution_profit_if_win: `9.840000000000`
- liquidity_exit_quality: `GOOD`
- spread_risk: `LOW`
- rules_risk: `HIGH`
- risk_of_reversal: `HIGH`
- decision: `HOLD_REVIEW`
- missing_inputs_json: `[]`
- confidence: `null`

Missing-data sample:

- decision: `INSUFFICIENT_DATA`
- missing_inputs_json: `["BASIC_POSITION_DATA_MISSING", "EXIT_NOW_UNAVAILABLE", "TIME_TO_RESOLUTION_MISSING"]`
- confidence: `null`

Dashboard/API checks:

- `GET /dashboard/api/v2/exit-hold`: `mock_data=false`, `status=OK`, `total_evaluations=121`
- `GET /dashboard/api/v2/paper/trade-forensics/7668d890-0fe3-5aa3-bc32-996a2f121da2`: includes exit/hold fields and decision `HOLD_REVIEW`
- `GET /dashboard/api/v2/system-power`: power `OFF`, live/shadow false

## Before / After Safety Counts

Before:

- exit_hold_evaluations: `0`
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

- exit_hold_evaluations: `121`
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

- `docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest -q tests/test_exit_hold_reasoning.py"`: `13 passed, 1 warning`
- `docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest -q tests/test_payout_odds.py tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_open_position_watchdog.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py"`: `44 passed, 1 warning`
- migration check: `migrations_ok`
- parse check: `compile_parse_ok`

## Safety Checklist

- No live enabled.
- No shadow enabled.
- No real orders created.
- No Paper orders/fills/positions created by evaluator.
- No Paper closes created by evaluator.
- No balance mutation.
- No fake PnL.
- No fake fair probability, EV, or confidence.
- No 30m run started.

## Remaining Risks

- Many candidate rows lack complete basic subject data or current exit price and are correctly marked `INSUFFICIENT_DATA`.
- Dialogue materialization follows existing SYSTEM power gating; with SYSTEM OFF, normal dialogue materialization is blocked even though the `Exit/Hold` component is wired.
- The model is conservative and observational; it does not yet implement full lifecycle mesh arbitration or capital efficiency.

## Phase Status

YELLOW.

The model, dashboard, forensics, and tests are working, and no trading mutation occurred. Status remains YELLOW because security governance is accepted-yellow and many non-position subjects lack full source data.

Can move to Capital Efficiency Model: YES.
