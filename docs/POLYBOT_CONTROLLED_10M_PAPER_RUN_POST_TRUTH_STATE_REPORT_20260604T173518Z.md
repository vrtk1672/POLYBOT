# POLYBOT Controlled 10m PAPER Run Post Truth State Report - 20260604T173518Z

- run_id: `controlled_10m_paper_run_post_truth_state_20260604T173518Z`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- preflight_status: `YELLOW`
- run_started: `YES`
- phase_status: `YELLOW`
- phase_status_note: `Run completed safely with no Paper trades; harness safety status was GREEN, mission rubric classifies safe no-trade validation as YELLOW.`
- start_utc: `2026-06-04T17:35:39.122056+00:00`
- end_utc: `2026-06-04T17:45:39.810608+00:00`
- start_local: `2026-06-04T20:35:39.122056+03:00`
- end_local: `2026-06-04T20:45:39.810608+03:00`
- duration_seconds: `600.7`
- cycles: `3`
- hard_stop: `NO`
- hard_stop_reason: `NONE`
- log_path: `logs\observation\controlled_10m_paper_run_post_truth_state_20260604T173518Z.log`
- report_path: `docs\POLYBOT_CONTROLLED_10M_PAPER_RUN_POST_TRUTH_STATE_REPORT_20260604T173518Z.md`

## Preflight

- blockers: `[]`
- warnings: `['SAFE_YELLOW_AI_OPTIONAL_DEGRADED']`
- healthz: `ok`
- runtime health: `SAFE_STOPPED`
- system power before run: `OFF`
- runtime mode: `PAPER`
- live enabled: `False`
- shadow enabled: `False`
- capital reconciliation: `OK`
- truth state endpoint: `OK`
- freshness governance endpoint: `OK`
- lifecycle governance endpoint: `OK`

## Cycle Status

- source_to_neuron: `['OK', 'OK', 'OK']`
- fresh_market_identity: `['OK', 'OK', 'OK']`
- clob_token_book_verification: `['OK', 'OK', 'OK']`
- live_orderbook_watcher: `['OK', 'OK', 'OK']`
- fresh_seed_paper_path: `['OK', 'OK', 'OK']`
- payout_odds: `['OK', 'OK', 'OK']`
- exit_hold: `['OK', 'OK', 'OK']`
- capital_efficiency: `['OK', 'OK', 'OK']`
- trade_lifecycle: `['OK', 'OK', 'OK']`
- truth_state: `['OK', 'OK', 'OK']`
- freshness_governance: `['OK', 'OK', 'OK']`
- lifecycle_governance: `['OK', 'OK', 'OK']`
- paper_intents: `['OK', 'OK', 'OK']`
- paper_execution: `['NO_VALID_PAPER_INTENTS', 'NO_VALID_PAPER_INTENTS', 'NO_VALID_PAPER_INTENTS']`
- open_position_watchdog: `['OK', 'OK', 'OK']`
- paper_exits: `['NO_OPEN_PAPER_POSITIONS', 'NO_OPEN_PAPER_POSITIONS', 'NO_OPEN_PAPER_POSITIONS']`

## Deltas

- events_by_type_delta: `{"AI_CONTEXT_UNAVAILABLE": 0, "AI_CONTEXT_UPDATED": 3, "HOLD_REVIEW": 0, "LIQUIDITY_CHANGED": 5, "MARKET_REPRICING": 7, "NEWS_DETECTED": 6, "ORDERBOOK_REFRESHED": 63, "PNL_CHANGED": 0, "POSITION_ORDERBOOK_REFRESHED": 0, "RISK_CHANGED": 0, "SPREAD_CHANGED": 13, "TOKEN_BOOK_UNAVAILABLE": 6, "WHALE_DETECTED": 0}`
- mesh_deltas: `{"mesh_brain_opinions": 12, "mesh_conflict_records": 3, "mesh_coordinator_decisions": 3, "mesh_sessions": 3, "mesh_shared_awareness": 3, "neural_events": 103}`
- reasoning_deltas: `{"capital_efficiency_evaluations": 116, "exit_hold_evaluations": 108, "payout_odds_evaluations": 74, "trade_lifecycle_plans": 240}`
- truth_state_count_deltas: `{"ACTIVE_FRESH": 560, "HISTORICAL_ONLY": 0, "LAST_KNOWN": 535, "REFRESH_REQUIRED": -13}`
- decision_permission_deltas: `{"CAN_AUTHORIZE": 409, "CAN_INFORM_ONLY": 686, "CAN_TEACH_ONLY": 0, "MUST_REFRESH": -13}`
- freshness_governance_deltas: `{"freshness_governance_checks": 0, "lifecycle_governance_decisions": 298, "old_intents_requiring_refresh": 0, "stale_same_market_guard_count": 0, "stale_sources_count": 354, "truth_state_registry": 1082}`
- paper_deltas: `{"active_positions_without_fills": 0, "canonical_positions": 0, "closed_positions": 0, "fills_v2": 0, "live_orders": 0, "open_positions": 0, "orders_v2": 0, "paper_fills": 0, "paper_intents": 0, "paper_orders": 0, "paper_position_closes": 0, "paper_positions": 0, "paper_trade_ledger": 0, "real_orders_current": 0}`

## Capital

