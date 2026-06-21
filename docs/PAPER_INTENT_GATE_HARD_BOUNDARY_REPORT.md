# Paper Intent Gate Hard Boundary Report

## 1. Purpose

Fix the Phase 10 RED finding where a `paper_intents` row was created while Paper Simulation was OFF.

Hard boundary:

- DATA_ONLY may write truth/explanation/audit rows.
- `paper_intents` may be written only after explicit Paper Simulation ON.
- Paper OFF may not create paper intents, orders, fills, or positions.

## 2. Phase 10 RED Finding

During Phase 10 Controlled Paper Certification:

- Paper Simulation was not activated.
- Pre-check had zero current `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` candidates.
- One new `paper_intents` row was created by `paper_intent_gate`.
- The row was paper-only and non-executable, but it was still a Paper artifact.

New row from the RED run:

- `paper_intent_eligibility_exit_risk_thesis_coord_0ad21404aecd4ed0bfde6c80fe905789`
- created_at: `2026-06-16T09:06:00Z`
- `paper_only=true`
- `live=false`
- `execution_allowed=false`
- `order_intent_created=false`

## 3. Root Cause

`PaperIntentGateService.build_intents()` checked SYSTEM ON/runtime work but did not enforce the explicit Paper Simulation ON flag before inserting into `paper_intents`.

The insert path was:

```text
Runtime / recovery caller
-> PaperIntentGateService.build_intents(write_intents=True)
-> PaperIntentRepository.upsert_paper_intent()
-> paper_intents
```

This path is a real canonical paper intent path, not just an explanation path.

## 4. Files Inspected

- `app/services/paper_intents.py`
- `app/repositories/paper_intent_repository.py`
- `app/control_center/runtime_supervisor.py`
- `app/control_center/paper_simulation.py`
- `app/control_center/action_service.py`
- `app/control_center/paper_actionability.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/pre_paper_safety.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/services/paper_execution.py`
- `app/services/paper_eligibility.py`
- `app/services/risk_evidence_mesh.py`
- `app/services/trade_thesis_engine.py`
- `app/services/lifecycle_governance.py`
- related paper intent/readiness/actionability tests

## 5. Files Changed

- `app/services/paper_intents.py`
- `tests/test_paper_intent_gate_hard_boundary.py`
- `tests/test_no_paper_artifacts_when_paper_off.py`
- `tests/test_phase10_precheck_no_intents.py`

## 6. Guard Implementation

Added central guard in `PaperIntentGateService.build_intents()`:

- If `write_intents=True` and Paper Simulation is OFF, the service does not call `upsert_paper_intent`.
- It records no-trade explanation rows instead when requested.
- It returns:
  - `status=BLOCKED`
  - `error_summary=PAPER_SIMULATION_OFF_NO_INTENT_CREATED`
  - `paper_intents_created=0`
  - `paper_intents_updated=0`

The guard also checks `StateGovernor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION)`.

## 7. DATA_ONLY Replacement Behavior

When Paper Simulation is OFF, candidates are converted to no-trade/explanation records with blockers:

- `PAPER_SIMULATION_OFF`
- `PAPER_SIMULATION_OFF_NO_INTENT_CREATED`

No `paper_intents` row is created. Historical `paper_intents` rows are not deleted.

## 8. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_intent_gate_hard_boundary.py tests/test_no_paper_artifacts_when_paper_off.py tests/test_phase10_precheck_no_intents.py -q
6 skipped in 1.97s
```

The focused tests are Postgres-backed and skipped under the local pytest DB fixture precondition.

Related:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "paper_intent or paper_readiness or paper_actionability or paper_certification or paper_execution or paper_ledger or live_safety"
27 passed, 60 skipped, 1991 deselected in 5.38s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 9. Deployment Result

```text
docker compose build api
docker compose up -d --no-deps api
```

Verification:

- `/healthz`: `ok`, `ready=true`
- `/runtime/health`: reachable
- Paper Simulation: `DISABLED`
- Live execution: disabled

## 10. Controlled DATA_ONLY Verification

Production verification used SYSTEM ON only with Paper Simulation OFF.

Before:

- `paper_intents=21`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`
- `shadow_orders=0`
- `source_refresh_cycles=101`
- `trade_thesis_evaluations=500`

Action:

- `POST /dashboard/api/v2/control/actions/system-on`
- waited through four verification ticks and multiple source refresh cycles
- did not enable Paper Simulation
- did not start Full Monitor Run

During run:

- source refresh remained `ACTIVE`
- `source_refresh_cycles=101 -> 104`
- `trade_thesis_evaluations=500 -> 560`
- Paper Simulation remained OFF
- `paper_intents` stayed `21`
- paper orders/fills/positions stayed unchanged
- live/shadow artifacts stayed unchanged

Direct central guard verification while SYSTEM ON and Paper OFF:

```text
status=BLOCKED
error_summary=PAPER_SIMULATION_OFF_NO_INTENT_CREATED
paper_intents_created=0
paper_intents_updated=0
paper_intents_before=21
paper_intents_after=21
```

Cleanup:

- `POST /dashboard/api/v2/control/actions/system-off`
- final `/runtime/health`: `SAFE_STOPPED`
- system power: `OFF`
- supervisor: `STOPPED`
- Paper Simulation: `DISABLED`

## 11. Before / After Artifact Counts

| Artifact | Before | After |
|---|---:|---:|
| `paper_intents` | 21 | 21 |
| `paper_orders` | 12 | 12 |
| `paper_fills` | 9 | 9 |
| `paper_positions` | 12 | 12 |
| `paper_position_closes` | 9 | 9 |
| `live_orders` | 0 | 0 |
| `positions` | 0 | 0 |
| `shadow_orders` | 0 | 0 |

## 12. Can Retry Phase 10

YES, the RED safety boundary is fixed.

Do not proceed to extended Paper Runtime yet. Retry only the bounded Phase 10 Controlled Paper Certification.

## 13. Safety Result

Status: GREEN.

- Paper Simulation remained OFF during production verification.
- No paper intents were created while Paper OFF.
- No paper orders/fills/positions were created while Paper OFF.
- No live/shadow artifacts were created.
- Historical paper intents were not deleted.
- DATA_ONLY explanations still work through `no_trade_log`.
- Paper ON canonical path remains test-covered.
- Risk, Exit, and Lifecycle rules were not loosened.
- No destructive DB action was performed.
