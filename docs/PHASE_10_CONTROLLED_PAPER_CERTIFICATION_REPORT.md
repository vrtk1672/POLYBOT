# Phase 10 Controlled Paper Certification Report

## 1. Purpose

Run a bounded Phase 10 Paper Certification attempt after the Paper Intent hard-boundary fix.

Certification rules:

- Paper Simulation may be enabled only after a fresh pre-check passes.
- Shadow and Live must remain disabled.
- Full Monitor Run must not start.
- Paper artifacts may only be created after explicit Paper Simulation ON.
- If no fully qualified candidate exists, Paper remains OFF.

## 2. Pre-Check Readiness

Pre-restart state:

- `/healthz`: `ok`, `ready=true`
- `/runtime/health`: `SAFE_STOPPED`
- system power: `OFF`
- runtime: `STOPPED`
- Paper Simulation: `DISABLED`
- Live execution: `false`
- Shadow artifacts: zero
- active non-excluded paper positions: `0`

Last-known actionability while stopped showed `32` rows labeled `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`, but runtime truth was stopped and stale. Certification therefore required SYSTEM ON and fresh cycle confirmation before Paper activation.

## 3. Baseline Counts

Baseline captured at `2026-06-16T11:28:01.959078+00:00`.

| Table | Count |
|---|---:|
| `paper_intents` | 21 |
| `paper_orders` | 12 |
| `paper_fills` | 9 |
| `paper_positions` | 12 |
| `paper_position_closes` | 9 |
| `paper_trade_ledger` | 18 |
| `paper_daily_pnl` | 5 |
| `paper_capital_ledger` | 38 |
| `live_orders` | 0 |
| `positions` | 0 |
| `shadow_orders` | 0 |
| `real_orders` | not present |
| `live_positions` | not present |
| `source_refresh_cycles` | 104 |
| `risk_evidence_mesh_evaluations` | 5833 |
| `trade_thesis_evaluations` | 560 |
| `capital_efficiency_evaluations` | 6072 |
| `lifecycle_governance_decisions` | 14571 |
| `exit_plans` | 20967 |
| `brain_outputs` | 47992 |
| `coordinator_decisions` | 26500 |

## 4. Restart Action

Action:

```text
docker compose restart api
```

Result:

- API restarted safely.
- No DB reset.
- No volume reset.
- No destructive command.
- `/healthz`: `ok`, `ready=true`
- `/runtime/health`: `SAFE_STOPPED`
- Paper Simulation: `DISABLED`
- Live execution: `false`

## 5. SYSTEM ON Result

Action:

```text
POST /dashboard/api/v2/control/actions/system-on
```

Result:

- status: `ACCEPTED`
- mode: `DATA_ONLY`
- system power: `ON`
- runtime: `ALIVE`
- supervisor: `RUNNING`
- Paper Simulation: `DISABLED`
- paper execution enabled: `false`
- live execution enabled: `false`
- shadow/live allowed: `false`

The system ran through multiple DATA_ONLY supervisor/source-refresh cycles.

## 6. Certification Runtime Timeline

SYSTEM ON window:

- started: `2026-06-16T11:28:54Z`
- cleanup requested: `2026-06-16T11:36:10Z`
- duration: about `7m16s`

Fresh-cycle observations:

| Tick | Runtime | Paper | Source Refresh Cycles | Thesis Evals | Actionable Count | Paper Intents |
|---:|---|---|---:|---:|---:|---:|
| 1 | `ALIVE` | `DISABLED` | 105 | 580 | 32 | 21 |
| 2 | `ALIVE` | `DISABLED` | 106 | 600 | 32 | 21 |
| 3 | `ALIVE` | `DISABLED` | 107 | 620 | 32 | 21 |
| 4 | `ALIVE` | `DISABLED` | 108 | 640 | 15 | 21 |

The Paper Intent hard boundary held during DATA_ONLY:

