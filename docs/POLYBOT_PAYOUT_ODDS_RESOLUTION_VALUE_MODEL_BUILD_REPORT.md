# POLYBOT Payout / Odds / Resolution Value Model Build Report

## Dispatch

- Executor: Codex
- Task mode: CONTROLLED_RUNTIME_FEATURE + ECONOMIC_REASONING + PAYOUT_ODDS_MODEL
- Risk: VERY HIGH
- ChatGPT review: REQUIRED
- Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Current Reality Found

- Entry price is stored in `paper_positions.avg_entry`, `paper_fills.fill_price`, `paper_orders.avg_fill_price`, and `paper_position_closes.entry_price`.
- Executable/intended price is stored in `paper_intents.intended_price` and evidence/orderbook fields such as `orderbook_best_ask`.
- Paper sizing uses safe notional/quantity in `paper_intents.evidence`; current Paper Intent sizing uses fixed safe notional with quantity clamping.
- Quantity is effectively shares, but prior code did not explain it as shares or payout.
- No application-level `payout_if_win`, `profit_if_win`, `break_even_probability`, source-backed EV, or settlement value table existed before this phase.
- Paper Forensics showed price/quantity/capital lineage but not payout/odds fields.
- Capital Brain, Exit Foundation, and Coordinator did not consume payout/odds. They now expose it as observational-only context.

## Files Created

- `app/db/migrations/0119_payout_odds_resolution_value.sql`
- `app/services/payout_odds.py`
- `tests/test_payout_odds.py`
- `docs/POLYBOT_PAYOUT_ODDS_RESOLUTION_VALUE_MODEL.md`
- `docs/POLYBOT_PAYOUT_ODDS_RESOLUTION_VALUE_MODEL_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/paper_trade_forensics.py`
- `app/capital_brain/service.py`
- `app/services/exit_foundation.py`
- `app/mesh_coordinator/service.py`
- `app/services/paper_intents.py`
- `app/services/paper_execution.py`
- `app/services/fresh_seed_paper_path.py`
- `app/services/brain_dialogue.py`

## Migration

Applied production migration:

- `0119_payout_odds_resolution_value.sql`

It adds `payout_odds_evaluations` and `payout_odds_sources`.

## Model

The evaluator records derived truth for:

- `FRESH_SEED`
- `PAPER_CANDIDATE`
- `PAPER_INTENT`
- `PAPER_POSITION`
- `PAPER_CLOSE`

It is idempotent by deterministic `evaluation_id`. It records `MISSING_PRICE` instead of inventing a price and keeps `fair_probability` / `expected_value` null without source-backed fair probability.

## Runtime Smoke

SYSTEM remained OFF.

Before evaluation:

- `payout_odds_evaluations=0`
- `payout_odds_sources=0`
- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=8`
- `paper_capital_ledger=36`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- paper account: current `996.84932200`, available `996.68932200`, locked `0.16000000`, open exposure `0.16000000`, realized `-3.15067800`, unrealized `-0.04000000`

Evaluation result:

- subjects checked: `160`
- evaluations created: `160`
- `OK=104`
- `MISSING_PRICE=56`
- trading mutation: `false`

After evaluation:

- `payout_odds_evaluations=160`
- `payout_odds_sources=160`
- `FRESH_SEED=20`
- `PAPER_CANDIDATE=100`
- `PAPER_INTENT=20`
- `PAPER_POSITION=12`
- `PAPER_CLOSE=8`
- `missing_price_count=56`
- `avg_risk_reward=65.1033517771954002208575358964`
- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=8`
- `paper_capital_ledger=36`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`
- capital balances unchanged.

Dashboard smoke:

- `GET /healthz`: ready
- `GET /system/power`: OFF, runtime work not allowed
- `GET /dashboard/api/v2/payout-odds?limit=3`: `mock_data=false`, `total_evaluations=160`, `missing_price_count=56`, warm response `183ms`
- `GET /dashboard/api/v2/paper/trade-forensics/7668d890-0fe3-5aa3-bc32-996a2f121da2`: includes payout/odds fields

## Sample Evaluations

Open position `598936 YES`:

- entry price: `0.016`
- quantity/shares: `10`
- cost basis: `0.16`
- payout if win: `10`
- profit if win: `9.84`
- max loss: `0.16`
- risk/reward: `61.5`
- implied probability: `0.016`
- current exit value from best bid: `0.08`
- fair probability: `NULL`
- expected value: `NULL`

Intent `598936 YES`:

- price: `0.016`
- stake: `5.0`
- shares if buy: `312.5`
- payout if win: `312.5`
- profit if win: `307.5`
- risk/reward: `61.5`
- fair probability: `NULL`
- expected value: `NULL`

Missing-price sample:

- subject type: `PAPER_CANDIDATE`
- status: `MISSING_PRICE`
- price: `NULL`
- price source: `NULL`

## Tests

Commands run:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app python -m py_compile app/services/payout_odds.py app/api/routes.py app/services/paper_trade_forensics.py app/capital_brain/service.py app/services/exit_foundation.py app/mesh_coordinator/service.py app/services/paper_intents.py app/services/paper_execution.py app/services/fresh_seed_paper_path.py app/services/brain_dialogue.py"
```

Result: passed.

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_payout_odds.py -q"
```

Result: `13 passed, 1 warning`.

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_same_market_side_guard.py tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py -q"
```

Result: `26 passed`.

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPATH=/app pytest tests/test_fresh_seed_paper_path.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q"
```

Result: `25 passed, 1 warning`.

## Safety Checklist

- Live enabled: NO
- Shadow enabled: NO
- Real order created: NO
- Paper order/fill/position created by evaluator: NO
- Paper intent forced: NO
- Risk/exit thresholds changed: NO
- Balance mutated: NO
- Fair probability faked: NO
- EV faked: NO
- 30m run started: NO
- SYSTEM remains OFF: YES

## Remaining Risks

- Many historical candidates lack executable price and correctly produce `MISSING_PRICE`.
- This phase does not decide whether the market-implied payout is attractive versus a source-backed fair probability; that belongs to the next Exit Now vs Hold-to-Resolution and EV reasoning phase.
- Capital/Exit/Coordinator visibility is observational only and does not yet change decisions.

## Phase Status

GREEN.

Can move to Exit Now vs Hold-to-Resolution Reasoning: YES, after ChatGPT/operator review.
