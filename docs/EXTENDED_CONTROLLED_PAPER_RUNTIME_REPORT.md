# Extended Controlled Paper Runtime Report

## 1. Purpose

Run an extended Paper Simulation-only runtime with strict guardrails, monitoring, and artifact validation.

The goal was to let POLYBOT operate naturally long enough to create a paper trade chain only if a strict Paper Actionability candidate appeared:

`Candidate -> Trade Thesis -> Strict Paper Actionability -> Paper Intent -> Paper Order -> Paper Fill -> Paper Position -> Ledger/PnL -> Exit Monitoring`

## 2. Baseline Counts

Baseline captured at `2026-06-16T20:36:09Z`.

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
| source_refresh_cycles | 139 |
| trade_thesis_evaluations | 1260 |
| risk_evidence_mesh_evaluations | 7723 |
| lifecycle_governance_decisions | 15761 |
| capital_efficiency_evaluations | 7262 |
| exit_plans | 21061 |
| brain_outputs | 52242 |
| coordinator_decisions | 27406 |
| orderbook_snapshots | 57160 |
| orderbook_signals | 2775 |
| market_technical_signals | 2775 |
| open_paper_positions | 0 |

## 3. Restart Result

No restart was required. The API had already been rebuilt and recreated in the previous controlled Paper runtime after the strict Paper intent guard was added.

Pre-run verification:

- `/healthz`: ok
- `/runtime/health`: reachable
- system power: `OFF`
- Paper Simulation: `DISABLED`
- Live execution: disabled
- Shadow: disabled

## 4. SYSTEM ON Result

SYSTEM ON accepted at `2026-06-16T20:36:09Z`.

The runtime was allowed to complete initial DATA_ONLY cycles before Paper Simulation was enabled.

Pre-Paper actionability after initial cycles still showed no strict candidate:

- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`
- strict Paper Actionability blockers remained current

## 5. Paper Simulation ON Result

Paper Simulation was enabled through the canonical Control Center endpoint at `2026-06-16T20:37:55Z`.

Immediate checks:

- Paper Simulation: enabled
- Paper-only mode: true
- live execution: false
- Shadow: disabled
- forbidden counts unchanged
- strict Paper intent guard active

## 6. Runtime Timeline

Runtime log:

`docs/run_logs/EXTENDED_CONTROLLED_PAPER_RUNTIME_20260616T203500Z.jsonl`

Window:

- first monitor tick: `2026-06-16T20:38:07Z`
- final monitor tick: `2026-06-16T21:41:33Z`
- 91 monitor ticks
- duration: about 63 minutes 26 seconds
- stop reason: normal completion, no safety stop

This was a bounded extended run inside the requested 4-hour maximum.

## 7. 30-Minute Summaries

Tick 30, `2026-06-16T20:59:00Z`:

- strict actionable: 0
- paper intents/orders/fills/positions delta: 0
- open paper positions: 0
- top blockers: `MISSING_CANDIDATE_EVENT_LINK`, `BLOCKED_BY_LIFECYCLE_CURRENT`, `NOT_ACTIONABLE_EVENT_SCOPE`
- safety status: OK

Tick 60, `2026-06-16T21:19:59Z`:

- strict actionable: 0
- paper intents/orders/fills/positions delta: 0
- open paper positions: 0
- top blockers: `BLOCKED_BY_LIFECYCLE_CURRENT`, `MISSING_CANDIDATE_EVENT_LINK`, `NOT_ACTIONABLE_EVENT_SCOPE`
- safety status: OK

Final tick 90, `2026-06-16T21:41:33Z`:

- strict actionable: 0
- paper intents/orders/fills/positions delta: 0
- open paper positions: 0
- top blockers: `BLOCKED_BY_LIFECYCLE_CURRENT`, `MISSING_CANDIDATE_EVENT_LINK`
- safety status: OK

## 8. Actionability Timeline

First tick:

- items checked: 100
- candidate-scoped bundles: 21
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`
- blocked by lifecycle: 39
- blocked by risk: 43
- blocked by exit: 18

Final tick:

