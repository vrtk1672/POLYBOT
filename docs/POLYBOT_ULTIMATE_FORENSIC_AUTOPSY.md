# POLYBOT Ultimate Forensic Autopsy

Date: 2026-06-14
Repository: `C:\Server\apps\polybot`
Mode: read-only forensic investigation
Status: YELLOW
Confidence: HIGH for static/runtime/DB facts inspected; MEDIUM for full dead-code classification because the repository has 870 Python files and no Git metadata in this folder.

## 1. Executive Summary

POLYBOT is not dead, but it is not a fully living Neural Mesh either.

The current system is best classified as a `PARTIAL_MESH` and `PARTIALLY_CONTINUOUS` runtime: FastAPI, Postgres, Redis, health truth, event logging, market refresh, data foundation, signal production, brain outputs, coordinator decisions, paper ledgers, no-trade ledgers, and Control Center truth surfaces exist and are real. However, the effective runtime observed during this audit is `SAFE_STOPPED`: system power is `OFF`, current mode is `DATA_ONLY`, scheduler is `BLOCKED_BY_MODE`, `/health` has no in-process refresh, and paper simulation is disabled.

The strongest runtime path is still centered on `MarketService.refresh()`. It performs scanner/data/intelligence/evidence/recovery/paper-intent/paper-execution/paper-exit/neural-event-bus/dialogue work sequentially inside one refresh cycle. That is richer than a simple scanner, but it is not a true autonomous nervous system where events independently wake multiple brains and continuously affect open positions.

The most important paper-trading truth is this:

- Candidate/eligibility records are still being created.
- Fresh paper intents/orders/fills/positions are not being created now.
- Paper intent creation stopped on 2026-06-03.
- Latest eligibility/no-trade/risk/exit rows were refreshed on 2026-06-11.
- The main blockers are risk, exit readiness, missing side/market/orderbook/binding, stale intent/orderbook freshness, and system power being off.

## 2. Final Classifications

| Area | Classification | Evidence |
| --- | --- | --- |
| System | `PARTIAL_MESH` | `neuron_signals=25081`, `brain_outputs=20494`, `coordinator_decisions=20458`, but event consumers are sparse and major work is refresh/manual-run driven. |
| Runtime | `PARTIALLY_CONTINUOUS` / currently `SAFE_STOPPED` | Docker API is up; scheduler exists; current `/runtime/health` says `SAFE_STOPPED`, system power `OFF`, scheduler `BLOCKED_BY_MODE`. |
| Paper | `PARTIAL` / currently `BLOCKED` | Historical paper rows exist: 20 intents, 12 orders, 9 fills, 12 positions; no fresh orders since 2026-06-03. |
| Control Center | `PARTIAL_TRUTH` | Frontend/backend use real truth envelopes and ledger-backed data, but many screens are partial/not implemented and status can look healthier than row activity. |
| Neural Mesh | `PARTIAL_NERVOUS_SYSTEM` | Mesh tables and producer/brain/coordinator rows exist, but event delivery and autonomous consumers are not broad enough for `REAL_NERVOUS_SYSTEM`. |

## 3. Repository Map

Static inventory:

- Python files under `app`: 870.
- Public DB tables: 323.
- Migrations: 127 SQL files, `0001` through `0127` with gaps.
- FastAPI route decorators found statically: 427.
- Frontend Control Center source files: React/TypeScript under `frontend/control-center/src`.

Major active/partial/legacy areas:

| Area | Key paths | Classification | Evidence |
| --- | --- | --- | --- |
| FastAPI runtime | `app/main.py`, `app/scheduler.py` | ACTIVE | Docker API up on `8000`; `/healthz` returns ok. |
| Canonical refresh | `app/ingestion/market_service.py` | PARTIALLY_ACTIVE | Central cycle exists, but blocked while system power OFF. |
| State Governor | `app/runtime/state_governor.py`, `app/api/runtime_routes.py` | ACTIVE | `/runtime/state` returns `DATA_ONLY`, system power `OFF`, all trading permissions false. |
| System power | `app/services/system_power.py`, `app/api/system_power_routes.py` | ACTIVE | `/system/power` returns DB-backed OFF state. |
| Runtime supervisor | `app/control_center/runtime_supervisor.py` | PARTIALLY_ACTIVE | Starts through SYSTEM ON; not running in current process. |
| Full Monitor Run | `app/control_center/full_monitor_run_service.py` | PARTIALLY_ACTIVE | Available, process-local; status says no run started in this process. |
| Event bus | `app/events/event_bus.py`, `app/neural_bus/service.py` | PARTIALLY_ACTIVE | `event_log=548388`, `neural_events=3996`, `neural_event_delivery=1`. |
| Data foundation | `app/data_foundation`, `app/services/orderbook_snapshots.py` | ACTIVE/PARTIAL | Markets/orderbooks exist; latest snapshots from 2026-06-11. |
| Neural mesh | `app/neural_mesh`, `app/services/runtime_*`, `app/services/neuron_*` | PARTIALLY_ACTIVE | Signal/brain/coordinator rows exist; event delivery sparse. |
| Paper trading | `app/services/paper_*`, canonical `paper_*` tables | PARTIAL/BLOCKED | Historical orders/fills/positions exist; current gates block fresh paper. |
| Risk/exit | `app/services/risk_core.py`, `app/services/exit_foundation.py` | PARTIALLY_ACTIVE | 20,162 risk decisions and exit plans, mostly blocking/not execution-allowed. |
| Opportunity/strategy V2 | `app/opportunity`, `app/strategy` | INACTIVE/SKELETON | `opportunity_scores_v2=0`, `strategy_routes_v2=0`. |
| Dashboard API | `app/api/routes.py`, `app/services/query/*`, `app/control_center/*` | ACTIVE/PARTIAL | GET endpoints return real DB counts and truth envelopes. |
| Control Center frontend | `frontend/control-center/src` | ACTIVE/PARTIAL | Cockpit and page shells use read-only endpoints and action wrapper. |
| Legacy paper | `app/stage3`, `logs/paper_trading.db` | LEGACY | AGENTS declares Stage 3 SQLite paper legacy/reference only. |
| Legacy root scripts | `brain.py`, `gamma_crawler.py` | UNKNOWN/LEGACY | Present but not canonical startup path. |

