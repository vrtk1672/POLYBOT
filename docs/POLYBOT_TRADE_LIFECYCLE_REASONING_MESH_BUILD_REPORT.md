# POLYBOT Trade Lifecycle Reasoning Mesh Build Report

Date: 2026-06-03
Executor: Codex
Security governance: YELLOW_ACCEPTED_BY_OPERATOR
ChatGPT review: REQUIRED
Status: YELLOW

## Summary

Implemented the Trade Lifecycle Reasoning Mesh as a derived, source-backed planning layer. It creates lifecycle plans for fresh seeds, paper candidates, paper intents, and open paper positions without creating trades, closing positions, mutating balances, or bypassing existing gates.

The model aggregates Payout/Odds, Exit/Hold, Capital Efficiency, Same-Market Guard, Risk, Exit Foundation, Capital Brain, Orderbook/Liquidity, Position Watchdog, Rules/Wording, News, Whale, Memory, and Coordinator inputs when present.

## Current Reality Found

Production source counts before implementation:

- mesh_sessions: 57
- mesh_shared_awareness: 57
- mesh_brain_opinions: 251
- mesh_coordinator_decisions: 47
- mesh_conflict_records: 35
- payout_odds_evaluations: 160
- exit_hold_evaluations: 121
- capital_efficiency_evaluations: 141
- same_market_side_guard_decisions: 0
- risk_decisions: 10580
- exit_plans: 10580
- capital_brain_evaluations: 57
- paper_intents: 20
- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- open paper positions: 1

Current open position:

- paper_position_id: 7668d890-0fe3-5aa3-bc32-996a2f121da2
- market_id: 598936
- side: YES
- entry_price: 0.016
- quantity: 10
- capital locked: 0.16
- open exposure: 0.16

Fragmentation found:

- Payout, exit/hold, capital efficiency, risk, exit foundation, capital, orderbook, watchdog, news, rules, and coordinator records existed in separate tables.
- No single lifecycle plan existed.
- Same-market guard production table existed but contained zero decisions.
- Market memory and whale context were largely unavailable for current subjects.

## Files Created

- `app/db/migrations/0122_trade_lifecycle_reasoning_mesh.sql`
- `app/services/trade_lifecycle.py`
- `tests/test_trade_lifecycle.py`
- `docs/POLYBOT_TRADE_LIFECYCLE_REASONING_MESH.md`
- `docs/POLYBOT_TRADE_LIFECYCLE_REASONING_MESH_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/paper_trade_forensics.py`
- `app/capital_brain/service.py`
- `app/services/exit_foundation.py`
- `app/mesh_coordinator/service.py`
- `app/services/brain_dialogue.py`

## DB Migration

Applied:

- `0122_trade_lifecycle_reasoning_mesh.sql`

Tables:

- `trade_lifecycle_plans`
- `trade_lifecycle_plan_sources`
- `trade_lifecycle_brain_contributions`

Only derived lifecycle tables were created. Paper, live, canonical execution, and capital tables were not changed.

## Model

Supported subjects:

- FRESH_SEED
- PAPER_CANDIDATE
- PAPER_INTENT
- PAPER_POSITION

Allowed plan statuses:

- COMPLETE
- PARTIAL
- WATCH
- NO_TRADE
- BLOCKED
- INSUFFICIENT_DATA

Allowed decision classes:

- PAPER_CANDIDATE_REVIEW
- PAPER_INTENT_READY_CONTEXT
- HOLD_REVIEW
- EXIT_REVIEW
- NO_TRADE
- WATCH
- BLOCKED
- INSUFFICIENT_DATA

## Strategy Rules

Hard source-backed blockers dominate:

- same-market guard BLOCK -> SAME_MARKET_BLOCKED / BLOCKED
- risk BLOCK -> RISK_BLOCKED / BLOCKED
- exit plan BLOCKED -> EXIT_BLOCKED / BLOCKED
- capital recommendation CAPITAL_BLOCK -> CAPITAL_BLOCKED / BLOCKED

Otherwise:

- exit now / partial / emergency exit reasoning -> EXIT_NOW_REVIEW
- open position hold reasoning -> HOLD_REVIEW
- coordinator candidate review -> REPRICING_CANDIDATE
- capital support -> CAPITAL_EFFICIENCY_PLAY
- missing source-backed rationale -> WATCH_ONLY or INSUFFICIENT_DATA

