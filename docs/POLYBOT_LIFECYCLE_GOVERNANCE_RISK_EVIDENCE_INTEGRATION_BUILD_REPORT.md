# POLYBOT Lifecycle Governance Risk Evidence Integration Build Report

Date: 2026-06-05

Security governance status: `YELLOW_ACCEPTED_BY_OPERATOR`

## Summary

Implemented Lifecycle Governance calibration so fresh Risk Evidence Mesh decisions are selected over stale legacy risk summaries. Fresh `RISK_REVIEW` no longer inherits generic stale legacy `RISK_BLOCKED` / `RISK_BLOCKED_LINEAGE` / `RISK_BLOCKED_NO_EDGE` / `STALE_RISK_DECISION`.

Critical non-risk blockers still block. No trading mutation occurred.

## Current Reality Found

Before the change:

* `risk_evidence_mesh_evaluations`: 716
* `RISK_REVIEW`: 24
* `RISK_BLOCK`: 692
* source-backed edge types:
  * `PRICE_PAYOUT_ASYMMETRY`: 12
  * `NEWS_REPRICING_SIGNAL`: 12
* Lifecycle Governance still had `ACTIONABLE_SMALL_PAPER=0` and `allow_paper_intent_count=0`

Deep dive showed the 24 `RISK_REVIEW` rows had no Risk Evidence critical blockers, but related lifecycle governance decisions stayed blocked by stale legacy risk and stale non-risk sources. After inspection, the valid remaining critical blockers were primarily:

* `STALE_EXIT_PLAN`
* `STALE_ORDERBOOK`
* `STALE_CAPITAL_EVALUATION`
* `STALE_LIFECYCLE_PLAN`

## Root Cause Fixed

Lifecycle Governance seeded critical blockers from legacy lifecycle plan status and missing inputs before selecting Risk Evidence. For non-blocking Risk Evidence it removed only generic `RISK_BLOCKED`, leaving stale legacy risk sub-blockers and later freshness `STALE_RISK_DECISION`.

The fix removes all legacy risk blockers when fresh non-blocking Risk Evidence is selected, while preserving unrelated critical blockers.

## Files Created

* `docs/POLYBOT_LIFECYCLE_GOVERNANCE_RISK_EVIDENCE_INTEGRATION.md`
* `docs/POLYBOT_LIFECYCLE_GOVERNANCE_RISK_EVIDENCE_INTEGRATION_BUILD_REPORT.md`

## Files Changed

* `app/services/lifecycle_governance.py`
* `app/services/paper_trade_forensics.py`
* `app/services/brain_dialogue.py`
* `tests/test_lifecycle_governance.py`

## DB Migrations

None.

Trace data is stored in existing `lifecycle_governance_decisions.metadata_json` and source rows are written through existing `lifecycle_governance_sources`.

## Risk Source Priority Model

Priority:

1. Risk Evidence Mesh
2. Fresh legacy Risk Core
3. Last-known legacy risk for context
4. Historical risk for forensics

Fresh non-blocking Risk Evidence removes:

* `RISK_BLOCKED`
* `RISK_BLOCKED_BAD_LIQUIDITY`
* `RISK_BLOCKED_SPREAD`
* `RISK_BLOCKED_STALE_DATA`
* `RISK_BLOCKED_NO_TRUSTED_ORDERBOOK`
* `RISK_BLOCKED_MISSING_EXECUTABLE_PRICE`
* `RISK_BLOCKED_LOW_CONFIDENCE`
* `RISK_BLOCKED_NO_EDGE`
* `RISK_BLOCKED_LINEAGE`
* `RISK_BLOCKED_UNKNOWN`
* `RISK_BLOCKED_CRITICAL_MISSING`
* `STALE_RISK_DECISION`

Fresh `RISK_BLOCK` still hard-blocks.

## Actionability Mapping Rules

* `RISK_BLOCK` -> `HARD_BLOCK`
* `RISK_REVIEW` with only stale/legacy risk blockers -> `WATCH_FOR_CONFIRMATION`
* `RISK_REVIEW` with stale exit/orderbook/capital/lifecycle blockers -> `HARD_BLOCK`
* `RISK_SUPPORT` can contribute to actionability only if all other critical Paper gates are clear

No fake actionable plans were created.

## 24 Risk Review Deep Dive

The latest 24 `RISK_REVIEW` subjects were re-evaluated directly.

All selected `RISK_EVIDENCE_MESH` as the risk source.

All ignored stale legacy risk sources.

All remained `HARD_BLOCK` because non-risk critical blockers remained:

* `STALE_CAPITAL_EVALUATION`
* `STALE_EXIT_PLAN`
* `STALE_LIFECYCLE_PLAN`
* `STALE_ORDERBOOK`

No `RISK_REVIEW` became actionable in production smoke.

## Governance Decision Trace Changes

