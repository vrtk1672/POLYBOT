# POLYBOT Active 30m Observation Report

- run_id: active_30m_observation_20260604T115835Z
- status: GREEN
- started_at: 2026-06-04T11:58:35.730664+00:00
- finished_at: 2026-06-04T11:58:52.573568+00:00
- samples: 0
- stop_reason: NONE

## Preflight
```json
{
  "mock_data": false,
  "status": "YELLOW",
  "blockers": [],
  "warnings": [
    "SAFE_YELLOW_AI:['COMPLETED', 'OK', 'OLLAMA_TIMEOUT']"
  ],
  "payload_summary": {
    "/healthz": {
      "status": "ok",
      "mock_data": null,
      "secrets_exposed": null
    },
    "/runtime/health": {
      "status": "SAFE_STOPPED",
      "mock_data": null,
      "secrets_exposed": null
    },
    "/system/power": {
      "status": "OK",
      "mock_data": null,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/source-to-neuron-flow": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": false
    },
    "/dashboard/api/v2/ai-context-router": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": false
    },
    "/dashboard/api/v2/neural-bus": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/mesh-sessions": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/shared-awareness": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/multi-brain-consumption": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/mesh-coordinator": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/capital-brain": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/positions-awareness": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/fresh-market-identity": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/clob-token-book-verification": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/live-orderbook-watcher": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/open-position-watchdog": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/fresh-seed-paper-path": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/payout-odds": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/exit-hold": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/capital-efficiency": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/trade-lifecycle": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/freshness-governance": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/lifecycle-governance": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/paper": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/paper/capital": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/paper/trade-forensics": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/overnight/status": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/source-status": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    }
  }
}
```

## First Sample
```json
{}
```