No fair probability, confidence, edge, or thesis is generated without source-backed input.

## API and Dashboard

Added:

- `GET /dashboard/api/v2/trade-lifecycle`
- `GET /dashboard/api/v2/trade-lifecycle/{plan_id}`
- `POST /trade-lifecycle/build`

Dashboard summary returns:

- `mock_data=false`
- plan totals
- subject type counts
- strategy counts
- status counts
- latest plans
- top missing inputs
- security governance status

## Forensics

Paper trade forensics now includes:

- `trade_lifecycle_plan`
- lifecycle strategy/status/decision class
- economic, entry, exit, and hold theses
- capital plan
- monitoring plan
- invalidation rules
- coordinator judgment
- missing inputs
- lifecycle brain contributions
- lifecycle lineage in non-compact mode

## Coordinator, Capital, Exit Visibility

Capital Brain, Exit Foundation, and Mesh Coordinator now expose lifecycle visibility as observational input.

The lifecycle mesh does not override Coordinator decisions and does not alter capital, exit, or execution behavior.

## Dialogue

Brain Dialogue includes a `trade_lifecycle` component and source-backed lifecycle messages:

- blocked plans
- partial plans with missing inputs
- position hold review
- position exit review
- generic lifecycle context

Normal dialogue materialization remains blocked while SYSTEM is OFF by existing project convention.

## Tests Run

Commands and results:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_trade_lifecycle.py"
10 passed, 1 warning

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_payout_odds.py"
13 passed, 1 warning

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_exit_hold_reasoning.py"
13 passed, 1 warning

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_capital_efficiency.py"
12 passed, 1 warning

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_same_market_side_guard.py"
14 passed

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_paper_no_live_safety.py tests/test_paper_execution_safety.py tests/test_paper_exit_safety.py"
3 passed, 1 warning

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py tests/test_open_position_watchdog.py"
19 passed

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_v2_paper_intent_safety.py tests/test_v2_paper_eligibility_safety.py"
3 passed

docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_paper_capital_account.py tests/test_dashboard_paper_capital_truth.py tests/test_paper_execution_capital_guards.py tests/test_paper_pnl_reconciliation.py"
16 passed, 1 warning
```

A combined regression command timed out before returning results and was stopped; the same suites were then run individually or in smaller groups with the passing results above.

## Runtime Smoke

SYSTEM state:

- system_power: OFF
- current_mode: PAPER
- live metadata: false
- shadow metadata: false

Migration:

- Applied `0122_trade_lifecycle_reasoning_mesh.sql`

Dry run:

- `TradeLifecycleService().build_recent(limit=200, dry_run=True)` generated source-backed outcomes without writes.

Bounded build:

- `TradeLifecycleService().build_recent(limit=200, dry_run=False)`
- subjects_checked: 241
- plans_created: 241
- trading_mutation: false

Dashboard/API smoke:

- `GET /dashboard/api/v2/trade-lifecycle`: 200, `mock_data=false`
- `GET /dashboard/api/v2/trade-lifecycle/{plan_id}`: 200, contributions present
- `GET /dashboard/api/v2/paper/trade-forensics/{open_position_id}`: 200, lifecycle strategy HOLD_REVIEW, status WATCH
- `GET /dashboard/api/v2/capital-brain`: 200, lifecycle observational flag true
- `GET /dashboard/api/v2/exit-foundation`: 200, lifecycle observational flag true
- `GET /dashboard/api/v2/mesh-coordinator`: 200, lifecycle observational flag true

## Before and After Counts

Before bounded build:

- trade_lifecycle_plans: 0
- trade_lifecycle_plan_sources: 0
- trade_lifecycle_brain_contributions: 0
- paper_intents: 20
- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- paper_position_closes: 8
- paper_capital_ledger: 36
- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0
- current_balance: 996.84932200
- available_balance: 996.68932200
- locked_balance: 0.16000000
- open_exposure: 0.16000000
- realized_pnl: -3.15067800
- unrealized_pnl: -0.04000000

After bounded build:

- trade_lifecycle_plans: 241
- trade_lifecycle_plan_sources: 3770
- trade_lifecycle_brain_contributions: 3070
- paper_intents: 20
- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- paper_position_closes: 8
- paper_capital_ledger: 36
- live_orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0
- current_balance: 996.84932200
- available_balance: 996.68932200
- locked_balance: 0.16000000
- open_exposure: 0.16000000
- realized_pnl: -3.15067800
- unrealized_pnl: -0.04000000

Plan counts after bounded build:

- FRESH_SEED: 20
- PAPER_CANDIDATE: 200
- PAPER_INTENT: 20
- PAPER_POSITION: 1
- COMPLETE: 0
- PARTIAL: 45
- WATCH: 5
- NO_TRADE: 0
- BLOCKED: 191
- INSUFFICIENT_DATA: 0

Strategy counts:

- CAPITAL_BLOCKED: 4
- EXIT_NOW_REVIEW: 4
- HOLD_REVIEW: 1
- REPRICING_CANDIDATE: 42
- RISK_BLOCKED: 187
- WATCH_ONLY: 3

Top missing inputs:

- MEMORY_CONTEXT_MISSING: 241
- SAME_MARKET_GUARD_MISSING: 241
- WHALE_CONTEXT_MISSING: 241
- FAIR_PROBABILITY_MISSING: 141
- EXIT_HOLD_MISSING: 120
- BASIC_POSITION_DATA_MISSING: 100
- CAPITAL_EFFICIENCY_MISSING: 100
- EXIT_NOW_UNAVAILABLE: 100
- PAYOUT_ODDS_MISSING: 100
- TIME_TO_RESOLUTION_MISSING: 76

## Sample Open Position Plan

- subject_type: PAPER_POSITION
- subject_id: 7668d890-0fe3-5aa3-bc32-996a2f121da2
- market_id: 598936
- side: YES
- strategy_type: HOLD_REVIEW
- plan_status: WATCH
- decision_class: HOLD_REVIEW
- payout price: 0.016
- implied_probability: 0.016
- profit_if_win: 9.84
- risk_reward: 61.5
- exit_now_pnl: -0.08
- hold_to_resolution_profit_if_win: 9.84
- capital_locked: 0.16
- capital_efficiency_recommendation: CAPITAL_WATCH
- missing_inputs: FAIR_PROBABILITY_MISSING, MEMORY_CONTEXT_MISSING, POSITION_WATCHDOG_MISSING, SAME_MARKET_GUARD_MISSING, WHALE_CONTEXT_MISSING

## Sample Candidate Plan

- subject_type: PAPER_CANDIDATE
- subject_id: eligibility_exit_risk_thesis_coord_8bd1a2ff82a54fd7bc58f174fd87a964
- market_id: 824952
- side: YES
- strategy_type: WATCH_ONLY
- plan_status: PARTIAL
- decision_class: WATCH
- missing_inputs: CAPITAL_EFFICIENCY_MISSING, EXIT_HOLD_MISSING, MEMORY_CONTEXT_MISSING, PAYOUT_ODDS_MISSING, SAME_MARKET_GUARD_MISSING, WHALE_CONTEXT_MISSING

## Sample Blocked Plan

- subject_type: FRESH_SEED
- subject_id: fresh_seed_2354064_YES
- market_id: 2354064
- side: YES
- strategy_type: RISK_BLOCKED
- plan_status: BLOCKED
- decision_class: BLOCKED
- reason: risk decision blocked entry

No same-market blocked production sample exists because `same_market_side_guard_decisions` currently contains zero rows.

## Safety Checklist

- Live not enabled.
- Shadow not enabled.
- SYSTEM remained OFF.
- No order/write endpoints called.
- No paper intents created.
- No paper orders created.
- No paper fills created.
- No paper positions created.
- No paper closes created.
- No paper capital ledger mutation.
- No paper account balance mutation.
- No live orders created.
- No orders_v2 or fills_v2 mutation.
- No canonical positions created.
- No fake fair probability, confidence, edge, or thesis.

## Remaining Risks

- Many production plans are PARTIAL or WATCH because same-market guard, whale, and memory inputs are absent for all built subjects.
- Fair probability and expected value remain intentionally missing unless a source-backed fair-probability model is added.
- Candidate coverage was bounded by `limit=200`; more historical candidates can be built later.
- The mesh is observational only; execution enforcement should be a later explicit phase.

## Phase Status

YELLOW.

The lifecycle mesh is implemented, tested, source-backed, and non-mutating. It is not GREEN because no production plan is COMPLETE and several optional-but-important context sources are missing.

Can move to Mesh Compliance Audit: YES.

