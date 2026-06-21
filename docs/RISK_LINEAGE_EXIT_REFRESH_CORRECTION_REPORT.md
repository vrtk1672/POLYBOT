# Risk Lineage / Candidate Identity + Exit Refresh Correction Report

## 1. Purpose

This pass corrected the final pre-Phase-10 blocker path between candidate-scoped Mesh evidence and Paper actionability:

candidate-scoped event -> candidate identity -> risk lineage -> exit plan -> lifecycle -> coordinator -> paper actionability.

The goal was not to force readiness. The goal was to remove stale or incomplete lineage/exit blockers and determine whether Phase 10 can start from current source-backed evidence.

## 2. Current Reality Before Correction

The latest decision run proved:

- SYSTEM ON starts the retained Runtime Supervisor.
- Candidate-scoped events and Mesh bundles exist.
- Liquidity, Risk, Exit, Capital, and Lifecycle opinions are event-native.
- Duplicate active intent and open paper position false positives were corrected.
- Same-market guard revalidation works.
- Paper Simulation remains OFF.

Remaining blockers were:

- `RISK_BLOCKED_LINEAGE_CRITICAL`
- `STALE_EXIT_PLAN` on some fresh-seed paths

## 3. Risk Lineage Root Cause

`RISK_BLOCKED_LINEAGE_CRITICAL` is produced by `RiskEvidenceMeshService._classify` when critical candidate lineage is missing.

The break point was candidate identity construction in `RiskEvidenceMeshService._candidate_records`. It selected candidate fields directly from `paper_eligibility_candidates`, where `expected_token_id` can be blank and `condition_id` was projected as `NULL::text`, even though fresh candidate-scoped `orderbook_snapshots` and `markets_v2` contained the missing token and condition evidence.

This caused candidate-scoped bundles to reach lifecycle with incomplete risk identity despite having source-backed candidate/event/orderbook truth elsewhere.

## 4. Candidate Identity Correction

`app/services/risk_evidence_mesh.py` now builds candidate risk identity from candidate-scoped sources:

- `paper_eligibility_candidates`
- latest candidate-scoped `orderbook_snapshots`
- `markets_v2`

The service now coalesces:

- `condition_id` from `markets_v2.condition_id`
- `token_id` from candidate `expected_token_id`, latest candidate-scoped snapshot token, or canonical market side token
- `orderbook_snapshot_id` from candidate or latest candidate-scoped snapshot

The classifier also preserves missing critical lineage as `RISK_BLOCKED_LINEAGE_CRITICAL` instead of masking it behind edge-source blockers.

## 5. Exit Refresh Root Cause

`STALE_EXIT_PLAN` came from lifecycle source refs selecting stale legacy `exit_plans`. Existing Exit Foundation generation was broad and risk-decision based; it did not provide a narrow candidate-specific DATA_ONLY refresh path tied to the current candidate-scoped orderbook event.

## 6. Exit Refresh Correction

`app/services/exit_foundation.py` now supports:

`ExitFoundationService.build_candidate_exit_plan_with_conn(...)`

This creates or updates `exit_candidate_{candidate_id}` plans from candidate-scoped evidence:

- candidate id
- market id / condition id
- side
- token id
- latest candidate-scoped orderbook snapshot
- latest risk evidence mesh row
- event id and correlation id

The refresh is DATA_ONLY safe. It does not create intents, orders, fills, positions, or execution permission.

`app/events/consumers/orderbook_mesh_consumer.py` now refreshes the candidate-specific exit plan before forced lifecycle re-evaluation.

## 7. Lifecycle Re-Evaluation Result

Lifecycle no longer blocks because stale capital, duplicate/open-position false positives, missing risk lineage, or stale exit plan evidence.

The current sampled lifecycle blocker is source-backed:

- `RISK_BLOCKED`
- `RISK_BLOCKED_NO_SOURCE_BACKED_EDGE`

Candidate-specific exit plans are now fresh and mirror that current risk block.

## 8. Paper Actionability Result

After the correction run:

- `ACTIONABLE_SMALL_PAPER = 0`
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED = 0`
- `blocked_by_lifecycle = 50`

The generic no-actionability path is not the blocker. Paper actionability is specific: lifecycle blocks because current risk evidence reports no source-backed edge.

## 9. Pre-Paper Safety Result

Pre-paper safety remains:

`PRE_PAPER_NOT_READY`

Current blockers include:

- `PAPER_SIMULATION_OFF` (expected operational blocker)
- `BLOCKED_BY_LIFECYCLE`
- `MISSING_CANDIDATE_EVENT_LINK` for non-candidate-linked samples

## 10. What-If Analysis

Current state:

- Lifecycle: denied
- Actionability: `BLOCKED_BY_LIFECYCLE`
- Root blocker: `RISK_BLOCKED_NO_SOURCE_BACKED_EDGE`

If Paper Simulation were ON only:

- Still blocked by lifecycle.
- Phase 10 would not create valid candidate actionability from Paper ON alone.

If Risk lineage blocker cleared:

- Already cleared for sampled candidate-scoped rows.
- Current blocker becomes source-backed edge absence, not lineage.

If stale Exit plan cleared:

- Cleared by candidate-specific exit refresh.
- Exit remains blocked only because risk is currently blocked.

If Risk and Exit both cleared:

- Candidate could progress to lifecycle allow/re-evaluation and then potentially `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`, assuming no new current blockers appear.

If all current blockers cleared:

- Phase 10 would be useful only after at least one candidate has source-backed risk support and fresh exit readiness.

## 11. Files Changed

- `app/services/risk_evidence_mesh.py`
- `app/services/trade_lifecycle.py`
- `app/services/exit_foundation.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `tests/test_risk_lineage_candidate_identity.py`
- `tests/test_exit_candidate_specific_refresh.py`

No DB migration was added.

## 12. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_risk_lineage_candidate_identity.py tests/test_exit_candidate_specific_refresh.py -q
4 passed in 0.37s
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_pre_paper_blocker_correction.py tests/test_paper_actionability_contract.py tests/test_pre_paper_safety_invariants.py tests/test_candidate_scoped_event_production.py tests/test_lifecycle_capital_event_native_opinions.py tests/test_mesh_evidence_bundle.py tests/test_paper_readiness.py -q
25 passed, 21 skipped in 3.18s
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "risk or lineage or exit or lifecycle or pre_paper or paper_actionability or candidate_scoped or mesh"
149 passed, 291 skipped, 1543 deselected in 8.15s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 13. Deployment Result

```text
docker compose build api
Succeeded

docker compose up -d --no-deps api
Succeeded
```

Active API verification:

- `/healthz`: `status=ok`, `ready=true`
- `/dashboard/api/v2/control/paper-actionability`: `status=REAL`
- `/dashboard/api/v2/control/pre-paper-safety`: `status=PARTIAL`, `readiness_state=PRE_PAPER_NOT_READY`
- `/dashboard/api/v2/control/paper-readiness`: `status=LOCKED`, `readiness_state=BLOCKED`
- `/dashboard/api/v2/control/paper-certification-plan`: `status=REAL`

## 14. Controlled SYSTEM ON Decision Run

Action:

- POST `/system/power/on`
- Waited for supervisor cycles
- Did not enable Paper Simulation
- Did not start Full Monitor Run
- POST `/system/power/off`

During run:

- Candidate-scoped events existed.
- Candidate-scoped Mesh bundles existed.
- All-five opinions remained present.
- Risk lineage identity was corrected.
- Candidate-specific exit plans were refreshed.
- Lifecycle re-evaluated from corrected inputs.
- Paper actionability stayed specific and blocked.

## 15. Forbidden Artifact Counts

Before -> After:

- `paper_intents`: 20 -> 20
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `paper_position_closes`: 9 -> 9
- `live_orders`: 0 -> 0
- `positions`: 0 -> 0

DATA_ONLY derived rows increased as expected:

- `event_log`
- `orderbook_snapshots`
- `risk_decisions`
- `exit_plans`
- `lifecycle_governance_decisions`
- `brain_outputs`
- `coordinator_decisions`
- `no_trade_log`

## 16. Remaining Blockers

Minimum blocker before Phase 10:

- At least one candidate needs source-backed risk support. Current sampled candidate-scoped rows block with `RISK_BLOCKED_NO_SOURCE_BACKED_EDGE`.

Expected operational blocker:

- `PAPER_SIMULATION_OFF`

Non-qualifying samples may also show candidate-link blockers, but candidate-scoped samples no longer fail due stale lineage or stale exit plan.

## 17. READY_FOR_PHASE_10

`READY_FOR_PHASE_10 = NO`

Reason:

No sampled candidate reaches `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`. The remaining blocker is current and source-backed: risk cannot prove source-backed edge for the candidate-scoped evidence.

## 18. Recommended Next Step

Do not start Phase 10 yet.

Next correction should target risk edge source production/classification, not lineage. Specifically, determine why candidate-scoped fresh orderbook/market evidence still yields `RISK_BLOCKED_NO_SOURCE_BACKED_EDGE`, and whether a missing edge-source feed, scoring threshold, or evidence join is preventing at least one candidate from reaching risk support.
