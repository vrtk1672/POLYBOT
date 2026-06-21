# POLYBOT Controlled 30m PAPER Run Post Freshness Calibration Report - 20260604T115905Z

- run_id: `active_30m_observation_20260604T115905Z`
- controlled_log_path: `logs/observation/controlled_30m_paper_run_post_freshness_calibration_20260604T115905Z.log`
- source_log_path: `logs/observation/active_30m_observation_20260604T115905Z.log`
- report_path: `docs/POLYBOT_CONTROLLED_30M_PAPER_RUN_POST_FRESHNESS_CALIBRATION_REPORT_20260604T115905Z.md`
- source_report_path: `docs/POLYBOT_ACTIVE_30M_OBSERVATION_REPORT_20260604T115905Z.md`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- preflight_status: `YELLOW`
- run_started: `YES`
- phase_status: `YELLOW`
- start_utc: `2026-06-04T11:59:05.261624+00:00`
- end_utc: `2026-06-04T12:29:11.704224+00:00`
- start_local: `2026-06-04T14:59:05.261624+03:00`
- end_local: `2026-06-04T15:29:11.704224+03:00`
- duration_seconds: `1806.4`
- cycles: `10`
- hard_stop: `NO`
- hard_stop_reasons: `[]`
- final_system_state: `OFF`

## Preflight

- blockers: `[]`
- warnings: `["SAFE_YELLOW_AI:['COMPLETED', 'OK', 'OLLAMA_TIMEOUT']"]`
- healthz: `OK`
- runtime health while OFF: `SAFE_STOPPED`
- system power before run: `OFF`
- runtime mode: `PAPER`
- live enabled: `false`
- shadow enabled: `false`
- lifecycle governance endpoint: `OK`
- freshness governance endpoint: `OK`
- trade lifecycle endpoint: `OK`
- dashboard mock_data: `false`
- capital reconciliation: `OK`

Note: a zero-duration preflight invocation was run first at `20260604T115835Z`; it briefly toggled SYSTEM ON/OFF through official endpoints, produced zero samples, and showed `GREEN` preflight. The actual 30m run used `active_30m_observation_20260604T115905Z`.

## Cycle Results

Every cycle used official API endpoints. No direct service constructors or legacy Paper paths were called.

| Component | Cycles | Status |
| --- | ---: | --- |
| source-to-neuron | 10 | `OK` |
| Fresh Market Identity | 10 | `OK` |
| CLOB verification | 10 | `OK` |
| Live Orderbook Watcher | 10 | `OK` |
| Fresh Seed Paper Path | 10 | `OK` |
| Payout/Odds | 10 | `OK` |
| Exit/Hold | 10 | `OK` |
| Capital Efficiency | 10 | `OK` |
| Trade Lifecycle | 10 | `OK` |
| Freshness Governance | 10 | `OK` |
| Lifecycle Governance | 10 | `OK` |
| Paper Intent builder | 10 | `OK` |
| Paper Execution | 10 | `NO_VALID_PAPER_INTENTS` |
| Open Position Watchdog | 10 | `OK` |
| Paper Exits | 10 | `NO_OPEN_PAPER_POSITIONS` |

## Before / After Counts

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| neural_events | 3160 | 3475 | 315 |
| mesh_sessions | 161 | 173 | 12 |
| mesh_shared_awareness | 161 | 173 | 12 |
| mesh_brain_opinions | 619 | 667 | 48 |
| mesh_coordinator_decisions | 151 | 163 | 12 |
| mesh_conflict_records | 128 | 130 | 2 |
| payout_odds_evaluations | 1560 | 1673 | 113 |
| exit_hold_evaluations | 2788 | 3028 | 240 |
| capital_efficiency_evaluations | 2835 | 3088 | 253 |
| trade_lifecycle_plans | 7693 | 8493 | 800 |
| lifecycle_governance_decisions | 7793 | 8791 | 998 |
| freshness_governance_checks | 816 | 3674 | 2858 |
| stale_sources_count | 816 | 1164 | 348 |
| old_intents_requiring_refresh | 14 | 14 | 0 |
| paper_intents | 20 | 20 | 0 |
| paper_orders | 12 | 12 | 0 |
| paper_fills | 9 | 9 | 0 |
| paper_positions | 12 | 12 | 0 |
| paper_position_closes | 9 | 9 | 0 |
| paper_trade_ledger | 18 | 18 | 0 |
| live_orders | 0 | 0 | 0 |
| orders_v2 | 1 | 1 | 0 |
| fills_v2 | 1 | 1 | 0 |
| canonical positions | 0 | 0 | 0 |

