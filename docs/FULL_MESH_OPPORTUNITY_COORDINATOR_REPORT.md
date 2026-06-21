# Full Mesh Opportunity Coordinator Report

## Purpose

POLYBOT needed a Full Mesh opportunity coordinator so duplicate, blocked, already-processed, active-intent, and position states are classified and routed instead of dominating the runtime as terminal blockers. This implementation keeps PAPER runtime behavior intact while adding a read-only active opportunity pool, intent queue, candidate consumption view, and learning-report summaries.

## Stage A Audit Findings

Current PAPER runtime already continues through most candidate blockers, but the truth was scattered:

- `PaperRuntimeDecisionService` creates current PAPER decisions and Defense-adjusted ENTER/WATCH/BLOCK rows.
- `PaperIntentGateService` creates current-session `paper_intents` or no-trade rows and is idempotent for duplicate eligibility.
- `PaperExecutionService` consumes current-session `CREATED` intents, but stale or missing execution prerequisites were only visible in aggregate run reasons.
- Autopsy/report layers showed blocker truth but did not expose one active opportunity pool.
- Duplicate active intent and already-existing intent states could appear as top blockers instead of lifecycle states.

Primary architectural gap: `NO_ACTIVE_OPPORTUNITY_POOL`.

Secondary gaps:

- `DUPLICATE_STATUS_TREATED_AS_TERMINAL_BLOCKER`
- `LIFECYCLE_STATES_MISSING`
- execution diagnosis existed at run level but not clearly per active intent

## Linear Behavior Found

No single organ was crashing the cycle on ordinary blockers, but reporting and lifecycle visibility still looked linear:

- Duplicate active intent was a blocker, not `HAS_ACTIVE_INTENT`.
- Created intents with no order/fill/position were not visible as pending or stuck queue items.
- Closed positions could still look like active lifecycle unless explicitly classified.
- Blocker summaries could obscure that the system was still routing other candidates to intent, execution, or exit organs.

## Candidate Lifecycle Model

Implemented computed lifecycle states:

- `READY_FOR_INTENT`
- `ALLOWED_FOR_LEARNING`
- `BLOCKED_INTEGRITY`
- `BLOCKED_STRATEGIC`
- `ARBITRATED_DEMOTED`
- `SKIPPED_DUPLICATE`
- `HAS_ACTIVE_INTENT`
- `INTENT_PENDING_EXECUTION`
- `INTENT_STUCK`
- `ORDER_CREATED`
- `FILL_CREATED`
- `POSITION_OPEN`
- `POSITION_CLOSED`

No new trading authority was added. The coordinator is a read model/router.

## Opportunity Mesh Design

Added `OpportunityMeshCoordinator` in `app/services/opportunity_mesh_coordinator.py`.

It computes:

- active PAPER session
- current runtime decisions
- current-session paper intents
- linked order/fill/position/close lifecycle
- lifecycle state
- next action
- owning organ
- consumption policy
- blockers, warnings, Defense effects
- arbitration and side-evidence summaries
- intent queue and stuck status

## Candidate Consumption Policy

Implemented computed policies:

- `CONSUME_CREATE_INTENT`
- `CONSUME_SKIP_DUPLICATE_CONTINUE`
- `CONSUME_SKIP_BLOCKED_CONTINUE`
- `CONSUME_ROUTE_TO_EXECUTION`
- `CONSUME_ROUTE_TO_EXIT`
- `CONSUME_RETRY_LATER`
- `CONSUME_EXPIRE`

The coordinator never stops the system at a duplicate or blocker. It classifies, records the route, and shows the next item.

## Intent Queue Handling

Current-session intents are shown with:

- intent id
- market/side
- status
- age
- execution status
- next action
- execution block reason
- linked order/fill/position
- stuck yes/no

An intent is `INTENT_STUCK` if it has no order/fill/position and either has an execution diagnosis or is older than the stuck threshold.

## Duplicate Skip-And-Continue Behavior

Duplicate active intent is now visible as lifecycle, not as a terminal blocker:

- candidate state: `HAS_ACTIVE_INTENT`
- next action: `CHECK_INTENT_EXECUTION`
- consumption policy: `CONSUME_ROUTE_TO_EXECUTION`

Duplicate blockers remain visible in blocker/autopsy surfaces when relevant, but the opportunity mesh separates lifecycle status from blocker cause.

## API / CLI

Read-only APIs added:

- `GET /dashboard/api/v2/control/opportunity-mesh`
- `GET /dashboard/api/v2/control/intent-queue`
- `GET /dashboard/api/v2/control/candidate-consumption`

CLI commands added:

- `.\tools\polybot.ps1 opportunity-mesh [-limit 50]`
- `.\tools\polybot.ps1 intent-queue [-limit 50]`
- `.\tools\polybot.ps1 candidate-consumption [-limit 50]`

`.\tools\polybot.ps1 report` now includes the Opportunity Mesh section.

## Learning Report

The session learning report now includes:

- `opportunity_mesh_summary`
- `candidate_consumption_summary`
- `intent_queue_summary`

The report reuses its existing DB connection to avoid nested connection waits.

