# POLYBOT 4h Technical Paper Soak Report

## Investigation Update

- investigation_status: STOPPED / PAPER_LINEAGE_INCONSISTENCY
- stopped_by: codex
- stopped_reason: stop soak due paper execution lineage consistency investigation
- stopped_at: 2026-05-31T00:53:37Z

The soak did not complete. It exposed a paper lineage anomaly: `paper_orders` and `paper_positions` increased from 3 to 6 while `paper_intents` and `paper_fills` stayed unchanged. The root cause was the legacy runtime paper path creating paper orders/positions without canonical `paper_fills` or `paper_trade_ledger` OPEN rows. This report must not be treated as a passed 4h soak.

## Quarantine Update

- quarantine_status: COMPLETED
- quarantined_positions: 3
- active paper lineage: OK after quarantine
- raw audit lineage: RED by design because quarantined legacy rows remain visible
- fake fills created: 0
- fake ledger rows created: 0
- rows deleted: 0

The three legacy positions were quarantined instead of repaired because no true paper fill or OPEN ledger evidence existed. They are excluded from active Paper truth and preserved for audit.

- status: RUNNING
- started_at: 2026-05-30T23:39:59Z
- expected_end_at: 2026-05-31T03:39:59Z
- process_id: 14268
- log_path: `logs/soak/4h_paper_soak_20260530T233959Z.log`
- stop_reason: NONE

## First Sample

The first sample was written at `2026-05-30T23:40:00.117963+00:00`.

```json
{
  "system_power": "ON",
  "runtime_health": "OK",
  "paper_intents": 3,
  "paper_orders": 3,
  "paper_fills": 3,
  "paper_positions": 3,
  "open_paper_positions": 0,
  "closed_paper_positions": 3,
  "paper_position_closes": 3,
  "paper_trade_ledger": 6,
  "paper_daily_pnl": 1,
  "realized_pnl": 23.25,
  "unrealized_pnl": 0.0,
  "orphan_positions_count": 0,
  "duplicate_orders_count": 0,
  "duplicate_fills_count": 0,
  "duplicate_positions_count": 0,
  "stale_price_count": 0,
  "live_orders": 0,
  "real_orders": 1,
  "orders_v2": 1,
  "fills_v2": 1,
  "canonical_positions": 0,
  "safety_delta": {
    "real_orders_current": 0,
    "orders_v2": 0,
    "fills_v2": 0,
    "canonical_positions": 0
  }
}
```

## Note

The safe Paper Exit Loop closed the three open paper positions after the Governor was moved to PAPER and before the runner baseline was captured. The close rows and realized PnL are persisted paper ledger truth, not live or real execution.