- before: `{"available_balance": 996.819322, "capital_reconciliation_status": "OK", "closed_positions_with_active_lock": [], "closes_without_realized_pnl_applied": [], "closes_without_release": [], "current_balance": 996.819322, "duplicate_realized_pnl_apply_count": 0, "duplicate_releases": [], "expected_locked_balance": 0.0, "expected_open_exposure": 0.0, "locked_balance": 0.0, "locks_without_open_position": [], "open_exposure": 0.0, "open_positions_without_lock": [], "realized_pnl": -3.180678, "realized_pnl_double_apply_count": 0, "reconciliation_status": "OK", "unrealized_pnl": 0.0}`
- after: `{"available_balance": 996.819322, "capital_reconciliation_status": "OK", "closed_positions_with_active_lock": [], "closes_without_realized_pnl_applied": [], "closes_without_release": [], "current_balance": 996.819322, "duplicate_realized_pnl_apply_count": 0, "duplicate_releases": [], "expected_locked_balance": 0.0, "expected_open_exposure": 0.0, "locked_balance": 0.0, "locks_without_open_position": [], "open_exposure": 0.0, "open_positions_without_lock": [], "realized_pnl": -3.180678, "realized_pnl_double_apply_count": 0, "reconciliation_status": "OK", "unrealized_pnl": 0.0}`

## Truth State Validation

- before truth states: `{'REFRESH_REQUIRED': 830, 'LAST_KNOWN': 300, 'HISTORICAL_ONLY': 47, 'ACTIVE_FRESH': 3}`
- after truth states: `{'LAST_KNOWN': 835, 'REFRESH_REQUIRED': 817, 'ACTIVE_FRESH': 563, 'HISTORICAL_ONLY': 47}`
- before decision permissions: `{'MUST_REFRESH': 830, 'CAN_INFORM_ONLY': 300, 'CAN_TEACH_ONLY': 47, 'CAN_AUTHORIZE': 3}`
- after decision permissions: `{'CAN_INFORM_ONLY': 986, 'MUST_REFRESH': 817, 'CAN_AUTHORIZE': 412, 'CAN_TEACH_ONLY': 47}`
- fresh data became ACTIVE_FRESH: `YES`
- old/stale data visible as LAST_KNOWN/HISTORICAL_ONLY/REFRESH_REQUIRED: `YES`
- old intents requiring refresh after run: `20`
- stale same-market guard sources after run: `110`

## Governance / Blockers

- actionability: `{'HARD_BLOCK': 8889, 'WATCH_FOR_CONFIRMATION': 300}`
- allow_paper_intent_count: `0`
- allow_paper_execution_count: `0`
- top critical blockers: `[{'item': 'RISK_BLOCKED', 'count': 5376}, {'item': 'SAME_MARKET_OPPOSING_SIDE_BLOCK', 'count': 3481}, {'item': 'STALE_CAPITAL_EVALUATION', 'count': 860}, {'item': 'STALE_EXIT_PLAN', 'count': 846}, {'item': 'STALE_RISK_DECISION', 'count': 846}, {'item': 'STALE_PAYOUT_ODDS', 'count': 824}, {'item': 'RISK_BLOCKED_LINEAGE', 'count': 750}, {'item': 'RISK_BLOCKED_NO_EDGE', 'count': 750}, {'item': 'STALE_SAME_MARKET_GUARD', 'count': 686}, {'item': 'STALE_CAPITAL_EFFICIENCY', 'count': 684}, {'item': 'STALE_ORDERBOOK', 'count': 626}, {'item': 'STALE_EXIT_HOLD', 'count': 324}, {'item': 'STALE_LIFECYCLE_PLAN', 'count': 236}, {'item': 'STALE_PAPER_INTENT', 'count': 210}, {'item': 'STALE_PAPER_CANDIDATE', 'count': 92}, {'item': 'RISK_BLOCKED_SPREAD', 'count': 60}, {'item': 'CAPITAL_BLOCKED', 'count': 4}]`
- top optional missing: `None`
- bypass paths found: `[]`

## Paper Result

- paper trades opened: `NO`
- paper trades closed: `NO`
- paper intents increased: `0`
- paper orders/fills/positions increased: `0/0/0`
- paper closes increased: `0`

## Safety Checks

- stale data authorized Paper: `NO`
- historical data hard-blocked as active exposure: `NO_CURRENT_EVIDENCE`; stale same-market remains `REFRESH_REQUIRED`
- stale same-market acted as current conflict: `NO_CURRENT_EVIDENCE`
- bypass check: `PASS`
- hard stop: `NO`
- secret exposure check: `PASS`
- final system state: `OFF`

## Validation Answers

1. SYSTEM ON stayed active: `YES`
2. Runtime mode PAPER: `PAPER`
3. Cycles ran: `3`
4. Source-to-neuron ran: `YES`
5. Fresh Identity ran: `YES`
6. CLOB verification ran: `YES`
7. Live Watcher ran: `YES`
8. Payout/Odds ran: `YES`
9. Exit/Hold ran: `YES`
10. Capital Efficiency ran: `YES`
11. Trade Lifecycle ran: `YES`
12. Truth State ran: `YES`
13. Freshness Governance ran: `NO_DELTA`
14. Lifecycle Governance ran: `YES`
15. Plans actionable: `0`
16. Capital reconciled: `OK`
17. Position Watchdog ran: `YES`
18. Any stale data authorized action: `NO`
19. Any bypass: `NO`
20. Final SYSTEM state: `OFF`

## Recommended Next Step

If no Paper trades occurred, inspect current-run `RISK_BLOCKED` and trusted-orderbook/market-link lineage. Truth-state separation worked if same-market stale rows remain refresh-required and no stale/historical source authorized Paper.
