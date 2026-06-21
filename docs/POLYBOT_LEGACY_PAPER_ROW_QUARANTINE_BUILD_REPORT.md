# POLYBOT Legacy Paper Row Quarantine Build Report

## Current Reality Found

Before quarantine:

- SYSTEM was OFF.
- no 4h soak runner process was found.
- `paper_intents=3`
- `paper_orders=6`
- `paper_fills=3`
- `paper_positions=6`
- `open_paper_positions=3`
- `closed_paper_positions=3`
- `paper_position_closes=3`
- `paper_trade_ledger=6`
- `paper_daily_pnl=2`
- `positions_without_fills_count=3`
- `positions_without_open_ledger_count=3`
- `quarantined_paper_positions_count=0`
- `paper_lineage_consistency_status=RED`
- soak readiness `RED`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`

## Bad Position Traces

### `f929eb8a-54cd-4635-86b7-3becae5eba0d`

- market_id: `629035`
- side: `YES`
- status: `OPEN`
- entry_price: `0.230000`
- quantity: `60.304000`
- opened_at: `2026-05-30T23:41:27.746835Z`
- source_intent_id: none
- paper_order_id: `2ad1cb21-a481-4b7f-9726-8415a6704ed0`
- paper_fill_id: none
- matching paper_order: YES
- matching paper_fill: NO
- matching paper_intent: NO
- OPEN ledger row: NO
- CLOSE ledger row: NO
- close row: NO
- source service: `EXECUTION_AWARE_PAPER`
- recommended action: QUARANTINE

### `a0a5a06b-5419-4e2a-afd5-47f56e34af39`

- market_id: `678929`
- side: `YES`
- status: `OPEN`
- entry_price: `0.190000`
- quantity: `97.315000`
- opened_at: `2026-05-30T23:41:27.851953Z`
- source_intent_id: none
- paper_order_id: `6504b45d-44eb-4b3b-8fea-74dda88fddb2`
- paper_fill_id: none
- matching paper_order: YES
- matching paper_fill: NO
- matching paper_intent: NO
- OPEN ledger row: NO
- CLOSE ledger row: NO
- close row: NO
- source service: `EXECUTION_AWARE_PAPER`
- recommended action: QUARANTINE

### `0d423170-fc01-4292-9dee-69a690610419`

- market_id: `678937`
- side: `NO`
- status: `OPEN`
- entry_price: `0.190000`
- quantity: `31.589000`
- opened_at: `2026-05-30T23:41:27.951263Z`
- source_intent_id: none
- paper_order_id: `ab9bd908-2b01-4b88-850b-eb5b68b8047e`
- paper_fill_id: none
- matching paper_order: YES
- matching paper_fill: NO
- matching paper_intent: NO
- OPEN ledger row: NO
- CLOSE ledger row: NO
- close row: NO
- source service: `EXECUTION_AWARE_PAPER`
- recommended action: QUARANTINE

## Repair Decision

Repair was rejected. There was no true fill evidence and no OPEN ledger evidence for the three positions. Creating fills or ledger rows would be fake lineage and fake accounting.

Quarantine was chosen.

## Files Created

- `app/db/migrations/0097_legacy_paper_lineage_quarantine.sql`
- `app/services/paper_lineage_quarantine.py`
- `tests/test_paper_lineage_quarantine.py`
- `docs/POLYBOT_LEGACY_PAPER_ROW_QUARANTINE.md`
- `docs/POLYBOT_LEGACY_PAPER_ROW_QUARANTINE_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/paper_dashboard_truth.py`
- `scripts/run_4h_technical_paper_soak.py`
- `tests/test_soak_runner_paper_consistency_guards.py`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_READINESS.md`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260530T233959Z.md`

## DB Migration

Applied:

- `0097_legacy_paper_lineage_quarantine.sql`

Adds:

- quarantine/status fields to `paper_positions`
- `paper_lineage_quarantine` audit table

No destructive DB command was run.

## Runtime Quarantine Result

`POST /paper/lineage/quarantine/run` returned:

- status: `OK`
- quarantined_count: `3`

Second run was idempotent:

- quarantined_count: `0`
- `paper_lineage_quarantine` remained one audit record per quarantined position

## After Counts

- `paper_intents=3`
- `paper_orders=6`
- `paper_fills=3`
- `paper_positions=6`
- `open_paper_positions=0`
- `active_open_paper_positions=0`
- `raw_open_paper_positions=0`
- `closed_paper_positions=3`
- `paper_position_closes=3`
- `paper_trade_ledger=6`
- `paper_daily_pnl=2`
- `positions_without_fills_count=0`
- `raw_positions_without_fills_count=3`
- `positions_without_open_ledger_count=0`
- `raw_positions_without_open_ledger_count=3`
- `quarantined_paper_positions_count=3`
- `paper_lineage_consistency_status=OK`
- `paper_lineage_consistency_raw_status=RED`
- `paper_lineage_readiness_status=OK`
- soak readiness: `GREEN`
- `can_start_4h_soak=true`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`

## Tests Run

Quarantine focused:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_paper_lineage_quarantine.py tests/test_soak_runner_paper_consistency_guards.py -q
```

Result:

- `7 passed`

Broader targeted regression:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py tests/test_paper_dashboard_truth.py tests/test_soak_runner_paper_consistency_guards.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_paper_pnl_reconciliation.py tests/test_paper_no_live_safety.py tests/test_paper_no_orphans_duplicates.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_brain_dialogue_service.py tests/test_brain_dialogue_materialization.py tests/test_dashboard_brain_dialogue_api.py tests/test_neuron_dialogue_sources.py tests/test_neuron_dialogue_coverage_service.py tests/test_dashboard_neuron_dialogue_api.py -q
```

Result:

- `59 passed, 1 warning in 292.00s`

## Runtime Smoke

SYSTEM was turned ON for a short validation window and then OFF.

Before/mid/after:

- `paper_orders=6 -> 6 -> 6`
- `paper_fills=3 -> 3 -> 3`
- `paper_positions=6 -> 6 -> 6`
- `quarantined_paper_positions=3 -> 3 -> 3`
- `active_open_paper_positions=0 -> 0 -> 0`
- `positions_without_fills_count=0 -> 0 -> 0`
- `positions_without_open_ledger_count=0 -> 0 -> 0`
- `paper_lineage_readiness_status=OK -> OK -> OK`
- `live_orders=0 -> 0 -> 0`
- `orders_v2=1 -> 1 -> 1`
- `fills_v2=1 -> 1 -> 1`
- canonical `positions=0 -> 0 -> 0`

Final SYSTEM state: OFF.

## Safety Confirmation

- No live/shadow enablement.
- No real orders.
- No live orders.
- No mutation of `orders_v2`, `fills_v2`, or canonical `positions`.
- No fake fills.
- No fake ledger rows.
- No fake PnL.
- No rows deleted.

## Remaining Risks

Soak readiness is GREEN for active Paper truth, but a human/ChatGPT review is still required before starting the next 4h soak. Quarantined legacy rows remain visible as raw audit issues by design.

## Phase Status

GREEN pending required ChatGPT review.
