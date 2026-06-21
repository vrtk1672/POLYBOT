# Full Rebuild Defense 20 30-Minute Observation Report

## Purpose

Perform a clean POLYBOT rebuild/redeploy, start a fresh PAPER session with Defense 20, observe runtime for 30 minutes, capture Full Mesh forensic outputs, repair any clear in-scope bug, and report the actual PAPER lifecycle truth.

## Build / Redeploy Results

- `docker compose -f .\docker-compose.yml build api`: passed.
- `docker compose -f .\docker-compose.yml build migrate`: passed.
- `docker compose -f .\docker-compose.yml run --rm migrate`: passed, no pending migrations.
- `docker compose -f .\docker-compose.yml up -d --no-deps api`: passed.
- `.\tools\polybot.ps1 health`: `/healthz ok`, DB `OK`.

After the reporting patch, the API and migrate images were rebuilt again, migrations still had no pending changes, and API health remained OK.

## Pre-Flight Audit

- Git status: unavailable because `C:\Server\apps\polybot` is not a Git checkout.
- Required migrations present: `0146_paper_session_reset.sql`, `0147_paper_global_defense_level.sql`, `0148_same_market_side_arbitration.sql`, `0149_same_market_side_evidence_fields.sql`, `0150_opportunity_memory_intent_expiry.sql`.
- Required service files present: `paper_defense`, `paper_session`, `paper_intents`, `paper_runtime_decisions`, `paper_execution`, `same_market_arbitration`, `side_evidence`, `opportunity_mesh_coordinator`, `opportunity_memory`, `decision_autopsy`.
- `tools/polybot.ps1` exposes the expected status/report/defense/autopsy/opportunity-memory commands.
- `docker-compose.yml` exists.
- Pre-rebuild API health was reachable and returned `ok`.

## Baseline Session State

- Command: `.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20`.
- New active session: `paper_session_20260620T133422Z_63eb14ef`.
- Previous session archived: `paper_session_20260620T125338Z_a40c5a2e`.
- Starting balance: `1000.0`.
- Defense level: `20`.
- Adjusted threshold: `42.0`.
- Max deployed capital: `80%`.
- Max single trade: `15%`.
- Max open positions: `15`.
- Strategic blockers: `WARNING_ONLY`.
- Integrity blockers: `HARD`.
- Current session counts started at `0/0/0/0`.
- Historical totals were preserved.

## 30-Minute Timeline

| Time | Supervisor | Events | Triggers | Candidates | AI Insights | ENTER | Learning | Intents | Orders | Fills | Positions | Ready | Pending | Expired | Latest errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| T+0 | RUNNING | 7364 | 753 | 4641 | 1971 | 9 | 0 | 0 | 0 | 0 | 0 | 9 | 0 | 0 | none |
| T+5 | RUNNING | 7438 | 755 | 4643 | 1975 | 9 | 17 | 7 | 0 | 0 | 0 | 2 | 7 | 0 | none |
| T+10 | RUNNING | 7438 | 762 | 4650 | 1983 | 8 | 17 | 7 | 0 | 0 | 0 | 8 | 7 | 0 | none |
| T+15 | RUNNING | 7438 | 764 | 4654 | 1987 | 8 | 17 | 13 | 0 | 0 | 0 | 2 | 6 | 7 | none |
| T+20 | DEGRADED | 7518 | 769 | 4659 | 1991 | 9 | 17 | 13 | 0 | 0 | 0 | 2 | 6 | 7 | `UNEXPECTED_PAPER_INTENTS_DELTA:6` |
| T+25 | DEGRADED | 7518 | 774 | 4683 | 1999 | 9 | 17 | 13 | 0 | 0 | 0 | 2 | 0 | 13 | `UNEXPECTED_PAPER_INTENTS_DELTA:6` |
| T+30 | DEGRADED | 7518 | 778 | 4701 | 2007 | 9 | 17 | 13 | 0 | 0 | 0 | 2 | 0 | 13 | `UNEXPECTED_PAPER_INTENTS_DELTA:6` |

Post-repair 10-minute verification:

- Supervisor: `RUNNING`.
- Source refresh: `ACTIVE`.
- Recent events: `7673`.
- Triggers: `787`.
- Candidates: `4736`.
- AI insights: `2019`.
- Current session counts: intents/orders/fills/positions `13/0/0/0`.
- Latest errors: `none reported`.

## Runtime Continuity Verdict

`CONTINUOUS`.

Cycles advanced throughout the 30-minute run. The supervisor briefly reported `DEGRADED` because expected PAPER intent deltas were misclassified as latest errors. That reporting bug was repaired and the post-repair verification returned supervisor `RUNNING`.

## Hunting Verdict

`BROAD_HUNTING`.

The system continued adding events, triggers, candidates, AI insights, arbitration records, and Paper intent attempts. It did not stop at duplicates or blocked candidates.

## Defense 20 Verdict

Defense 20 was active and applied:

- Learning entries: `17`.
- Ignored blockers: `15`.
- Softened blockers: `15`.
- Fallback exits: `15`.
- Strategic blockers were softened/warnings.
- Integrity blockers remained hard.

## Opportunity Mesh Verdict

The Opportunity Mesh worked as a route/classify/read model:

- Active pool size: `17`.
- Ready for intent at T+30: `2`.
- Intent pending execution at T+30: `0`.
- Intent stuck at T+30: `0`.
- Intent expired at T+30: `13`.
- Softened by defense: `2`.
- Arbitrated demoted: `2`.
- Routed to execution: `13`.
- System errors: `0`.

