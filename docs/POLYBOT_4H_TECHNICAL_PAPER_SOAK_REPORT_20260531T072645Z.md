# POLYBOT 4h Technical Paper Soak Report

- status: RED
- started_at: 2026-05-31T07:26:45.025506+00:00
- finished_at: 2026-05-31T07:26:47.000114+00:00
- samples: 1
- stop_reason: RAW_PAPER_POSITIONS_WITHOUT_FILLS_INCREASED

## Baseline
```json
{
  "mock_data": false,
  "generated_at": "2026-05-31T07:26:45.137491+00:00",
  "system_power": "ON",
  "runtime_health": "OK",
  "paper_status": "GREEN",
  "paper_intents_total": 3,
  "executable_paper_intents": 0,
  "paper_orders_total": 6,
  "paper_fills_total": 3,
  "paper_positions_total": 6,
  "open_paper_positions": 0,
  "active_open_paper_positions": 0,
  "raw_open_paper_positions": 0,
  "closed_paper_positions": 3,
  "quarantined_paper_positions_count": 3,
  "quarantined_paper_positions": [
    {
      "paper_position_id": "0d423170-fc01-4292-9dee-69a690610419",
      "market_id": "678937",
      "side": "NO",
      "entry_price": 0.19,
      "quantity": 31.589,
      "opened_at": "2026-05-30T23:41:27.951263+00:00",
      "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
      "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
      "quarantine_source": "PaperLineageQuarantineService",
      "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
    },
    {
      "paper_position_id": "a0a5a06b-5419-4e2a-afd5-47f56e34af39",
      "market_id": "678929",
      "side": "YES",
      "entry_price": 0.19,
      "quantity": 97.315,
      "opened_at": "2026-05-30T23:41:27.851953+00:00",
      "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
      "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
      "quarantine_source": "PaperLineageQuarantineService",
      "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
    },
    {
      "paper_position_id": "f929eb8a-54cd-4635-86b7-3becae5eba0d",
      "market_id": "629035",
      "side": "YES",
      "entry_price": 0.23,
      "quantity": 60.304,
      "opened_at": "2026-05-30T23:41:27.746835+00:00",
      "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
      "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
      "quarantine_source": "PaperLineageQuarantineService",
      "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
    }
  ],
  "paper_position_closes": 3,
  "paper_trade_ledger": 6,
  "paper_daily_pnl": 2,
  "latest_paper_intent_at": "2026-05-30T20:56:52.370959+00:00",
  "latest_paper_order_at": "2026-05-30T23:41:27.643996+00:00",
  "latest_paper_fill_at": "2026-05-30T20:56:52.816586+00:00",
  "latest_paper_position_at": "2026-05-30T23:41:27.951263+00:00",
  "latest_exit_check_at": "2026-05-31T01:51:17.191771+00:00",
  "latest_position_close_at": "2026-05-30T23:39:40.466599+00:00",
  "realized_pnl": 0.0,
  "unrealized_pnl": 0.157945,
  "daily_pnl": {
    "id": 14,
    "pnl_date": "2026-05-31",
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.157945,
    "net_pnl": 0.157945,
    "gross_profit": 0.0,
    "gross_loss": 0.0,
    "closed_trades_count": 0,
    "open_positions_count": 3,
    "winning_trades_count": 0,
    "losing_trades_count": 0,
    "stale_price_count": 0,
    "updated_at": "2026-05-31T00:45:23.544474+00:00"
  },
  "gross_profit": 0.0,
  "gross_loss": 0.0,
  "winning_trades_count": 0,
  "losing_trades_count": 0,
  "orphan_positions_count": 0,
  "duplicate_orders_count": 0,
  "duplicate_fills_count": 0,
  "duplicate_positions_count": 0,
  "duplicate_intent_orders_count": 0,
  "duplicate_order_fills_count": 0,
  "duplicate_fill_positions_count": 0,
  "positions_without_fills_count": 0,
  "raw_positions_without_fills_count": 3,
  "fills_without_orders_count": 0,
  "positions_without_open_ledger_count": 0,
  "raw_positions_without_open_ledger_count": 3,
  "closed_positions_without_close_count": 0,
  "closed_positions_without_close_ledger_count": 0,
  "executed_intents_reexecuted_count": 0,
  "paper_lineage_consistency_status": "OK",
  "paper_lineage_consistency_raw_status": "RED",
  "paper_lineage_readiness_status": "OK",
  "stale_price_count": 0,
  "no_fake_pnl": true,
  "live_orders": 0,
  "real_orders_baseline": 1,
  "real_orders_current": 1,
  "orders_v2": 1,
  "fills_v2": 1,
  "canonical_positions": 0,
  "live_enabled": false,
  "shadow_enabled": false,
  "brain_dialogue_latest_at": "2026-05-31T01:51:17.220875+00:00",
  "neuron_dialogue_latest_at": "2026-05-31T01:51:17.220875+00:00",
  "brain_dialogue_events": 12243,
  "neuron_dialogue_events": 3980,
  "top_current_blockers": [
    {
      "blocker": "MISSING_TRUSTED_ORDERBOOK",
      "count": 723
    },
    {
      "blocker": "INTENT_ALREADY_EXECUTED",
      "count": 6
    }
  ],
  "warnings": [],
  "readiness_status": "GREEN",
  "latest_runtime": {
    "runtime_health": "OK",
    "scheduler_health": "RUNNING",
    "latest_cycle_id": "v2-20260531T072552-4eec9a6bec",
    "latest_cycle_at": "2026-05-31T07:25:52.838133+00:00"
  }
}
```