- `paper_intents`: `21 -> 21`
- `paper_orders`: `12 -> 12`
- `paper_fills`: `9 -> 9`
- `paper_positions`: `12 -> 12`

## 7. Candidate Selected

No candidate was selected for Paper Simulation.

Reason:

The strict certification pre-check requires a current candidate with:

- `EDGE_SUPPORTED`
- `source_backed=true`
- `risk_usable=true`
- valid Trade Thesis
- valid Exit Intent
- dynamic hold-time trace
- Risk OK / existing gate approval
- Exit READY
- Capital OK
- Lifecycle allowed
- candidate-scoped event linkage

The current actionability rows were labeled `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`, but the rows that would be selected for Paper had:

- `risk_gate_state=RISK_REVIEW`
- `candidate_event_scope=NOT_ACTIONABLE`
- `candidate_event_link_state=TOKEN_SIDE_MISMATCH`
- missing `trade_thesis_type` / `exit_intent` / dynamic hold-time fields in the actionability row

The trade-thesis endpoint did contain a thesis for one candidate, but the actionability-to-thesis trace was not fully reconciled for Paper activation.

Example supporting thesis found separately:

- candidate_id: `eligibility_exit_risk_thesis_coord_23aa4307ab254193a250b99e5adb32db`
- thesis_id: `trade_thesis_53c81afd948552fe88b102b8519243e2`
- thesis type: `MISPRICING_REVERSION`
- exit intent: `PRICE_TARGET_EXIT`
- status: `THESIS_SUPPORTED`
- expected hold time: `48.0` hours
- target exit price: `0.35`
- source_refresh_cycle_id: `source_refresh_46f65621be6d4237ab16be60bbe02559`

But the actionability row for that candidate still showed:

- `candidate_event_scope=NOT_ACTIONABLE`
- `candidate_event_link_state=TOKEN_SIDE_MISMATCH`
- `risk_gate_state=RISK_REVIEW`

## 8. Paper Simulation ON Result

Paper Simulation was not activated.

This was intentional. The pre-check failed before Paper ON.

No canonical Paper Simulation artifact chain was attempted.

## 9. Trade Thesis Evidence

Trade thesis production was active:

- `trade_thesis_evaluations`: `560 -> 740`

The trade-thesis endpoint contained valid supported theses, including the example above. However, selected actionability rows did not expose a complete thesis/dynamic hold-time trace, so the Paper activation boundary stayed closed.

## 10. Dynamic Hold-Time Evidence

Dynamic hold-time evidence exists in trade-thesis rows, for example:

- `expected_hold_time_hours=48.0`
- `trade_thesis_type=MISPRICING_REVERSION`
- `exit_intent=PRICE_TARGET_EXIT`

The actionability row did not carry those fields for the selected candidate. Certification therefore treated dynamic hold-time trace as incomplete for Paper ON.

## 11. Risk / Exit / Lifecycle Evidence

Current selected actionability row evidence:

- Edge: `EDGE_SUPPORTED`
- `source_backed=true`
- `risk_usable=true`
- Risk-Capital classification: `PASSED`
- Capital: `CAPITAL_OK`
- Exit: `EXIT_READY`
- Same-Market Guard: `CAN_AUTHORIZE`
- Lifecycle: allowed for paper intent
- Operational blocker: Paper OFF

Blocking pre-check details:

- `risk_gate_state=RISK_REVIEW`
- `candidate_event_scope=NOT_ACTIONABLE`
- `candidate_event_link_state=TOKEN_SIDE_MISMATCH`
- actionability-to-thesis fields missing

Because this is first Paper activation, those inconsistencies were treated as hard pre-check blockers.

## 12. Paper Intent Details

No new paper intents were created.

- `paper_intents`: `21 -> 21`

This confirms the hard-boundary fix held during the certification retry.

## 13. Paper Order Details

No new paper orders were created.

- `paper_orders`: `12 -> 12`

## 14. Paper Fill Details