Most imported static dependencies:

- `app/db/connection.py`: 242 importing files.
- `app/events/event_bus.py` and `app/events/types.py`: 60 each.
- `app/runtime/modes.py`: 46.
- `app/runtime/state_governor.py`: 42.
- `app/services/system_power.py`: 34.

## 4. Runtime Map

Canonical startup:

1. `scripts/start_runtime.ps1` loads env, pins DB to local Postgres, disables live, enables kill switch defaults, starts `python -m uv run polybot`.
2. `app/main.py` builds FastAPI, `GammaClient`, `MarketService`, and `RefreshScheduler`.
3. Lifespan initializes `SafeStartupPolicy`, registers service-health labels, and starts `RefreshScheduler`.
4. Scheduler calls `MarketService.refresh()` every configured interval after initial delay.
5. Scheduler uses `StateGovernor.can_execute(COLLECT_DATA)` before refresh.

Observed runtime:

- Docker containers up: `polybot_api`, `polybot_postgres`, `polybot_postgres_test`, `polybot_redis`.
- `/healthz`: ok.
- `/health`: degraded because this process has no in-memory refresh yet.
- `/runtime/state`: `DATA_ONLY`, `system_power=OFF`, all paper/shadow/live permissions false.
- `/runtime/health`: `overall_status=SAFE_STOPPED`, scheduler `BLOCKED_BY_MODE`.
- Last successful runtime cycle: `v2-20260611T000525-e5b64cb06e`, completed at 2026-06-11 00:08:15 UTC.
- Active cycle row: `v2-20260610T230408-23b2e8c62b`, status `RUNNING`, intelligence not finished. This is stale historical truth, not a live current cycle.

## 5. Activation Map

| Trigger | Actual behavior | DB/runtime changes | Current observed state |
| --- | --- | --- | --- |
| App startup | Starts FastAPI and scheduler task. | Registers service health names; scheduler emits blocked events if Governor denies collection. | API up; scheduler blocked by system power OFF. |
| Docker startup | Starts API, Postgres, test Postgres, Redis. | DB persists from prior runs. | All listed containers healthy. |
| SYSTEM ON | `ControlCenterActionService` ensures `DATA_ONLY`, turns power ON, starts Runtime Supervisor. | Writes `system_state`, `system_state_history`, `system_power_transitions`. | Not currently ON. Last state is OFF. |
| SYSTEM OFF | Disables paper simulation, stops supervisor, turns power OFF. | Writes system state/history and paper simulation metadata. | Current power OFF from 2026-06-11. |
| PAPER SIMULATION ON | Requires system ON, DATA_ONLY, and Governor permission for paper simulation. | Stores metadata under `system_state.metadata_json.paper_simulation`. | Disabled. |
| PAPER SIMULATION OFF | Disables explicit paper simulation. | Updates state metadata. | Disabled by last system-off sequence. |
| FULL MONITOR RUN | Starts bounded background read-only/report run. | Writes process-local run reports, not DB lifecycle truth. Skips paper execution. | No run in this process. |
| KILL | Stops supervisor, disables paper simulation, activates Governor KILL. | Writes state transition. | Not active. |
| REFRESH | Scheduler calls `MarketService.refresh()` if Governor allows collection. | Writes runtime cycle, event log, market snapshots, signals, brains, eligibility/no-trade, paper stages if gates allow. | Blocked by power OFF. |

## 6. Continuous Process Trace

Long-running or loop-capable components:

| Process | Start condition | Frequency | Output | Current state |
| --- | --- | --- | --- | --- |
| FastAPI app | Docker/API process start | Continuous HTTP server | Routes, health, dashboard | Running. |
| `RefreshScheduler` | FastAPI lifespan | configured interval, default 60s | Runtime cycle events; calls `MarketService.refresh()` | Running but blocked by Governor/system power. |
| `RuntimeSupervisorService` | SYSTEM ON action | 30-300s interval | Read-only modules; optional paper simulation cycle | Not running in current process. |
| `FullMonitorRunService` | Start monitoring action | bounded run interval | Read-only report files | Not running in current process. |
| EventBus auto-dispatch | On `EventBus.publish()` | Synchronous in-process | Delivery attempts if consumers exist | Limited; `event_consumers=0`. |
| Neural bus delivery | Called from `MarketService.refresh()` | Per refresh | `neural_event_delivery` | Sparse; only 1 delivery row. |
| Paper execution loop | Supervisor paper cycle or refresh call | Per cycle when gates allow | Paper orders/fills/positions | Blocked/stale. |
| Paper exit loop | Refresh/supervisor paper cycle | Per cycle when called | closes/PnL | Latest exit check 2026-06-11; no open positions now. |