- items checked: 100
- candidate-scoped bundles: 27
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`
- all 100 displayed candidates: `BLOCKED_BY_LIFECYCLE`
- top blockers: `BLOCKED_BY_LIFECYCLE_CURRENT`, `MISSING_CANDIDATE_EVENT_LINK`

No strict actionable candidate appeared.

## 9. Paper Artifact Timeline

Trade-chain artifacts did not change:

| Artifact | Delta |
|---|---:|
| paper_intents | 0 |
| paper_orders | 0 |
| paper_fills | 0 |
| paper_positions | 0 |
| paper_position_closes | 0 |
| paper_trade_ledger | 0 |
| paper_capital_ledger | 0 |

`paper_daily_pnl` increased by 1 with a zero-valued daily aggregate for `2026-06-16`:

- realized PnL: 0
- unrealized PnL: 0
- net PnL: 0
- open positions: 0
- closed trades: 0

This is a Paper PnL truth aggregate, not an intent/order/fill/position trade artifact.

## 10. Best Candidates Seen

Best repeated candidates were source-backed and thesis-backed but still not paper-qualified.

Representative final candidate:

- candidate_id: `eligibility_exit_risk_thesis_coord_73e4d1e656b44f2986c7afbf4743f5e8`
- market_id: `691547`
- side: `YES`
- token_id: `34626184950254225208692030156208941308358060420950772251072421141618169142241`
- actionability: `BLOCKED_BY_LIFECYCLE`
- edge_state: `EDGE_SUPPORTED`
- source_backed: true
- risk_usable: true
- trade_thesis_type: `MISPRICING_REVERSION`
- exit_intent: `PRICE_TARGET_EXIT`
- expected_hold_time_hours: `48`
- risk_gate_state: `RISK_REVIEW`
- exit_gate_state: `EXIT_READY`
- capital_gate_state: `CAPITAL_OK`
- risk_capital_policy_state: `CAPITAL_WATCH`

## 11. Trade Thesis Evidence

Trade Thesis ran continuously:

- `trade_thesis_evaluations`: `1260 -> 2440`
- delta: `+1180`

Top candidates had supported-style thesis fields such as:

- thesis type: `MISPRICING_REVERSION`
- exit intent: `PRICE_TARGET_EXIT`
- expected hold time: `48h`

These were not sufficient for Paper because strict Risk/Lifecycle/current-link gates did not pass.

## 12. Dynamic Hold-Time Evidence

Dynamic hold-time evidence was present on top candidates:

- expected hold time: `48h`
- thesis: `MISPRICING_REVERSION`
- exit intent: `PRICE_TARGET_EXIT`

Dynamic hold-time improved candidate context but did not override Risk/Lifecycle requirements.

## 13. Risk / Exit / Lifecycle Evidence

During the run:

- risk evidence rows: `7723 -> 10814`, delta `+3051`
- lifecycle decisions: `15761 -> 17672`, delta `+1891`
- capital efficiency evaluations: `7262 -> 9173`, delta `+1891`
- exit plans: `21061 -> 21179`, delta `+118`

Final observed candidate state:

- Risk: `RISK_REVIEW`
- Exit: `EXIT_READY`
- Capital: `CAPITAL_OK`
- Risk-Capital policy: `CAPITAL_WATCH`
- Lifecycle/Actionability: `BLOCKED_BY_LIFECYCLE`

## 14. Intent / Order / Fill / Position Chain

No paper trade chain was created.

Reason:

- no row reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`
- therefore the strict Paper intent gate created no `paper_intents`
- no order/fill/position could follow

Artifact integrity check:

- new intents: 0
- new orders: 0
- new fills: 0
- new positions: 0
- violations: none

## 15. Ledger / PnL Truth

No trade ledger or capital ledger rows were created.

One `paper_daily_pnl` aggregate row was created for the run date with all zero values and zero open/closed trades. This did not represent a trade, position, or capital mutation.

## 16. Forbidden Artifact Counts

Forbidden artifacts stayed unchanged:

| Artifact | Baseline | Final | Delta |
|---|---:|---:|---:|
| live_orders | 0 | 0 | 0 |
| positions | 0 | 0 | 0 |
| shadow_orders | 0 | 0 | 0 |
| real_orders | not present | not present | n/a |
| live_positions | not present | not present | n/a |

## 17. Cleanup Result

Cleanup completed at `2026-06-16T21:41:37Z`.

- Paper Simulation OFF: accepted
- SYSTEM OFF: accepted
- runtime life state: `STOPPED`
- supervisor state: `STOPPED`
- system power: `OFF`
- Paper Simulation: `DISABLED`
- live execution: false

## 18. Status

`YELLOW`

The extended Paper runtime was safe and completed normally, but no strict actionable candidate appeared and no full paper trade chain was produced. This is a safe no-trade/idle result, not a full Paper execution certification.

## 19. Is Extended Paper Runtime Passed

YES for safety and controlled Paper-only operation.

NO for full trade-chain validation, because no candidate qualified and no intent/order/fill/position chain was created.

## 20. Shadow Allowed

NO.

## 21. Live Allowed

NO.

## 22. Recommended Next Step

Continue controlled Paper-only runtime only if the operator wants more observation time.

Implementation focus should be on the current non-actionable blockers:

- `MISSING_CANDIDATE_EVENT_LINK`
- `BLOCKED_BY_LIFECYCLE_CURRENT`
- Risk states remaining `RISK_REVIEW`
- Risk-Capital policy remaining `CAPITAL_WATCH`

Do not advance to Shadow or Live.