## Event Deltas

```json
{
  "AI_CONTEXT_UNAVAILABLE": 0,
  "AI_CONTEXT_UPDATED": 10,
  "HOLD_REVIEW": 0,
  "LIQUIDITY_CHANGED": 10,
  "MARKET_REPRICING": 13,
  "NEWS_DETECTED": 20,
  "ORDERBOOK_REFRESHED": 210,
  "PNL_CHANGED": 0,
  "POSITION_ORDERBOOK_REFRESHED": 0,
  "RISK_CHANGED": 0,
  "SPREAD_CHANGED": 30,
  "TOKEN_BOOK_UNAVAILABLE": 20,
  "WHALE_DETECTED": 2
}
```

## Freshness / Governance

Freshness governance ran every cycle.

Final freshness status counts:

- `FRESH`: 2510
- `EXPIRED`: 896
- `STALE`: 268

Final stale source count:

- `1164`

Final lifecycle governance distribution:

- `HARD_BLOCK`: 8491
- `WATCH_FOR_CONFIRMATION`: 300
- `NO_TRADE`: 0
- `ACTIONABLE_SMALL_PAPER`: 0
- `ACTIONABLE_STANDARD_PAPER`: 0
- `COMPLETE_HIGH_CONFIDENCE`: 0
- `allow_paper_intent_count`: 0
- `allow_paper_execution_count`: 0

Top critical blockers:

- `RISK_BLOCKED`: 5160
- `SAME_MARKET_OPPOSING_SIDE_BLOCK`: 3481
- `STALE_PAYOUT_ODDS`: 824
- `STALE_CAPITAL_EFFICIENCY`: 684
- `STALE_CAPITAL_EVALUATION`: 612
- `STALE_EXIT_PLAN`: 598
- `STALE_RISK_DECISION`: 598
- `RISK_BLOCKED_LINEAGE`: 550
- `RISK_BLOCKED_NO_EDGE`: 550
- `STALE_SAME_MARKET_GUARD`: 504
- `STALE_ORDERBOOK`: 432
- `STALE_EXIT_HOLD`: 324
- `STALE_PAPER_INTENT`: 154
- `STALE_LIFECYCLE_PLAN`: 118
- `STALE_PAPER_CANDIDATE`: 46
- `RISK_BLOCKED_SPREAD`: 44
- `CAPITAL_BLOCKED`: 4

Top optional missing context:

- `MEMORY_CONTEXT_MISSING`: 8791
- `WHALE_CONTEXT_MISSING`: 8791
- `FAIR_PROBABILITY_MISSING`: 8691
- `NEWS_CONTEXT_MISSING`: 4921

Assessment: optional missing context did not authorize Paper and did not appear to be the sole hard-blocker. The run remained non-actionable because critical risk, same-market, and stale/refresh blockers persisted.

## Capital

| Metric | Before | After |
| --- | ---: | ---: |
| current_balance | 996.819322 | 996.819322 |
| available_balance | 996.819322 | 996.819322 |
| locked_balance | 0.0 | 0.0 |
| open_exposure | 0.0 | 0.0 |
| realized_pnl | -3.180678 | -3.180678 |
| unrealized_pnl | 0.0 | 0.0 |
| expected_locked_balance | 0.0 | 0.0 |
| expected_open_exposure | 0.0 | 0.0 |
| capital_reconciliation_status | OK | OK |

Capital lineage:

- open positions without lock: `[]`
- locks without open position: `[]`
- closed positions with active lock: `[]`
- closes without release: `[]`
- closes without realized PnL applied: `[]`
- duplicate releases: `[]`
- duplicate realized PnL apply count: `0`

## Paper Result

- Paper trades opened: `NO`
- Paper trades closed: `NO`
- Paper intents delta: `0`
- Paper orders delta: `0`
- Paper fills delta: `0`
- Paper positions delta: `0`
- Paper closes delta: `0`

