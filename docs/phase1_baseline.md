# Phase 1 Baseline

Phase 1 is GREEN when all Phase 1 migrations apply on PostgreSQL and the Phase 1 PG-backed tests pass.

Commands:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'
$env:PHASE1_PERSISTENCE_ENABLED='true'
python -m uv run python -m app.db.migrate
python -m uv run pytest tests\test_phase1_cycle_replay.py tests\test_phase1_execution_memory.py tests\test_phase1_closeout.py -q
python -m uv run pytest tests\test_stage4.py -q
```

Checkpoint contents:

- core cycle memory: `cycles`, `market_snapshots`, `ranking_snapshots`, `decision_ledger`
- execution memory: `live_orders`, `order_status_history`, `positions`, `position_events`
- closeout memory: `run_artifacts`, `rejection_ledger`
- operator reads: cycle summary, cycle rejections, market decision details, market order history, position lifecycle