Conclusion: POLYBOT has loops, but most domain services are not independent resident workers. They run from scheduler refresh, supervisor cycle, or manual Control Center actions.

## 7. Database Map

Public tables: 323.

Key row/freshness evidence:

| Table | Rows | Latest timestamp | Classification |
| --- | ---: | --- | --- |
| `system_state` | 1 | 2026-06-11 00:07:31 | ACTIVE |
| `runtime_cycles_v2` | 11,593 | 2026-06-11 00:05:25 | STALE/RUN_HISTORY |
| `service_health` | 30 | 2026-06-14 00:12:20 | ACTIVE |
| `event_log` | 548,388 | 2026-06-14 00:12:25 | ACTIVE, mostly blocked scheduler events now |
| `neural_events` | 3,996 | 2026-06-10 22:32:09 | PARTIAL/STALE |
| `neural_event_delivery` | 1 | 2026-05-31 22:54:59 | PARTIAL/STALE |
| `event_consumers` | 0 | n/a | INACTIVE |
| `neural_event_consumers` | 1 | n/a | PARTIAL |
| `markets_v2` | 13 | 2026-06-11 00:05:34 | STALE |
| `market_snapshots` | 115,458 | 2026-06-11 00:05:32 | STALE |
| `market_snapshots_v2` | 115,460 | 2026-06-11 00:05:34 | STALE |
| `orderbook_snapshots` | 50,652 | 2026-06-11 00:05:50 | STALE for execution |
| `source_status` | 12 | 2026-06-10 22:32:09 | STALE |
| `neuron_registry` | 22 | 2026-05-21+ | ACTIVE CONFIG |
| `neuron_health` | 22 | 2026-06-11 | PARTIAL |
| `neuron_producers` | 6 | 2026-05-21+ | ACTIVE CONFIG |
| `neuron_signals` | 25,081 | 2026-06-11 00:05:37 | STALE |
| `neuron_signal_bindings` | 25,023 | 2026-06-11 00:05:37 | STALE |
| `brain_outputs` | 20,494 | 2026-06-11 00:05:42 | STALE |
| `coordinator_decisions` | 20,458 | 2026-06-11 00:05:45 | STALE |
| `opportunity_scores_v2` | 0 | n/a | INACTIVE |
| `strategy_routes_v2` | 0 | n/a | INACTIVE |
| `risk_decisions` | 20,162 | 2026-06-11 00:06:59 | STALE |
| `risk_gate_decisions` | 0 | n/a | INACTIVE |
| `risk_evidence_mesh_evaluations` | 1,596 | 2026-06-07 11:44:55 | STALE |
| `exit_plans` | 20,162 | 2026-06-11 00:06:59 | STALE |
| `paper_eligibility_candidates` | 20,162 | 2026-06-11 00:07:00 | STALE but most recent candidate stage |
| `paper_intents` | 20 | 2026-06-03 12:34:05 | STALE |
| `paper_orders` | 12 | 2026-06-03 13:04:44 | STALE |
| `paper_fills` | 9 | 2026-06-03 13:04:45 | STALE |
| `paper_positions` | 12 | 2026-06-03 13:04:45 | STALE; no open positions |
| `paper_position_closes` | 9 | 2026-06-03 22:58:51 | STALE |
| `paper_daily_pnl` | 5 | 2026-06-11 00:07:24 | ACTIVE/STATS |
| `no_trade_log` | 20,162 | 2026-06-11 00:07:00 | STALE but meaningful |
| `truth_state_registry` | 8,831 | 2026-06-10 22:21:51 | STALE |
| `lifecycle_governance_decisions` | 10,750 | 2026-06-10 22:18:14 | STALE |
| `brain_dialogue_events` | 298,514 | 2026-06-11 00:08:15 | STALE |
| `mesh_sessions` | 192 | 2026-06-10 22:32:09 | STALE |
| `capital_brain_evaluations` | 192 | 2026-06-10 22:32:09 | STALE |
| `live_orders` | 0 | n/a | SAFE/INACTIVE |
| `orders_v2` | 1 | 2026-05-21 00:12:50 | LEGACY/STALE |
| `fills_v2` | 1 | 2026-05-21 00:12:50 | LEGACY/STALE |
| `positions` | 0 | n/a | SAFE/INACTIVE |

Truth-state distribution:

- `LAST_KNOWN / CAN_INFORM_ONLY`: 3,966.
- `REFRESH_REQUIRED / MUST_REFRESH`: 3,475.
- `ACTIVE_FRESH / CAN_AUTHORIZE`: 960.
- `ACTIVE_FRESH / CAN_INFORM_ONLY`: 383.
- `HISTORICAL_ONLY / CAN_TEACH_ONLY`: 47.

## 8. API Map

Static route decorators: 427.

Observed API probes:

| Endpoint | Result | Classification |
| --- | --- | --- |
| `GET /healthz` | `status=ok`, `ready=true` | REAL |
| `GET /health` | `degraded`, no last refresh in process | REAL/PARTIAL |
| `GET /runtime/state` | DATA_ONLY, system power OFF, all trade permissions false | REAL |
| `GET /runtime/health` | SAFE_STOPPED, scheduler BLOCKED_BY_MODE | REAL |
| `GET /system/power` | OFF, runtime work not allowed | REAL |
| `GET /dashboard/api/v2/control/overview` | PARTIAL, source counts and latest rows | REAL/PARTIAL |
| `GET /dashboard/api/v2/control/full-monitor-run` | MISSING; no run in this process | REAL |
| `GET /dashboard/api/v2/paper` | GREEN/readiness from historical rows, stale latest paper creation | REAL but operator interpretation risk |

Risk: some dashboards report service names as `RUNNING` from registered service-health rows even when their ledgers are stale or empty. Use activity timestamps and row counts, not service labels alone.

## 9. Control Center Map

Frontend page registry contains 17 page shells:

- Overview / Command Cockpit.
- Decision X-Ray.
- Blocker Center.
- Closest to Actionable.
- Truth State.
- Risk Evidence Mesh.
- Lifecycle Governance.
- Live Flow.
- PnL Ledger.
- Positions.
- Capital.
- Organ Health.
- AI Brain.
- Logs & Errors.
- Settings / Controls.
- Mesh Dialogues.
- No-Trade.

Frontend endpoint map includes:

- `/dashboard/api/v2/control/overview`
- `/dashboard/api/v2/control/organs`
- `/dashboard/api/v2/control/live-flow`
- `/dashboard/api/v2/control/decision-xray`
- `/dashboard/api/v2/control/blockers`
- `/dashboard/api/v2/control/closest-actionable`
- `/dashboard/api/v2/control/truth-state`
- `/dashboard/api/v2/control/risk-evidence`
- `/dashboard/api/v2/control/lifecycle-governance`
- `/dashboard/api/v2/control/mesh-dialogues`
- `/dashboard/api/v2/control/pnl-ledger`
- `/dashboard/api/v2/control/positions`
- `/dashboard/api/v2/control/no-trade`
- `/dashboard/api/v2/control/ai`
- `/dashboard/api/v2/control/logs`
- `/dashboard/api/v2/control/truth-contract`
- `/dashboard/api/v2/control/full-monitor-run`
- `/dashboard/api/v2/control/runtime-supervisor`
- `/dashboard/api/v2/control/paper-simulation`

Control action wrapper:

- `system-on`
- `system-off`
- `kill-switch`
- `enable-paper-simulation`
- `disable-paper-simulation`
- `start-full-monitor-run`
- `stop-current-run`
- `reset-paper-balance` is known but locked.

Classification:

| Screen/panel | Classification | Evidence |
| --- | --- | --- |
| Overview/Cockpit | PARTIAL_TRUTH | DB-backed source counts plus action buttons. |
| Live Flow | PARTIAL | Reads event/log rows; not a streaming nervous system. |
| Decision X-Ray | PARTIAL | Reads decision/risk evidence where present. |
| Risk Evidence | PARTIAL | Real rows, stale and incomplete. |
| Lifecycle Governance | PARTIAL | Real rows, stale. |
| Mesh Dialogues | PARTIAL | Real `brain_dialogue_events`, stale. |
| PnL | REAL/PARTIAL | Ledger-backed; latest PnL stats current-ish but trades stale. |
| Capital | REAL/PARTIAL | Paper account ledger-backed. |
| Positions | REAL/PARTIAL | Canonical paper rows; no active open positions. |
| AI | NOT_IMPLEMENTED/PARTIAL in frontend shell | Registry marks AI Brain `NOT_IMPLEMENTED` in shell. |
| Logs | REAL/PARTIAL | Event/log rows real. |
| Blockers/No-Trade | REAL/PARTIAL | Real blockers/no-trade rows; stale. |
| Organ Health | PARTIAL | Service health can overstate activity if not paired with last success. |
| Truth State | REAL/PARTIAL | Real truth registry; many refresh-required rows. |

## 10. Neural Mesh Autopsy

Mesh assets that exist:

- Neuron registry/health/producers/signals/bindings tables.
- Runtime producer evidence runs.
- Runtime brain producer runs.
- Runtime coordinator runs.
- Brain outputs and coordinator decisions.
- Neural events and mesh sessions.
- Shared awareness, multi-brain consumption, mesh coordinator decisions, capital brain evaluations, position awareness.

What actually participates:

- During `MarketService.refresh()`, the system calls evidence refresh, side evidence, trusted orderbook, neuron intelligence, downstream recompute, post-side readiness, eligibility recovery, paper intents, paper execution, paper exit, neural event publishing/delivery, and brain dialogue materialization.
- This is orchestrated by the refresh method, not by independent event consumers.
- `event_consumers=0` and `neural_event_delivery=1` show the current event bus is not broadly dispatching to many autonomous workers.

Nervous system tests from evidence:

| Question | Answer | Evidence |
| --- | --- | --- |
| Can one event wake multiple brains? | PARTIAL/NOT PROVEN | Brain outputs exist, but event consumer delivery is sparse. |
| Can brains influence each other? | PARTIAL | Shared awareness and mesh sessions exist; runtime autonomy not proven. |
| Can opinions conflict? | PARTIAL | `brain_output_conflicts` and coordinator tables exist; current observed focus is stale. |
| Can Coordinator resolve conflict? | PARTIAL | 20,458 coordinator decisions exist. |
| Can open positions react to new events? | WEAK | Position awareness has 3 rows; no open paper positions now. |
| Can new information modify existing decisions? | PARTIAL | Truth registry and lifecycle decisions exist; mostly refresh-driven. |
| Can Risk influence Exit? | YES/PARTIAL | Exit plans source risk status and blockers. |
| Can Capital influence Risk? | WEAK/PARTIAL | Capital brain rows exist, but not current gating proof. |
| Can News influence open positions? | NOT PROVEN | No fresh news/provider evidence in current runtime sample. |
| Can Lifecycle influence Capital? | PARTIAL | Lifecycle governance and paper capital guards exist. |
| Can Coordinator observe all of the above? | PARTIAL | Coordinator sees brain outputs/signals, not all event workers autonomously. |

