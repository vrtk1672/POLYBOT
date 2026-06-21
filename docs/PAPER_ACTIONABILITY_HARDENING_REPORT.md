# POLYBOT Phase 9D Hardening Report

## Purpose

Phase 9D hardens the candidate-scoped Coordinator-to-Paper Actionability contract after the Phase 9C-B fix proved candidate-scoped `orderbook.snapshot.created` events.

The objective is to ensure candidate-scoped mesh evidence maps to a precise paper actionability state instead of a vague `NO_PAPER_ACTIONABILITY` blocker.

## Current Reality Found

- Candidate-scoped events are now present.
- Candidate-scoped bundles are present.
- All five mesh opinions are present on recent bundles: liquidity, risk, exit, capital, lifecycle.
- Current candidates are not paper-actionable because lifecycle and safety blockers remain.
- Paper Simulation is OFF and must remain separate from candidate-level actionability.
- Existing historical paper artifacts remain in the database: `paper_intents=20`, `paper_orders=12`, `paper_fills=9`, `paper_positions=12`.

## Actionability Contract

The contract now separates:

- Candidate Paper Actionability: whether the candidate could theoretically progress based on candidate-scoped mesh evidence.
- Operational Paper Execution State: whether paper execution is currently enabled and safe.

New or hardened states:

- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`
- `EXECUTION_DISABLED_PAPER_OFF`
- `EXECUTION_READY_IF_ENABLED`
- `EXECUTION_DISABLED_SAFETY`
- `EXECUTION_NOT_READY`
- `WAITING_FOR_LIFECYCLE`
- `WAITING_FOR_CAPITAL`
- `WAITING_FOR_RISK`
- `WAITING_FOR_EXIT`
- `BLOCKED_BY_DUPLICATE`
- `BLOCKED_BY_OPEN_POSITION`

Specific blockers now replace generic no-actionability where candidate-scoped bundles exist:

- `BLOCKED_BY_LIFECYCLE`
- `BLOCKED_BY_CAPITAL`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_EXIT`
- `BLOCKED_BY_DUPLICATE`
- `BLOCKED_BY_OPEN_POSITION`
- `WAITING_FOR_PRICE_REFRESH`
- `MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE`

## Files Inspected

- `app/control_center/paper_actionability.py`
- `app/control_center/pre_paper_safety.py`
- `app/control_center/unified_blockers.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/candidate_scoped_events.py`
- `app/control_center/candidate_event_correlation.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/candidate_explanations.py`
- `tests/test_paper_actionability_contract.py`

## Files Changed

- `app/control_center/paper_actionability.py`
- `app/control_center/pre_paper_safety.py`
- `app/control_center/unified_blockers.py`
- `app/control_center/candidate_explanations.py`
- `tests/test_paper_actionability_contract.py`

## Tests Added/Updated

Updated `tests/test_paper_actionability_contract.py` to prove:

- all-good candidate maps to `ACTIONABLE_SMALL_PAPER`
- all-good candidate with Paper OFF maps to `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` and `EXECUTION_DISABLED_PAPER_OFF`
- lifecycle denied maps to `BLOCKED_BY_LIFECYCLE`
- lifecycle stale maps to `WAITING_FOR_LIFECYCLE`
- capital blocked maps to `BLOCKED_BY_CAPITAL`
- capital missing maps to `WAITING_FOR_CAPITAL`
- risk blocked maps to `BLOCKED_BY_RISK`
- exit blocked maps to `BLOCKED_BY_EXIT`
- duplicate active intent maps to `BLOCKED_BY_DUPLICATE`
- open paper position maps to `BLOCKED_BY_OPEN_POSITION`
- stale orderbook maps to `WAITING_FOR_PRICE_REFRESH`
- market-level event maps to `BLOCKED_BY_DATA`
- generic no-actionability is not used when a specific blocker exists

## Tests Run

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_actionability_contract.py -q
13 passed in 1.73s
```

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_actionability_contract.py tests/test_candidate_explanations.py -q
13 passed, 15 skipped in 2.34s
```

```text
.venv\Scripts\python.exe -m pytest tests/test_candidate_scoped_event_production.py tests/test_pre_paper_safety_invariants.py tests/test_unified_blocker_shape.py tests/test_candidate_event_correlation.py tests/test_mesh_evidence_bundle.py tests/test_eligible_intent_bridge.py tests/test_paper_readiness.py -q
9 passed, 42 skipped in 3.34s
```

```text
.venv\Scripts\python.exe -m pytest tests -q -k "paper_actionability or pre_paper or candidate_scoped or blocker or mesh"
58 passed, 126 skipped, 1786 deselected in 6.94s
```

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