No new paper fills were created.

- `paper_fills`: `9 -> 9`

## 15. Paper Position Details

No new paper positions were created.

- `paper_positions`: `12 -> 12`
- active non-excluded paper positions after cleanup: `0`

## 16. Ledger / PnL Details

No new ledger or PnL rows were created.

- `paper_trade_ledger`: `18 -> 18`
- `paper_daily_pnl`: `5 -> 5`
- `paper_capital_ledger`: `38 -> 38`

## 17. Forbidden Artifact Counts

Forbidden artifacts remained zero:

| Artifact | Before | After |
|---|---:|---:|
| `live_orders` | 0 | 0 |
| `positions` | 0 | 0 |
| `shadow_orders` | 0 | 0 |
| `real_orders` | not present | not present |
| `live_positions` | not present | not present |

## 18. Cleanup Result

Cleanup actions:

```text
POST /dashboard/api/v2/control/actions/disable-paper-simulation
POST /dashboard/api/v2/control/actions/system-off
```

Final state at `2026-06-16T11:36:44.330342+00:00`:

- `/healthz`: `ok`, `ready=true`
- `/runtime/health`: `SAFE_STOPPED`
- runtime: `STOPPED`
- system power: `OFF`
- supervisor: `STOPPED`
- Paper Simulation: `DISABLED`
- paper execution enabled: `false`
- live execution enabled: `false`
- Full Monitor Run: `DIAGNOSTIC_IDLE`

## 19. Tests Run

Paper selector:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "paper and not live"
98 passed, 178 skipped, 1802 deselected in 6.33s
```

Paper readiness/execution selector:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "paper_actionability or paper_readiness or paper_certification or paper_execution or paper_ledger or live_safety"
22 passed, 40 skipped, 2016 deselected in 5.77s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 20. Final Certification Status

Status: `YELLOW`.

Controlled Paper Certification passed: `NO`.

Paper Simulation was not activated because the strict pre-check found no fully qualified current candidate. The system stayed safe and produced no new Paper/Live/Shadow artifacts.

## 21. Recommended Next Step

Fix the actionability/thesis/event-scope reconciliation before retrying Phase 10:

1. Ensure `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` rows carry the matching `thesis_id`, `trade_thesis_type`, `exit_intent`, and dynamic hold-time fields.
2. Do not mark a row Paper-actionable if `candidate_event_scope=NOT_ACTIONABLE` or `candidate_event_link_state=TOKEN_SIDE_MISMATCH`.
3. Clarify whether `RISK_REVIEW` is allowed for first Paper certification. If not, require `RISK_OK` or an explicit Paper-certification-approved risk state.
4. Retry Phase 10 only after the selected candidate has a fully reconciled Paper activation trace.

## 22. Safety Result

- Active server verified: YES
- SYSTEM ON used correctly: YES
- Paper Simulation activated only after pre-check: YES, because it was not activated
- Paper Simulation remained Paper only: YES
- Live remained disabled: YES
- Shadow remained disabled: YES
- Full Monitor Run was not started: YES
- No live orders created: YES
- No real orders created: YES
- No shadow orders created: YES
- Paper artifacts stayed within certification limits: YES, no new artifacts
- Every new paper intent has candidate/actionability linkage: N/A, no new intent
- Every new paper order has intent linkage: N/A, no new order
- Every new paper fill has order linkage: N/A, no new fill
- Every new paper position has fill linkage: N/A, no new position
- No orphan paper rows created: YES
- Capital ledger remained consistent: YES, unchanged
- PnL rows link to positions: YES for existing rows; no new rows
- Duplicate exposure guard held: YES, no open non-excluded paper positions
- Open position truth correct: YES, active count `0`
- Paper Simulation OFF cleanup completed: YES
- SYSTEM OFF cleanup completed: YES
- No DB reset: YES
- No volume reset: YES
- No destructive DB action: YES
- No secrets printed: YES
