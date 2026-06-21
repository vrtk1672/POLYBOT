# POLYBOT Controlled 10m PAPER Run Post Exit-Capital Fix Report - 20260604T000248Z

- run_id: `controlled_10m_paper_run_post_exit_capital_fix_20260604T000248Z`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- preflight_status: `SAFE-YELLOW`
- run_started: `True`
- phase_status: `YELLOW`
- start_utc: `2026-06-04T00:02:52.910273+00:00`
- end_utc: `2026-06-04T00:13:36.016129+00:00`
- start_local: `2026-06-04T03:02:52.910273+03:00`
- end_local: `2026-06-04T03:13:36.016129+03:00`
- duration_seconds: `643.1`
- cycles: `9`
- hard_stop: `False`
- hard_stop_reasons: `[]`
- final_system_state: `OFF`
- log_path: `logs\observation\controlled_10m_paper_run_post_exit_capital_fix_20260604T000248Z.log`

## Preflight
- blockers: `[]`
- warnings: `['SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR']`
- runtime mode: `PAPER`
- runtime health: `SAFE_STOPPED`
- capital status: `OK`

## Before / After Counts
- neural_events: `455` -> `704` delta `249`
- mesh_sessions: `60` -> `70` delta `10`
- mesh_shared_awareness: `60` -> `70` delta `10`
- mesh_brain_opinions: `215` -> `255` delta `40`
- mesh_coordinator_decisions: `50` -> `60` delta `10`
- mesh_conflict_records: `34` -> `44` delta `10`
- clob_books_verified: `18` -> `18` delta `0`
- orderbook_snapshots: `18` -> `18` delta `0`
- trusted_orderbook_evidence_links: `0` -> `0` delta `0`
- live_orderbook_watchlist: `20` -> `20` delta `0`
- live_orderbook_refreshes: `210` -> `390` delta `180`
- payout_odds_evaluations: `504` -> `616` delta `112`
- exit_hold_evaluations: `180` -> `572` delta `392`
- capital_efficiency_evaluations: `210` -> `607` delta `397`
- trade_lifecycle_plans: `320` -> `1048` delta `728`
- lifecycle_governance_decisions: `320` -> `1048` delta `728`
- paper_intents: `20` -> `20` delta `0`
- paper_orders: `12` -> `12` delta `0`
- paper_fills: `9` -> `9` delta `0`
- paper_positions: `12` -> `12` delta `0`
- paper_position_closes: `9` -> `9` delta `0`
- paper_trade_ledger: `18` -> `18` delta `0`
- open_positions: `0` -> `0` delta `0`
- closed_positions: `9` -> `9` delta `0`
- quarantined_positions: `3` -> `3` delta `0`
- active_positions_without_fills: `0` -> `0` delta `0`
- live_orders: `0` -> `0` delta `0`
- orders_v2: `1` -> `1` delta `0`
- fills_v2: `1` -> `1` delta `0`
- canonical_positions: `0` -> `0` delta `0`