No new fill required a capital lock. No open position required active lock verification. No new close required release/PnL verification.

## Stale Data Authorization Check

No Paper artifact was created.

No Paper Intent or Paper Execution was authorized by stale data. Stale and expired critical sources appeared in governance as blockers, including `STALE_ORDERBOOK`, `STALE_RISK_DECISION`, `STALE_EXIT_PLAN`, `STALE_CAPITAL_EVALUATION`, `STALE_PAPER_INTENT`, and related stale economic-reasoning sources.

## Bypass Check

- lifecycle bypass paths found: `[]`
- paper order without intent: `NO`
- paper fill without order: `NO`
- paper position without fill: `NO`
- orders_v2 unexpected delta: `0`
- fills_v2 unexpected delta: `0`
- canonical positions unexpected delta: `0`

Bypass result: `PASS`

## Validation Answers

1. Did SYSTEM ON stay active? `YES`
2. Was runtime mode PAPER? `YES`
3. How many cycles ran? `10`
4. Did source-to-neuron run? `YES`
5. Did Fresh Identity run? `YES`
6. Did CLOB verification run? `YES`
7. Did Live Watcher run? `YES`
8. Did Payout/Odds run? `YES`
9. Did Exit/Hold run? `YES`
10. Did Capital Efficiency run? `YES`
11. Did Trade Lifecycle run? `YES`
12. Did Freshness Governance run? `YES`
13. Did Lifecycle Governance run? `YES`
14. Were any plans ACTIONABLE? `NO`
15. Did Paper Intent increase? `NO`
16. Did Paper Orders/Fills/Positions increase? `NO`
17. Did Paper Closes increase? `NO`
18. For every new fill, was capital locked? `NO_NEW_FILLS`
19. For every open position, does active lock exist? `NO_OPEN_POSITIONS`
20. For every new close, was capital released? `NO_NEW_CLOSES`
21. For every new close, was realized PnL applied once? `NO_NEW_CLOSES`
22. Did locked_balance/open_exposure reconcile? `YES`
23. Did Position Watchdog run? `YES`
24. Did any stale data authorize action? `NO`
25. Did any bypass occur? `NO`
26. Did any hard stop occur? `NO`
27. Final SYSTEM state: `OFF`

## No-Trade Blocker Assessment

The run did not trade because no lifecycle governance decision reached an actionable class.

Top blockers were critical, not optional-only:

- Risk remained blocked across many candidates, with precision signals like `RISK_BLOCKED_LINEAGE`, `RISK_BLOCKED_NO_EDGE`, and `RISK_BLOCKED_SPREAD`.
- Same-market opposition remained a critical blocker for many fresh seed / lifecycle records.
- Freshness governance correctly blocked stale critical sources, especially orderbook, risk, exit, capital, same-market, and older paper-intent sources.
- Optional context such as memory, whale, fair probability, and news remained missing but did not grant action and did not appear to be the only reason for `HARD_BLOCK`.

Recommended next improvement:

- Investigate why trusted orderbook evidence remains missing or stale for many candidates despite live orderbook refreshes.
- Continue precision work on `RISK_BLOCKED` and same-market guard examples to separate truly non-actionable markets from candidates that only need a fresh orderbook/trusted evidence refresh.

## Safety Checklist

- live enabled: `false`
- shadow enabled: `false`
- live_orders: `0`
- order/write endpoint called: `NO`
- orders_v2 delta: `0`
- fills_v2 delta: `0`
- canonical positions delta: `0`
- fake dashboard data: `NO`
- secrets exposed: `NO`
- capital reconciliation: `OK`
- SYSTEM OFF at end: `YES`

## Phase Status

Status: `YELLOW`

The 30-minute run completed safely, all key cycles ran, Freshness Governance and Lifecycle Governance were active, no stale data authorized Paper, no bypass occurred, and capital stayed reconciled. The phase is YELLOW because no Paper trades occurred and all Paper action remained blocked for critical/stale reasons.

Can run 4h observation next: `YES`, with the expectation that no trades should occur unless fresh trusted orderbook/risk/exit/capital/same-market conditions clear and lifecycle governance reaches an actionable class.
