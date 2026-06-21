# PAPER Intent Gate Idempotency Repair Report

## Purpose

Fix the Defense 20 PAPER runtime failure where `paper_intents` insertion crashed with:

`UniqueViolation: duplicate key value violates unique constraint "paper_intents_eligibility_id_key"`.

This repair preserves the Paper Defense dial, current-session accounting, historical paper data, duplicate exposure safety, and Live/Shadow/Real zero-state.

## Runtime Symptom

After:

```powershell
.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20
```

Defense 20 was active and learning entries were moving, but the Paper simulation cycle failed when the Paper Intent Gate re-encountered an eligibility/runtime decision that already had a `paper_intents.eligibility_id` row.

## Root Cause Audit

- Table: `paper_intents`
- Constraint: `paper_intents_eligibility_id_key`
- Constraint definition: `UNIQUE (eligibility_id)`
- Schema source: `app/db/migrations/0084_v2_neural_mesh_paper_intent_no_trade_ledger.sql`
- Insert path: `app/repositories/paper_intent_repository.py::upsert_paper_intent`
- Gate path: `app/services/paper_intents.py::PaperIntentGateService.build_intents`
- Runtime intent builder: `app/services/paper_intents.py::_intent_from_candidate`

The repository insert used `ON CONFLICT (paper_intent_id)` only. It did not handle the separate unique constraint on `eligibility_id`, so a repeated eligibility raised a database exception and aborted the whole cycle.

Runtime-created Paper intent IDs were session-aware, but their stored `eligibility_id` was still the raw `paper_runtime_decision_*` id. Historical sessions already contained these unscoped ids, so a clean Paper session could collide with prior session rows when Defense 20 reprocessed a current runtime decision.

Primary classification: `D. MISSING_IDEMPOTENT_INSERT`

Contributing issue: runtime Paper intent `eligibility_id` was not session-scoped while the corresponding `paper_intent_id` was.

## Exact Duplicate Source

The observed duplicate came from `paper_runtime_decision_*` eligibility IDs created by `PaperRuntimeDecisionService` and consumed by `PaperIntentGateService`.

The duplicate was expected runtime reprocessing behavior. The bug was treating it as an unhandled insert failure.

## Schema / Constraint Analysis

`paper_intents.eligibility_id` remains globally unique. The constraint was not dropped. The repair avoids collisions by:

- session-scoping runtime Paper intent eligibility IDs
- preserving original runtime decision ids in `evidence.original_eligibility_id`
- adding repository get-or-create behavior when an eligibility already exists

No migration was required.

## Repair Design

Implemented:

- Runtime Paper intent eligibility is now scoped as:
  `paper_runtime_decision_<hash>_<paper_session_id>`
- Original runtime eligibility remains in intent evidence.
- `PaperIntentRepository.upsert_paper_intent` checks for existing `eligibility_id` before insert.
- Existing eligibility returns the existing row and records:
  - `ALREADY_INTENT_EXISTS_FOR_ELIGIBILITY`
  - `duplicate_eligibility_encountered`
  - `duplicate_crash_prevented`
  - `REUSED_EXISTING_INTENT` or `SKIPPED_EXISTING_INTENT`
- Gate run payload and paper-intent dashboard summary expose idempotency counts.
- CLI report prints:
  `Intent duplicate eligibility: encountered=...; reused=...; skipped=...; crash_prevented=...`

## Files Changed

- `app/repositories/paper_intent_repository.py`
- `app/services/paper_intents.py`
- `tools/polybot.ps1`
- `tests/test_paper_intent_gate_idempotency.py`
- `tests/test_paper_intent_duplicate_eligibility.py`
- `tests/test_paper_defense_learning_idempotency.py`
- `tests/test_paper_defense_learning_ledger.py`
- `tests/test_paper_session_status_report.py`

## Tests Run

Focused:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_intent_gate_idempotency.py tests/test_paper_intent_duplicate_eligibility.py tests/test_paper_defense_learning_idempotency.py tests/test_enter_lifecycle_autopsy.py tests/test_hunting_autopsy.py tests/test_report_autopsy_output.py -q
```

Result: `8 passed in 215.01s`.

Related:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_defense_level.py tests/test_paper_defense_blocker_policy.py tests/test_paper_defense_learning_ledger.py tests/test_paper_session_status_report.py tests/test_enter_to_intent_bridge.py tests/test_paper_execution_adapter_runtime.py -q
```

Result: `14 passed in 412.73s`.

Compile:

```powershell
.venv\Scripts\python.exe -m compileall app tests
```

Result: passed.

## Runtime Verification

Deployment:

```powershell
docker compose build api
docker compose build migrate
docker compose run --rm migrate
docker compose up -d --no-deps api
.\tools\polybot.ps1 health
```

Migration result: no pending migrations.

Started:

```powershell
.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20
```

Observed for 15 minutes in three 5-minute slices.

Final verification:

- Runtime: PAPER
- Supervisor: RUNNING
- Defense level: 20
- Base threshold: 60
- Adjusted threshold: 42
- Max deployed capital: 80%
- Max single trade: 15%
- Max open positions: 15
- Exit fallback: true
- Strategic blockers: WARNING_ONLY
- Integrity blockers: HARD
- Latest errors: none reported
- UniqueViolation: gone
- Intent duplicate eligibility: `encountered=1; reused=1; skipped=0; crash_prevented=True`
- Current-session paper intents/orders/fills/positions: `1 / 1 / 1 / 1`
- Open paper positions: `0`
- Realized PnL: `-20.0`
- Learning entries / ignored blockers / softened blockers / fallback exits: `17 / 15 / 15 / 15`
- Live orders: `0`
- Shadow orders: `0`
- Real orders: `0`

Session report generated:

```text
run_reports/paper_session_learning_paper_session_20260619T222447Z_779e17e4/paper_session_learning_report_paper_session_20260619T222447Z_779e17e4.json
```

System cleanup:

```powershell
.\tools\polybot.ps1 off
.\tools\polybot.ps1 health
```

Final cleanup state:

- System power: OFF
- Runtime state: DATA_ONLY
- Execution mode: DISABLED
- Paper adapter: DISABLED
- Live adapter: BLOCKED
- API health: OK

## Defense 20 Behavior After Fix

Defense 20 remained active. Strategic blockers continued to be softened/ignored according to policy. Integrity blockers remained hard. The repair did not lower thresholds, bypass risk/capital/exit, or force trades.

## Autopsy / Report Changes

`.\tools\polybot.ps1 report` now shows PaperIntentGate idempotency:

```text
Intent duplicate eligibility: encountered=1; reused=1; skipped=0; crash_prevented=True
```

Handled duplicate eligibility no longer appears as a latest error.

## Safety Checklist

- Old Paper history preserved: YES
- No destructive DB action: YES
- No migration required: YES
- Duplicate eligibility handled idempotently: YES
- No duplicate paper intents for one eligibility: YES
- No duplicate orders/fills/positions from duplicate eligibility: YES
- Defense 20 unchanged: YES
- Strategic blockers still Defense-aware: YES
- Integrity blockers remain hard: YES
- LIVE adapter remained blocked: YES
- Shadow remained disabled: YES
- No real orders created: YES
- No live orders created: YES
- No shadow orders created: YES
- No secrets printed: YES

## Remaining Risks

- If future code creates non-runtime Paper intents from old global eligibility sources, those remain intentionally global one-shot unless made session-aware by design.
- The 15-minute runtime hit the duplicate and handled it successfully; longer Defense 20 sessions should continue to be monitored for any other idempotency contracts.

## Status

GREEN.

Safe to continue Defense 20 Paper sessions: YES.