Final nervous-system classification: `PARTIAL_NERVOUS_SYSTEM`.

## 11. Decision Lifecycle Trace

Actual observed flow:

1. Market fetch: `GammaClient.fetch_active_events()` inside `MarketService.refresh()`.
2. Normalization/scoring: `MarketService._normalize_market()` and `OpportunityScorer`.
3. Phase 1 persistence: `cycles`, `market_snapshots`, `ranking_snapshots`.
4. Data foundation: `DataFoundationService.process_markets()` into V2 market/orderbook/liquidity data.
5. Runtime intelligence/mesh: source/brain/evidence services inside refresh.
6. Risk core: `risk_decisions` from thesis profiles, with `paper_candidate_allowed=false`, `execution_allowed=false`.
7. Exit foundation: `exit_plans`, with `paper_exit_ready` true for some but still `paper_intent_allowed=false`.
8. Paper eligibility: `paper_eligibility_candidates`.
9. Paper intent: `PaperIntentGateService.build_intents()`, blocked by system power OFF now and by candidate blockers when on.
10. Paper execution: `PaperExecutionService.run_execution()`, requires valid fresh paper intents, fresh orderbook within 180 seconds, marketable fill, capital guard, lifecycle governance, and Governor paper-simulation permission.
11. Paper fills/positions: `paper_orders`, `paper_fills`, `paper_positions`.
12. Exit/PnL: `PaperExitLoopService`, `paper_position_closes`, `paper_trade_ledger`, `paper_daily_pnl`.

V2 opportunity/strategy gap:

- `opportunity_scores_v2=0`.
- `strategy_routes_v2=0`.

So the current active candidate/paper path is not V2 Opportunity Cortex -> Strategy Router -> Capital -> Risk -> Execution. It is more accurately mesh/thesis/risk/exit/eligibility/paper-intent/paper-execution around the canonical `paper_*` tables.

## 12. Paper Trading Autopsy

Current capability:

| Artifact | Can exist? | Exists now? | Fresh? |
| --- | --- | --- | --- |
| Paper intent | Yes | 20 | No, latest 2026-06-03 |
| Paper order | Yes | 12 | No, latest 2026-06-03 |
| Paper fill | Yes | 9 | No, latest 2026-06-03 |
| Paper position | Yes | 12 | No, latest 2026-06-03 |
| Paper close | Yes | 9 | No, latest 2026-06-03 |
| Paper PnL | Yes | 5 daily rows | Latest stats 2026-06-11 |

Current paper gate blockers:

- System power is OFF; `PaperIntentGateService` returns `SYSTEM_POWER_OFF` if called.
- `PaperSimulationControlService` is disabled; paper simulation requires SYSTEM ON first.
- Governor permissions currently deny `RUN_PAPER_SIMULATION`.
- Fresh candidate rows are mostly blocked.
- Existing paper intents are stale.
- Execution requires orderbook snapshot not older than 180 seconds; latest orderbook snapshot is 2026-06-11 and current date is 2026-06-14.

Paper intent statuses:

- `CREATED`: 14, all `execution_allowed=false`.
- `CLOSED`: 6, all `execution_allowed=false`.

Paper order statuses:

- `FILLED`: 12.

Paper dashboard showed `readiness_status=GREEN`, but that is a historical/lineage/capital reconciliation truth, not proof that fresh paper trades are currently possible while power is OFF and orderbook/intents are stale.

## 13. Candidate Autopsy

Recent 10 candidates sampled from `paper_eligibility_candidates`:

| Candidate | Market | Side | Status | Score | Risk | Exit | Paper intent | Execution | Blockers |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| `eligibility_exit_risk_thesis_coord_3bfd...` | `691547` | YES | BLOCKED | 0 | false | false | false | false | EXIT_NOT_READY, RISK_BLOCKED, RISK_NOT_APPROVED, THESIS_NOT_COMPLETE |
| `eligibility_exit_risk_thesis_coord_f5fd...` | missing | missing | BLOCKED | 0 | false | false | false | false | EXIT_NOT_READY, MISSING_FRESH_ORDERBOOK, MISSING_MARKET_ID, MISSING_SIDE, MISSING_SIGNAL_MARKET_BINDING, RISK_BLOCKED, RISK_NOT_APPROVED, THESIS_NOT_COMPLETE |
| `eligibility_exit_risk_thesis_coord_cde8...` | `691547` | YES | BLOCKED | 0 | false | false | false | false | EXIT_NOT_READY, RISK_BLOCKED, RISK_NOT_APPROVED, THESIS_NOT_COMPLETE |
| `eligibility_exit_risk_thesis_coord_3942...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |
| `eligibility_exit_risk_thesis_coord_cdfa...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |
| `eligibility_exit_risk_thesis_coord_0438...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |
| `eligibility_exit_risk_thesis_coord_d8f6...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |
| `eligibility_exit_risk_thesis_coord_5c37...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |
| `eligibility_exit_risk_thesis_coord_bc4d...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |
| `eligibility_exit_risk_thesis_coord_d539...` | missing | missing | BLOCKED | 0 | false | false | false | false | same missing-data/risk/exit blockers |