## Final
```json
{
  "mock_data": false,
  "generated_at": "2026-05-31T07:26:46.913496+00:00",
  "system_power": "OFF",
  "runtime_health": "OK",
  "paper_status": "GREEN",
  "paper_intents_total": 3,
  "executable_paper_intents": 0,
  "paper_orders_total": 6,
  "paper_fills_total": 3,
  "paper_positions_total": 6,
  "open_paper_positions": 0,
  "active_open_paper_positions": 0,
  "raw_open_paper_positions": 0,
  "closed_paper_positions": 3,
  "quarantined_paper_positions_count": 3,
  "quarantined_paper_positions": [
    {
      "paper_position_id": "0d423170-fc01-4292-9dee-69a690610419",
      "market_id": "678937",
      "side": "NO",
      "entry_price": 0.19,
      "quantity": 31.589,
      "opened_at": "2026-05-30T23:41:27.951263+00:00",
      "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
      "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
      "quarantine_source": "PaperLineageQuarantineService",
      "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
    },
    {
      "paper_position_id": "a0a5a06b-5419-4e2a-afd5-47f56e34af39",
      "market_id": "678929",
      "side": "YES",
      "entry_price": 0.19,
      "quantity": 97.315,
      "opened_at": "2026-05-30T23:41:27.851953+00:00",
      "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
      "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
      "quarantine_source": "PaperLineageQuarantineService",
      "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
    },
    {
      "paper_position_id": "f929eb8a-54cd-4635-86b7-3becae5eba0d",
      "market_id": "629035",
      "side": "YES",
      "entry_price": 0.23,
      "quantity": 60.304,
      "opened_at": "2026-05-30T23:41:27.746835+00:00",
      "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
      "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
      "quarantine_source": "PaperLineageQuarantineService",
      "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
    }
  ],
  "paper_position_closes": 3,
  "paper_trade_ledger": 6,
  "paper_daily_pnl": 2,
  "latest_paper_intent_at": "2026-05-30T20:56:52.370959+00:00",
  "latest_paper_order_at": "2026-05-30T23:41:27.643996+00:00",
  "latest_paper_fill_at": "2026-05-30T20:56:52.816586+00:00",
  "latest_paper_position_at": "2026-05-30T23:41:27.951263+00:00",
  "latest_exit_check_at": "2026-05-31T01:51:17.191771+00:00",
  "latest_position_close_at": "2026-05-30T23:39:40.466599+00:00",
  "realized_pnl": 0.0,
  "unrealized_pnl": 0.157945,
  "daily_pnl": {
    "id": 14,
    "pnl_date": "2026-05-31",
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.157945,
    "net_pnl": 0.157945,
    "gross_profit": 0.0,
    "gross_loss": 0.0,
    "closed_trades_count": 0,
    "open_positions_count": 3,
    "winning_trades_count": 0,
    "losing_trades_count": 0,
    "stale_price_count": 0,
    "updated_at": "2026-05-31T00:45:23.544474+00:00"
  },
  "gross_profit": 0.0,
  "gross_loss": 0.0,
  "winning_trades_count": 0,
  "losing_trades_count": 0,
  "orphan_positions_count": 0,
  "duplicate_orders_count": 0,
  "duplicate_fills_count": 0,
  "duplicate_positions_count": 0,
  "duplicate_intent_orders_count": 0,
  "duplicate_order_fills_count": 0,
  "duplicate_fill_positions_count": 0,
  "positions_without_fills_count": 0,
  "raw_positions_without_fills_count": 3,
  "fills_without_orders_count": 0,
  "positions_without_open_ledger_count": 0,
  "raw_positions_without_open_ledger_count": 3,
  "closed_positions_without_close_count": 0,
  "closed_positions_without_close_ledger_count": 0,
  "executed_intents_reexecuted_count": 0,
  "paper_lineage_consistency_status": "OK",
  "paper_lineage_consistency_raw_status": "RED",
  "paper_lineage_readiness_status": "OK",
  "stale_price_count": 0,
  "no_fake_pnl": true,
  "live_orders": 0,
  "real_orders_baseline": 1,
  "real_orders_current": 1,
  "orders_v2": 1,
  "fills_v2": 1,
  "canonical_positions": 0,
  "live_enabled": false,
  "shadow_enabled": false,
  "brain_dialogue_latest_at": "2026-05-31T01:51:17.220875+00:00",
  "neuron_dialogue_latest_at": "2026-05-31T01:51:17.220875+00:00",
  "brain_dialogue_events": 12243,
  "neuron_dialogue_events": 3980,
  "top_current_blockers": [
    {
      "blocker": "MISSING_TRUSTED_ORDERBOOK",
      "count": 723
    },
    {
      "blocker": "INTENT_ALREADY_EXECUTED",
      "count": 6
    }
  ],
  "warnings": [],
  "readiness_status": "GREEN",
  "latest_runtime": {
    "runtime_health": "OK",
    "scheduler_health": "RUNNING",
    "latest_cycle_id": "v2-20260531T072552-4eec9a6bec",
    "latest_cycle_at": "2026-05-31T07:25:52.838133+00:00"
  }
}
```

