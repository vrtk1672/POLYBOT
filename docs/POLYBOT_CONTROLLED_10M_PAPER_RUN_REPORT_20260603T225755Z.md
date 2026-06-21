# POLYBOT Controlled 10m PAPER Run Report - 20260603T225755Z

- run_id: `controlled_10m_paper_run_20260603T225755Z`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- preflight_status: `SAFE-YELLOW`
- run_started: `True`
- phase_status: `RED`
- start_utc: `2026-06-03T22:57:57.091781+00:00`
- end_utc: `2026-06-03T22:58:54.973913+00:00`
- start_local: `2026-06-04T01:57:57.091781+03:00`
- end_local: `2026-06-04T01:58:54.973913+03:00`
- duration_seconds: `57.9`
- cycles: `1`
- hard_stop: `True`
- hard_stop_reasons: `['CAPITAL_RECONCILIATION_NOT_OK:RED']`
- final_system_state: `OFF`

## Preflight
- blockers: `[]`
- warnings: `['SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR']`
- runtime mode: `PAPER`
- runtime health: `SAFE_STOPPED`
- capital status: `OK`

## Before / After Counts
- neural_events: `411` -> `455` delta `44`
- mesh_sessions: `57` -> `60` delta `3`
- mesh_shared_awareness: `None` -> `None` delta `0`
- mesh_brain_opinions: `None` -> `None` delta `0`
- mesh_coordinator_decisions: `None` -> `None` delta `0`
- fresh_market_identity_runs: `None` -> `None` delta `0`
- clob_verification_runs: `None` -> `None` delta `0`
- fresh_candidate_seeds: `20` -> `20` delta `0`
- orderbook_snapshots: `None` -> `None` delta `0`
- trusted_orderbook_evidence_links: `None` -> `None` delta `0`
- live_orderbook_watchlist: `20` -> `20` delta `0`
- live_orderbook_watcher_runs: `None` -> `None` delta `0`
- payout_odds_evaluations: `160` -> `504` delta `344`
- exit_hold_evaluations: `121` -> `180` delta `59`
- capital_efficiency_evaluations: `141` -> `210` delta `69`
- trade_lifecycle_plans: `241` -> `320` delta `79`
- lifecycle_governance_decisions: `241` -> `320` delta `79`
- HARD_BLOCK: `191` -> `262` delta `71`
- NO_TRADE: `0` -> `0` delta `0`
- WATCH_FOR_CONFIRMATION: `50` -> `58` delta `8`
- ACTIONABLE_SMALL_PAPER: `0` -> `0` delta `0`
- ACTIONABLE_STANDARD_PAPER: `0` -> `0` delta `0`
- COMPLETE_HIGH_CONFIDENCE: `0` -> `0` delta `0`
- paper_intents: `0` -> `0` delta `0`
- paper_orders: `0` -> `0` delta `0`
- paper_fills: `0` -> `0` delta `0`
- paper_positions: `0` -> `0` delta `0`
- paper_position_closes: `8` -> `9` delta `1`
- paper_trade_ledger: `17` -> `18` delta `1`
- open_positions: `1` -> `0` delta `-1`
- closed_positions: `None` -> `None` delta `0`
- quarantined_positions: `3` -> `3` delta `0`
- active_positions_without_fills: `0` -> `0` delta `0`
- paper_capital_ledger: `None` -> `None` delta `0`
- live_orders: `0` -> `0` delta `0`
- orders_v2: `1` -> `1` delta `0`
- fills_v2: `1` -> `1` delta `0`
- canonical_positions: `0` -> `0` delta `0`

## Capital
- current_balance: `996.849322` -> `996.849322`
- available_balance: `996.689322` -> `996.689322`
- locked_balance: `0.16` -> `0.16`
- open_exposure: `0.16` -> `0.16`
- realized_pnl: `-3.150678` -> `-3.150678`
- unrealized_pnl: `-0.04` -> `-0.04`
- expected_locked_balance: `0.16` -> `0.0`
- expected_open_exposure: `0.16` -> `0.0`
- capital_reconciliation_status: `OK` -> `RED`

## Events By Type
```json
[
  {
    "event_type": "ORDERBOOK_REFRESHED",
    "count": 247,
    "latest_at": "2026-06-03T22:58:33.970194Z"
  },
  {
    "event_type": "NEWS_DETECTED",
    "count": 57,
    "latest_at": "2026-06-03T22:58:00.582842Z"
  },
  {
    "event_type": "SPREAD_CHANGED",
    "count": 44,
    "latest_at": "2026-06-03T22:58:34.056003Z"
  },
  {
    "event_type": "MARKET_REPRICING",
    "count": 33,
    "latest_at": "2026-06-03T22:58:30.040308Z"
  },
  {
    "event_type": "LIQUIDITY_CHANGED",
    "count": 32,
    "latest_at": "2026-06-03T22:58:28.549498Z"
  },
  {
    "event_type": "AI_CONTEXT_UPDATED",
    "count": 28,
    "latest_at": "2026-06-03T22:58:15.173609Z"
  },
  {
    "event_type": "PNL_CHANGED",
    "count": 4,
    "latest_at": "2026-06-03T22:58:50.552258Z"
  },
  {
    "event_type": "RISK_CHANGED",
    "count": 4,
    "latest_at": "2026-06-01T09:01:42.617863Z"
  },
  {
    "event_type": "AI_CONTEXT_UNAVAILABLE",
    "count": 2,
    "latest_at": "2026-06-02T00:14:56.757407Z"
  },
  {
    "event_type": "WHALE_DETECTED",
    "count": 2,
    "latest_at": "2026-06-02T09:29:54.738094Z"
  },
  {
    "event_type": "HOLD_REVIEW",
    "count": 1,
    "latest_at": "2026-06-03T22:58:50.699101Z"
  },
  {
    "event_type": "POSITION_ORDERBOOK_REFRESHED",
    "count": 1,
    "latest_at": "2026-06-03T22:58:50.043543Z"
  }
]
```

