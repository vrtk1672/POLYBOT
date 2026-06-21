# POLYBOT 4h Observation Report

Run id: overnight_observation_20260602T002301Z
Status at start: RUNNING
PID: 7888

## Schedule

- Start UTC: 2026-06-02T00:23:01Z
- Expected end UTC: 2026-06-02T04:23:01Z
- Start local: 2026-06-02T03:23:01+03:00
- Expected end local: 2026-06-02T07:23:01+03:00
- Duration: 4 hours
- Sample interval: 5 minutes

## Paths

- Log: logs/overnight/overnight_observation_20260602T002301Z.log
- Runner report: docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md
- This report: docs/POLYBOT_4H_OBSERVATION_REPORT_20260602T002301Z.md

## Preflight

- Result: SAFE-YELLOW
- Blockers: none
- Safe-yellow reason: AI_CONTEXT_UNAVAILABLE with AI_REQUIRED=false
- SYSTEM power: OFF
- Runtime health: SAFE_STOPPED
- Source status: OK
- Paper readiness: GREEN
- Overnight safety: GREEN
- Dashboard mock_data: false

## AI Provider Status

- Ollama: OLLAMA_TIMEOUT
- OpenAI: OPENAI_RATE_LIMITED
- Anthropic: ANTHROPIC_DEGRADED
- Final AI context status: AI_CONTEXT_UNAVAILABLE
- Fake AI context emitted: no
- Runtime continues: yes

## First Sample Metrics

- endpoint_errors: []
- mock_data_endpoints: []
- unsafe_degraded_sources: []
- provider_failure: false
- repeated_provider_failures: 0
- live_orders: 0
- real_orders_current: 1
- orders_v2: 1
- fills_v2: 1
- canonical_positions: 0
- safety_delta.real_orders_current: 0
- safety_delta.orders_v2: 0
- safety_delta.fills_v2: 0
- safety_delta.canonical_positions: 0
- paper_intents: 6
- paper_orders: 9
- paper_fills: 6
- paper_positions: 9
- open_positions: 0
- active_positions_without_fills: 0
- paper_lineage: OK
- capital_reconciliation_status: OK
- realized_pnl: 23.55
- unrealized_pnl: 0.0
- forensics_active_count: 6
- forensics_quarantined_count: 3

## Monitor

PowerShell:

```powershell
Get-Content -Wait logs\overnight\overnight_observation_20260602T002301Z.log
Get-Process -Id 7888
```

## Stop

PowerShell:

```powershell
Stop-Process -Id 7888
```

After a manual stop, verify SYSTEM OFF:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/system/power
```

## Current Status

The run was started safely and produced a clean first sample. Final completion status will be written by the runner report if the process reaches the 4-hour end or hits a hard-stop.