Candidate totals:

- `BLOCKED`: 17,222.
- `ELIGIBLE`: 2,940.

But even risk-approved and exit-complete groups had `paper_candidate_allowed=false`, `paper_intent_allowed=false`, and `execution_allowed=false` in sampled aggregate queries.

## 14. Replay Autopsies

Five rejected-candidate replay pattern:

1. Candidate enters from exit/risk/thesis/coordinator records.
2. `PaperEligibilityService._candidate_from_exit_plan()` checks exit ID, risk ID, thesis ID, market ID, side, orderbook freshness, signal links, lineage, dry-run status, and coordinator execution flags.
3. If risk is not approved, adds `RISK_NOT_APPROVED`.
4. If exit is blocked or `paper_exit_ready=false`, adds `EXIT_NOT_READY`.
5. If thesis status is not complete, adds `THESIS_NOT_COMPLETE`.
6. If market/side/binding/orderbook evidence missing, adds corresponding missing blockers.
7. Candidate is written as `BLOCKED`.
8. `PaperIntentGateService._paper_intent_blockers()` adds `CANDIDATE_NOT_ELIGIBLE` plus missing/risk/exit/lineage/dry-run/executable-price blockers.
9. Gate writes no-trade record instead of paper intent.
10. Paper execution never sees a fresh executable intent.

For currently existing stale paper intents:

1. `_list_created_intents()` can select `CREATED` paper intents.
2. `_intent_blockers()` adds `STALE_PAPER_INTENT` and `REFRESH_REQUIRED_BEFORE_EXECUTION` when older than 600 seconds.
3. `_orderbook_for_intent()` requires matching non-stale orderbook within 180 seconds.
4. Existing intents/orders are historical; execution blocks or skips duplicates.

## 15. Event Causality Graph

```mermaid
flowchart TD
  "FastAPI startup" --> "RefreshScheduler"
  "RefreshScheduler" -->|"StateGovernor COLLECT_DATA allowed"| "MarketService.refresh"
  "RefreshScheduler" -->|"system power OFF"| "event_log: runtime.cycle.finished BLOCKED_BY_MODE"
  "MarketService.refresh" --> "GammaClient fetch"
  "GammaClient fetch" --> "market_snapshots / ranking_snapshots"
  "market_snapshots / ranking_snapshots" --> "DataFoundationService"
  "DataFoundationService" --> "markets_v2 / market_snapshots_v2 / orderbook_snapshots"
  "MarketService.refresh" --> "runtime intelligence and mesh evidence services"
  "runtime intelligence and mesh evidence services" --> "neuron_signals / bindings / brain_outputs / coordinator_decisions"
  "coordinator_decisions" --> "risk_decisions"
  "risk_decisions" --> "exit_plans"
  "exit_plans" --> "paper_eligibility_candidates"
  "paper_eligibility_candidates" -->|"blocked"| "no_trade_log"
  "paper_eligibility_candidates" -->|"eligible + gates pass"| "paper_intents"
  "paper_intents" -->|"fresh, marketable, power ON, sim ON"| "paper_orders / paper_fills / paper_positions"
  "paper_positions" --> "paper_position_closes / paper_daily_pnl"
```

Current propagation reality:

- Scheduler events continue while blocked.
- Current blocked scheduler events do not wake a broad mesh; they record status.
- Most meaningful mesh/paper propagation last happened June 10-11 or June 3 depending on layer.

## 16. Freshness Chain

Source -> Collector -> DB -> Service -> Decision -> UI:

| Chain point | Current truth |
| --- | --- |
| Source | Gamma/CLOB had historical reachability; current refresh blocked by system power OFF. |
| Collector | `MarketService.refresh()` blocked now. |
| DB market/orderbook | Latest market/orderbook rows from 2026-06-11. |
| Services | Service-health labels updated on API health request; row activity stale. |
| Decisions | Risk/exit/eligibility/no-trade latest 2026-06-11; paper orders latest 2026-06-03. |
| UI | Control Center shows real DB-backed partial/stale states, but paper page can look GREEN for historical reconciliation. |

Freshness is lost at current runtime power/scheduler gate and at paper execution freshness gates. The freshest data in this audit is service health and scheduler blocked events, not actionable market/orderbook/paper evidence.

## 17. Manual Run vs Continuous System

| Behavior | SYSTEM ON / Supervisor | FULL MONITOR RUN |
| --- | --- | --- |
| Purpose | Normal DATA_ONLY monitoring supervisor; optional explicit paper simulation. | Bounded diagnostic/report action. |
| Execution | Paper simulation can call paper intent/execution/exit only after explicit PAPER SIMULATION ON. | Skips paper execution. |
| Persistence | Emits events and can create paper rows when enabled and gated. | Writes report files; read-only modules. |
| Current observed | Not running; system power OFF. | No run started in current process. |

Answer: Full Monitor Run is not doing the work the Supervisor should do. It is intentionally read-only. However, operator workflows can confuse this because the cockpit places both concepts together. Normal system life is `SYSTEM ON` -> Runtime Supervisor, not Full Monitor Run.

