# Continuous Hunting Runtime Audit Report

## Purpose

Audit and repair POLYBOT's continuous PAPER hunting runtime so the Full Mesh can prove whether it is still hunting, repeatedly circling stale blockers, or stopped at a gate after a trade lifecycle.

Paper remains only the execution adapter. No live, shadow, or real execution behavior was enabled or changed.

## Current Reality Audit

The pre-repair audit showed the runtime was not stopped. Runtime cycles, source/event work, trigger generation, candidate generation, Mesh review, PaperRuntimeDecisionService, PaperIntentGate, PaperExecutionAdapter, and PaperExitLoop continued to run after SYSTEM ON in PAPER mode.

Key pre-repair live observations:

- System power: ON
- Runtime state: PAPER
- Execution mode: PAPER
- Paper adapter: ENABLED
- Live adapter: BLOCKED
- Supervisor: RUNNING
- Active paper session: present
- Current session paper intents/orders/fills/positions: 0/0/0/0
- Open paper positions: 0
- Live/shadow/real orders: 0/0/0
- Runtime PAPER decisions: 17
- Paper ENTER decisions: 2
- Decision unique markets: 9
- Decision unique sides: 2
- Duplicate suppressed: 965

## Runtime Continuity Findings

Runtime was moving, but runtime truth had stale open cycle rows. Recent completed cycles advanced every few minutes, while older RUNNING/STARTING cycles remained open beyond a safe TTL.

Pre-repair cycle findings:

- Latest current cycle existed.
- Latest completed cycle advanced.
- Several older RUNNING cycles were stale.
- Stale abandoned cycles already existed.
- Average completed cycle duration was about 298 seconds.

Verdict before repair: PARTIAL. The machine was moving, but stale open cycle cleanup was incomplete.

## Organ Heartbeat Findings

Recent organ activity was visible from existing ledgers:

- Market/source refresh: moving through source event and linked event counts.
- Trigger generation: moving.
- Candidate generation: moving.
- Mesh review: moving.
- AI Mesh: active and JSON reliable.
- PaperRuntimeDecisionService: multiple recent runs.
- PaperIntentGateService: multiple recent runs.
- PaperExecutionAdapter: multiple recent runs.
- PaperExitLoopService: multiple recent runs.

Gap found: there was no single operator-facing hunting autopsy endpoint combining runtime continuity, organ heartbeats, progression windows, decision diversity, ENTER lifecycle, post-trade rehunt, and latest error classification.

## Hunting Progression Findings

Recent movement proved the system was generating new work instead of only replaying old state:

- Last 10 minutes: new events, linked events, triggers, seeds, Mesh reviews, runtime decision runs, no-trade records, intent gate runs, execution runs, and exit runs moved.
- Last 30 minutes: the same organs continued moving with larger deltas.
- Active paper session: source/event/trigger/candidate/Mesh/runtime/gate activity continued, but current-session paper ledger remained at 0 because no current-session ENTER passed the gate.

Verdict before repair: the machine was hunting, but current trade entry was stopped at gate-level conflicts and policy blockers.

## Decision Diversity Findings

Runtime decisions were not globally stuck on one row:

- Current runtime decision markets: 9
- Current runtime decision sides: 2
- Current WATCH rows spanned multiple market/side pairs.

The ENTER subset was narrow:

- ENTER market: 691547
- ENTER sides: YES and NO
- Both sides had the same opportunity score around 61.99.

This created same-market/opposing-side conflict behavior at the PaperIntentGate.

## Post-Trade Re-Hunt Findings

Historical Paper sessions proved open/close/PnL behavior worked. For the current active session before repair, no new Paper intent/order/fill/position had been created yet.

The runtime continued hunting after prior closes:

- Candidate generation continued.
- Runtime decision runs continued.
- PaperIntentGate runs continued.
- PaperExitLoop runs continued.
- No previous-session closed position was found blocking current-session checks.

Verdict before repair: post-trade re-hunt was active at the organ level, but current-session entry was stopped at gate conflicts and blockers.

## ENTER Lifecycle Findings

Latest ENTER decisions showed same-market/opposing-side contention:

- market 691547 YES ENTER
- market 691547 NO ENTER
- both score approximately 61.99
- both current-session lifecycle stopped before intent creation
- no live/shadow/real orders created

Decision autopsy already made expected skip reasons visible after the prior bridge repair. This task added upstream arbitration so the Full Mesh no longer sends opposing ENTER sides for the same market into the intent gate together.

## Same-Market Conflict Findings

Root cause:

The PaperRuntimeDecisionService could emit YES and NO as ENTER for the same market in the same current batch when both met PAPER ENTER criteria and scores tied or were close. The duplicate/exposure guard correctly prevented unsafe entry, but the conflict was being resolved too late.