## Final Sample
```json
{
  "timestamp": "2026-06-04T11:58:52.473385+00:00",
  "system_power": "OFF",
  "runtime_health": "SAFE_STOPPED",
  "endpoint_status": {
    "/healthz": "OK",
    "/runtime/health": "OK",
    "/system/power": "OK",
    "/dashboard/api/v2/source-to-neuron-flow": "OK",
    "/dashboard/api/v2/ai-context-router": "OK",
    "/dashboard/api/v2/neural-bus": "OK",
    "/dashboard/api/v2/mesh-sessions": "OK",
    "/dashboard/api/v2/shared-awareness": "OK",
    "/dashboard/api/v2/multi-brain-consumption": "OK",
    "/dashboard/api/v2/mesh-coordinator": "OK",
    "/dashboard/api/v2/capital-brain": "OK",
    "/dashboard/api/v2/positions-awareness": "OK",
    "/dashboard/api/v2/fresh-market-identity": "OK",
    "/dashboard/api/v2/clob-token-book-verification": "OK",
    "/dashboard/api/v2/live-orderbook-watcher": "OK",
    "/dashboard/api/v2/open-position-watchdog": "OK",
    "/dashboard/api/v2/fresh-seed-paper-path": "OK",
    "/dashboard/api/v2/payout-odds": "OK",
    "/dashboard/api/v2/exit-hold": "OK",
    "/dashboard/api/v2/capital-efficiency": "OK",
    "/dashboard/api/v2/trade-lifecycle": "OK",
    "/dashboard/api/v2/freshness-governance": "OK",
    "/dashboard/api/v2/lifecycle-governance": "OK",
    "/dashboard/api/v2/paper": "OK",
    "/dashboard/api/v2/paper/capital": "OK",
    "/dashboard/api/v2/paper/trade-forensics": "OK",
    "/dashboard/api/v2/overnight/status": "OK",
    "/dashboard/api/v2/source-status": "OK"
  },
  "mock_data_endpoints": [],
  "secret_exposed": false,
  "source_health": "OK",
  "degraded_sources": [],
  "ai_router": {
    "latest_status": "OK",
    "selected_provider": "anthropic",
    "ollama_status": {
      "status": "FAILED",
      "reason": "OLLAMA_TIMEOUT",
      "last_run_id": "source_to_neuron_0b8beb09560e44708bd191adc00d5d72"
    },
    "anthropic_status": {
      "status": "OK",
      "reason": "COMPLETED",
      "last_run_id": "source_to_neuron_0b8beb09560e44708bd191adc00d5d72"
    },
    "openai_status": {
      "status": "NO_RUNS",
      "reason": null,
      "last_run_id": null
    },
    "success_count": 119,
    "unavailable_count": 2,
    "secrets_exposed": false
  },
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
  "neural_events": 3160,
  "mesh_sessions": 161,
  "shared_awareness": 161,
  "brain_opinions": 619,
  "mesh_coordinator_decisions": 151,
  "mesh_conflicts_detected": 128,
  "source_brain_count_avg": 4.0195,
  "capital_evaluations": 161,
  "payout_odds_evaluations": 1560,
  "exit_hold_evaluations": 2788,
  "capital_efficiency_evaluations": 2835,
  "trade_lifecycle_plans": 7693,
  "freshness_governance_checks": 0,
  "stale_sources_count": 816,
  "old_intents_requiring_refresh": 14,
  "freshness_status_counts": {
    "EXPIRED": 816
  },
  "lifecycle_governance_decisions": 7793,
  "governance_actionability": {
    "HARD_BLOCK": 7493,
    "WATCH_FOR_CONFIRMATION": 300
  },
  "allow_paper_intent_count": 0,
  "allow_paper_execution_count": 0,
  "top_critical_blockers": [
    {
      "item": "RISK_BLOCKED",
      "count": 4620
    },
    {
      "item": "SAME_MARKET_OPPOSING_SIDE_BLOCK",
      "count": 3023
    },
    {
      "item": "STALE_CAPITAL_EFFICIENCY",
      "count": 100
    },
    {
      "item": "STALE_EXIT_PLAN",
      "count": 100
    },
    {
      "item": "STALE_LIFECYCLE_PLAN",
      "count": 100
    },
    {
      "item": "STALE_PAYOUT_ODDS",
      "count": 100
    },
    {
      "item": "STALE_RISK_DECISION",
      "count": 100
    },
    {
      "item": "STALE_CAPITAL_EVALUATION",
      "count": 94
    },
    {
      "item": "STALE_ORDERBOOK",
      "count": 94
    },
    {
      "item": "STALE_EXIT_HOLD",
      "count": 60
    },
    {
      "item": "RISK_BLOCKED_LINEAGE",
      "count": 50
    },
    {
      "item": "RISK_BLOCKED_NO_EDGE",
      "count": 50
    },
    {
      "item": "STALE_PAPER_CANDIDATE",
      "count": 46
    },
    {
      "item": "STALE_SAME_MARKET_GUARD",
      "count": 46
    },
    {
      "item": "STALE_PAPER_INTENT",
      "count": 14
    },
    {
      "item": "CAPITAL_BLOCKED",
      "count": 4
    },
    {
      "item": "RISK_BLOCKED_SPREAD",
      "count": 4
    }
  ],
  "top_optional_missing": [
    {
      "item": "MEMORY_CONTEXT_MISSING",
      "count": 7793
    },
    {
      "item": "WHALE_CONTEXT_MISSING",
      "count": 7793
    },
    {
      "item": "FAIR_PROBABILITY_MISSING",
      "count": 7693
    },
    {
      "item": "NEWS_CONTEXT_MISSING",
      "count": 4341
    }
  ],
  "bypass_paths_found": [],
  "capital_decisions": {
    "CAPITAL_SUPPORT": 148,
    "CAPITAL_BLOCK": 10,
    "CAPITAL_WATCH": 2,
    "CAPITAL_RELEASE_REVIEW": 1
  },
  "position_awareness": 3,
  "position_reactions": {
    "PNL_RISING": 5,
    "CAPITAL_PRESSURE": 3,
    "PNL_FALLING": 3,
    "POSITION_ORDERBOOK_REFRESHED": 2,
    "HOLD_REVIEW": 1,
    "POSITION_AGING": 1
  },
  "paper": {
    "live_orders": 0,
    "live_enabled": false,
    "shadow_enabled": false,
    "real_orders_current": 1,
    "orders_v2": 1,
    "fills_v2": 1,
    "canonical_positions": 0,
    "paper_intents": 20,
    "paper_orders": 12,
    "paper_fills": 9,
    "paper_positions": 12,
    "paper_position_closes": 9,
    "paper_trade_ledger": 18,
    "open_positions": 0,
    "closed_positions": 9,
    "active_positions_without_fills": 0,
    "paper_lineage": "OK",
    "capital_reconciliation": "OK",
    "realized_pnl": -3.180678,
    "unrealized_pnl": 0.0,
    "available_balance": 996.819322,
    "locked_balance": 0.0,
    "open_exposure": 0.0,
    "expected_locked_balance": 0.0,
    "actual_locked_balance": 0.0,
    "expected_open_exposure": 0.0,
    "actual_open_exposure": 0.0,
    "open_positions_without_lock": [],
    "locks_without_open_position": [],
    "duplicate_releases": [],
    "realized_pnl_double_apply_count": 0,
    "top_blockers": [
      {
        "blocker": "MISSING_TRUSTED_ORDERBOOK",
        "count": 6432
      },
      {
        "blocker": "INTENT_ALREADY_EXECUTED",
        "count": 2836
      }
    ]
  },
  "paper_capital_truth": {
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
    "duplicate_realized_pnl_apply_count": 0
  },
  "forensics_active_count": 9,
  "forensics_quarantined_count": 3
}
```

## Samples
```json
[]
```