## Governance Actionability
- HARD_BLOCK: `262` -> `934` delta `672`
- NO_TRADE: `0` -> `0` delta `0`
- WATCH_FOR_CONFIRMATION: `58` -> `114` delta `56`
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
  "AI_CONTEXT_UPDATED": 9,
  "HOLD_REVIEW": 0,
  "LIQUIDITY_CHANGED": 9,
  "MARKET_REPRICING": 9,
  "NEWS_DETECTED": 18,
  "ORDERBOOK_REFRESHED": 189,
  "PNL_CHANGED": 1,
  "POSITION_ORDERBOOK_REFRESHED": 0,
  "RISK_CHANGED": 0,
  "SPREAD_CHANGED": 13,
  "WHALE_DETECTED": 1
}
```

## Cycle Calls
### Cycle 1
- source_to_neuron: ok=`True` duration_s=`29.172` summary=`{'events_created': 8, 'sessions_updated': 8, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`1.14` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`5.09` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.636` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`6.137` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.192` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.582` summary=`{'evaluations_created': 58, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.372` summary=`{'evaluations_created': 61, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`2.497` summary=`{'plans_created': 78, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.287` summary=`{'decisions_created': 78, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`1.981` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.098` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.251` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.238` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 2
- source_to_neuron: ok=`True` duration_s=`17.427` summary=`{'events_created': 7, 'sessions_updated': 35, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`1.044` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`4.929` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.686` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`4.351` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.206` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.78` summary=`{'evaluations_created': 65, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.387` summary=`{'evaluations_created': 67, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`3.076` summary=`{'plans_created': 85, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.215` summary=`{'decisions_created': 85, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.345` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.073` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.167` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.055` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 3
- source_to_neuron: ok=`True` duration_s=`21.047` summary=`{'events_created': 7, 'sessions_updated': 62, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`0.827` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`7.924` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.041` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`9.62` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.215` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.597` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.513` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`3.674` summary=`{'plans_created': 78, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.267` summary=`{'decisions_created': 78, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.317` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.069` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.168` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.05` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 4
- source_to_neuron: ok=`True` duration_s=`19.786` summary=`{'events_created': 7, 'sessions_updated': 89, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`0.889` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`5.075` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`6.836` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`3.062` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.151` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.557` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.319` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`2.493` summary=`{'plans_created': 78, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.323` summary=`{'decisions_created': 78, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.324` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.073` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.165` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.059` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 5
- source_to_neuron: ok=`True` duration_s=`19.819` summary=`{'events_created': 8, 'sessions_updated': 117, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`0.832` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`9.099` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.936` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`3.492` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.337` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.644` summary=`{'evaluations_created': 44, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.347` summary=`{'evaluations_created': 44, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`3.427` summary=`{'plans_created': 85, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.306` summary=`{'decisions_created': 85, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.32` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.174` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.261` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.121` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 6
- source_to_neuron: ok=`True` duration_s=`19.946` summary=`{'events_created': 7, 'sessions_updated': 144, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`5.544` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`5.139` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.302` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`3.493` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.151` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.492` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.328` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`2.434` summary=`{'plans_created': 79, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.178` summary=`{'decisions_created': 79, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.244` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.072` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.158` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.057` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 7
- source_to_neuron: ok=`True` duration_s=`29.389` summary=`{'events_created': 7, 'sessions_updated': 173, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`0.967` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`4.953` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.481` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`3.803` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.203` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.53` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.566` summary=`{'evaluations_created': 34, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`2.483` summary=`{'plans_created': 79, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.214` summary=`{'decisions_created': 79, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.267` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.088` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.506` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.05` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 8
- source_to_neuron: ok=`True` duration_s=`22.338` summary=`{'events_created': 7, 'sessions_updated': 202, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`0.8` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`6.111` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`9.322` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`3.668` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.173` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.536` summary=`{'evaluations_created': 44, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.397` summary=`{'evaluations_created': 44, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`6.618` summary=`{'plans_created': 86, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.218` summary=`{'decisions_created': 86, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.327` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.092` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.262` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.057` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`
### Cycle 9
- source_to_neuron: ok=`True` duration_s=`20.508` summary=`{'events_created': 7, 'sessions_updated': 223, 'status': 'OK'}` error=`None`
- fresh_market_identity: ok=`True` duration_s=`0.726` summary=`{'status': 'OK'}` error=`None`
- clob_token_book_verification: ok=`True` duration_s=`5.825` summary=`{'snapshots_created': 18, 'status': 'OK', 'trusted_links_created': 0}` error=`None`
- live_orderbook_watcher: ok=`True` duration_s=`7.807` summary=`{'orderbooks_refreshed': 20, 'snapshots_created': 20, 'status': 'OK'}` error=`None`
- fresh_seed_paper_path: ok=`True` duration_s=`3.391` summary=`{'status': 'OK'}` error=`None`
- payout_odds: ok=`True` duration_s=`0.416` summary=`{'evaluations_created': 0, 'status': 'OK'}` error=`None`
- exit_hold: ok=`True` duration_s=`0.764` summary=`{'evaluations_created': 45, 'status': 'OK'}` error=`None`
- capital_efficiency: ok=`True` duration_s=`0.622` summary=`{'evaluations_created': 45, 'status': 'OK'}` error=`None`
- trade_lifecycle: ok=`True` duration_s=`3.691` summary=`{'plans_created': 80, 'status': 'OK'}` error=`None`
- lifecycle_governance: ok=`True` duration_s=`0.203` summary=`{'decisions_created': 80, 'status': 'OK'}` error=`None`
- paper_intents: ok=`True` duration_s=`0.249` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'OK'}` error=`None`
- paper_execution: ok=`True` duration_s=`0.072` summary=`{'fills_created': 0, 'orders_created': 0, 'positions_created': 0, 'status': 'NO_VALID_PAPER_INTENTS'}` error=`None`
- open_position_watchdog: ok=`True` duration_s=`0.156` summary=`{'orderbooks_refreshed': 0, 'status': 'OK'}` error=`None`
- paper_exits: ok=`True` duration_s=`0.051` summary=`{'status': 'NO_OPEN_PAPER_POSITIONS'}` error=`None`
- hard_stop_reasons: `[]`

## Validation Answers
- Did SYSTEM ON stay active? `YES`
- Was runtime mode PAPER? `YES`
- How many cycles ran? `9`
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
- Can run 4h observation next: `YES`

## Governance / Top Blockers
- top critical blockers: `[{'item': 'RISK_BLOCKED', 'count': 509}, {'item': 'SAME_MARKET_OPPOSING_SIDE_BLOCK', 'count': 421}, {'item': 'CAPITAL_BLOCKED', 'count': 4}]`
- top optional missing: `[{'item': 'MEMORY_CONTEXT_MISSING', 'count': 1048}, {'item': 'WHALE_CONTEXT_MISSING', 'count': 1048}, {'item': 'FAIR_PROBABILITY_MISSING', 'count': 948}, {'item': 'NEWS_CONTEXT_MISSING', 'count': 207}]`
- bypass_paths_found: `[]`

## Trade Result
- paper_trades_opened: `NO`
- paper_trades_closed: `NO`
- top blockers if no trades: `[{'item': 'RISK_BLOCKED', 'count': 509}, {'item': 'SAME_MARKET_OPPOSING_SIDE_BLOCK', 'count': 421}, {'item': 'CAPITAL_BLOCKED', 'count': 4}]`

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
  "timestamp": "2026-06-04T00:16:24.668474+00:00",
  "system_power": "OFF",
  "runtime_mode": "PAPER",
  "runtime_health": "SAFE_STOPPED",
  "neural_events": 704,
  "events_by_type": {
    "ORDERBOOK_REFRESHED": 436,
    "NEWS_DETECTED": 75,
    "SPREAD_CHANGED": 57,
    "MARKET_REPRICING": 42,
    "LIQUIDITY_CHANGED": 41,
    "AI_CONTEXT_UPDATED": 37,
    "PNL_CHANGED": 5,
    "RISK_CHANGED": 4,
    "WHALE_DETECTED": 3,
    "AI_CONTEXT_UNAVAILABLE": 2,
    "HOLD_REVIEW": 1,
    "POSITION_ORDERBOOK_REFRESHED": 1
  },
  "mesh_sessions": 70,
  "mesh_shared_awareness": 70,
  "mesh_brain_opinions": 255,
  "mesh_coordinator_decisions": 60,
  "mesh_conflict_records": 44,
  "clob_books_verified": 18,
  "orderbook_snapshots": 18,
  "trusted_orderbook_evidence_links": 0,
  "live_orderbook_watchlist": 20,
  "live_orderbook_refreshes": 390,
  "payout_odds_evaluations": 616,
  "exit_hold_evaluations": 572,
  "capital_efficiency_evaluations": 607,
  "trade_lifecycle_plans": 1048,
  "lifecycle_governance_decisions": 1048,
  "governance_actionability": {
    "HARD_BLOCK": 934,
    "WATCH_FOR_CONFIRMATION": 114
  },
  "allow_paper_intent_count": 0,
  "allow_paper_execution_count": 0,
  "top_critical_blockers": [
    {
      "item": "RISK_BLOCKED",
      "count": 509
    },
    {
      "item": "SAME_MARKET_OPPOSING_SIDE_BLOCK",
      "count": 421
    },
    {
      "item": "CAPITAL_BLOCKED",
      "count": 4
    }
  ],
  "top_optional_missing": [
    {
      "item": "MEMORY_CONTEXT_MISSING",
      "count": 1048
    },
    {
      "item": "WHALE_CONTEXT_MISSING",
      "count": 1048
    },
    {
      "item": "FAIR_PROBABILITY_MISSING",
      "count": 948
    },
    {
      "item": "NEWS_CONTEXT_MISSING",
      "count": 207
    }
  ],
  "bypass_paths_found": [],
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_fills": 9,
  "paper_positions": 12,
  "paper_position_closes": 9,
  "paper_trade_ledger": 18,
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
  "position_watchdog_runs_seen": true,
  "position_watchdog_positions_checked": 0,
  "mock_data_any": false
}
```