## Samples
```json
[
  {
    "timestamp": "2026-05-31T07:26:46.886148+00:00",
    "system_power": "ON",
    "runtime_health": "OK",
    "scheduler_cycle_count": null,
    "latest_cycle_timestamp": "2026-05-31T07:25:52.838133+00:00",
    "brain_dialogue_events": 12243,
    "neuron_dialogue_events": 3980,
    "components_speaking": 13,
    "components_silent": 4,
    "paper_intents": 3,
    "paper_orders": 6,
    "paper_fills": 3,
    "paper_positions": 6,
    "open_paper_positions": 0,
    "closed_paper_positions": 3,
    "paper_position_closes": 3,
    "paper_trade_ledger": 6,
    "paper_daily_pnl": 2,
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.157945,
    "orphan_positions_count": 0,
    "duplicate_orders_count": 0,
    "duplicate_fills_count": 0,
    "duplicate_positions_count": 0,
    "duplicate_intent_orders_count": 0,
    "duplicate_order_fills_count": 0,
    "duplicate_fill_positions_count": 0,
    "positions_without_fills_count": 0,
    "positions_without_open_ledger_count": 0,
    "closed_positions_without_close_count": 0,
    "closed_positions_without_close_ledger_count": 0,
    "executed_intents_reexecuted_count": 0,
    "paper_lineage_consistency_status": "OK",
    "paper_lineage_readiness_status": "OK",
    "quarantined_paper_positions_count": 3,
    "raw_positions_without_fills_count": 3,
    "raw_positions_without_open_ledger_count": 3,
    "stale_price_count": 0,
    "live_orders": 0,
    "real_orders": 1,
    "orders_v2": 1,
    "fills_v2": 1,
    "canonical_positions": 0,
    "top_blockers": [
      {
        "blocker": "MISSING_TRUSTED_ORDERBOOK",
        "count": 723
      },
      {
        "blocker": "INTENT_ALREADY_EXECUTED",
        "count": 6
      }
    ],
    "endpoint_health": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/positions": "OK",
      "/dashboard/api/v2/paper/pnl": "OK",
      "/dashboard/api/v2/paper/soak-readiness": "OK",
      "/dashboard/api/v2/brain-dialogue": "OK",
      "/dashboard/api/v2/neuron-dialogue": "OK",
      "/dashboard/api/v2/system-life": "OK"
    },
    "endpoint_errors": [],
    "mock_data_endpoints": [],
    "safety_delta": {
      "real_orders_current": 0,
      "orders_v2": 0,
      "fills_v2": 0,
      "canonical_positions": 0,
      "paper_intents": -3,
      "paper_orders": -6,
      "paper_fills": -3,
      "paper_positions": -6,
      "paper_trade_ledger": 0,
      "quarantined_paper_positions_count": 0
    }
  }
]
```