## 18. Dead System Report

Confirmed inactive or skeleton surfaces:

- `event_consumers`: 0 rows.
- `opportunity_scores_v2`: 0 rows.
- `strategy_routes_v2`: 0 rows.
- `risk_gate_decisions`: 0 rows.
- `live_orders`: 0 rows.
- `positions`: 0 rows.
- `event_delivery` style neural delivery is sparse: `neural_event_delivery=1`.
- AI Brain frontend shell marked `NOT_IMPLEMENTED`.
- Stage 3 SQLite paper path is legacy/reference only.
- News/social/whale current provider surfaces are not proven fresh in this audit.

Zombie/ambiguous:

- Many `service_health` rows say `RUNNING` while last success is null or stale.
- `runtime_cycles_v2` has a stale `RUNNING` active cycle from 2026-06-10.
- Paper dashboard readiness can show GREEN from historical reconciliation, while fresh paper is blocked.

## 19. Top Blockers Preventing Paper Trades

Top eligibility blockers:

| Rank | Blocker | Count |
| ---: | --- | ---: |
| 1 | `RISK_BLOCKED` | 17,219 |
| 2 | `EXIT_NOT_READY` | 17,219 |
| 3 | `RISK_NOT_APPROVED` | 17,219 |
| 4 | `THESIS_NOT_COMPLETE` | 17,217 |
| 5 | `MISSING_SIDE` | 15,451 |
| 6 | `MISSING_FRESH_ORDERBOOK` | 12,506 |
| 7 | `MISSING_SIGNAL_MARKET_BINDING` | 12,436 |
| 8 | `MISSING_MARKET_ID` | 11,061 |

Additional execution blockers from code/dashboard:

- `SYSTEM_POWER_OFF`.
- `PAPER_BLOCKED_BY_MODE`.
- `STALE_PAPER_INTENT`.
- `REFRESH_REQUIRED_BEFORE_EXECUTION`.
- `MISSING_TRUSTED_ORDERBOOK`.
- `INTENT_ALREADY_EXECUTED`.
- `MISSING_QUANTITY`.
- `LIMIT_NOT_MARKETABLE`.
- `LIFECYCLE_GOVERNANCE_DENIED`.
- `MAX_OPEN_POSITIONS` in historical capital ledger.

## 20. Missing Systems

- Broad autonomous event consumers.
- Fresh provider-backed news/social/whale ingestion evidence.
- Active V2 Opportunity Cortex rows.
- Active V2 Strategy Router rows.
- Active risk gate decision rows.
- Fresh paper intents/orders/fills/positions.
- Current open-position reaction loop.
- Proof that one event wakes multiple brains independently of refresh orchestration.

## 21. Existing But Inactive Systems

- V2 Opportunity Cortex code/schema/routes.
- V2 Strategy Router/engines code/schema/routes.
- Risk gate decision tables.
- News/social/whale provider shells.
- Full Monitor Run process-local runner.
- Runtime Supervisor in the current process.
- Paper simulation switch in the current state.

## 22. Architectural Risks

1. Mesh naming can overstate runtime reality. The system has mesh tables and rows, but not broad event-driven autonomy.
2. Service-health labels can overstate activity. Pair them with table latest timestamps.
3. The paper dashboard can read as green from historical reconciliation while fresh paper is blocked.
4. Stale `RUNNING` cycles can confuse runtime status unless active-cycle age is highlighted.
5. Full Monitor Run and Runtime Supervisor are easy to confuse operationally.
6. V2 opportunity/strategy tables are empty while downstream paper/risk/exit tables have many rows, meaning there are parallel lifecycle concepts.

## 23. Runtime Risks

1. System power OFF currently blocks runtime work, by design.
2. Scheduler produces blocked events while system is off.
3. Paper simulation requires explicit ON and cannot run from SYSTEM ON alone.
4. Fresh orderbook and stale intent thresholds are very tight relative to current staleness.
5. Existing historical paper rows should not be interpreted as current paper readiness.
6. No live orders were present, which is safe.

## 24. Top 10 Fixes By Leverage

This report is not an implementation request. These are diagnosis outputs only.

1. Make Control Center explicitly distinguish historical paper reconciliation from current paper readiness.
2. Surface stale active runtime cycles as stale/abandoned instead of active.
3. Add a single current-paper-readiness endpoint that requires power ON, simulation ON, fresh orderbook, fresh intents, and Governor permission.
4. Promote `SYSTEM ON -> Runtime Supervisor` as the normal life path; label Full Monitor Run as diagnostic only.
5. Add/activate event consumers for at least one non-trading mesh path to prove true event fan-out.
6. Ensure every candidate blocker produces a no-trade record with a current timestamp when power is on.
7. Reconcile why approved/complete risk/exit rows still have paper intent/execution flags false.
8. Add current freshness checks to paper dashboard status.
9. Add UI warnings when latest paper order/fill/position is older than the execution TTL.
10. Decide whether V2 Opportunity/Strategy tables are future-only or should become canonical before more paper work.

## 25. Commands Run

Read/context:

