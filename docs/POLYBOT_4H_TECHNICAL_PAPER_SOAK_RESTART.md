# POLYBOT 4h Technical Paper Soak Restart

## Purpose

Restart the 4h Technical Paper Soak after legacy paper row quarantine, using active paper lineage truth only while preserving raw quarantined legacy rows for audit.

## Preconditions

- SYSTEM OFF before preflight.
- Runtime mode PAPER.
- Live and shadow disabled.
- Active paper lineage clean.
- Quarantined legacy rows preserved and excluded from active paper truth.
- Targeted paper, lineage, soak, dashboard, system power, brain dialogue, and neuron dialogue tests pass.

## Soak Guard Contract

The soak runner samples runtime and dashboard truth every 5 minutes. It hard-stops and requests SYSTEM OFF if any critical safety, lineage, API, mock-data, duplicate, orphan, quarantine-growth, or live/real mutation condition appears.

Active lineage must remain:

- `paper_lineage_consistency_status=OK`
- `paper_lineage_readiness_status=OK`
- `positions_without_fills_count=0`
- `positions_without_open_ledger_count=0`

Raw quarantine must remain stable:

- `raw_positions_without_fills_count=3`
- `raw_positions_without_open_ledger_count=3`
- `quarantined_paper_positions_count=3`

## Active Run

- soak_id: `20260531T073303Z`
- status at restart handoff: RUNNING
- pid: `11112`
- log: `logs/soak/4h_paper_soak_20260531T073303Z.log`
- report: `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260531T073303Z.md`
- started_at_utc: `2026-05-31T07:33:03Z`
- expected_end_utc: `2026-05-31T11:33:03Z`
- started_at_asia_jerusalem: `2026-05-31T10:33:03+03:00`
- expected_end_asia_jerusalem: `2026-05-31T14:33:03+03:00`

## Monitor

```powershell
Get-Content -Wait logs\soak\4h_paper_soak_20260531T073303Z.log
```

## Stop

```powershell
Stop-Process -Id 11112
Invoke-RestMethod -Method Post -ContentType 'application/json' -Body '{"actor":"operator","reason":"manual_stop_4h_soak","correlation_id":"20260531T073303Z"}' -Uri 'http://127.0.0.1:8000/system/power/off'
```

## 12h Status

Do not start 12h until the 4h report completes GREEN and ChatGPT review is done.