## Tests Run

Focused:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_opportunity_mesh_coordinator.py tests/test_candidate_consumption_policy.py tests/test_duplicate_skip_and_continue.py tests/test_intent_queue_visibility.py tests/test_intent_stuck_detection.py tests/test_opportunity_mesh_report.py tests/test_paper_defense_level.py tests/test_paper_intent_gate_idempotency.py -q
2 passed, 9 skipped
```

Related:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_side_evidence.py tests/test_same_market_side_arbitration.py tests/test_arbitration_autopsy.py tests/test_paper_defense_learning_ledger.py tests/test_paper_execution_adapter_runtime.py tests/test_paper_session_status_report.py -q
4 passed, 6 skipped
```

Compile:

```text
.\.venv\Scripts\python.exe -m compileall app tests
passed
```

Skips were due the local shell not having `POLYBOT_DATABASE_URL`; Docker runtime verification used the active API/Postgres environment.

## Runtime Verification

Build/restart:

- `docker compose build api`: passed
- `docker compose build migrate`: passed
- `docker compose run --rm migrate`: no pending migrations
- `docker compose up -d --no-deps api`: passed
- health `/docs`: HTTP 200

Fresh PAPER Defense 20 session:

- command: `.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20`
- new session: `paper_session_20260620T102146Z_7a17c698`
- starting balance: `1000`
- Defense level: `20`
- live/shadow/real: `0/0/0`

20-minute observation:

- runtime continuity: `CONTINUOUS`
- hunting verdict: `BROAD_HUNTING`
- trade lifecycle: `ENTER_EXECUTE_EXIT_REHUNT_OK`
- current session paper counts: intents/orders/fills/positions `9/4/4/4`
- open paper positions: `1`
- realized/unrealized/net PnL: `-7.5595235 / -18.75 / -26.3095235`
- live/shadow/real: `0/0/0`

Opportunity Mesh after verification:

- active pool size: `17`
- ready for intent: `4`
- intent pending execution: `2`
- intent stuck: `3`
- blocked integrity: `0`
- blocked strategic: `0`
- softened by defense: `3`
- arbitrated demoted: `4`
- routed to execution: `9`
- routed to exit: `1`
- system errors: `0`

Intent queue:

- stuck intents: `3`
- pending execution: `2`
- closed positions correctly classified as `POSITION_CLOSED`
- open position routed to exit as `POSITION_OPEN`

Learning report generated:

- JSON: `run_reports/paper_session_learning_paper_session_20260620T102146Z_7a17c698/paper_session_learning_report_paper_session_20260620T102146Z_7a17c698.json`
- Markdown: `run_reports/paper_session_learning_paper_session_20260620T102146Z_7a17c698/paper_session_learning_report_paper_session_20260620T102146Z_7a17c698.md`
- CSV: `run_reports/paper_session_learning_paper_session_20260620T102146Z_7a17c698/paper_session_trades_paper_session_20260620T102146Z_7a17c698.csv`

Final runtime status:

- System power: `ON`
- Runtime state: `PAPER`
- Paper adapter: `ENABLED`
- Live adapter: `BLOCKED`
- Supervisor: `RUNNING`
- live/shadow/real: `0/0/0`

## Before / After Example

Before:

```text
DUPLICATE_ACTIVE_PAPER_INTENT appeared as a blocker and could obscure whether an intent was pending, stuck, executed, or closed.
```

After:

```text
2354064 NO state=HAS_ACTIVE_INTENT policy=CONSUME_ROUTE_TO_EXECUTION next=CHECK_INTENT_EXECUTION
2354064 YES state=INTENT_STUCK policy=CONSUME_ROUTE_TO_EXECUTION next=DIAGNOSE_EXECUTION
2365093 YES state=POSITION_CLOSED policy=CONSUME_ROUTE_TO_EXECUTION next=NONE
691547 YES state=POSITION_OPEN policy=CONSUME_ROUTE_TO_EXECUTION next=ROUTE_TO_EXIT
```

## Remaining Risks

- `INTENT_STUCK` currently reports and diagnoses; it does not automatically retry, expire, or cancel. That should be a separate execution-worker repair.
- Some currently stuck intents show `PENDING_OVER_STUCK_THRESHOLD` rather than a precise execution reason until the execution validator updates `execution_block_reason` in a future run.
- Source refresh showed `NOT_CONFIGURED` after API restart, but runtime supervisor was restored to `RUNNING` with `.\tools\polybot.ps1 on -mode paper`.

## Safety Checklist

- Live orders untouched: YES
- Shadow orders untouched: YES
- Real orders untouched: YES
- Paper only: YES
- No thresholds lowered: YES
- No risk bypass: YES
- No capital bypass: YES
- No exit bypass: YES
- Duplicate exposure guard preserved: YES
- Historical Paper data preserved: YES
- Current session counts remain session-scoped: YES
- No fake activity: YES
- No secrets printed: YES
- KILL/DATA_ONLY/PAPER rules preserved: YES

## Status

Status: GREEN for Full Mesh opportunity visibility and skip/route/continue behavior.

Safe to continue Defense 20 PAPER runtime: YES.