Repair:

Same-market opposing ENTER arbitration now runs inside PaperRuntimeDecisionService before decisions are persisted as current batch decisions.

Rules:

- At most one side can remain ENTER per market per batch.
- If one side has the higher opportunity score, it remains ENTER and the losing side is demoted.
- If sides tie, all opposing ENTER sides are demoted with an explicit conflict blocker.
- No thresholds, risk rules, capital rules, exit rules, or duplicate exposure guards were loosened.

## PaperIntentGate Scheduler Findings

PaperIntentGate was running repeatedly. It was not a one-shot startup-only organ. Recent gate ledgers showed repeated OK runs. The gate was seeing current candidates, creating/updating no-trade records, and preserving safety.

No scheduler repair was required for PaperIntentGate continuity.

## Exit/Reallocation Findings

The exit loop continued running after positions were closed and also when no positions were open. Current-session open exposure was 0 before the repair audit.

No exit reallocation bug was confirmed.

## Latest Errors/Noise Classification

Pre-repair classifications:

- SQL IndeterminateDatatype: not present.
- Expected Paper activity deltas under latest errors: not present.
- Supervisor DEGRADED without reason: not present in supervisor autopsy.
- Stale open cycles: BUG_SUSPECT runtime truth issue.
- Historical CREATED intent scanning in PaperExecutionAdapter: REPORTING/WORK_SELECTION_NOISE and fixed by active-session filtering.
- Same-market opposing ENTERs: primary runtime bottleneck.

## Primary Bottleneck

Primary bottleneck: SAME_MARKET_OPPOSING_ENTER_CONFLICT.

Evidence:

- Current ENTER decisions included YES and NO for market 691547.
- Both sides had the same score.
- Current-session paper ledger remained 0 because no safe single side was selected before the intent gate.
- Other markets remained WATCH/BLOCK due policy blockers such as score below threshold, thesis not supported, exit not ready, and observation policy not allowed.

## Repair Needed

YES.

Repair scope:

- Read-only hunting autopsy endpoint and CLI command.
- Runtime cycle stale open cleanup at new cycle start.
- Active-session filtering for PaperExecutionAdapter CREATED intents.
- Same-market/opposing-side ENTER arbitration before PaperIntentGate.
- Decision autopsy/blocker metadata for new arbitration outcomes.
- Tests and report.

## Repair Implemented

Implemented:

- `HuntingAutopsyService` for runtime continuity, hunting progression, decision diversity, ENTER lifecycle, post-trade rehunt, and safety truth.
- `GET /dashboard/api/v2/control/hunting-autopsy`.
- `.\tools\polybot.ps1 hunting-autopsy`.
- Report summary line showing runtime/hunting/lifecycle verdicts and primary bottleneck.
- Same-market opposing ENTER arbitration in PaperRuntimeDecisionService.
- Stale open cycle TTL cleanup at runtime cycle start.
- Active-session filtering in PaperExecutionService intent selection.
- Autopsy and bridge mappings for same-market opposing ENTER blockers.

## Files Created

- `app/services/hunting_autopsy.py`
- `tests/test_hunting_autopsy.py`
- `tests/test_runtime_continuity_autopsy.py`
- `tests/test_post_trade_rehunt.py`
- `tests/test_decision_diversity_autopsy.py`
- `tests/test_same_market_enter_arbitration.py`
- `tests/test_opposing_side_enter_resolution.py`
- `docs/CONTINUOUS_HUNTING_RUNTIME_AUDIT_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/runtime/cycle_orchestrator.py`
- `app/services/decision_autopsy.py`
- `app/services/paper_execution.py`
- `app/services/paper_intents.py`
- `app/services/paper_runtime_decisions.py`
- `tools/polybot.ps1`
- `tests/test_paper_execution_adapter_runtime.py`

## Tests Run

Focused:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_hunting_autopsy.py tests/test_runtime_continuity_autopsy.py tests/test_post_trade_rehunt.py tests/test_decision_diversity_autopsy.py tests/test_same_market_enter_arbitration.py tests/test_opposing_side_enter_resolution.py -q
```

Result: 7 passed.

Related:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_paper_session_reset.py tests/test_paper_session_status_report.py tests/test_enter_to_intent_bridge.py tests/test_enter_lifecycle_autopsy.py tests/test_decision_autopsy.py tests/test_blocker_autopsy.py tests/test_paper_execution_adapter_runtime.py -q
```

Result: 12 passed.

Compile:

```powershell
.venv\Scripts\python.exe -m compileall app tests
```

Result: passed.

## Runtime Verification

Deployment and runtime verification completed.

