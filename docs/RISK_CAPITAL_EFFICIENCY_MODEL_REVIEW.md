# Risk-Capital Efficiency Model Review

## 1. Purpose

Validate whether `RISK_BLOCKED_CAPITAL` is a correct current blocker or caused by a formula, stale-row, sizing, reward, hold-time, liquidity, or policy mismatch.

This review did not enable Paper Simulation, Shadow, Live, Full Monitor Run, or any execution action.

## 2. Current State

Latest runtime truth before review:

- Runtime healthy.
- Source Refresh active.
- Derived signals active.
- Full Mesh and fresh Edge/Risk propagation working.
- Exit and Lifecycle stale blockers fixed.
- Paper Actionability remains `0`.
- Current exact blocker: `RISK_BLOCKED_CAPITAL`.

Controlled 30-minute monitor showed source-backed candidates, but Risk-Capital blocked all observed paper-actionability candidates.

## 3. Formula Location

Primary implementation:

- `app/services/capital_efficiency.py`

Relevant functions:

- `_metrics`: builds input metrics.
- `_score`: computes `capital_efficiency_score`.
- `_recommendation`: maps score and inputs to `CAPITAL_SUPPORT`, `CAPITAL_WATCH`, `CAPITAL_BLOCK`, or other capital recommendations.

Risk consumption:

- `app/services/risk_evidence_mesh.py`
- `RISK_BLOCKED_CAPITAL` is emitted when Risk consumes a candidate capital-efficiency row with `recommendation = CAPITAL_BLOCK`.

Lifecycle/actionability trace:

- `app/services/lifecycle_governance.py`
- `app/control_center/paper_actionability.py`
- `app/control_center/decision_propagation_trace.py`

## 4. Formula Explanation

`reward_per_dollar_hour`:

```text
potential_reward / (capital_locked * max(time_to_resolution_seconds / 3600, MIN_HOURS))
```

Unit:

```text
expected/potential profit per locked dollar per hour
```

The value is not a fair-probability EV. It is potential reward divided by locked capital and holding time, using source-backed payout and exit-hold inputs.

`capital_efficiency_score`:

```text
base = 0.50
if reward_per_dollar_hour >= 0.10: +0.30
elif reward_per_dollar_hour >= 0.01: +0.15
else: -0.10

if liquidity_exit_quality == GOOD: +0.10
elif liquidity_exit_quality in {POOR, EXIT_LIQUIDITY_UNKNOWN}: -0.15

if rules_risk == HIGH or risk_of_reversal == HIGH: -0.20
elif rules_risk == RULES_RISK_UNKNOWN: -0.05

if TIME_TO_RESOLUTION_MISSING: -0.10
clamp to [0, 1]
```

Recommendation:

- missing capital/reward: `CAPITAL_INSUFFICIENT_DATA`
- poor liquidity: `CAPITAL_BLOCK`
- missing time/rules/liquidity: `CAPITAL_WATCH`
- score `>= 0.70`, RPDH present, no high risk: `CAPITAL_SUPPORT`
- score `< 0.30`: `CAPITAL_BLOCK`
- otherwise: `CAPITAL_WATCH`

## 5. Input Trace

Top 20 current `EDGE_SUPPORTED`, `source_backed=true`, `risk_usable=true` candidates all traced to candidate-scoped capital-efficiency rows.

Representative values:

| Field | Value |
| --- | --- |
| market_id | `691547` |
| side | `YES` |
| capital_locked | `100` |
| potential_reward | `170.2702702702702702702702703` or `42.8571428571428571428571429` |
| hold_time_estimate_hours | about `4780.86` |
| reward_per_dollar_hour | about `0.00035615` or `0.00008964` |
| liquidity_exit_quality | `FAIR` |
| rules_risk | `HIGH` |
| risk_of_reversal | `HIGH` |
| missing_inputs_json | `[]` |
| capital_efficiency_score | `0.2000` |
| recommendation | `CAPITAL_BLOCK` |
| Risk result | `RISK_BLOCK / RISK_BLOCKED_CAPITAL` |

Top-100 supported sample summary:

- `CAPITAL_BLOCK`: 74
- `CAPITAL_INSUFFICIENT_DATA`: 3
- `CAPITAL_WATCH`: 6

For latest `PAPER_CANDIDATE` capital rows:

- `CAPITAL_BLOCK`: 83
- RPDH range for blockers: `0.0000896387` to `0.0012868904`
- candidates with RPDH `>= 0.01`: `0`
- high-risk rows: `82`

## 6. Why capital_efficiency_score Is 0.2

For the representative blocker:

```text
base 0.50
low reward_per_dollar_hour (<0.01): -0.10
liquidity FAIR: 0.00
rules_risk HIGH or risk_of_reversal HIGH: -0.20
missing time: 0.00
= 0.20
```

That score is below the model's block threshold of `0.30`, so `CAPITAL_BLOCK` is expected under the current formula.

## 7. Why reward_per_dollar_hour Is Low

The primary driver is long time-to-resolution.

Example:

```text
potential_reward = 170.2702702703
capital_locked = 100
time_to_resolution_seconds = 17,211,102
hold_time_hours = 4,780.86
reward_per_dollar_hour = 170.2702702703 / (100 * 4,780.86)
                       ~= 0.00035615
```

The formula is unit-consistent. It is not dividing by 100 twice and is not mixing percent and decimal units in the observed rows.