## Intent Queue Verdict

Intent queue behavior was correct for stale non-executed intents:

- 13 current-session intents were created.
- 0 became orders/fills/positions.
- 13 expired as `EXPIRED_NO_EXECUTION`.
- 0 remained stuck.
- Each expired intent linked to an `opportunity_memory_*` row.

## Execution Verdict

No PAPER order/fill/position was created because the execution adapter found no executable intents.

Execution aggregate for the observation window:

- Execution runs: `16`.
- Intents checked: `53`.
- Blocked intents: `53`.
- Executable intents: `0`.
- Orders created: `0`.
- Main execution integrity blocker: `MISSING_TRUSTED_ORDERBOOK`.

This is not a Defense-level strategic blocker. It is an execution-validity/integrity blocker and was not softened.

## Opportunity Memory Verdict

Opportunity memory worked:

- Remembered opportunities: `13`.
- Waiting for new evidence: `13`.
- Reactivated opportunities: `0`.

No natural reactivation was observed because the expired opportunities did not receive a meaningful new evidence fingerprint during the run.

## Paper Session Counts And PnL

Current session after observation/post-repair:

- Paper intents: `13`.
- Paper orders: `0`.
- Paper fills: `0`.
- Paper positions: `0`.
- Open positions: `0`.
- Realized PnL: `0.0`.
- Unrealized PnL: `0.0`.
- Net PnL: `0.0`.

Historical totals remained visible separately:

- Historical paper intents: at least `105` by T+30.
- Historical paper orders: `31`.
- Historical paper fills: `28`.
- Historical paper positions: `31`.

Live/shadow/real remained `0/0/0`.

## Top Blockers

Decision-level top blocker:

- `OPPOSING_SIDE_DEMOTED_BY_ARBITRATION`: count `8`, expected, owner `SameMarketSideArbitrator`.

Execution-level top blocker:

- `MISSING_TRUSTED_ORDERBOOK`: all 53 checked execution intents were blocked by missing trusted execution orderbook.

## Errors / Noise Classification

Initial observation:

- `UNEXPECTED_PAPER_INTENTS_DELTA:6` appeared as a latest error at T+20 through T+30.
- Classification: reporting noise / false positive. Current mode was PAPER, and the delta was PAPER adapter ledger activity.

Repair:

- Updated `RuntimeSupervisorService` safety-delta classification so `paper_intents`, `paper_orders`, `paper_fills`, and `paper_positions` deltas are expected only when Governor mode is PAPER.
- Non-PAPER execution deltas such as `orders_v2`, `fills_v2`, `canonical_positions`, and live orders remain hard errors.

Post-repair:

- Latest errors: `none reported`.
- Runtime health: `RUNNING`.

## Files Changed

- `app/control_center/runtime_supervisor.py`
- `tests/test_control_center_runtime_supervisor.py`

## Migrations

No new migration was required.

## Tests Run

Focused after repair:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_control_center_runtime_supervisor.py tests/test_paper_delta_autopsy.py tests/test_report_autopsy_output.py -q
```

Result: `13 passed, 3 skipped`.

Required PAPER regression set:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py tests/test_same_market_side_arbitration.py tests/test_side_evidence.py tests/test_opportunity_mesh_coordinator.py tests/test_paper_intent_expiry.py tests/test_opportunity_memory.py tests/test_paper_execution_adapter_runtime.py tests/test_paper_session_status_report.py -q
```

Result: `6 passed, 12 skipped`.

Compile:

```powershell
.venv\Scripts\python.exe -m compileall app tests
```

Result: passed.

Skipped tests were local DB-fixture skips. Docker-backed runtime verification used the active API/Postgres environment.

## Report Artifacts

Observation run directory:

- `run_reports/full_rebuild_defense20_observation_20260620T133413Z/`

Session learning report:

- JSON: `run_reports/paper_session_learning_paper_session_20260620T133422Z_63eb14ef/paper_session_learning_report_paper_session_20260620T133422Z_63eb14ef.json`
- Markdown: `run_reports/paper_session_learning_paper_session_20260620T133422Z_63eb14ef/paper_session_learning_report_paper_session_20260620T133422Z_63eb14ef.md`
- CSV: `run_reports/paper_session_learning_paper_session_20260620T133422Z_63eb14ef/paper_session_trades_paper_session_20260620T133422Z_63eb14ef.csv`

## Remaining Bottleneck

Primary remaining bottleneck: `MISSING_TRUSTED_ORDERBOOK`.

The Full Mesh now reaches Paper intents, routes them to execution, expires stale non-executed intents, and remembers opportunities. The next repair should focus on trusted orderbook availability/selection for Paper execution candidates, not on Defense thresholds or blocker weakening.

## Safety Checklist

- PAPER only: YES.
- Live orders untouched: YES.
- Shadow orders untouched: YES.
- Real orders untouched: YES.
- No thresholds lowered: YES.
- No risk bypass: YES.
- No capital bypass: YES.
- No exit bypass: YES.
- Integrity blockers remain hard: YES.
- Historical Paper data preserved: YES.
- Current session counts remain session-scoped: YES.
- No fake activity: YES.
- No secrets printed: YES.

## Status

YELLOW.

The rebuild, migration, Defense 20 session, 30-minute observation, reporting capture, and in-scope reporting repair all completed. Runtime is continuous and safe, but no orders/fills/positions occurred because execution is blocked by trusted orderbook integrity.

Safe to continue Defense 20 PAPER runtime: YES.