Added metadata:

* `selected_risk_source`
* `selected_risk_source_freshness`
* `selected_risk_evidence_evaluation_id`
* `legacy_risk_decision_id`
* `legacy_risk_state`
* `legacy_ignored`
* `ignored_legacy_risk_sources`
* `ignored_reason`
* `final_risk_interpretation`
* `blockers_by_priority`

## API / Dashboard Changes

Extended `GET /dashboard/api/v2/lifecycle-governance` with:

* `risk_evidence_used_count`
* `legacy_risk_ignored_count`
* `risk_review_promoted_to_watch_count`
* `risk_review_kept_blocked_count`
* `risk_review_actionable_count`
* `latest_risk_review_traces`

All dashboard responses remain `mock_data=false`.

## Forensics / Dialogue Changes

Paper forensics now exposes:

* lifecycle governance risk source trace
* selected risk source
* legacy risk ignored flag

Brain dialogue now emits clearer lifecycle governance messages when fresh Risk Evidence replaced stale legacy risk.

## Tests Added

Added coverage for:

* fresh `RISK_REVIEW` ignoring stale legacy risk
* fresh `RISK_REVIEW` preserving non-risk critical blockers
* fresh `RISK_BLOCK` remaining hard-block
* dashboard risk-evidence integration counts

## Tests Run

Compile:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app python -m py_compile app/services/lifecycle_governance.py app/services/paper_trade_forensics.py app/services/brain_dialogue.py tests/test_lifecycle_governance.py"
```

Result: passed.

New targeted tests:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_lifecycle_governance.py -k 'risk_review or fresh_risk_block or dashboard_exposes'"
```

Result: `4 passed, 12 deselected, 1 warning`

Lifecycle governance:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_lifecycle_governance.py"
```

Result: `16 passed, 1 warning`

Risk evidence:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_risk_evidence_mesh.py"
```

Result: `13 passed, 1 warning`

Truth and Paper safety:

```text
docker compose --profile test run --rm -v ${PWD}:/app test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_truth_state_service.py tests/test_paper_no_live_safety.py tests/test_paper_execution_service.py"
```

Result: `16 passed, 1 warning`

One grouped Docker wrapper run timed out before returning results and was replaced by the smaller passing commands above.

## Runtime Smoke Results

No 10m/30m/4h runtime run was started.

System stayed `OFF`.

Bounded derived evaluation:

* `/lifecycle-governance/evaluate` checked 100 plans
* direct service smoke re-evaluated 24 latest `RISK_REVIEW` subjects
* no Paper/live/capital mutation

After smoke:

* `risk_evidence_used_count`: 108
* `legacy_risk_ignored_count`: 12
* `risk_review_promoted_to_watch_count`: 0
* `risk_review_kept_blocked_count`: 12
* `risk_review_actionable_count`: 0
* `allow_paper_intent_count`: 0
* `allow_paper_execution_count`: 0

## Safety Counts

Unchanged:

* `paper_intents`: 20
* `paper_orders`: 12
* `paper_fills`: 9
* `paper_positions`: 12
* `paper_position_closes`: 9
* `paper_capital_ledger`: 38
* `live_orders`: 0
* `orders_v2`: 1
* `fills_v2`: 1
* canonical `positions`: 0

Capital unchanged:

* `current_balance`: 996.819322
* `available_balance`: 996.819322
* `locked_balance`: 0
* `open_exposure`: 0
* `realized_pnl`: -3.180678
* `unrealized_pnl`: 0

## Samples

Stale legacy risk ignored:

* subject `fresh_seed_2354064_YES`
* selected source `RISK_EVIDENCE_MESH`
* ignored `RISK_BLOCKED`, `STALE_RISK_DECISION`
* remained blocked by `STALE_CAPITAL_EVALUATION`, `STALE_EXIT_PLAN`, `STALE_LIFECYCLE_PLAN`, `STALE_ORDERBOOK`

Risk review kept blocked:

* subject `fresh_seed_597964_YES`
* `RISK_REVIEW`
* source-backed `PRICE_PAYOUT_ASYMMETRY`
* no Risk Evidence critical missing
* blocked by stale non-risk critical sources

Risk review promoted to watch/actionable:

* no production subject promoted in smoke because stale non-risk critical gates remained
* test coverage confirms promotion to `WATCH_FOR_CONFIRMATION` when only stale legacy risk blockers exist

## Remaining Risks

* Current production candidates still need fresh exit, capital, lifecycle, and orderbook sources before actionability can appear.
* Dashboard aggregate history still includes older lifecycle governance decisions; use the new trace fields to distinguish selected current risk source.
* No live run was performed in this phase.

## Phase Status

GREEN for the integration fix.

Operational status remains YELLOW until a fresh runtime cycle clears non-risk stale blockers.

Can run trade-focused 10m validation: YES.

