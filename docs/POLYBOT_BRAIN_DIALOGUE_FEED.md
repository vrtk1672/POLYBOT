# POLYBOT Brain Dialogue Feed

POLYBOT Brain Dialogue Feed is an observational layer for the living Brain Mesh.
It does not trade, approve risk, complete exits, create eligibility, create paper
artifacts, or mutate execution state. It only materializes factual dialogue rows
from existing DB/runtime source records.

## Source Of Truth

Dialogue events are persisted in `brain_dialogue_events`.
Each row cites a source table and source record, with a uniqueness guard on
`source_table + source_record_id + event_type` so dashboard reads cannot create
duplicates.

Supported source records include:

- `system_power_transitions`
- `runtime_cycles_v2`
- `event_log` rows from `data_foundation`
- `brain_mesh_activation_runs`
- `evidence_refresh_runs`
- `side_evidence_recovery_runs`
- `downstream_evidence_recompute_runs`
- `post_side_risk_exit_recovery_runs`
- `risk_decisions`
- `exit_plans`
- `paper_eligibility_candidates`
- `paper_intent_runs` and `paper_intents`
- `paper_execution_runs` and `paper_positions`
- `paper_exit_loop_runs`
- `paper_daily_pnl`
- `no_trade_log`

## Runtime Behavior

`MarketService.refresh()` calls `BrainDialogueService.materialize_recent()` at
the end of the safe runtime cycle, after paper exit/PnL checks. If SYSTEM OFF is
active, normal component dialogue is blocked. Optional system power dialogue may
be materialized from `system_power_transitions`, but no data/brain/evidence/risk
or paper dialogue is produced while OFF.

## API

- `GET /dashboard/api/v2/brain-dialogue`
- `GET /dashboard/api/v2/system-life`
- `GET /dashboard/api/v2/brain-dialogue/{candidate_id}`

All endpoints are read-only and return `mock_data=false`.

## Safety Contract

- Dialogue is observational only.
- Every dialogue row requires a real source record.
- Dashboard reads do not materialize events.
- SYSTEM OFF blocks normal dialogue generation.
- Component activity is based on recent source/dialogue rows, not decorative
  service registry status.
- Live and real orders remain disabled and unchanged.

## Known Gap

`Dashboard Truth` is shown on the System Life Screen as not yet wired because
there is no independent dashboard-run source table. The endpoints themselves
return `mock_data=false`, but the dialogue feed does not invent a dashboard
component source record.
