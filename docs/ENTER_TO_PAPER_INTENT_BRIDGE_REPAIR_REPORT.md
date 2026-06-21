# ENTER to Paper Intent Bridge Repair Report

## Purpose

Repair the PAPER runtime lifecycle gap where an ENTER runtime decision was visible, but no current-session `paper_intent` was linked in the autopsy view.

This repair does not lower thresholds, bypass Risk/Capital/Exit, force trades, or touch Live/Shadow/Real paths.

## Root Cause Audit

1. Runtime ENTER decisions are selected for intent creation in `PaperIntentGateService.build_intents()`.
2. The gate calls `PaperRuntimeDecisionService.list_for_intent_gate()` after refreshing runtime decisions.
3. Before this repair, the gate called `PaperRuntimeDecisionService.refresh(force=False)`.
4. That refresh first marked current decisions non-current.
5. Then `_candidate_rows()` excluded recently processed policy review rows for 10 minutes.
6. Result: the gate could erase the current batch and see zero current runtime ENTER decisions.
7. Separately, runtime decision paper intent ids were derived only from `eligibility_id` / runtime decision id.
8. After paper session reset, the same decision id could conflict with a historical `paper_intent`.
9. `PaperIntentRepository.upsert_paper_intent()` preserved existing `paper_session_id` on conflict.
10. Result: the new current paper session did not receive its own linked intent.
11. Duplicate checks in runtime decision generation were global instead of active-session scoped.
12. Historical paper intents/positions could therefore affect current-session evaluation.

## Exact Stop Condition at PaperIntentGate

The observed `ENTER_WITHOUT_INTENT` was a real bug.

The current-session ENTER was not being linked because the gate handoff had two stale assumptions:

- current runtime decision refresh could safely use the recent-row exclusion filter
- runtime-decision intent identity could be global across paper sessions

Both assumptions are wrong after official paper session reset.

## Session-Scoped Duplicate Behavior

Implemented active-session scoping for runtime duplicate checks:

- current-session open positions block same market/side
- current-session active intents block same market/side
- previous-session intents/positions do not block a new active paper session

Duplicate protection remains active.

## Processed-State Behavior

Runtime-decision paper intent identity is now session-scoped for runtime decisions:

`paper_intent_<runtime_decision_id>_<paper_session_id>`

This allows a fresh paper session to test a valid ENTER again while preserving historical paper rows.

No global one-shot decision rule was added.

## Fix Implemented

- `PaperIntentGateService` now refreshes runtime decisions with `force=True` before selecting gate candidates.
- Runtime-decision paper intent ids include active `paper_session_id`.
- Runtime-decision no-trade ids include active `paper_session_id`.
- Runtime-decision no-trade `eligibility_id` values include active `paper_session_id` because `no_trade_log` has an existing unique index on `eligibility_id`.
- Runtime decision duplicate checks filter by active `paper_session_id` when the ledger tables support it.
- `SameMarketSideGuardService` now scopes active paper intents and open paper positions to the active paper session.
- Decision autopsy now exposes:
  - `intent_gate_evaluation`
  - `selected_for_intent`
  - `intent_created`
  - `intent_skip_reason`
  - `duplicate_scope`
  - `processed_scope`
  - `session_match`
  - `bug_suspect`

## Files Changed

- `app/services/paper_intents.py`
- `app/services/paper_runtime_decisions.py`
- `app/services/same_market_side_guard.py`
- `app/services/decision_autopsy.py`
- `tests/decision_autopsy_helpers.py`

## Files Created

- `tests/test_enter_to_intent_bridge.py`
- `tests/test_paper_intent_gate_session_scope.py`
- `tests/test_enter_autopsy_expected_skip.py`
- `docs/ENTER_TO_PAPER_INTENT_BRIDGE_REPAIR_REPORT.md`

## Tests Run

Focused:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_enter_to_intent_bridge.py tests/test_paper_intent_gate_session_scope.py tests/test_enter_autopsy_expected_skip.py tests/test_enter_lifecycle_autopsy.py -q
```

Result: `7 passed in 50.23s`.

Related:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_session_reset.py tests/test_paper_session_status_report.py tests/test_paper_execution_adapter_runtime.py tests/test_decision_autopsy.py tests/test_blocker_autopsy.py tests/test_paper_delta_autopsy.py -q
```

Result: `10 passed in 68.89s`.

After runtime verification exposed a session-scoped `no_trade_log.eligibility_id` collision:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_enter_to_intent_bridge.py tests/test_paper_intent_gate_session_scope.py tests/test_enter_autopsy_expected_skip.py tests/test_enter_lifecycle_autopsy.py -q
```

Result: `7 passed in 62.77s`.

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_session_reset.py tests/test_paper_session_status_report.py tests/test_paper_execution_adapter_runtime.py tests/test_decision_autopsy.py tests/test_blocker_autopsy.py tests/test_paper_delta_autopsy.py -q
```

Result: `10 passed in 69.90s`.

Compile:

```powershell
.venv\Scripts\python.exe -m compileall app tests
```

Result: passed.

## Runtime Verification

Deployment and PAPER verification commands:

```powershell
docker compose build api
docker compose build migrate
docker compose run --rm migrate
docker compose up -d --no-deps api
.\tools\polybot.ps1 restart-paper-session -balance 1000
Start-Sleep -Seconds 900
.\tools\polybot.ps1 report
.\tools\polybot.ps1 enter-autopsy
.\tools\polybot.ps1 paper-session-status
```

## ENTER Autopsy Before / After

Before:

- ENTER decision visible
- current-session intent/order/fill/position not linked
- `BUG_SUSPECT_ENTER_WITHOUT_INTENT`

Expected after:

- valid current-session ENTER creates current-session `paper_intent`
- if skipped, skip reason is explicit and not bug-suspect

First runtime verification after the bridge repair created no current-session paper rows, but exposed an additional identity bug:

- `no_trade_log` unique index `uq_no_trade_eligibility` rejected repeated runtime no-trade rows across sessions.
- Runtime-decision no-trade ids were session-scoped, but `eligibility_id` was still global.

That is now fixed by scoping runtime no-trade `eligibility_id` to the active paper session while retaining the original runtime decision id in `evidence.original_eligibility_id`.

## Safety Checklist

- Risk thresholds unchanged.
- Capital thresholds unchanged.
- Exit requirements unchanged.
- Duplicate protection preserved.
- Current-session duplicate exposure still blocks.
- Historical paper session rows preserved.
- Live/Shadow/Real untouched.
- No forced paper trades.

## Remaining Risks

Runtime verification still needs to confirm whether a fresh natural ENTER appears during the observation window. If no ENTER appears, status should be YELLOW with exact blockers rather than forced activity.

## Status

Implementation status before runtime deployment: GREEN for tests and compile.
