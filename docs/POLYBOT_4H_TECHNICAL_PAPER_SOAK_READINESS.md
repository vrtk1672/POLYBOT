# POLYBOT 4h Technical Paper Soak Readiness

## Preflight Status

Status is machine-readable at:

- `GET /dashboard/api/v2/paper/soak-readiness`

The soak may start only when `readiness_status=GREEN` and `can_start_4h_soak=true`.

## Required Services

- FastAPI: `/healthz`
- Runtime health: `/runtime/health`
- System power: `/system/power`
- Paper dashboard truth: `/dashboard/api/v2/paper`
- Paper positions: `/dashboard/api/v2/paper/positions`
- Paper PnL: `/dashboard/api/v2/paper/pnl`
- Brain dialogue: `/dashboard/api/v2/brain-dialogue`
- Neuron dialogue: `/dashboard/api/v2/neuron-dialogue`

## Required DB Tables

- `system_state`
- `runtime_cycles_v2`
- `brain_mesh_activation_runs`
- `evidence_refresh_runs`
- `side_evidence_recovery_runs`
- `post_side_risk_exit_recovery_runs`
- `paper_intents`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_position_closes`
- `paper_trade_ledger`
- `paper_daily_pnl`
- `paper_execution_runs`
- `paper_exit_loop_runs`
- `brain_dialogue_events`
- `orders_v2`
- `fills_v2`
- `positions`
- `live_orders`

## Safety Locks

- `live_orders` must remain `0`.
- `live_enabled` must remain `false`.
- `shadow_enabled` must remain `false`.
- `orders_v2`, `fills_v2`, and canonical `positions` must not increase during the paper soak.
- Dashboard responses must report `mock_data=false`.
- No fake paper orders, fills, positions, or PnL may be inserted.

## Baseline

Capture before soak:

- `paper_intents_total`
- `paper_orders_total`
- `paper_fills_total`
- `paper_positions_total`
- `open_paper_positions`
- `closed_paper_positions`
- `paper_position_closes`
- `paper_trade_ledger`
- `paper_daily_pnl`
- `brain_dialogue_events`
- `neuron_dialogue_events`
- `live_orders`
- `real_orders_current`
- `orders_v2`
- `fills_v2`
- `canonical_positions`

## Expected Observations

- SYSTEM ON remains active.
- Runtime cycles continue.
- Brain Mesh, evidence refresh, side evidence, risk/exit, eligibility, paper intent gate, paper execution, paper exit, PnL, and dialogue timestamps advance when real work exists.
- Paper artifacts remain internally consistent.
- Open paper positions are observed by the exit loop.
- PnL is derived from paper ledger truth or explicitly reports unavailable/stale mark price.

## Stop Conditions

The runner stops and posts `SYSTEM OFF` if any critical condition occurs:

- `live_orders > 0`
- real order delta increases
- `orders_v2`, `fills_v2`, or canonical `positions` increase unexpectedly
- `paper_orders` increases while `paper_intents` is unchanged
- `paper_positions` increases while `paper_fills` is unchanged
- `paper_positions` increases without matching `paper_trade_ledger` growth
- duplicate paper fills or positions are detected
- duplicate lineage is detected by source intent, order, fill, or position
- orphan paper positions are detected
- paper positions without `paper_fill_id` are detected
- paper positions without OPEN ledger rows are detected
- `paper_lineage_consistency_status != OK`
- `paper_lineage_readiness_status != OK`
- quarantine count increases during the soak
- fake/mock dashboard data is detected
- critical PnL reconciliation failure
- runtime health is `RED`
- repeated API or DB unavailability

## Pass Criteria

- Four full hours elapsed.
- Final report exists.
- No stop condition occurred.
- Safety deltas for real/live execution are zero.
- Dashboard truth remains `mock_data=false`.
- Quarantined legacy rows, if any, remain stable and auditable.

## Commands

Preflight:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/paper/soak-readiness
```

Run:

```powershell
.\scripts\run_4h_technical_paper_soak.ps1 -BaseUrl http://127.0.0.1:8000
```

Monitor:

```powershell
Get-Content .\logs\soak\4h_paper_soak_<timestamp>.log -Tail 20 -Wait
```

Stop:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/system/power/off -ContentType application/json -Body '{"actor":"operator","reason":"manual paper soak stop"}'
```

## Log Paths

- `logs/soak/4h_paper_soak_<timestamp>.log`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_<timestamp>.md`
