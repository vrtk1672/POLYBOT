# Candidate-Scoped Event Production Fix Report

## 1. Purpose

Fix Phase 9C-B candidate-scoped event production so candidate-targeted orderbook refreshes produce `orderbook.snapshot.created` events carrying `candidate_id`.

This phase remained DATA_ONLY. Paper Simulation, Shadow, Live, Full Monitor Run, and execution actions were not activated.

## 2. Root Cause Found

Candidate metadata was already supported at snapshot normalization and event publication, but the active supervisor did not produce candidate-scoped events because the candidate-targeted trusted orderbook refresher skipped CLOB refresh when a fresh global/market-level orderbook already existed.

The bounded resolver then spent its first 20 slots on stale historical candidates whose CLOB token returned `404`, so it never reached current refreshable candidates with fresh market-level books that needed candidate-scoped snapshots.

## 3. Exact Break Point In Candidate ID Propagation

Break point:

```text
TrustedOrderbookEvidenceService._load_candidates
↓
TrustedOrderbookEvidenceService._resolve_candidate
↓
_should_refresh_candidate_book(latest_expected)
```

The old behavior considered a fresh market-level orderbook sufficient and skipped candidate-targeted refresh. That meant:

- no candidate-scoped snapshot was created
- no snapshot metadata carried `candidate_id`
- `orderbook.snapshot.created` stayed market-level
- mesh bundle stayed market-scoped
- paper actionability correctly blocked on missing candidate-scoped event

## 4. Files Inspected

- `app/control_center/candidate_price_path.py`
- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/candidate_scoped_events.py`
- `app/control_center/candidate_event_correlation.py`
- `app/control_center/paper_actionability.py`
- `app/control_center/pre_paper_safety.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/control_center/event_mesh_proof.py`
- `app/control_center/runtime_supervisor.py`
- `app/services/trusted_orderbook.py`
- `app/data_foundation/orderbook_snapshotter.py`
- `app/repositories/orderbook_snapshot_repository.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/events/event_bus.py`
- `app/events/types.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_intents.py`
- `app/api/routes.py`

## 5. Files Changed

- `app/services/trusted_orderbook.py`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `tests/test_candidate_scoped_event_production.py`
- `docs/CANDIDATE_SCOPED_EVENT_PRODUCTION_FIX_REPORT.md`

## 6. Tests Added/Changed

Updated `tests/test_candidate_scoped_event_production.py` to prove:

- event payload preserves canonical candidate-scoped metadata
- fresh market-level book still requires candidate-scoped refresh
- fresh same-candidate scoped book does not require redundant refresh

## 7. Tests Run And Exact Results

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_candidate_scoped_event_production.py -q
3 passed in 1.89s
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_candidate_event_correlation.py tests/test_paper_actionability_contract.py tests/test_pre_paper_safety_invariants.py tests/test_mesh_evidence_bundle.py tests/test_event_mesh_proof.py tests/test_candidate_price_path.py tests/test_paper_readiness.py -q
10 passed, 37 skipped in 3.68s
```

Broad related slice:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "candidate_scoped or candidate_event or paper_actionability or pre_paper or mesh or event"
69 passed, 200 skipped, 1693 deselected in 6.11s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

Frontend:

```text
npm run typecheck
```

From repo root this failed because `package.json` is not at the root. Re-run from `frontend/control-center`:

```text
npm run typecheck
passed
```

## 8. Deployment/Restart Result

Port 8000 is served by Docker container `polybot_api`.

Deployment action:

```text
docker compose build api
docker compose up -d --no-deps api
```

No migrations, DB destructive actions, or volume resets were run.

## 9. Controlled Smoke Result

Procedure:

- captured baseline counts
- POSTed `system-on` through the official Control Center action endpoint
- waited 75 seconds for supervisor cycles
- did not enable Paper Simulation
- did not start Full Monitor Run
- polled read-only GET endpoints
- POSTed `system-off`
- verified stopped/blocked runtime truth and final counts

Result:

- `candidate_event_scoped`: 20
- `linked_to_candidate`: 20
- mesh bundles candidate-scoped: 20
- paper actionability evaluated candidate-scoped evidence
- Paper remained BLOCKED because Paper Simulation stayed OFF and lifecycle/paper blockers remain
- no forbidden artifact counts increased

## 10. Before/After Candidate Event Scoped Counts

Before smoke:

```json
{"candidate_event_scoped":0,"market_event_only":42,"token_side_mismatch":8}
```

During smoke:

```json
{"candidate_event_scoped":20,"market_event_only":28,"ambiguous_candidate_event":1,"token_side_mismatch":1}
```

After cleanup:

```json
{"candidate_event_scoped":20,"market_event_only":26,"ambiguous_candidate_event":2,"token_side_mismatch":2}
```

## 11. Sample Candidate-Scoped Event

```json
{
  "event_id": "4c5e66e2-1e64-4338-9d6e-748e5f3049b5",
  "correlation_id": "trusted_orderbook_e5077b7688af422880cfc1aae31b1d4b:ob_5dad358437234242a91860d5c79b05e6",
  "candidate_id": "eligibility_exit_risk_thesis_coord_c0d051b495b340fd89729ae752232ced",
  "market_id": "691547",
  "side": "YES",
  "token_id": "34626184950254225208692030156208941308358060420950772251072421141618169142241",
  "orderbook_snapshot_id": "ob_5dad358437234242a91860d5c79b05e6",
  "refresh_scope": "CANDIDATE_SCOPED",
  "candidate_event_scoped": true,
  "source": "polymarket_clob_candidate_recovery",
  "source_service": "TrustedOrderbookEvidenceService"
}
```

## 12. Sample Mesh Bundle

Sample bundle:

- `candidate_event_link_state`: `LINKED_TO_CANDIDATE`
- `candidate_event_actionability_scope`: `CANDIDATE_SCOPED`
- `correlation_confidence`: `HIGH`
- `bundle_state`: `CONFLICTED`
- `mesh_consensus_state`: `CONSENSUS_BLOCKED`
- all five opinions present
- lifecycle opinion blocks progression

## 13. Paper Actionability Impact

Paper actionability now consumes candidate-scoped evidence.

Sample:

- `candidate_event_link_state`: `LINKED_TO_CANDIDATE`
- `candidate_event_actionability_scope`: `CANDIDATE_SCOPED`
- `candidate_price_path_state`: `CANDIDATE_PRICE_READY`
- `paper_actionability_state`: `BLOCKED_BY_LIFECYCLE`
- `execution_allowed`: false

The blocker is no longer `NO_CANDIDATE_SCOPED_EVENT` for the candidate-scoped sample.

## 14. Pre-Paper Safety Impact

`NO_CANDIDATE_SCOPED_EVENT` cleared after active smoke.

Remaining pre-paper blockers include:

- `PAPER_SIMULATION_OFF`
- `NO_PAPER_ACTIONABILITY`
- `DUPLICATE_ACTIVE_INTENT_RISK`
- `OPEN_PAPER_POSITION_CONFLICT`
- `MARKET_SCOPED_ONLY_EVENT`
- `BLOCKED_BY_LIFECYCLE`

## 15. Artifact Safety Counts

Before smoke:

```json
{"event_log":552060,"orderbook_snapshots":51152,"brain_outputs":21612,"coordinator_decisions":20808,"paper_eligibility_candidates":20272,"paper_intents":20,"paper_orders":12,"paper_fills":9,"paper_positions":12,"live_orders":0,"positions":0}
```

During smoke:

```json
{"event_log":552186,"orderbook_snapshots":51232,"brain_outputs":22022,"coordinator_decisions":20898,"paper_eligibility_candidates":20272,"paper_intents":20,"paper_orders":12,"paper_fills":9,"paper_positions":12,"live_orders":0,"positions":0}
```

After cleanup:

```json
{"event_log":552188,"orderbook_snapshots":51232,"brain_outputs":22022,"coordinator_decisions":20898,"paper_eligibility_candidates":20272,"paper_intents":20,"paper_orders":12,"paper_fills":9,"paper_positions":12,"live_orders":0,"positions":0}
```

Only DATA_ONLY event/orderbook/brain/coordinator activity changed. Forbidden paper/live artifact counts were unchanged.

## 16. Remaining Risks

- Paper actionability remains blocked by lifecycle and pre-paper safety blockers.
- Some latest events remain market-level, ambiguous, or token-side mismatched. These are visible and non-actionable.
- Historical paper artifacts and duplicate active intent/open paper position conflict remain existing blockers.

## 17. Can Proceed To 9D/10

Can proceed to the next pre-paper hardening phase: YES.

Safe for PAPER/SHADOW/LIVE activation now: NO.
