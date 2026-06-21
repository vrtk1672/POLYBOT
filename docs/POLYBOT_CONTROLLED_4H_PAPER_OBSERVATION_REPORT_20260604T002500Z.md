# POLYBOT Controlled 4h PAPER Observation Report - 20260604T002500Z

- run_id: `controlled_4h_paper_observation_20260604T002500Z`
- source_runner_run_id: `active_30m_observation_20260604T002500Z`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- preflight_status: `YELLOW`
- run_started: `True`
- phase_status: `YELLOW`
- start_utc: `2026-06-04T00:25:08.846626+00:00`
- end_utc: `2026-06-04T04:25:00.388215+00:00`
- start_local: `2026-06-04T03:25:08.846626+03:00`
- end_local: `2026-06-04T07:25:00.388215+03:00`
- duration_seconds: `14391.5`
- cycles: `82`
- hard_stop: `False`
- hard_stop_reasons: `[]`
- final_system_state: `OFF`
- log_path: `C:\Server\apps\polybot\logs\observation\controlled_4h_paper_observation_20260604T002500Z.log`

## Preflight
- blockers: `[]`
- warnings: `["SAFE_YELLOW_AI:['COMPLETED', 'OK', 'OLLAMA_TIMEOUT']"]`
- runtime mode: `None`
- runtime health: `SAFE_STOPPED`
- capital status: `OK`

## Before / After Counts
- neural_events: `704` -> `3160` delta `2456`
- mesh_sessions: `70` -> `161` delta `91`
- mesh_shared_awareness: `70` -> `161` delta `91`
- mesh_brain_opinions: `255` -> `619` delta `364`
- mesh_coordinator_decisions: `60` -> `151` delta `91`
- mesh_conflict_records: `44` -> `128` delta `84`
- clob_books_verified: `None` -> `18` delta `18`
- orderbook_snapshots: `None` -> `18` delta `18`
- trusted_orderbook_evidence_links: `None` -> `0` delta `0`
- live_orderbook_watchlist: `None` -> `22` delta `22`
- live_orderbook_refreshes: `None` -> `2026` delta `2026`
- payout_odds_evaluations: `616` -> `1560` delta `944`
- exit_hold_evaluations: `572` -> `2788` delta `2216`
- capital_efficiency_evaluations: `607` -> `2835` delta `2228`
- trade_lifecycle_plans: `1048` -> `7693` delta `6645`
- lifecycle_governance_decisions: `1048` -> `7693` delta `6645`
- paper_intents: `20` -> `20` delta `0`
- paper_orders: `12` -> `12` delta `0`
- paper_fills: `9` -> `9` delta `0`
- paper_positions: `12` -> `12` delta `0`
- paper_position_closes: `9` -> `9` delta `0`
- paper_trade_ledger: `18` -> `18` delta `0`
- paper_capital_ledger: `38` -> `38` delta `0`
- open_positions: `0` -> `0` delta `0`
- closed_positions: `9` -> `9` delta `0`
- quarantined_positions: `None` -> `3` delta `3`
- active_positions_without_fills: `0` -> `0` delta `0`
- live_orders: `0` -> `0` delta `0`
- orders_v2: `1` -> `1` delta `0`
- fills_v2: `1` -> `1` delta `0`
- canonical_positions: `0` -> `0` delta `0`

## Governance Actionability
- HARD_BLOCK: `934` -> `7393` delta `6459`
- NO_TRADE: `0` -> `0` delta `0`
- WATCH_FOR_CONFIRMATION: `114` -> `300` delta `186`
- ACTIONABLE_SMALL_PAPER: `0` -> `0` delta `0`
- ACTIONABLE_STANDARD_PAPER: `0` -> `0` delta `0`
- COMPLETE_HIGH_CONFIDENCE: `0` -> `0` delta `0`
- allow_paper_intent_count: `0` -> `0` delta `0`
- allow_paper_execution_count: `0` -> `0` delta `0`

