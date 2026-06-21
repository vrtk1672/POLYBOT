# First 30 Minute System Monitor Report

## 1. Purpose

Run a controlled DATA_ONLY restart and observe POLYBOT for the first 30 minutes after SYSTEM ON.

The run was operational only. Paper Simulation, Full Monitor Run, Shadow, and Live were not activated.

## 2. Restart Action

Baseline was captured before restart, then the API container was safely restarted:

```text
docker compose restart api
```

No DB reset, volume reset, row deletion, or destructive command was used.

Post-restart verification:

- `/healthz`: `status=ok`, `ready=true`
- `/runtime/health`: reachable
- runtime before SYSTEM ON: stopped/safe
- Paper Simulation: OFF

Structured runtime log:

```text
docs/run_logs/FIRST_30_MIN_SYSTEM_MONITOR_20260616_023505.jsonl
```

## 3. Baseline State

Forbidden artifact baseline:

| Table | Baseline |
| --- | ---: |
| `paper_intents` | 20 |
| `paper_orders` | 12 |
| `paper_fills` | 9 |
| `paper_positions` | 12 |
| `paper_position_closes` | 9 |
| `live_orders` | 0 |
| `positions` | 0 |

Selected data/runtime baseline:

| Table | Baseline |
| --- | ---: |
| `source_refresh_cycles` | 38 |
| `orderbook_snapshots` | 54562 |
| `orderbook_signals` | 760 |
| `market_technical_signals` | 760 |
| `liquidity_signals` | 760 |
| `time_signals` | 760 |
| `fee_reward_signals` | 760 |
| `payout_odds_evaluations` | 2183 |
| `news_impact_scores` | 505 |
| `news_market_links` | 505 |
| `neuron_signals` | 25551 |
| `neuron_signal_bindings` | 25493 |
| `signal_quality_evaluations` | 22401 |
| `risk_evidence_mesh_evaluations` | 3050 |
| `lifecycle_governance_decisions` | 12348 |
| `brain_outputs` | 39022 |
| `coordinator_decisions` | 24578 |
| `exit_plans` | 20750 |
| `capital_efficiency_evaluations` | 4609 |

## 4. SYSTEM ON Result

SYSTEM ON was posted with DATA_ONLY monitoring reason.

Initial checks showed:

- runtime state: RUNNING
- runtime life state: ALIVE
- supervisor state: RUNNING
- mode: DATA_ONLY
- Paper Simulation: OFF
- Shadow: OFF
- Live: OFF

## 5. Minute-by-Minute Summary

The monitor captured minute `0` through minute `30`.

Key trend:

| Minute | Source Cycles | EDGE_SUPPORTED | source_backed | risk_usable | actionable if Paper enabled | blocked by Risk |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 38 | 91 | 91 | 91 | 0 | 100 |
| 5 | 44 | 100 | 100 | 100 | 0 | 100 |
| 10 | 49 | 100 | 100 | 100 | 0 | 100 |
| 15 | 54 | 100 | 100 | 100 | 0 | 100 |
| 20 | 59 | 100 | 100 | 100 | 0 | 100 |
| 25 | 64 | 100 | 100 | 100 | 0 | 100 |
| 30 | 69 | 100 | 100 | 100 | 0 | 100 |

Some one-minute runtime-health reads reported transient `STALE` active-cycle state while the supervisor remained `RUNNING` and source cycles advanced. The final runtime cleanup returned `SAFE_STOPPED`.

## 6. Five-Minute Deep Snapshots

Top candidate snapshots:

| Minute | Edge | Source Backed | Risk Usable | Risk | Capital Score | Reward/$/hr | Exit | Actionability |
| ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |
| 0 | `EDGE_STALE` | false | false | `RISK_BLOCK` | 0.2 | 0.00035609 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |
| 5 | `DERIVED_SIGNALS_WATCH_ONLY` | false | false | `RISK_BLOCK` | 0.2 | 0.00008963 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |
| 10 | `EDGE_SUPPORTED` | true | true | `RISK_BLOCK` | 0.2 | 0.00035612 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |
| 15 | `EDGE_SUPPORTED` | true | true | `RISK_BLOCK` | 0.2 | 0.00035613 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |
| 20 | `EDGE_SUPPORTED` | true | true | `RISK_BLOCK` | 0.2 | 0.00035614 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |
| 25 | `EDGE_SUPPORTED` | true | true | `RISK_BLOCK` | 0.2 | 0.00035614 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |
| 30 | `EDGE_SUPPORTED` | true | true | `RISK_BLOCK` | 0.2 | 0.00035615 | `EXIT_BLOCKED` | `BLOCKED_BY_RISK` |

Interpretation:

The system found source-backed edge after warm-up, but the Risk-Capital policy did not allow those candidates. Exit remained blocked as a dependent gate because current Risk was blocked.

## 7. Source Refresh Behavior

Source Refresh stayed ACTIVE.