## 8. Capital OK vs Risk-Capital Block

These are distinct concepts.

`CAPITAL_OK` means lifecycle has current capital evidence and available balance is not the direct blocker.

`RISK_BLOCKED_CAPITAL` means Risk-Capital policy does not consider locking capital efficient enough given reward, time, liquidity, and risk.

The reviewed rows had available paper capital around `996.819322`, no open exposure, and no missing reward/capital fields. The block is therefore not caused by insufficient account balance.

## 9. Bugs Found

One trace-only bug was found:

- `lifecycle_governance._risk_capital_summary` read `missing_inputs`, but persisted capital-efficiency rows store `missing_inputs_json`.

Effect:

- Missing reward/capital evidence could be under-reported in risk-capital traces.

Non-decision-impacting observation:

- Some Risk rows referenced the prior same-candidate capital-efficiency evaluation even though a newer same-candidate row existed after the latest source cycle.
- The newer rows had the same `CAPITAL_BLOCK`, score, and reason.
- This did not cause the current blocker, but future propagation work should align Risk references to the latest same-cycle capital-efficiency row.

## 10. Fixes Made

Fixed trace specificity:

- `app/services/lifecycle_governance.py`
- `_risk_capital_summary` now reads `missing_inputs` or `missing_inputs_json`.

No formula, threshold, risk, capital, exit, lifecycle, or actionability pass/fail policy was changed.

## 11. Policy Questions

The current behavior is model-valid, but it may be too strict for a controlled Small Paper certification if the policy expects micro-sized observational paper tests.

Questions for human policy decision:

1. Should Small Paper use a lower explicit notional than the current `capital_locked = 100` candidate assumption?
2. Should Phase 10 require full `CAPITAL_SUPPORT`, or is `CAPITAL_WATCH` acceptable for controlled certification only?
3. Should very long time-to-resolution markets be excluded earlier from candidate promotion instead of failing only at Risk-Capital?
4. Should reward-per-dollar-hour use expected value only when fair probability is source-backed, and otherwise produce a more specific blocker?
5. Should high rules/reversal risk be allowed to block even source-backed Edge when Paper Simulation is only observational?

No policy change was implemented.

## 12. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_risk_capital_efficiency_model.py tests/test_reward_per_dollar_hour.py tests/test_risk_capital_actionability_trace.py -q
8 passed in 0.79s
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_risk_capital_resolution.py tests/test_exit_readiness_resolution.py tests/test_final_actionability_phase10_gate.py tests/test_lifecycle_gate_reconciliation.py tests/test_fresh_source_truth_propagation.py tests/test_paper_actionability_contract.py -q
26 passed in 3.04s
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "risk_capital or capital_efficiency or reward_per_dollar or actionability or phase10 or risk or capital"
97 passed, 143 skipped, 1823 deselected in 6.18s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 13. Controlled SYSTEM ON Review Run

Run:

- `POST /system/power/on`
- waited 6 source-refresh cycles
- did not enable Paper Simulation
- did not start Full Monitor Run
- `POST /system/power/off`

Observed:

- source cycles: `70 -> 76`
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED = 0`
- `blocked_by_risk = 100`
- top risk-capital state: `CAPITAL_BLOCK`
- top capital efficiency score: `0.2`
- top RPDH: about `0.00035617`
- runtime cleanup: `SAFE_STOPPED`, `STOPPED`, system power `OFF`, supervisor `STOPPED`

Forbidden artifacts:

| Artifact | Before | After |
| --- | ---: | ---: |
| `paper_intents` | 20 | 20 |
| `paper_orders` | 12 | 12 |
| `paper_fills` | 9 | 9 |
| `paper_positions` | 12 | 12 |
| `paper_position_closes` | 9 | 9 |
| `live_orders` | 0 | 0 |
| `positions` | 0 | 0 |

## 14. Deployment

Code changed, so API was rebuilt and restarted:

```text
docker compose build api
docker compose up -d --no-deps api
```

Post-deploy verification:

- `/healthz`: `status=ok`, `ready=true`
- `/runtime/health`: `SAFE_STOPPED`, `STOPPED`, system power `OFF`
- `/paper-actionability?limit=20`: reachable and fresh

## 15. READY_FOR_PHASE_10

`READY_FOR_PHASE_10 = NO`

Exact reason:

```text
RISK_BLOCKED_CAPITAL remains a valid current blocker under the existing Risk-Capital formula and policy.
```

## 16. RISK_CAPITAL_MODEL_STATE

`RISK_CAPITAL_MODEL_STATE = VALID_CURRENT_BLOCKER`

With note:

```text
Trace specificity bug fixed; no decision-changing calculation bug found.
```

## 17. Safety Result

- Paper Simulation was not activated.
- Full Monitor Run was not started.
- Shadow and Live remained disabled.
- No paper intents, orders, fills, positions, live orders, or shadow orders were created.
- Capital balances were not mutated.
- No thresholds were lowered.
- No fake reward, fair probability, or capital efficiency was introduced.

## 18. Recommended Next Step

Human policy decision is needed only if the intended Phase 10 standard is less strict than current Risk-Capital policy.

Otherwise, continue DATA_ONLY until candidates have better capital efficiency: shorter hold time, higher source-backed reward, lower rules/reversal risk, or better liquidity evidence.
