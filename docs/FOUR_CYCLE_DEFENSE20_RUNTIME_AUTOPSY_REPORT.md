# Four-Cycle Defense 20 Runtime Autopsy Report

## Purpose

Run four controlled 20-minute PAPER runtime cycles under Paper Defense 20, capture the Full Mesh lifecycle truth after each cycle, repair clear in-scope bugs, and compare cycle-to-cycle behavior.

## Preflight

- Run root: `run_reports/four_cycle_defense20_autopsy_20260621T172222Z/`
- Git status: unavailable; `C:\Server\apps\polybot` is not a Git checkout.
- Pre-rebuild API health: reachable.
- Pre-rebuild runtime state: PAPER, supervisor DEGRADED from prior session.
- Required migrations present: `0146`, `0147`, `0148`, `0149`, `0150`.
- Rebuild/deploy:
  - `docker compose build api`: passed.
  - `docker compose build migrate`: passed.
  - `docker compose run --rm migrate`: passed, no pending migrations.
  - `docker compose up -d --no-deps api`: passed.
  - post-start `/healthz`: OK.

## Repair Performed After Cycle 1

Cycle 1 proved the runtime could hunt and execute PAPER trades, but four otherwise executable intents expired with:

- `POSITION_SIZE_LIMIT`
- `RISK_PER_TRADE_LIMIT`

Root cause:

- Paper Defense 20 intent sizing targeted about 15% of the original 1000 balance.
- The capital precheck compared the requested notional against current balance/risk capacity after realized losses.
- The execution path blocked the whole intent instead of reducing quantity to the still-valid current allowed notional.
- Daily realized PnL was also globally scoped by date in `PaperCapitalService`, which could produce a false `DAILY_LOSS_LIMIT` after session reset.

Fix:

- Added Paper-only risk/capital quantity clamp for `POSITION_SIZE_LIMIT` / `RISK_PER_TRADE_LIMIT`.
- Clamp does not soften `DAILY_LOSS_LIMIT`, balance, max-open-position, exposure, or invalid-notional guards.
- Added `SIZE_BELOW_MIN_AFTER_RISK_CLAMP` when the clamped size is too small for a meaningful Paper sample.
- Scoped daily realized PnL guard to active `paper_session_id` when the schema supports it.
- Recorded clamp metadata on orders/fills/positions.

Changed files:

- `app/services/paper_capital.py`
- `app/services/paper_execution.py`
- `tests/test_paper_execution_capital_guards.py`

No migration was required.

## Cycle Summary

| Cycle | Session | Verdict | Main bottleneck | Intents | Orders | Fills | Positions | Closes | Expired | Clamped | Remembered | Reactivated | PnL |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `paper_session_20260621T172400Z_95780e59` | `YELLOW_CYCLE_BLOCKED_BY_RISK` | `RISK_CAPITAL` | 8 | 4 | 4 | 4 | 4 | 4 | 0 | 4 | 0 | -18.50 |
| 2 | `paper_session_20260621T175635Z_83fc51d4` | `GREEN_CYCLE_FULL_PAPER_LIFECYCLE` | `EXIT_LOGIC_OBSERVATION_WINDOW` | 6 | 6 | 6 | 6 | 6 | 0 | 1 | 0 | 0 | -42.454543 |
| 3 | `paper_session_20260621T181754Z_b752045b` | `GREEN_CYCLE_FULL_PAPER_LIFECYCLE` | `EXIT_LOGIC_OBSERVATION_WINDOW` | 6 | 6 | 6 | 6 | 6 | 0 | 1 | 0 | 0 | -45.628125 |
| 4 | `paper_session_20260621T184033Z_7ddb7b31` | `YELLOW_CYCLE_EXECUTION_BUT_LOSSY` | `EXIT_LOGIC_OBSERVATION_WINDOW` | 6 | 6 | 6 | 6 | 3 | 0 | 2 | 0 | 0 | -59.584 |

Cycle 4 PnL includes `-19.0` realized and `-40.584` unrealized with three open positions at the final snapshot.

## Runtime Continuity

- All four cycles started fresh active Paper sessions with Defense 20.
- Runtime remained PAPER and API health remained OK.
- Source refresh and runtime cycles advanced during observation.
- Latest errors were `none reported` in all final cycle reports.
- No duplicate eligibility crash occurred.
- No `MISSING_TRUSTED_ORDERBOOK` bottleneck recurred after the prior orderbook/fallback repair.

## Hunting And Decisions

Across cycles:

- Market universe increased from 1013 to 1015.
- Recent events increased from 14228 baseline to 14736 by Cycle 4 final.
- Triggers increased from 1805 to 1876.
- Candidates increased from 7918 to 8133.
- AI insights increased from 3547 to 3647.
- Runtime PAPER decisions stayed at 17 with 8-9 Paper-enter decisions.
- Decision diversity stayed narrow: 9 unique markets, 2 sides, concentration score 0.0588.