```powershell
Get-Content -Raw docs/POLYBOT_CONTEXT_INDEX.md
Get-Content -Raw docs/POLYBOT_AGENT_DISPATCH_PROTOCOL.md
Get-Content -Raw AGENTS.md
Get-Content -Raw docs/POLYBOT_V2_MASTER_CONTEXT.md
Get-Content -Raw docs/POLYBOT_SAFETY_RULES.md
Get-Content -Raw docs/POLYBOT_AGENT_WORKFLOW.md
Get-Content -Raw C:\Users\harel\.codex\attachments\66d6ba74-4327-48f8-b5e3-80817ea24f1b\pasted-text.txt
```

Repository/static:

```powershell
git status --short
rg --files -g '!**/__pycache__/**' -g '!**/.git/**' -g '!**/node_modules/**' -g '!**/.venv/**'
Get-ChildItem -Force
Get-ChildItem -Recurse -Directory -Depth 2
Get-ChildItem -Recurse app -File -Include *.py
Get-ChildItem -Recurse frontend\control-center\src -File
Get-ChildItem -Recurse app\db\migrations -File
```

Key files read:

```powershell
Get-Content -Raw app\main.py
Get-Content -Raw app\scheduler.py
Get-Content -Raw app\ingestion\market_service.py
Get-Content -Raw app\events\event_bus.py
Get-Content -Raw app\runtime\state_governor.py
Get-Content -Raw app\services\system_power.py
Get-Content -Raw app\api\runtime_routes.py
Get-Content -Raw app\api\system_power_routes.py
Get-Content -Raw app\api\routes.py
Get-Content -Raw app\services\paper_intents.py
Get-Content -Raw app\services\paper_execution.py
Get-Content -Raw app\services\paper_eligibility.py
Get-Content -Raw app\services\risk_core.py
Get-Content -Raw app\control_center\full_monitor_run_service.py
Get-Content -Raw app\control_center\runtime_supervisor.py
Get-Content -Raw app\control_center\action_service.py
Get-Content -Raw app\control_center\paper_simulation.py
Get-Content -Raw frontend\control-center\src\pages\pageRegistry.ts
Get-Content -Raw frontend\control-center\src\api\controlCenterEndpoints.ts
Get-Content -Raw frontend\control-center\src\pages\CommandCenterHome.tsx
Get-Content -Raw frontend\control-center\src\pages\PageShell.tsx
```

Runtime/API:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
Get-NetTCPConnection -LocalPort 55432 -State Listen
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
Invoke-RestMethod -Uri http://127.0.0.1:8000/healthz
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/runtime/state
Invoke-RestMethod -Uri http://127.0.0.1:8000/runtime/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/system/power
Invoke-RestMethod -Uri http://127.0.0.1:8000/dashboard/api/v2/control/overview
Invoke-RestMethod -Uri http://127.0.0.1:8000/dashboard/api/v2/control/full-monitor-run
Invoke-RestMethod -Uri http://127.0.0.1:8000/dashboard/api/v2/paper
```

Database:

```powershell
docker exec polybot_postgres psql -U polybot -d polybot -At -c "select count(*) from information_schema.tables where table_schema='public';"
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select t.table_name, ... timestamp columns ..."
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select ... key table counts ..."
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select ... key table max timestamps ..."
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select eligibility_id, market_id, side, status, ... from paper_eligibility_candidates order by created_at desc limit 10;"
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select blocker, count(*) from paper_eligibility_candidates cross join lateral jsonb_array_elements_text(eligibility_blockers) group by blocker order by count(*) desc limit 20;"
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select status, count(*) from paper_eligibility_candidates group by status;"
docker exec polybot_postgres psql -U polybot -d polybot -F "|" -At -c "select intent_status, execution_allowed, execution_block_reason, count(*) from paper_intents group by intent_status, execution_allowed, execution_block_reason;"
```

Notes:

- `git status --short` failed because `C:\Server\apps\polybot` is not a Git repository from this shell.
- No destructive command was run.
- No POST action endpoint was called.
- No live/shadow/paper activation was performed.
- No `.env` contents or secret values were printed.
- No tests were run because this was a read-only forensic audit and no code behavior was changed.

## 26. Direct Answers

Is SYSTEM ON truly alive?

- Not currently, because system power is OFF.
- When used, SYSTEM ON starts the Runtime Supervisor in DATA_ONLY monitoring mode. That is a bounded form of life, but it is not a fully autonomous mesh.

Is Full Monitor Run masking missing behavior?

- Partly in operator perception, yes.
- Technically, Full Monitor Run is explicit read-only diagnostics and skips paper execution. It does not replace the Runtime Supervisor.

Is the Neural Mesh real?

- Partially.
- The schema, producers, signals, bindings, brain outputs, coordinator decisions, and dialogue events exist.
- The autonomous nervous-system behavior is not fully proven; event consumers and neural deliveries are sparse.

Is Paper Trading actually possible today?

- Historically yes.
- Right now, not under current state. System power is OFF, paper simulation is disabled, scheduler is blocked, intents/orderbooks are stale, and most candidates are blocked by risk/exit/missing evidence.

Biggest root cause:

- POLYBOT has built many durable organs, but current operation depends on explicit power/supervisor/refresh cycles and strict freshness gates. The system is stopped and stale; current paper creation fails before execution because candidates/intents do not satisfy risk, exit, orderbook, lineage, lifecycle, and freshness requirements.

Safe to proceed?

- Safe to proceed with read-only review, dashboard truth hardening, stale-state surfacing, and non-trading diagnostics.
- Not safe to proceed to PAPER/SHADOW/LIVE activation based on this audit alone.