```text
npm run typecheck
passed
```

## Deployment / Restart

The API container was rebuilt and recreated only:

```text
docker compose build api
docker compose up -d --no-deps api
```

No DB reset, volume deletion, or destructive action was performed.

## GET Verification

After deployment and cleanup:

- `/runtime/health`: HTTP 200, `STOPPED`, `BLOCKED`, `FRESH`
- `/dashboard/api/v2/control/paper-actionability`: HTTP 200, `REAL`, `PARTIAL`, `FRESH`
- `/dashboard/api/v2/control/pre-paper-safety`: HTTP 200, `PARTIAL`, `PRE_PAPER_NOT_READY`, `FRESH`
- `/dashboard/api/v2/control/paper-readiness`: HTTP 200, `LOCKED`, `BLOCKED`, `STALE`
- `/dashboard/api/v2/control/candidate-scoped-events`: HTTP 200, `REAL`, `READY`, `FRESH`
- `/dashboard/api/v2/control/mesh-evidence-bundles`: HTTP 200, `REAL`, `READY`, `FRESH`
- `/dashboard/api/v2/control/eligible-intent-bridge`: HTTP 200, `REAL`, `BLOCKED`, `FRESH`
- `/dashboard/api/v2/control/candidate-explanations`: HTTP 200, `REAL`, `BLOCKED`, `FRESH`

## Smoke Results

Controlled SYSTEM ON smoke was run in DATA_ONLY only.

Observed during smoke:

- candidate-scoped events remained present
- paper actionability evaluated candidate-scoped bundles
- `NO_CANDIDATE_SCOPED_EVENT` remained cleared
- generic `NO_PAPER_ACTIONABILITY` was replaced by specific blockers in pre-paper safety
- Paper Simulation remained OFF
- paper readiness remained blocked
- SYSTEM OFF cleanup completed

Paper actionability counts during smoke:

```json
{
  "items_checked": 50,
  "candidate_scoped_bundles": 22,
  "actionable_small_paper": 0,
  "actionable_if_paper_enabled": 0,
  "blocked_by_lifecycle": 50,
  "blocked_by_capital": 0,
  "blocked_by_risk": 0,
  "blocked_by_exit": 0,
  "blocked_by_duplicate": 0,
  "blocked_by_open_position": 0,
  "blocked_by_data": 0,
  "unknown": 0
}
```

Sample item:

```json
{
  "candidate_paper_actionability_state": "BLOCKED_BY_LIFECYCLE",
  "operational_paper_execution_state": "EXECUTION_DISABLED_PAPER_OFF",
  "actionability_confidence": "HIGH",
  "opinions": {
    "liquidity": "PRESENT",
    "risk": "PRESENT",
    "exit": "PRESENT",
    "capital": "CAPITAL_OK",
    "lifecycle": "LIFECYCLE_DENIED"
  },
  "blockers": [
    "BLOCKED_BY_LIFECYCLE",
    "BLOCKED_BY_DUPLICATE",
    "BLOCKED_BY_OPEN_POSITION"
  ],
  "next_possible_state": "WAITING_FOR_LIFECYCLE_CLEARANCE"
}
```

## Pre-Paper Safety Impact

Pre-paper safety now reports specific actionability blockers instead of generic `NO_PAPER_ACTIONABILITY` when candidate-scoped bundles exist.

Smoke blockers included:

- `PAPER_SIMULATION_OFF`
- `BLOCKED_BY_LIFECYCLE`
- `BLOCKED_BY_DUPLICATE`
- `BLOCKED_BY_OPEN_POSITION`
- `MISSING_CANDIDATE_EVENT_LINK`
- `MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE`
- `WAITING_FOR_PRICE_REFRESH`
- `BLOCKED_BY_DATA`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_EXIT`

## Artifact Safety Counts

Before final smoke:

```json
{
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_fills": 9,
  "paper_positions": 12,
  "live_orders": 0,
  "positions": 0
}
```

After cleanup:

```json
{
  "paper_intents": 20,
  "paper_orders": 12,
  "paper_fills": 9,
  "paper_positions": 12,
  "live_orders": 0,
  "positions": 0
}
```

No forbidden paper/live/shadow artifacts were created.

## Remaining Risks

- Current candidate-scoped bundles are blocked by lifecycle denial.
- Duplicate active intent and open paper position risks remain present and correctly surfaced as blockers.
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` count is currently zero because lifecycle blocks all checked candidate-scoped bundles.

## Can Proceed

Phase 9D hardening is complete. The system can continue to the next pre-paper hardening step, but it is not safe for PAPER, SHADOW, or LIVE activation.