Commands:

```powershell
docker compose build api
docker compose build migrate
docker compose run --rm migrate
docker compose up -d --no-deps api
.\tools\polybot.ps1 health
.\tools\polybot.ps1 restart-paper-session -balance 1000
.\tools\polybot.ps1 hunting-autopsy
.\tools\polybot.ps1 status
.\tools\polybot.ps1 report
.\tools\polybot.ps1 autopsy
.\tools\polybot.ps1 enter-autopsy
.\tools\polybot.ps1 paper-session-status
.\tools\polybot.ps1 supervisor-autopsy
.\tools\polybot.ps1 paper-delta-autopsy
.\tools\polybot.ps1 off
```

Results:

- API build: passed.
- Migrate build: passed.
- Migrations: no pending migrations.
- API health: ok.
- New active session: `paper_session_20260619T190134Z_c4f2b3db`.
- Starting balance: 1000.
- 20-minute observation completed.
- Runtime continuity: CONTINUOUS.
- Hunting verdict: BROAD_HUNTING.
- Trade lifecycle verdict: ENTER_OK_EXIT_UNKNOWN.
- Final primary bottleneck: NO_BUG_CONSERVATIVE_FILTERING.
- Stale open cycles after repair: 0.
- Current active cycle after OFF: none.
- Latest completed cycle after OFF: `v2-20260619T192234-81c01e1794`.
- Supervisor: RUNNING during observation, STOPPED after OFF.
- Latest errors: none reported.
- Paper deltas: NO_CHANGE and not errors.
- Live/shadow/real orders: 0/0/0.

20-minute movement:

- Events: 4913 -> 5057.
- Linked events: 2207 -> 2265.
- Triggers: 433 -> 443.
- Candidates generated: 3026 -> 3120.
- Mesh reviewed: 1160 -> 1230.
- AI insights: 1411 -> 1495.
- Last-mile refresh attempts: 35 -> 41.
- Runtime PAPER decisions remained current at 17 rows.
- Decision unique markets: 9.
- Decision unique sides: 2.
- Paper ENTER decisions after arbitration: 0.
- Current-session paper intents/orders/fills/positions: 0/0/0/0.

Hunting autopsy snapshots:

- 5 minutes: CONTINUOUS, BROAD_HUNTING, stale open cycles 0, active-session candidates +45, Mesh +50, runtime runs +2, gate runs +1.
- 10 minutes: CONTINUOUS, BROAD_HUNTING, active-session events +144, triggers +20, candidates +52, Mesh +70, runtime runs +5, gate runs +4.
- 15 minutes: CONTINUOUS, BROAD_HUNTING, active-session triggers +22, candidates +95, Mesh +110, runtime runs +8, gate runs +7.
- 20 minutes: CONTINUOUS, BROAD_HUNTING, active-session triggers +24, candidates +106, Mesh +154, runtime runs +10, gate runs +9.

Final blocker truth:

- Current batch has no ENTER decisions.
- Opposing ENTER markets: none reported.
- Top blockers remain explicit conservative filters:
  - EXISTING_HARD_BLOCKERS_PRESENT: 15
  - OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD: 15
  - SAME_MARKET_OPPOSING_ENTER_CONFLICT: historical/current autopsy count 2, not active in the final batch.

SYSTEM OFF cleanup:

- System power: OFF.
- Runtime state: DATA_ONLY.
- Execution mode: DISABLED.
- Paper adapter: DISABLED.
- Live adapter: BLOCKED.
- Current active cycle: none.

## Safety Checklist

- Live orders untouched: YES
- Shadow orders untouched: YES
- Real orders untouched: YES
- Paper only: YES
- No thresholds lowered: YES
- No risk bypass: YES
- No capital bypass: YES
- No exit bypass: YES
- No duplicate exposure guard removed: YES
- Historical Paper data preserved: YES
- Current session counts remain session-scoped: YES
- No fake activity: YES
- No secrets printed: YES
- KILL/DATA_ONLY/PAPER rules preserved: YES

## Remaining Risks

- Current PAPER activity may remain conservative after arbitration if non-dominant market/side rows continue to miss score, thesis, exit, or policy requirements.
- Longer observation is still required to prove whether a fresh current-session ENTER is found naturally after the arbitration repair.
- The report can prove hunting movement and bottlenecks; it does not force new trades.

## Status

GREEN for runtime continuity and safety.

YELLOW for autonomous PAPER trading frequency because the system correctly found no current clean ENTER during the 20-minute observation. This is conservative filtering, not a scheduler or gate failure.

## Safe To Continue PAPER Runtime

YES, with PAPER-only execution and Live/Shadow/Real remaining blocked.