## Capital
- current_balance: `996.819322` -> `996.819322`
- available_balance: `996.819322` -> `996.819322`
- locked_balance: `0.0` -> `0.0`
- open_exposure: `0.0` -> `0.0`
- realized_pnl: `-3.180678` -> `-3.180678`
- unrealized_pnl: `0.0` -> `0.0`
- expected_locked_balance: `0.0` -> `0.0`
- expected_open_exposure: `0.0` -> `0.0`
- capital_reconciliation_status: `OK` -> `OK`
- open_positions_without_lock: `[]` -> `[]`
- locks_without_open_position: `[]` -> `[]`
- closed_positions_with_active_lock: `[]` -> `[]`
- closes_without_release: `[]` -> `[]`
- closes_without_realized_pnl_applied: `[]` -> `[]`
- duplicate_releases: `[]` -> `[]`
- duplicate_realized_pnl_apply_count: `0` -> `0`

## Events By Type Delta
```json
{
  "AI_CONTEXT_UNAVAILABLE": 0,
  "AI_CONTEXT_UPDATED": 82,
  "HOLD_REVIEW": 0,
  "LIQUIDITY_CHANGED": 80,
  "MARKET_REPRICING": 86,
  "NEWS_DETECTED": 164,
  "ORDERBOOK_REFRESHED": 1716,
  "PNL_CHANGED": 0,
  "POSITION_ORDERBOOK_REFRESHED": 0,
  "RISK_CHANGED": 0,
  "SPREAD_CHANGED": 164,
  "TOKEN_BOOK_UNAVAILABLE": 156,
  "WHALE_DETECTED": 8
}
```

## Validation Answers
- Did SYSTEM ON stay active? `YES`
- Was runtime mode PAPER? `YES`
- How many cycles ran? `82`
- Did source-to-neuron run? `YES`
- Did Fresh Identity run? `YES`
- Did CLOB verification run? `YES`
- Did Live Watcher run? `YES`
- Did Payout/Odds run? `YES`
- Did Exit/Hold run? `YES`
- Did Capital Efficiency run? `YES`
- Did Lifecycle Plans update? `YES`
- Did Governance evaluate? `YES`
- Were any plans ACTIONABLE? `NO`
- Did Paper Intent increase? `NO`
- Did Paper Orders/Fills/Positions increase? `NO`
- Did Paper Closes increase? `NO`
- For every new fill, was capital locked? `NO_NEW_FILLS`
- For every open position, does active lock exist? `YES`
- For every new close, was capital released? `NO_NEW_CLOSES`
- For every new close, was realized PnL applied once? `NO_NEW_CLOSES`
- Did locked_balance/open_exposure reconcile? `YES`
- Did Position Watchdog run? `YES`
- Did any bypass occur? `NO`
- Did any hard stop occur? `NO`
- Final SYSTEM state: `OFF`
- Can proceed to next development phase: `YES`

## Governance / Top Blockers
- top critical blockers: `[{'item': 'RISK_BLOCKED', 'count': 4566}, {'item': 'SAME_MARKET_OPPOSING_SIDE_BLOCK', 'count': 2977}, {'item': 'CAPITAL_BLOCKED', 'count': 4}]`
- top optional missing: `[{'item': 'MEMORY_CONTEXT_MISSING', 'count': 7693}, {'item': 'WHALE_CONTEXT_MISSING', 'count': 7693}, {'item': 'FAIR_PROBABILITY_MISSING', 'count': 7593}, {'item': 'NEWS_CONTEXT_MISSING', 'count': 4283}]`
- bypass_paths_found: `[]`
- governance assessment: `Correctly blocking based on current critical blockers; no optional-only overblocking evidence in this run.`

## Trade Result
- paper_trades_opened: `NO`
- paper_trades_closed: `NO`
- top blockers if no trades: `[{'item': 'RISK_BLOCKED', 'count': 4566}, {'item': 'SAME_MARKET_OPPOSING_SIDE_BLOCK', 'count': 2977}, {'item': 'CAPITAL_BLOCKED', 'count': 4}]`
- closest actionable state: `No ACTIONABLE_SMALL_PAPER or ACTIONABLE_STANDARD_PAPER decisions were present.`
- recommended next improvement: `Investigate persistent RISK_BLOCKED and SAME_MARKET_OPPOSING_SIDE_BLOCK classifications before expecting Paper entries.`