## Cycle Calls
### Cycle 1
- source_to_neuron: ok=`True` status=`200` duration_s=`26.445` summary=`{'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` status=`200` duration_s=`1.113` summary=`{'status': 'OK'}` error=`None`
- clob_verification: ok=`True` status=`200` duration_s=`2.979` summary=`{'status': 'OK'}` error=`None`
- live_orderbook_watcher: ok=`True` status=`200` duration_s=`6.622` summary=`{'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` status=`200` duration_s=`11.004` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` status=`200` duration_s=`0.382` summary=`{'status': 'OK'}` error=`None`
- exit_hold: ok=`True` status=`200` duration_s=`0.525` summary=`{'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` status=`200` duration_s=`0.434` summary=`{'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` status=`200` duration_s=`2.489` summary=`{'status': 'OK', 'plans_created': 79}` error=`None`
- lifecycle_governance: ok=`True` status=`200` duration_s=`0.187` summary=`{'status': 'OK', 'decisions_created': 79}` error=`None`
- paper_intents: ok=`True` status=`200` duration_s=`0.263` summary=`{'status': 'OK', 'orders_created': 0, 'fills_created': 0, 'positions_created': 0}` error=`None`
- paper_execution: ok=`True` status=`200` duration_s=`0.08` summary=`{'status': 'NO_VALID_PAPER_INTENTS', 'orders_created': 0, 'fills_created': 0, 'positions_created': 0}` error=`None`
- position_watchdog: ok=`True` status=`200` duration_s=`1.377` summary=`{'status': 'OK'}` error=`None`
- paper_exits: ok=`True` status=`200` duration_s=`0.145` summary=`{'status': 'OK'}` error=`None`
- hard_stop_reasons: `['CAPITAL_RECONCILIATION_NOT_OK:RED']`

## Governance / Blockers
- decisions_by_actionability: `{'HARD_BLOCK': 262, 'WATCH_FOR_CONFIRMATION': 58}`
- allow_paper_intent_count: `0`
- allow_paper_execution_count: `0`
- top critical blockers: `[{'item': 'RISK_BLOCKED', 'count': 215}, {'item': 'SAME_MARKET_OPPOSING_SIDE_BLOCK', 'count': 43}, {'item': 'CAPITAL_BLOCKED', 'count': 4}]`
- top optional missing: `[{'item': 'MEMORY_CONTEXT_MISSING', 'count': 320}, {'item': 'WHALE_CONTEXT_MISSING', 'count': 320}, {'item': 'FAIR_PROBABILITY_MISSING', 'count': 220}, {'item': 'NEWS_CONTEXT_MISSING', 'count': 80}]`
- bypass_paths_found: `[]`

## Paper Trade Result
- paper_trades_opened: `False`
- paper_trades_closed: `True`

## Post-Stop Capital Diagnosis
- hard stop trigger: `CAPITAL_RECONCILIATION_NOT_OK:RED`
- observed state after stop: `open_positions=0`, `paper_position_closes=9`, `paper_trade_ledger=18`
- exact DB counts after stop: `paper_intents=20`, `paper_orders=12`, `paper_fills=9`, `paper_positions=12`, `paper_position_closes=9`, `paper_trade_ledger=18`, `paper_capital_ledger=36`, `live_orders=0`, `orders_v2=1`, `fills_v2=1`, `canonical_positions=0`
- run-created Paper close: `paper_close_7668d890-0fe3-5aa3-bc32-996a2f121da2`
- closed position: `7668d890-0fe3-5aa3-bc32-996a2f121da2`, market `598936`, side `YES`, entry `0.016`, exit `0.013`, quantity `10`, realized_pnl `-0.03`, exit_reason `MAX_HOLD_TIME`, correlation_id `controlled_10m_paper_run_20260603T225755Z`
- account actuals after stop: `locked_balance=0.16`, `open_exposure=0.16`
- expected after stop: `expected_locked_balance=0.0`, `expected_open_exposure=0.0`
- capital truth mismatch: closed position still has an unreleased active lock.
- `locks_without_open_position`: `[{paper_position_id: 7668d890-0fe3-5aa3-bc32-996a2f121da2, active_lock: 0.16}]`
- capital ledger trace for closed position: only `CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL` exists; no `CAPITAL_RELEASED_ON_CLOSE` and no `REALIZED_PNL_APPLIED` row exists for this close.
- conclusion: the official Paper Exit path closed the pre-existing open Paper position, but the matching capital release/account reconciliation did not complete. This is a real blocker before any longer run.

## Safety Checklist
- live/shadow disabled: `True`
- live_orders: `0`
- orders_v2 delta: `0`
- fills_v2 delta: `0`
- canonical positions delta: `0`
- capital reconciliation: `RED`
- mock_data_any: `False`
- SYSTEM OFF at end: `True`

## Recommendation
- Controlled run is RED. Do not proceed to 4h until listed blocker or hard-stop reasons are fixed.
