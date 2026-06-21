# POLYBOT Missing Trusted Orderbook Recovery Build Report

Date: 2026-06-02
Executor: Codex
Task mode: CONTROLLED_RUNTIME_FIX + ORDERBOOK_COVERAGE + TRUSTED_EVIDENCE_RECOVERY
Risk: VERY HIGH

## Current Reality Found

The post-observation blocker was real, but the naming differed between dashboard
and candidate tables:

- Raw `MISSING_TRUSTED_ORDERBOOK`: 0
- Raw `MISSING_FRESH_ORDERBOOK`: 6579
- Dashboard top blocker labelled as missing trusted/fresh orderbook
- Trusted orderbook matches before recovery smoke: 190
- Trusted orderbook matches after 50-candidate smoke: 193
- Latest precision smoke kept matches at 193

Root categories:

- `NO_MARKET_ID`: 5192 candidates
- `NO_EXPECTED_TOKEN` or missing side/token: 1356 candidates
- `SNAPSHOT_STALE`: 31 candidates

Only the stale/missing fresh orderbook class is directly recoverable by this
layer. The no-market/no-side classes require upstream lineage recovery.

## Root Cause

The existing trusted-orderbook resolver validated already-collected orderbooks,
but it did not perform a candidate-specific CLOB `/book` fetch when a candidate
had a valid market/side/token and only lacked fresh evidence.

This left valid candidates blocked until a separate generic orderbook collection
cycle happened to refresh the same token.

## Fixes Applied

- Added candidate-specific CLOB `/book` recovery to
  `TrustedOrderbookEvidenceService`.
- Added bounded `refresh_orderbooks` support to `POST /trusted-orderbook/resolve`.
- Added `GET /dashboard/api/v2/orderbook-blockers`.
- Added precise recovery metadata:
  - `candidate_specific_clob_refresh_enabled`
  - `orderbook_snapshots_created`
  - `orderbook_refresh_reason_counts`
- Added precise `CLOB_NO_BOOK` reporting when refresh fails.
- Preserved stale rejection; stale snapshots are never trusted.
- Added tests for fresh fetch, stale refresh, CLOB no-book, dashboard truth, and
  runtime routing.

## Files Created

- `docs/POLYBOT_MISSING_TRUSTED_ORDERBOOK_RECOVERY.md`
- `docs/POLYBOT_MISSING_TRUSTED_ORDERBOOK_RECOVERY_BUILD_REPORT.md`

## Files Changed

- `app/services/trusted_orderbook.py`
- `app/api/routes.py`
- `tests/test_trusted_orderbook_evidence_service.py`
- `tests/test_dashboard_trusted_orderbook_truth.py`

## Migrations

None.

Existing trusted evidence tables were sufficient:

- `trusted_orderbook_evidence_runs`
- `trusted_orderbook_evidence_links`
- `orderbook_snapshots`

## Runtime Smoke

### SYSTEM OFF Guard

`POST /trusted-orderbook/resolve` while SYSTEM OFF returned:

- status: `BLOCKED`
- error: `SYSTEM_POWER_OFF`
- candidates checked: 0
- orderbook snapshots created: 0

### 50-Candidate Recovery Smoke

Cycle: `missing_trusted_recovery_on_smoke`

- SYSTEM: ON only for bounded recovery
- candidates checked: 50
- candidates with side: 3864
- candidates with trusted binding: 3864
- candidates with orderbook: 3841
- trusted matches created: 3
- trusted matches refreshed: 16
- orderbook snapshots created: 1
- rejected count: 31
- missing fresh before/after: 6579 -> 6579
- live orders delta: 0
- real orders delta: 0

The run created real source-backed evidence, but the global blocker count did not
move because the candidate set still has upstream blockers.

### 5-Candidate Precision Smoke

Cycle: `missing_trusted_recovery_precision_smoke`

- SYSTEM: ON only for bounded recovery
- candidates checked: 5
- trusted matches created: 0
- trusted matches refreshed: 0
- orderbook snapshots created: 0
- rejected count: 5
- rejected reason: `CLOB_NO_BOOK`
- stale count: 0
- missing fresh before/after: 6579 -> 6579
- live orders delta: 0
- real orders delta: 0

SYSTEM was turned OFF after the smoke.

## Dashboard Result

`GET /dashboard/api/v2/orderbook-blockers?limit=50` returned:

- `mock_data=false`
- `total_blocked=6579`
- `missing_trusted_orderbook_count=0`
- `missing_fresh_orderbook_count=6579`
- `stale_snapshot_count=31`
- `clob_no_book_count=5`
- `trusted_link_not_consumed_count=0`
- latest run: `missing_trusted_recovery_precision_smoke`

Sample traces now show the five precision-smoke candidates as `CLOB_NO_BOOK`
instead of incorrectly preserving only `ORDERBOOK_STALE`.

## Tests Run

- `tests/test_trusted_orderbook_evidence_service.py tests/test_dashboard_trusted_orderbook_truth.py -q`
  - Result: 14 passed, 1 warning
- `tests/test_trusted_orderbook_evidence_service.py tests/test_trusted_orderbook_runtime.py tests/test_dashboard_trusted_orderbook_truth.py -q`
  - Result: 15 passed, 1 warning
- `tests/test_v3_source_to_neuron_ingestion_wiring.py -q`
  - Result: 8 passed, 1 warning
- `tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q`
  - Result: 26 passed

A broader combined test command timed out and left an orphan test container,
which was stopped. The focused required slices above passed.

## Safety Counts

Before recovery smoke:

- live orders: 0
- paper intents: 6
- paper orders: 9
- paper fills: 6
- paper positions: 9
- paper ledger rows: 12
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0 from dashboard safety summary

After precision smoke:

- live orders: 0
- paper intents: 6
- paper orders: 9
- paper fills: 6
- paper positions: 9
- paper ledger rows: 12
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0 from dashboard safety summary

No trading mutation was observed.

## Secret Exposure Check

FAILED.

During environment inspection, a `docker compose config` command exposed
compose-resolved credential values in tool output. No secret values are repeated
in this report. Operator should rotate any exposed CLOB credentials before
considering the phase fully clean.

## Remaining Risks

- Most remaining blocked candidates are missing market id or side, which this
  layer cannot fix.
- The stale market `824952` currently returned no usable CLOB book during the
  precision smoke, so it remains correctly blocked.
- The workspace is not a Git checkout, so changed-file reporting is path-based
  rather than Git-based.
- Secret exposure during inspection requires operator remediation.

## Phase Status

RED due to secret exposure during inspection.

Code behavior, tests, and runtime trading safety are otherwise controlled and
non-mutating.

## Can Run Another 30m Active Observation

No, not as a clean phase, until exposed credentials are rotated or explicitly
accepted by the operator.

From a trading-mutation perspective, the system ended OFF and safe. From an
operational-governance perspective, the secret exposure makes this phase RED.