Primary recurring decision blocker:

- `OPPOSING_SIDE_DEMOTED_BY_ARBITRATION`, expected, from side arbitration.

## Execution And Price Sources

Execution worked in every cycle:

- Cycle 1: 4 fills before the risk clamp repair.
- Cycle 2: 6 fills after repair.
- Cycle 3: 6 fills.
- Cycle 4: 6 fills.

Price source counts:

- Cycle 1: trusted 1, last-mile trusted 1, fallback 2.
- Cycle 2: trusted 1, fallback 5.
- Cycle 3: trusted 5, last-mile trusted 1.
- Cycle 4: trusted 4, last-mile trusted 2.

Fallback executions were labeled as `PAPER_LEARNING_PRICE_FALLBACK`; no fallback was labeled trusted.

## Risk / Capital

Cycle 1 exposed the risk sizing bug:

- `POSITION_SIZE_LIMIT` / `RISK_PER_TRADE_LIMIT` expired 4 intents.
- Session PnL was not zero by final, so this was not a false daily-loss event.

After repair:

- Cycles 2-4 had zero risk-expired intents.
- Clamp metadata appeared on 1 fill in Cycle 2, 1 fill in Cycle 3, and 2 fills in Cycle 4.
- No false `DAILY_LOSS_LIMIT` appeared in cycles 2-4.

## Opportunity Memory

- Cycle 1 remembered 4 expired risk-size opportunities.
- Cycles 2-4 had no expired intents and therefore no new opportunity memory rows.
- No reactivation was observed naturally.

## Deadlocks / Degraded Events

Docker API logs during the observation window contained one `DeadlockDetected` under `neural_event_bus_foundation_stage_failed` around 18:37 UTC.

Impact:

- PAPER runtime continued.
- API health remained OK.
- Final cycle reports still showed latest errors as none.
- This did not stop Paper execution or accounting.

Next repair candidate:

- Add bounded retry/backoff around the neural event bus or thesis/profile write path that hit the deadlock.

## Safety

- PAPER only.
- Live adapter remained blocked.
- `live_orders`: 0.
- Operator status reported Live/Shadow/Real orders as 0 in all final cycle snapshots.
- Historical `orders_v2` / `fills_v2` rows existed before this run and were not part of the PAPER cycle path.
- Historical Paper data was preserved.
- Current session counts remained session-scoped.
- No fake trades were created.
- No Defense thresholds were lowered.

## Tests

Focused after risk/capital repair:

```text
docker compose --profile test run --rm test python -m pytest tests/test_paper_execution_capital_guards.py -q
8 passed
```

Requested local regression command:

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py tests/test_opportunity_mesh_coordinator.py tests/test_opportunity_memory.py tests/test_paper_intent_expiry.py tests/test_paper_execution_trusted_orderbook.py tests/test_paper_execution_learning_fallback.py tests/test_paper_execution_adapter_runtime.py tests/test_paper_session_status_report.py -q
2 passed, 16 skipped
```

Docker DB-backed equivalent:

```text
docker compose --profile test run --rm test python -m pytest tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py tests/test_opportunity_mesh_coordinator.py tests/test_opportunity_memory.py tests/test_paper_intent_expiry.py tests/test_paper_execution_trusted_orderbook.py tests/test_paper_execution_learning_fallback.py tests/test_paper_execution_adapter_runtime.py tests/test_paper_session_status_report.py -q
18 passed, 1 warning
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

Requested `test_paper_risk_*` files were not present in this repository; coverage for the implemented risk repair was added to `tests/test_paper_execution_capital_guards.py`.

## Final Diagnosis

The Full Mesh PAPER runtime is continuous and functioning under Defense 20:

- Hunting continued.
- Candidates and AI insights advanced.
- Defense 20 softened strategic blockers.
- Integrity blockers remained hard.
- Arbitration selected/demoted sides.
- Paper intents became orders/fills/positions.
- Stale/risk-expired intents were visible and remembered before the fix.
- After the fix, risk-size intents clamped and executed instead of expiring.
- Learning reports were generated for every cycle.

Remaining bottleneck:

- Exit timing / open-position management within a 20-minute observation window.
- One non-fatal DB deadlock in the neural event bus/thesis path should be repaired next with retry/backoff.

## Status

YELLOW.

All four cycles completed and the in-scope risk/capital bug was repaired. The final cycle proved hunting, intent creation, execution, fills, positions, PnL, and report generation, but three positions remained open at the 20-minute cutoff and a non-fatal DB deadlock was observed in logs.

Safe to continue Defense 20 PAPER runtime: YES.
