# POLYBOT Legacy Paper Row Quarantine

## Status

GREEN for active Paper truth.

Three legacy `EXECUTION_AWARE_PAPER` positions from the interrupted 4h soak were quarantined. They remain in `paper_positions` and are auditable through `paper_lineage_quarantine`, but they are excluded from active Paper truth, active open position counts, and active unrealized PnL.

## Why Quarantine

Repair was not truthful because the rows had:

- no `source_intent_id`
- no `paper_fill_id`
- no matching `paper_fills` row
- no OPEN `paper_trade_ledger` row
- no matching paper intent

Creating fills or ledger rows after the fact would fabricate lineage and PnL. The correct action was quarantine.

## Quarantined Rows

- `f929eb8a-54cd-4635-86b7-3becae5eba0d`
- `a0a5a06b-5419-4e2a-afd5-47f56e34af39`
- `0d423170-fc01-4292-9dee-69a690610419`

Each row was marked:

- `consistency_status='QUARANTINED'`
- `current_status='QUARANTINED'`
- `excluded_from_active_paper_truth=true`
- `invalidated_at` set
- `quarantine_reason='LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER'`
- `quarantine_source='PaperLineageQuarantineService'`

## Dashboard Truth

After quarantine:

- active `positions_without_fills_count=0`
- active `positions_without_open_ledger_count=0`
- `paper_lineage_readiness_status=OK`
- `paper_lineage_consistency_status=OK`
- raw audit counts remain visible:
  - `raw_positions_without_fills_count=3`
  - `raw_positions_without_open_ledger_count=3`
  - `quarantined_paper_positions_count=3`
- soak readiness may be GREEN with warning `QUARANTINED_LEGACY_PAPER_POSITIONS_PRESENT`

## Operator Endpoints

- `POST /paper/lineage/quarantine/run`
- `GET /paper/lineage/quarantine/audit`
- `GET /dashboard/api/v2/paper`
- `GET /dashboard/api/v2/paper/soak-readiness`

## Safety

No rows were deleted. No fake fills, fake ledger rows, fake closes, or fake PnL were created. `orders_v2`, `fills_v2`, canonical `positions`, and `live_orders` were unchanged.
