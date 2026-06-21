# Paper Actionability Strict Qualification Report

## 1. Purpose

Fix the Phase 10 retry YELLOW finding where rows labeled `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` were not fully qualified for first Paper activation.

Hard rule:

`ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` may only appear when the selected row itself is candidate-scoped, token/side matched, risk-approved, thesis-backed, dynamic-hold-time-backed, exit-ready, capital-approved, lifecycle-allowed, and paper-safe.

## 2. Phase 10 Retry Finding

The Phase 10 retry correctly did not activate Paper Simulation.

False actionability rows had:

- `risk_gate_state=RISK_REVIEW`
- `candidate_event_scope=NOT_ACTIONABLE`
- `candidate_event_link_state=TOKEN_SIDE_MISMATCH`
- missing selected-row thesis fields
- missing selected-row dynamic hold-time fields

The system was safe, but Paper Actionability was looser than the Phase 10 pre-check.

## 3. Root Cause

`ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` was assigned in:

- `_map_actionability`
- `_reconcile_lifecycle_gate_actionability`

The lifecycle reconciliation helper allowed `RISK_REVIEW` and `RISK_WATCH` as ready states and did not require:

- valid candidate event link state
- token/side match
- final Risk approval
- joined supported trade thesis
- exit intent
- expected hold time / hold-time source
- strict risk-capital approval state

Trade thesis data existed separately in `trade_thesis_evaluations`, but the selected actionability row did not require a same-candidate, same-side, same-token, same-source-refresh-cycle thesis link.

## 4. Strict Qualification Contract

Added `is_strictly_paper_actionable(item)` and endpoint reconciliation in `app/control_center/paper_actionability.py`.

Rows now keep or receive `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` only if all required fields pass:

- complete candidate identity
- candidate-event scope in a candidate-actionable state
- candidate-event link state in a candidate-linked state
- no `TOKEN_SIDE_MISMATCH`
- `EDGE_SUPPORTED`
- `source_backed=true`
- `risk_usable=true`
- Risk state approved/support, not review/watch/blocked
- supported trade thesis present
- exit intent present
- expected hold time and hold-time source present
- risk-capital classification/policy approved or support
- exit ready
- lifecycle allows Paper intent with no critical blockers
- no stale selected gate
- no duplicate/open-position blocker

Failed rows are demoted to exact states such as:

- `NOT_ACTIONABLE_EVENT_SCOPE`
- `NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH`
- `NOT_ACTIONABLE_RISK_REVIEW`
- `NOT_ACTIONABLE_RISK_BLOCKED`
- `NOT_ACTIONABLE_MISSING_TRADE_THESIS`
- `NOT_ACTIONABLE_MISSING_TRADE_THESIS_LINK`
- `NOT_ACTIONABLE_MISSING_EXIT_INTENT`
- `NOT_ACTIONABLE_MISSING_DYNAMIC_HOLD_TIME`

## 5. Files Changed

- `app/control_center/paper_actionability.py`
- `tests/test_paper_actionability_strict_qualification.py`
- `tests/test_phase10_actionability_alignment.py`
- `tests/test_actionability_thesis_trace_join.py`
- `docs/PAPER_ACTIONABILITY_STRICT_QUALIFICATION_REPORT.md`

## 6. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_actionability_strict_qualification.py tests/test_phase10_actionability_alignment.py tests/test_actionability_thesis_trace_join.py -q
14 passed in 2.28s
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_intent_gate_hard_boundary.py tests/test_no_paper_artifacts_when_paper_off.py tests/test_phase10_precheck_no_intents.py tests/test_trade_thesis_classification.py tests/test_dynamic_hold_time_capital_efficiency.py tests/test_trade_thesis_actionability_trace.py tests/test_final_actionability_phase10_gate.py -q
10 passed, 6 skipped in 3.21s
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "paper_actionability or phase10 or strict_qualification or trade_thesis or dynamic_hold_time or paper_intent or paper_certification"
44 passed, 23 skipped, 2025 deselected in 5.32s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 7. Deployment Result

Deployment:

```text
docker compose build api
docker compose up -d --no-deps api
```

Verification:

- `/healthz`: `ok`
- `/runtime/health`: reachable
- `/dashboard/api/v2/control/paper-actionability?limit=100`: reachable
- Paper Simulation remained OFF
- Live execution remained disabled

No DB reset, no volume reset, and no destructive command.

## 8. DATA_ONLY Verification Result

Production verification used SYSTEM ON only in DATA_ONLY.

Before:

- `paper_intents=21`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `live_orders=0`
- `positions=0`
- `shadow_orders=0`
- `source_refresh_cycles=113`
- `trade_thesis_evaluations=740`

After four supervisor/source-refresh checks:

- `paper_intents=21`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `live_orders=0`
- `positions=0`
- `shadow_orders=0`
- `source_refresh_cycles=117`
- `trade_thesis_evaluations=800`

Paper remained OFF throughout.

## 9. Actionable Count Before / After

Before fix, Phase 10 retry observed false actionable rows:

- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`: `15` to `32` depending on tick
- selected rows included `TOKEN_SIDE_MISMATCH` and `RISK_REVIEW`

After fix and deployment:

- stopped endpoint check: `actionable_if_paper_enabled=0`
- DATA_ONLY tick 1: `actionable_if_paper_enabled=0`
- DATA_ONLY tick 2: `actionable_if_paper_enabled=0`
- DATA_ONLY tick 3: `actionable_if_paper_enabled=0`
- DATA_ONLY tick 4: `actionable_if_paper_enabled=0`

Example demoted blocker:

- candidate: `eligibility_exit_risk_thesis_coord_23aa4307ab254193a250b99e5adb32db`
- before: false `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`
- after: `NOT_ACTIONABLE_EVENT_SCOPE`
- evidence: `candidate_event_scope=NOT_ACTIONABLE`, `candidate_event_link_state=TOKEN_SIDE_MISMATCH`, `risk_gate_state=RISK_REVIEW`

Example candidate-scoped demotion:

- state: `NOT_ACTIONABLE_RISK_REVIEW`
- evidence: `candidate_event_scope=CANDIDATE_SCOPED`, `candidate_event_link_state=LINKED_TO_CANDIDATE`, `risk_gate_state=RISK_REVIEW`
- required: Risk must be approved, not review/watch/partial.

## 10. Can Retry Phase 10

YES, but only as a bounded Phase 10 retry and only if `/paper-actionability` shows a nonzero `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` count after this strict contract.

Current live verification produced zero strict-actionable rows, so Paper Simulation should not be enabled yet.

Extended Paper Runtime: NO.
Shadow: NO.
Live: NO.

## 11. Safety Result

Status: GREEN.

- Paper Simulation remained OFF during production verification.
- SYSTEM ON was used only for DATA_ONLY verification.
- SYSTEM OFF cleanup completed.
- No paper intents were created while Paper OFF.
- No paper orders were created while Paper OFF.
- No paper fills were created while Paper OFF.
- No paper positions were created while Paper OFF.
- No live orders were created.
- No shadow orders were created.
- Historical paper artifacts were not deleted.
- Risk, Exit, Lifecycle, Capital, and Actionability gates were tightened, not loosened.
- No destructive DB action was performed.
- No secrets were printed.
- Active server was verified.
