# POLYBOT Observation Run Failure Analysis

Generated: 2026-06-02T07:05Z
Scope: 4h observation run forensics only. No new observation run was started.

## Reported Run

- PID reported at launch: 7888
- Start UTC: 2026-06-02T00:23:01Z
- Expected end UTC: 2026-06-02T04:23:01Z
- Log: logs/overnight/overnight_observation_20260602T002301Z.log
- Report: docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md

## Actual Status

COMPLETED.

The runner completed the full 4-hour window and wrote a final GREEN report.

- started_at: 2026-06-02T00:23:01.877177+00:00
- finished_at: 2026-06-02T04:23:04.733257+00:00
- actual duration: 4h 0m 2.856s
- samples: 48
- stop_reason: NONE
- final status: GREEN
- PID after completion: not present, expected because the process exited normally

## Evidence

`docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md` begins with:

```text
- status: GREEN
- started_at: 2026-06-02T00:23:01.877177+00:00
- finished_at: 2026-06-02T04:23:04.733257+00:00
- samples: 48
- stop_reason: NONE
```

The final log event is:

```json
{"event":"final","report_path":"docs\\POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md","status":"GREEN","stop_reason":null,"timestamp":"2026-06-02T04:23:04.775784+00:00"}
```

The launcher stdout also confirms:

```json
{"status":"GREEN","log_path":"logs\\overnight\\overnight_observation_20260602T002301Z.log","report_path":"docs\\POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md","samples":48,"stop_reason":null}
```

## Why It Looked Like It Did Not Continue

There are three likely contributors:

1. The launched PID no longer existed after the expected end time because the run completed normally.
2. `docs/POLYBOT_4H_OBSERVATION_REPORT_20260602T002301Z.md` was a starter/status note, not the runner-owned final report. The final report was written to `docs/POLYBOT_OVERNIGHT_OBSERVATION_REPORT_20260602T002301Z.md`.
3. Two earlier launch artifacts exist:
   - `overnight_observation_launcher_20260602T002023Z.err.log` shows an argument parsing failure from an unquoted reason string.
   - `overnight_observation_20260602T002107Z.log` was an earlier short-lived attempt that was stopped after the first sample to patch safe-yellow classification for the intentionally disabled legacy `news_provider`.

The reported final run is the `20260602T002301Z` run, and it completed.

## Safety During Run

The final sample stayed clean:

- SYSTEM power: OFF
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
- safety deltas for real orders/orders_v2/fills_v2/canonical positions/paper ledger: 0
- paper_lineage: OK
- capital_reconciliation_status: OK
- realized_pnl: 23.55
- unrealized_pnl: 0.0

## Conclusion

The reported 4h observation run did not fail. It completed GREEN. The apparent failure was a reporting/expectation issue around process lifetime and the distinction between the starter status report and the runner final report.
