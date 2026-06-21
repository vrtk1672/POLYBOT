# Controlled Paper Runtime Report

## 1. Purpose

Run POLYBOT with `SYSTEM ON` and Paper Simulation explicitly `ON`, while allowing paper artifacts only through the canonical Paper Simulation path and only when a candidate satisfies strict Paper Actionability.

This run was also used to close one safety gap found before activation: the Paper intent builder still consumed `paper_eligibility_candidates` directly. It now requires a matching strict Paper Actionability row before creating a paper intent.

## 2. Baseline Counts

Captured before SYSTEM ON / Paper ON at `2026-06-16T13:06:09Z`.

| Table | Baseline |
|---|---:|
| paper_intents | 21 |
| paper_orders | 12 |
| paper_fills | 9 |
| paper_positions | 12 |
| paper_position_closes | 9 |
| paper_trade_ledger | 18 |
| paper_daily_pnl | 5 |
| paper_capital_ledger | 38 |
| live_orders | 0 |
| positions | 0 |
| shadow_orders | 0 |
| real_orders | not present |
| live_positions | not present |
| source_refresh_cycles | 117 |
| trade_thesis_evaluations | 820 |
| risk_evidence_mesh_evaluations | 6522 |
| lifecycle_governance_decisions | 15000 |
| capital_efficiency_evaluations | 6501 |
| exit_plans | 21006 |
| brain_outputs | 49592 |
| coordinator_decisions | 26844 |

## 3. Restart Result

API was rebuilt and recreated because the Paper intent gate needed a hard strict-actionability guard before any Paper ON runtime:

```text
docker compose build api
docker compose up -d --no-deps api
```

Health verification passed:

- `/healthz`: reachable / ok
- `/runtime/health`: reachable
- Paper Simulation: `DISABLED`
- Live execution: disabled
- Shadow: disabled

## 4. SYSTEM ON Result

SYSTEM ON accepted at `2026-06-16T13:07:10Z`.

- `system_power=ON`
- runtime supervisor started
- mode remained `DATA_ONLY`
- Paper Simulation remained `OFF`
- Live and Shadow remained disabled

After initial cycles, `/paper-actionability?limit=100` still reported:

- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`
- blockers mainly `BLOCKED_BY_RISK`, `BLOCKED_BY_EXIT`, and strict non-actionable states

## 5. Paper Simulation ON Result

Paper Simulation was enabled through the canonical endpoint at `2026-06-16T13:11:21Z`.

The State Governor response showed:

- Paper Simulation `ENABLED`
- paper-only / simulated-only true
- `live_execution_enabled=false`
- Shadow disabled
- real execution disabled

Immediate count check after Paper ON showed no artifact delta:

- paper_intents: `21 -> 21`
- paper_orders: `12 -> 12`
- paper_fills: `9 -> 9`
- paper_positions: `12 -> 12`
- live_orders: `0 -> 0`
- positions: `0 -> 0`
- shadow_orders: `0 -> 0`

## 6. Runtime Timeline

Runtime monitor log:

`docs/run_logs/CONTROLLED_PAPER_RUNTIME_20260616T131435Z.jsonl`

Controlled window:

- first tick: `2026-06-16T13:15:24Z`
- final tick: `2026-06-16T13:29:18Z`
- 21 ticks
- polling cadence: about 30 seconds plus endpoint/DB collection time
- duration: about 13 minutes 54 seconds

Paper remained ON during the window and was then disabled during cleanup.

## 7. Actionability Timeline

First tick:

- items checked: 100
- candidate-scoped bundles: 32
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`
- blocked by lifecycle: 40
- blocked by risk: 45
- blocked by exit: 14
- strict not actionable: 1

Final tick:

- items checked: 100
- candidate-scoped bundles: 20
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`
- blocked by lifecycle: 82
- blocked by risk: 15
- blocked by exit: 0
- strict not actionable: 3

No strict actionable candidate appeared.

## 8. Paper Artifact Timeline

During Paper ON runtime:

| Artifact | Delta |
|---|---:|
| paper_intents | 0 |
| paper_orders | 0 |
| paper_fills | 0 |
| paper_positions | 0 |
| paper_trade_ledger | 0 |
| paper_daily_pnl | 0 |
| paper_capital_ledger | 0 |

No canonical paper artifact chain was created because no candidate satisfied strict Paper Actionability.

## 9. Candidate Evidence

Best repeated candidates at final tick were source-backed and thesis-backed, but not paper-qualified.

Example top candidate:

- candidate_id: `eligibility_exit_risk_thesis_coord_220c6d3449b24bdca52886ccba803121`
- market_id: `691547`
- side: `YES`
- token_id: `34626184950254225208692030156208941308358060420950772251072421141618169142241`
- edge_state: `EDGE_SUPPORTED`
- trade_thesis_type: `MISPRICING_REVERSION`
- exit_intent: `PRICE_TARGET_EXIT`
- expected_hold_time_hours: `48`
- risk_gate_state: `RISK_REVIEW`
- exit_gate_state: `EXIT_READY`
- capital_gate_state: `CAPITAL_OK`
- risk_capital_policy_state: `CAPITAL_WATCH`
- actionability state: `BLOCKED_BY_LIFECYCLE`

## 10. Trade Thesis Evidence

Trade Thesis continued to run:

- `trade_thesis_evaluations`: `820 -> 1260`
- delta: `+440` from pre-run baseline
- delta during Paper ON monitor baseline: `+260`

Top candidates had `MISPRICING_REVERSION` thesis and `PRICE_TARGET_EXIT`, but strict qualification still failed due current Risk/Lifecycle state.

## 11. Dynamic Hold-Time Evidence

Dynamic hold time was present on top thesis-backed candidates:

- expected hold time: `48h`
- hold-time source implied by mispricing reversion thesis

The dynamic hold-time layer did not by itself authorize Paper because Risk stayed review/watch and lifecycle/actionability did not pass strict contract.

## 12. Risk / Exit / Lifecycle Evidence

During Paper ON monitor:

- risk evidence rows increased: `+699`
- lifecycle decisions increased: `+439`
- capital efficiency evaluations increased: `+419`
- exit plans increased: `+26`

Final actionability blocker mix:

- no `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`
- `BLOCKED_BY_LIFECYCLE=82`
- `BLOCKED_BY_RISK=15`
- `strict_not_actionable=3`

Representative blockers included:

- `BLOCKED_BY_LIFECYCLE_CURRENT`
- `BLOCKED_BY_RISK`
- `RISK_BLOCKED`
- `RISK_BLOCKED_STALE_CRITICAL_SOURCE`
- `STALE_ORDERBOOK`
- `STALE_RISK_DECISION`
- `MISSING_CANDIDATE_EVENT_LINK`
- `NOT_ACTIONABLE_EVENT_SCOPE`

## 13. Intent / Order / Fill / Position Chain

No new paper intent, order, fill, or position was created.

Reason: no selected row reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` under the strict qualification contract.

The strict Paper intent gate held: Paper ON did not convert looser paper eligibility rows into paper intents.

## 14. Ledger / PnL Truth

No new ledger or PnL rows were created during this controlled Paper runtime.

Existing historical paper ledger/PnL rows remained unchanged:

- `paper_trade_ledger=18`
- `paper_daily_pnl=5`
- `paper_capital_ledger=38`

## 15. Forbidden Artifact Counts

Forbidden artifact counts stayed unchanged.

| Artifact | Before | After | Delta |
|---|---:|---:|---:|
| live_orders | 0 | 0 | 0 |
| positions | 0 | 0 | 0 |
| shadow_orders | 0 | 0 | 0 |
| real_orders | not present | not present | n/a |
| live_positions | not present | not present | n/a |

## 16. Cleanup Result

Cleanup completed:

- Paper Simulation OFF accepted
- SYSTEM OFF accepted
- runtime life state: `STOPPED`
- supervisor state: `STOPPED`
- system power: `OFF`
- Paper Simulation: `DISABLED`
- Live and Shadow remained disabled

Final count capture at `2026-06-16T13:30:03Z`:

- `paper_intents=21`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`
- `shadow_orders=0`
- `source_refresh_cycles=139`
- `trade_thesis_evaluations=1260`
- `risk_evidence_mesh_evaluations=7723`
- `lifecycle_governance_decisions=15761`
- `capital_efficiency_evaluations=7262`
- `exit_plans=21061`
- `brain_outputs=52242`
- `coordinator_decisions=27406`

## 17. Status

`GREEN` for controlled Paper runtime safety.

Paper Simulation activated safely, idled correctly with no strict actionable candidate, created no paper artifacts, and created no live/shadow/real artifacts.

This is not a successful trade-chain certification because no paper intent/order/fill/position chain was created.

## 18. Extended Paper Runtime

Extended controlled Paper-only runtime is allowed next only under the same guardrails:

- strict Paper Actionability required
- Paper intent gate strict-actionability guard active
- live and shadow disabled
- bounded artifact limits
- continuous artifact/forbidden-count monitoring

Shadow is not allowed. Live is not allowed.

## 19. Recommended Next Step

Run a longer controlled Paper-only observation window, or focus on the current blockers preventing strict qualification:

- Risk review/watch states on otherwise thesis-backed candidates
- lifecycle current blockers
- stale orderbook/risk decision blockers
- candidate event link gaps

Do not proceed to Shadow or Live.

