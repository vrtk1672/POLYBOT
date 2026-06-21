# Final Risk-Capital & Exit Readiness Report

## 1. Purpose

Resolve the last pre-Phase-10 blockers after Full Mesh, Source Refresh, Edge propagation, and Lifecycle stale-window reconciliation were already working.

The target was not to force Paper readiness. The target was to determine whether any `EDGE_SUPPORTED`, `source_backed=true`, `risk_usable=true` candidate can pass Risk-Capital and Exit gates under existing policy.

## 2. Current State Before Resolution

Latest known pre-fix state:

- `EDGE_SUPPORTED = 50`
- `risk_usable = 50`
- `source_backed = 50`
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED = 0`
- `BLOCKED_BY_LIFECYCLE = 0`
- `BLOCKED_BY_RISK = 44`
- `BLOCKED_BY_EXIT = 6`

Representative traces showed `CAPITAL_OK` at the lifecycle capital gate while Risk still emitted `RISK_BLOCKED_CAPITAL`.

## 3. EDGE_SUPPORTED Candidate Summary

The latest source-backed edge surface produced current supported candidates. During the controlled final run:

- `/source-backed-edge?limit=50` returned `EDGE_SUPPORTED = 50`
- `source_backed = 50`
- `risk_usable = 50`
- `source_organs_queried = 500`
- `directional_sources_found = 148`

The supported candidates did not become paper-actionable because Risk-Capital remained blocked.

## 4. Risk-Capital Root Cause

`RISK_BLOCKED_CAPITAL` is generated in the Risk Evidence Mesh from `capital_efficiency_evaluations`.

The blocker is not the same gate as lifecycle `CAPITAL_OK`:

- Lifecycle `CAPITAL_OK` means candidate/cycle capital evidence is present and fresh enough for lifecycle gating.
- Risk-Capital policy evaluates capital efficiency and reward per dollar-hour as a risk policy layer.

Current representative Risk-Capital trace:

- `risk_result = RISK_BLOCK`
- `risk_capital_blocker = RISK_BLOCKED_CAPITAL`
- `risk_capital_policy_state = CAPITAL_BLOCK`
- `capital_gate_state = CAPITAL_BLOCK`
- `classification = CURRENT_REAL_BLOCKER`
- `capital_efficiency_score = 0.2`
- `reward_per_dollar_hour` observed around `0.00009` to `0.00036`
- `required_to_pass = Improve capital efficiency score, reward-per-dollar-hour, liquidity quality, or capital/reward evidence under existing policy.`

This is a valid two-layer policy result, not a stale capital row selection bug.

## 5. Capital Gate vs Risk-Capital Policy

Lifecycle can truthfully show `CAPITAL_OK` while Risk blocks on `RISK_BLOCKED_CAPITAL`.

That means:

- Capital evidence exists.
- Capital balances were not mutated.
- Risk policy still rejects the candidate because the capital efficiency evaluation is below policy requirements.

No thresholds were changed.

## 6. Exit Readiness Root Cause

The standalone exit blockers came from lifecycle/actionability using summary status such as `INSUFFICIENT_DATA` instead of the candidate-specific `exit_plans` row when one existed.

The existing Exit Foundation already produced candidate-specific rows with:

- candidate-specific token/side identity
- orderbook snapshot reference
- spread and liquidity fields
- `paper_exit_ready`
- blockers and missing evidence

The bug was selection and trace visibility, not absence of a safe exit computation path.

## 7. Small-Paper Exit Readiness Result

Lifecycle now prefers the candidate-specific `exit_plans` row and exposes an `exit_readiness_trace`.

Post-fix current traces show:

- Top actionability window has `blocked_by_exit = 0` as the primary actionability blocker.
- Exit remains `EXIT_BLOCKED` only as a dependent current blocker where Risk is already blocked by `RISK_BLOCKED_CAPITAL`.
- Representative spread: `0.07`
- Representative liquidity score: `0.404909`
- Representative exit price: `0.385`
- Representative orderbook snapshot id: present
- `paper_exit_ready = false` while Risk blockers are present

Exit readiness was not faked. It remains dependent on Risk clearing.

## 8. Paper Actionability Result

Post-fix `/paper-actionability?limit=100`:

- `actionable_small_paper = 0`
- `actionable_if_paper_enabled = 0`
- `blocked_by_risk = 100`
- `blocked_by_exit = 0`
- `blocked_by_lifecycle = 0`
- `candidate_actionability_exists = false`

The current exact gate is `RISK_BLOCKED_CAPITAL`.

## 9. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_risk_capital_resolution.py tests/test_exit_readiness_resolution.py tests/test_final_actionability_phase10_gate.py -q
8 passed in 2.12s
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_lifecycle_gate_reconciliation.py tests/test_final_phase10_readiness_closure.py tests/test_actionability_lifecycle_gate_trace.py tests/test_fresh_source_truth_propagation.py tests/test_decision_propagation_trace.py tests/test_edge_stale_handling.py tests/test_paper_actionability_contract.py tests/test_pre_paper_safety_invariants.py -q
29 passed in 3.06s
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "risk_capital or exit_readiness or phase10 or actionability or lifecycle or risk or capital or exit or pre_paper"
134 passed, 239 skipped, 1682 deselected in 7.28s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 10. Deployment Result

Code changed, so the API was rebuilt and restarted:

```text
docker compose build api
docker compose up -d --no-deps api
```

Verification:

- `/healthz`: `status=ok`, `ready=true`
- `/runtime/health`: active server verified

No DB reset or destructive command was used.

## 11. Controlled SYSTEM ON Final Run

Action:

- `POST /system/power/on`
- waited through at least 6 supervisor/source-refresh cycles
- did not enable Paper Simulation
- did not start Full Monitor Run
- `POST /system/power/off`

Runtime cleanup:

- `overall_status = SAFE_STOPPED`
- `runtime_state = STOPPED`
- `system_power = OFF`
- `supervisor_state = STOPPED`
- Paper Simulation remained OFF

## 12. Counts Before / After

Decision/data-only counts:

| Table | Before | After |
| --- | ---: | ---: |
| `source_refresh_cycles` | 29 | 38 |
| `risk_evidence_mesh_evaluations` | 2766 | 3050 |
| `lifecycle_governance_decisions` | 12064 | 12348 |
| `capital_efficiency_evaluations` | 4505 | 4609 |
| `exit_plans` | 20724 | 20750 |
| `orderbook_snapshots` | 54343 | 54562 |
| `brain_outputs` | 37897 | 39022 |
| `coordinator_decisions` | 24329 | 24578 |

Forbidden artifact counts:

| Artifact | Before | After |
| --- | ---: | ---: |
| `paper_intents` | 20 | 20 |
| `paper_orders` | 12 | 12 |
| `paper_fills` | 9 | 9 |
| `paper_positions` | 12 | 12 |
| `paper_position_closes` | 9 | 9 |
| `live_orders` | 0 | 0 |
| `positions` | 0 | 0 |

No forbidden artifact count increased.

## 13. RISK_CAPITAL_RESOLUTION_STATE

`BLOCKED_CURRENT`

Risk-Capital is now explained with source records and `required_to_pass`. The block is current and policy-backed.

## 14. EXIT_READINESS_STATE

`BUG_FIXED`

The stale/summary exit selection path was corrected. Current top-window actionability no longer reports standalone `BLOCKED_BY_EXIT`; exit remains blocked only as a dependent current blocker while Risk-Capital is blocked.

## 15. READY_FOR_PHASE_10

`READY_FOR_PHASE_10 = NO`

Exact current blocker:

`RISK_BLOCKED_CAPITAL`

Current required condition:

Improve capital efficiency score, reward-per-dollar-hour, liquidity quality, or capital/reward evidence under existing Risk-Capital policy.

## 16. Safety Result

- No Paper Simulation activation.
- No Full Monitor Run.
- No live/shadow activation.
- No paper intents, paper orders, paper fills, paper positions, live orders, or positions created.
- No capital balances mutated.
- Risk/Capital/Exit/Lifecycle thresholds were not loosened.
- Exit readiness was not faked.

## 17. Safe Next Step

Do not start Phase 10 yet.

Next work should focus on the capital efficiency policy inputs for the supported candidates: determine whether `CAPITAL_BLOCK` is expected for the current reward/time/liquidity profile or whether upstream reward-per-dollar-hour/liquidity quality evidence is under-scored.