## Safety Checklist
- live/shadow disabled: `YES`
- live_orders: `0`
- orders_v2 delta: `0`
- fills_v2 delta: `0`
- canonical positions delta: `0`
- capital reconciliation: `OK`
- mock_data_any: `False`
- SYSTEM OFF at end: `True`

## Raw Final Snapshot
```json
{
  "timestamp": "2026-06-04T04:36:36.924033+00:00",
  "system_power": "OFF",
  "runtime_mode": "PAPER",
  "runtime_health": "SAFE_STOPPED",
  "neural_events": 3160,
  "events_by_type": {
    "ORDERBOOK_REFRESHED": 2152,
    "NEWS_DETECTED": 239,
    "SPREAD_CHANGED": 221,
    "TOKEN_BOOK_UNAVAILABLE": 156,
    "MARKET_REPRICING": 128,
    "LIQUIDITY_CHANGED": 121,
    "AI_CONTEXT_UPDATED": 119,
    "WHALE_DETECTED": 11,
    "PNL_CHANGED": 5,
    "RISK_CHANGED": 4,
    "AI_CONTEXT_UNAVAILABLE": 2,
    "HOLD_REVIEW": 1,
    "POSITION_ORDERBOOK_REFRESHED": 1
  },
  "mesh_sessions": 161,
  "mesh_shared_awareness": 161,
  "mesh_brain_opinions": 619,
  "mesh_coordinator_decisions": 151,
  "mesh_conflict_records": 128,
  "clob_books_verified": 18,
  "orderbook_snapshots": 18,
  "trusted_orderbook_evidence_links": 0,
  "live_orderbook_watchlist": 22,
  "live_orderbook_refreshes": 2026,
  "payout_odds_evaluations": 1560,
  "exit_hold_evaluations": 2788,
  "capital_efficiency_evaluations": 2835,
  "trade_lifecycle_plans": 7693,
  "lifecycle_governance_decisions": 7693,
  "HARD_BLOCK": 7393,
  "WATCH_FOR_CONFIRMATION": 300,
  "ACTIONABLE_SMALL_PAPER": 0,
  "ACTIONABLE_STANDARD_PAPER": 0,
  "NO_TRADE": 0,
  "COMPLETE_HIGH_CONFIDENCE": 0,
  "allow_paper_intent_count": 0,
  "allow_paper_execution_count": 0,
  "top_critical_blockers": [
    {
      "item": "RISK_BLOCKED",
      "count": 4566
    },
    {
      "item": "SAME_MARKET_OPPOSING_SIDE_BLOCK",
      "count": 2977
    },
    {
      "item": "CAPITAL_BLOCKED",
      "count": 4
    }
  ],
  "top_optional_missing": [
    {
      "item": "MEMORY_CONTEXT_MISSING",
      "count": 7693
    },
    {
      "item": "WHALE_CONTEXT_MISSING",
      "count": 7693
    },
    {
      "item": "FAIR_PROBABILITY_MISSING",
      "count": 7593
    },
    {
      "item": "NEWS_CONTEXT_MISSING",
      "count": 4283
    }
  ],
  "bypass_paths_found": [],
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_fills": 9,
  "paper_positions": 12,
  "paper_position_closes": 9,
  "paper_trade_ledger": 18,
  "paper_capital_ledger": 38,
  "open_positions": 0,
  "closed_positions": 9,
  "quarantined_positions": 3,
  "active_positions_without_fills": 0,
  "paper_lineage_status": "OK",
  "current_balance": 996.819322,
  "available_balance": 996.819322,
  "locked_balance": 0.0,
  "open_exposure": 0.0,
  "realized_pnl": -3.180678,
  "unrealized_pnl": 0.0,
  "capital_reconciliation_status": "OK",
  "expected_locked_balance": 0.0,
  "expected_open_exposure": 0.0,
  "open_positions_without_lock": [],
  "locks_without_open_position": [],
  "closed_positions_with_active_lock": [],
  "closes_without_release": [],
  "closes_without_realized_pnl_applied": [],
  "duplicate_releases": [],
  "duplicate_realized_pnl_apply_count": 0,
  "live_orders": 0,
  "live_enabled": false,
  "shadow_enabled": false,
  "orders_v2": 1,
  "fills_v2": 1,
  "canonical_positions": 0,
  "mock_data_any": false
}
```