Source refresh cycles:

- baseline: 38
- final: 70
- delta: +32

Missing config remained visible:

- `ai_reasoner`

No failed sources were reported in the final summary.

## 8. Mesh Behavior

Full Mesh surfaces remained reachable and were included in the deep snapshots.

The final decision propagation trace was cycle-consistent:

- `propagation_state = ACTIVE`
- `propagation_breakpoint = null`
- `cycle_consistent = 5 / 5`

## 9. Edge Behavior

Edge improved during the run.

At minute 0 and minute 5, the top candidate was stale or watch-only. From minute 10 onward, top candidates were consistently:

- `EDGE_SUPPORTED`
- `source_backed = true`
- `risk_usable = true`

Final pre-cleanup edge snapshot:

- `EDGE_SUPPORTED = 80`
- `source_backed = 80`
- `risk_usable = 80`
- `EDGE_STALE = 0`

The larger minute summaries repeatedly showed up to `100` supported/source-backed/risk-usable candidates in the observed actionability window.

## 10. Risk Behavior

Risk continued to block.

Final actionability window:

- `blocked_by_risk = 100`
- top state: `BLOCKED_BY_RISK`
- top Risk-Capital state: `CAPITAL_BLOCK`
- exact blocker stack included:
  - `RISK_BLOCKED`
  - `RISK_BLOCKED_CAPITAL`

Representative capital efficiency:

- `capital_efficiency_score = 0.2`
- `reward_per_dollar_hour` around `0.000356`

## 11. Exit Behavior

Exit did not become the primary actionability blocker.

Final actionability window:

- `blocked_by_exit = 0`

Candidate traces still show `EXIT_BLOCKED` as a dependent lifecycle gate because Risk is blocked. This is expected under the current exit plan behavior: do not mark exit ready while Risk-Capital blocks the candidate.

## 12. Lifecycle Behavior

Lifecycle stale-window blockers did not reappear as the primary blocker.

Final actionability window:

- `blocked_by_lifecycle = 0`

Decision propagation trace:

- cycle consistent
- no propagation breakpoint
- exact gate preventing Phase 10: `RISK_BLOCKED_CAPITAL`

## 13. Paper Actionability Behavior

No candidate reached small-paper actionability.

Final actionability window:

- `ACTIONABLE_SMALL_PAPER = 0`
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED = 0`
- `blocked_by_risk = 100`
- `blocked_by_exit = 0`
- `blocked_by_lifecycle = 0`

## 14. Did Any Trades Happen?

No real trades happened.

## 15. Did Any Paper Trades Happen?

No paper trades happened. Paper Simulation remained OFF.

## 16. Did Any Candidate Become Actionable For Phase 10?

No.

## 17. Final Blocker

Final exact blocker:

```text
RISK_BLOCKED_CAPITAL
```

Current reason:

```text
CAPITAL_BLOCK from Risk-Capital policy, with capital_efficiency_score = 0.2 and weak reward_per_dollar_hour.
```

## 18. Progress During The 30 Minutes

The system improved operationally:

- source refresh cycles increased by 32
- orderbook snapshots increased by 845
- orderbook signals increased by 640
- market technical signals increased by 640
- liquidity/time/fee-reward signals increased by 640 each
- news impact and market links increased by 78 each
- payout odds evaluations increased by 80
- risk evaluations increased by 1079
- lifecycle decisions increased by 1079
- Edge became consistently source-backed/risk-usable after warm-up

The system did not improve enough to pass Risk-Capital.

## 19. Forbidden Artifact Counts Before / After

| Artifact | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `paper_intents` | 20 | 20 | 0 |
| `paper_orders` | 12 | 12 | 0 |
| `paper_fills` | 9 | 9 | 0 |
| `paper_positions` | 12 | 12 | 0 |
| `paper_position_closes` | 9 | 9 | 0 |
| `live_orders` | 0 | 0 | 0 |
| `positions` | 0 | 0 | 0 |

## 20. SYSTEM OFF Cleanup

SYSTEM OFF was posted after the 30-minute observation window.

Final runtime:

- `overall_status = SAFE_STOPPED`
- `runtime_state = STOPPED`
- `system_power = OFF`
- `supervisor_state = STOPPED`
- `readiness_state = BLOCKED`

## 21. Safety Result

Safety result: PASS.

- No Paper Simulation activation.
- No Full Monitor Run.
- No Shadow or Live activation.
- No forbidden artifacts created.
- No capital balance mutation.
- No DB reset.
- No volume reset.
- No destructive DB action.

## 22. Final Recommendation

`READY_FOR_PHASE_10 = NO`

Do not activate Paper, Shadow, or Live.

Next best step:

Review the Risk-Capital policy inputs, especially capital efficiency score and reward-per-dollar-hour. The runtime is healthy enough to produce source-backed candidates, but current candidates still fail the capital efficiency threshold under existing policy.
