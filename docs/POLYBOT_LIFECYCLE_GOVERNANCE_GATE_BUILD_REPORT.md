# POLYBOT Lifecycle Governance Gate Build Report

## Summary

Implemented the Lifecycle Governance Gate and actionability ladder so Trade Lifecycle Mesh plans govern canonical Paper Intent and Paper Execution.

Security governance status:

- `SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR`

## Files Created

- `app/db/migrations/0123_lifecycle_governance_gate.sql`
- `app/services/lifecycle_governance.py`
- `tests/test_lifecycle_governance.py`
- `docs/POLYBOT_LIFECYCLE_GOVERNANCE_GATE.md`
- `docs/POLYBOT_LIFECYCLE_GOVERNANCE_GATE_BUILD_REPORT.md`

## Files Changed

- `app/services/paper_intents.py`
- `app/services/paper_execution.py`
- `app/services/runtime_paper_trading.py`
- `app/services/paper_trade_forensics.py`
- `app/services/brain_dialogue.py`
- `app/api/routes.py`
- `tests/test_paper_execution_service.py`

## Migration

Applied:

- `0123_lifecycle_governance_gate.sql`

Tables:

- `lifecycle_governance_decisions`
- `lifecycle_governance_sources`

## Governance Model

Actionability classes:

- `HARD_BLOCK`
- `NO_TRADE`
- `WATCH_FOR_CONFIRMATION`
- `ACTIONABLE_SMALL_PAPER`
- `ACTIONABLE_STANDARD_PAPER`
- `COMPLETE_HIGH_CONFIDENCE`

Critical blockers deny Paper Intent and Paper Execution.

Optional context is recorded and visible, but does not become a hard blocker by itself.

Context-dependent inputs are recorded separately and downgrade actionability unless the relevant Paper request supplies source-backed clearance.

## Integrations

Paper Intent:

- `PaperIntentGateService.build_intents()` now requires lifecycle governance.
- Denied candidates are written to the no-trade ledger.

Paper Execution:

- `PaperExecutionService._validate_intents()` now requires lifecycle governance before capital precheck and execution.
- Old bad `CREATED` intents cannot execute silently.

Legacy Runtime:

- `RuntimePaperTradingService` no longer calls the old `ExecutionAwarePaperService.record_cycle()` Paper artifact path.
- Legacy staged paper order/position command mutations require lifecycle governance and otherwise return without mutating paper state.

API/Dashboard:

- `GET /dashboard/api/v2/lifecycle-governance`
- `GET /dashboard/api/v2/lifecycle-governance/{decision_id}`
- `POST /lifecycle-governance/evaluate`

Forensics:

- Paper forensics now exposes governance decision, actionability class, critical blockers, optional missing context, and allow flags.

Dialogue:

- Brain Dialogue can materialize source-backed Lifecycle Governance messages.

## Tests Run

```bash
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_lifecycle_governance.py"
```

Result:

- `9 passed, 1 warning`

```bash
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_paper_execution_service.py tests/test_paper_execution_capital_guards.py tests/test_v2_paper_intent_service.py tests/test_same_market_side_guard.py"
```

Result:

- `32 passed`

```bash
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_trade_lifecycle.py tests/test_paper_trade_forensics.py tests/test_runtime_integration_guards.py"
```

Result:

- `20 passed, 1 warning`

```bash
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_paper_execution_safety.py tests/test_v2_paper_intent_safety.py tests/test_v2_no_trade_ledger_safety.py tests/test_paper_execution_capital_guards.py"
```

Result:

- `9 passed`

## Runtime Smoke

System state:

- `SYSTEM OFF`
- current mode `PAPER`
- `runtime_work_allowed=false`
- `paper_allowed=false`
- `shadow_allowed=false`
- `live_allowed=false`
- real orders allowed `false`

Migration:

- Applied `0123_lifecycle_governance_gate.sql`

Bounded evaluation:

- Evaluated 241 lifecycle plans.
- Created 241 lifecycle governance decisions.
- Created 241 lifecycle governance source rows.

Governance after smoke:

- `HARD_BLOCK`: 191
- `WATCH_FOR_CONFIRMATION`: 50
- `ACTIONABLE_SMALL_PAPER`: 0
- `ACTIONABLE_STANDARD_PAPER`: 0
- `COMPLETE_HIGH_CONFIDENCE`: 0
- `allow_paper_intent_count`: 0
- `allow_paper_execution_count`: 0

Top critical blockers:

- `RISK_BLOCKED`: 187
- `CAPITAL_BLOCKED`: 4

Top optional missing:

- `MEMORY_CONTEXT_MISSING`: 241
- `WHALE_CONTEXT_MISSING`: 241
- `FAIR_PROBABILITY_MISSING`: 141
- `NEWS_CONTEXT_MISSING`: 68

Dry execution validation:

- `CREATED` intents checked: 15
- executable count: 0
- blockers: `MISSING_TRUSTED_ORDERBOOK=15`, `INTENT_ALREADY_EXECUTED=4`
- no execution was run.

## Before/After Counts

Before:

- lifecycle_governance_decisions: 0
- trade_lifecycle_plans: 241
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
- paper account current_balance: 996.84932200
- available_balance: 996.68932200
- locked_balance: 0.16000000
- open_exposure: 0.16000000
- realized_pnl: -3.15067800
- unrealized_pnl: -0.04000000

After:

- lifecycle_governance_decisions: 241
- lifecycle_governance_sources: 241
- trade_lifecycle_plans: 241
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
- paper account current_balance: 996.84932200
- available_balance: 996.68932200
- locked_balance: 0.16000000
- open_exposure: 0.16000000
- realized_pnl: -3.15067800
- unrealized_pnl: -0.04000000

Trading mutation:

- `false`

## Sample Decisions

Sample hard block:

- actionability: `HARD_BLOCK`
- critical blocker: `RISK_BLOCKED`
- reason: OBSERVE blocked by critical lifecycle governance blockers.

Sample watch:

- subject: open Paper position `7668d890-0fe3-5aa3-bc32-996a2f121da2`
- actionability: `WATCH_FOR_CONFIRMATION`
- optional missing: `FAIR_PROBABILITY_MISSING`, `MEMORY_CONTEXT_MISSING`, `WHALE_CONTEXT_MISSING`
- context-dependent missing: `POSITION_WATCHDOG_MISSING`, `SAME_MARKET_GUARD_MISSING`

Sample actionable:

- None in production smoke.
- Unit tests cover source-backed `ACTIONABLE_SMALL_PAPER` when critical blockers are clear and same-market/risk/exit/lineage are explicitly clear.

## Safety Checklist

- Live not enabled.
- Shadow not enabled.
- No real orders created.
- No paper orders created by governance.
- No paper fills created by governance.
- No paper positions created by governance.
- No paper closes created by governance.
- No paper capital ledger rows created by governance.
- Paper balances unchanged.
- SYSTEM remained OFF.
- No fake rationale, fake confidence, fake probability, or fake lifecycle plan.

## Remaining Risks

- Current production plans still have no actionable Paper authorization: 191 hard blocks and 50 watch decisions.
- Many plans still lack same-market guard records because no new Paper intent run has occurred since guard/governance enforcement.
- Optional missing context remains common, especially memory and whale context.
- Dry validation found current `CREATED` intents are blocked earlier by missing trusted orderbooks; lifecycle governance still protects execution once local prerequisites clear.

## Phase Status

Status: `GREEN`

Can run 30m controlled Paper run:

- `YES`, controlled only, because Paper Intent and Paper Execution now require lifecycle governance and SYSTEM remains OFF until explicitly started.
