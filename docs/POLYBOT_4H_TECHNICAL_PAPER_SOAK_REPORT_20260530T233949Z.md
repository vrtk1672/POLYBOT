# POLYBOT 4h Technical Paper Soak Report

- status: GREEN
- started_at: 2026-05-30T23:39:49.807472+00:00
- finished_at: 2026-05-30T23:39:50.007002+00:00
- samples: 0
- stop_reason: NONE

## Baseline
```json
{
  "mock_data": false,
  "generated_at": "2026-05-30T23:39:49.909480+00:00",
  "system_power": "ON",
  "runtime_health": "OK",
  "paper_status": "GREEN",
  "paper_intents_total": 3,
  "executable_paper_intents": 3,
  "paper_orders_total": 3,
  "paper_fills_total": 3,
  "paper_positions_total": 3,
  "open_paper_positions": 0,
  "closed_paper_positions": 3,
  "paper_position_closes": 3,
  "paper_trade_ledger": 6,
  "paper_daily_pnl": 1,
  "latest_paper_intent_at": "2026-05-30T20:56:52.370959+00:00",
  "latest_paper_order_at": "2026-05-30T20:56:52.761099+00:00",
  "latest_paper_fill_at": "2026-05-30T20:56:52.816586+00:00",
  "latest_paper_position_at": "2026-05-30T20:56:52.816586+00:00",
  "latest_exit_check_at": "2026-05-30T23:39:40.531831+00:00",
  "latest_position_close_at": "2026-05-30T23:39:40.466599+00:00",
  "realized_pnl": 23.25,
  "unrealized_pnl": 0.0,
  "daily_pnl": {
    "id": 1,
    "pnl_date": "2026-05-30",
    "realized_pnl": 23.25,
    "unrealized_pnl": 0.0,
    "net_pnl": 23.25,
    "gross_profit": 23.25,
    "gross_loss": 0.0,
    "closed_trades_count": 3,
    "open_positions_count": 0,
    "winning_trades_count": 3,
    "losing_trades_count": 0,
    "stale_price_count": 0,
    "updated_at": "2026-05-30T23:39:40.466599+00:00"
  },
  "gross_profit": 23.25,
  "gross_loss": 0.0,
  "winning_trades_count": 3,
  "losing_trades_count": 0,
  "orphan_positions_count": 0,
  "duplicate_orders_count": 0,
  "duplicate_fills_count": 0,
  "duplicate_positions_count": 0,
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
  "brain_dialogue_latest_at": "2026-05-30T23:39:40.554786+00:00",
  "neuron_dialogue_latest_at": "2026-05-30T23:39:40.554786+00:00",
  "brain_dialogue_events": 7076,
  "neuron_dialogue_events": 1707,
  "top_current_blockers": [
    {
      "blocker": "MISSING_TRUSTED_ORDERBOOK",
      "count": 507
    }
  ],
  "warnings": [],
  "readiness_status": "GREEN",
  "latest_runtime": {
    "runtime_health": "OK",
    "scheduler_health": "HEALTHY",
    "latest_cycle_id": "v2-20260530T233853-c1bbeae5f2",
    "latest_cycle_at": "2026-05-30T23:38:53.323112+00:00"
  }
}
```

## Final
```json
{
  "mock_data": false,
  "generated_at": "2026-05-30T23:39:49.960809+00:00",
  "system_power": "ON",
  "runtime_health": "OK",
  "paper_status": "GREEN",
  "paper_intents_total": 3,
  "executable_paper_intents": 3,
  "paper_orders_total": 3,
  "paper_fills_total": 3,
  "paper_positions_total": 3,
  "open_paper_positions": 0,
  "closed_paper_positions": 3,
  "paper_position_closes": 3,
  "paper_trade_ledger": 6,
  "paper_daily_pnl": 1,
  "latest_paper_intent_at": "2026-05-30T20:56:52.370959+00:00",
  "latest_paper_order_at": "2026-05-30T20:56:52.761099+00:00",
  "latest_paper_fill_at": "2026-05-30T20:56:52.816586+00:00",
  "latest_paper_position_at": "2026-05-30T20:56:52.816586+00:00",
  "latest_exit_check_at": "2026-05-30T23:39:40.531831+00:00",
  "latest_position_close_at": "2026-05-30T23:39:40.466599+00:00",
  "realized_pnl": 23.25,
  "unrealized_pnl": 0.0,
  "daily_pnl": {
    "id": 1,
    "pnl_date": "2026-05-30",
    "realized_pnl": 23.25,
    "unrealized_pnl": 0.0,
    "net_pnl": 23.25,
    "gross_profit": 23.25,
    "gross_loss": 0.0,
    "closed_trades_count": 3,
    "open_positions_count": 0,
    "winning_trades_count": 3,
    "losing_trades_count": 0,
    "stale_price_count": 0,
    "updated_at": "2026-05-30T23:39:40.466599+00:00"
  },
  "gross_profit": 23.25,
  "gross_loss": 0.0,
  "winning_trades_count": 3,
  "losing_trades_count": 0,
  "orphan_positions_count": 0,
  "duplicate_orders_count": 0,
  "duplicate_fills_count": 0,
  "duplicate_positions_count": 0,
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
  "brain_dialogue_latest_at": "2026-05-30T23:39:40.554786+00:00",
  "neuron_dialogue_latest_at": "2026-05-30T23:39:40.554786+00:00",
  "brain_dialogue_events": 7076,
  "neuron_dialogue_events": 1707,
  "top_current_blockers": [
    {
      "blocker": "MISSING_TRUSTED_ORDERBOOK",
      "count": 507
    }
  ],
  "warnings": [],
  "readiness_status": "GREEN",
  "latest_runtime": {
    "runtime_health": "OK",
    "scheduler_health": "HEALTHY",
    "latest_cycle_id": "v2-20260530T233853-c1bbeae5f2",
    "latest_cycle_at": "2026-05-30T23:38:53.323112+00:00"
  }
}
```

## Samples
```json
[]
```