---

## 2026-06-07 Calibration Addendum

Security governance status: `YELLOW_ACCEPTED_BY_OPERATOR`

### Summary

Tightened the Risk Evidence source priority model so Lifecycle Governance selects Risk Evidence Mesh only when the Risk Evidence row itself is fresh. Stale Risk Evidence is preserved as context and cannot override current governance.

### Root Cause Further Closed

The previous integration selected the latest Risk Evidence row without explicitly proving that row was `ACTIVE_FRESH`. That was directionally correct for the latest 10m run but incomplete against the lifecycle rule:

`Fresh Risk Evidence beats stale legacy Risk summary.`

The implementation now enforces the word fresh.

### Files Changed

* `app/services/lifecycle_governance.py`
* `app/services/risk_evidence_mesh.py`
* `tests/test_lifecycle_governance.py`
* `docs/POLYBOT_LIFECYCLE_GOVERNANCE_RISK_EVIDENCE_INTEGRATION.md`
* `docs/POLYBOT_LIFECYCLE_GOVERNANCE_RISK_EVIDENCE_INTEGRATION_BUILD_REPORT.md`

### Files Created

* `scripts/verify_lifecycle_governance_risk_evidence_smoke.py`

### DB Migrations

None. Existing `lifecycle_governance_decisions.metadata_json` and `lifecycle_governance_sources` remain the trace storage.

### Risk Source Priority Model Update

Priority is now:

1. `ACTIVE_FRESH` Risk Evidence Mesh evaluation.
2. Fresh legacy `risk_decision`.
3. Last-known Risk Evidence or legacy risk for context only.
4. Historical risk records for forensics only.

If a stale Risk Evidence row exists and no fresh legacy risk source is available, Lifecycle Governance adds `STALE_RISK_SOURCE_REFRESH_REQUIRED`.

### Dashboard/API Changes

Extended `GET /dashboard/api/v2/lifecycle-governance` and `GET /dashboard/api/v2/risk-evidence-mesh` with:

* `stale_legacy_risk_block_ignored_count`
* `risk_source_selection_summary`

Risk source traces now include:

* `selected_risk_evidence_truth_state`
* `selected_risk_evidence_age_seconds`
* `legacy_risk_truth_state`

### Tests Added

Added `test_stale_risk_evidence_does_not_override_legacy_risk_source`.

Updated dashboard coverage to assert:

* stale legacy risk block ignored count
* risk source selection summary

### Tests Run

Compile:

```text
python -m py_compile app\services\lifecycle_governance.py app\services\risk_evidence_mesh.py tests\test_lifecycle_governance.py
python -m py_compile scripts\verify_lifecycle_governance_risk_evidence_smoke.py
```

Result: passed.

Lifecycle governance:

```text
docker compose --profile test run --rm -v "C:\Server\apps\polybot:/app" test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_lifecycle_governance.py"
```

Result: `17 passed, 1 warning`.

Adjacent regression:

```text
docker compose --profile test run --rm -v "C:\Server\apps\polybot:/app" test sh -lc "PYTHONPYCACHEPREFIX=/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app pytest -q tests/test_risk_evidence_mesh.py tests/test_truth_state_service.py tests/test_paper_no_live_safety.py tests/test_paper_execution_service.py"
```

Result: `29 passed, 1 warning`.

### Runtime Smoke

No 10m/30m/4h runtime run was started.

Bounded Docker smoke:

```text
docker compose --profile test run --rm -v "C:\Server\apps\polybot:/app" test sh -lc "PYTHONPATH=/app python scripts/verify_lifecycle_governance_risk_evidence_smoke.py"
```

Result:

* status: `OK`
* plans_checked: `1`
* trading_mutation: `False`
* `risk_evidence_used_count`: `1`
* `legacy_risk_ignored_count`: `1`
* `stale_legacy_risk_block_ignored_count`: `1`
* `risk_review_promoted_to_watch_count`: `1`
* `risk_review_kept_blocked_count`: `0`
* `risk_review_actionable_count`: `0`
* `allow_paper_intent_count`: `0`
* `allow_paper_execution_count`: `0`

Safety counts were unchanged in the bounded smoke:

* `live_orders`: `0 -> 0`
* `paper_intents`: `0 -> 0`
* `paper_orders`: `0 -> 0`
* `paper_fills`: `0 -> 0`
* `paper_positions`: `0 -> 0`
* `paper_position_closes`: `0 -> 0`
* `paper_capital_ledger`: `1 -> 1`
* `orders_v2`: `2 -> 2`
* `fills_v2`: `2 -> 2`
* canonical `positions`: `0 -> 0`
* capital balances unchanged

### Phase Status

GREEN for code and test coverage.

Operational status remains YELLOW until production runtime evidence clears non-risk critical blockers with fresh orderbook, exit, capital, and lifecycle sources.
