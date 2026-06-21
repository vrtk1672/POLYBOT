# POLYBOT Fresh Market Identity Gate Build Report

Date: 2026-06-03
Executor: Codex
Task mode: CONTROLLED_RUNTIME_FIX + MARKET_IDENTITY_GATE + POLYMARKET_FRESH_IDENTITY
Risk: VERY HIGH
Security governance: YELLOW_ACCEPTED_BY_OPERATOR

## Current Reality Found

Production counts before the bounded smoke:

- total candidates: 10440
- candidates with market_id: 5236
- candidates missing market_id: 5204
- candidates with condition_id: 3950
- candidates missing condition_id: 1286
- candidates with side: 3840
- candidates missing side: 6600
- candidates with yes_token_id: 3950
- candidates with no_token_id: 3950
- candidates with expected_token_id: 3840
- candidates tied to stale market `824952`: 3863
- candidates with accepting_orders true through local market truth: 3950
- candidates with closed/resolved local market: 0
- `MISSING_FRESH_ORDERBOOK`: 6591

Local `markets_v2` still had a complete-looking row for market `824952`, but
current Gamma did not return that market during the smoke. The gate therefore
classifies those candidates as `STALE_MARKET`.

## Files Created

- `app/db/migrations/0112_fresh_market_identity_gate.sql`
- `app/services/fresh_market_identity.py`
- `tests/test_fresh_market_identity_gate.py`
- `docs/POLYBOT_FRESH_MARKET_IDENTITY_GATE.md`
- `docs/POLYBOT_FRESH_MARKET_IDENTITY_GATE_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Applied migration:

- `0112_fresh_market_identity_gate.sql`

New tables:

- `fresh_market_identity_runs`
- `fresh_market_identity_traces`

New candidate audit fields:

- `identity_status`
- `identity_verified_at`
- `identity_source`
- `expected_token_id`
- `identity_blocker_reason`

## Model And Rules

The gate requires current Gamma confirmation before `FRESH_VERIFIED`.

Backfill is deterministic only:

- market id from trusted `signal_market_links`
- side from existing deterministic side evidence on a trusted link
- condition and YES/NO tokens from current Gamma source truth

Ambiguous matches are blocked and not written. Missing side is not inferred from
text. Local market completeness alone is never considered fresh.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/fresh-market-identity`
- `POST /fresh-market-identity/recover`

Dashboard returns `mock_data=false`, latest run counts, sample traces, top stale
markets, safety counts, and
`security_governance_status=YELLOW_ACCEPTED_BY_OPERATOR`.

## Dialogue

`BrainDialogueService` now materializes `Fresh Market Identity` dialogue from
`fresh_market_identity_traces`.

Smoke created source-backed dialogue after the bounded run.

## Tests Added

`tests/test_fresh_market_identity_gate.py` covers:

- complete current identity becomes `FRESH_VERIFIED`
- market recovery from deterministic signal link
- ambiguous market match does not backfill
- condition_id remains separate from market_id
- missing side remains blocked
- YES/NO expected token mapping
- ambiguous outcome tokens blocked
- stale local market becomes `STALE_MARKET`
- closed market blocked
- accepting_orders false blocked
- SYSTEM OFF blocks mutating recovery
- dashboard `mock_data=false`
- no trading mutation

## Tests Run

- `python -m py_compile app\services\fresh_market_identity.py app\api\routes.py app\services\brain_dialogue.py tests\test_fresh_market_identity_gate.py`
  - Result: passed
- `docker compose --profile test run --rm test python -m pytest tests/test_fresh_market_identity_gate.py -q`
  - Result: 11 passed, 1 warning
- `docker compose --profile test run --rm test python -m pytest tests/test_polymarket_token_truth.py tests/test_polymarket_binding_recovery.py -q`
  - Result: 26 passed, 1 warning
- `docker compose --profile test run --rm test python -m pytest tests/test_trusted_orderbook_evidence_service.py tests/test_dashboard_trusted_orderbook_truth.py -q`
  - Result: 14 passed, 1 warning
- `docker compose --profile test run --rm test python -m pytest tests/test_v3_source_to_neuron_ingestion_wiring.py -q`
  - Result: 8 passed, 1 warning
- `docker compose --profile test run --rm test python -m pytest tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q`
  - Result: 26 passed

## Runtime Smoke

Commands were run through the rebuilt API image after applying migration 0112.

SYSTEM OFF guard:

- `POST` equivalent mutating recovery while OFF: `BLOCKED`
- candidates checked: 0
- blocker: `SYSTEM_POWER_OFF`

SYSTEM ON bounded run:

- cycle: `fresh_market_identity_smoke_100`
- candidates checked: 100
- `FRESH_VERIFIED`: 0
- `STALE_MARKET`: 100
- all 100 sampled candidates were tied to market `824952`
- current Gamma lookup status: `NOT_FOUND`
- CLOB book verification: not run by design
- dialogue materialization: `OK`, 137 events created
- final system power: OFF

Dashboard:

- `/healthz`: OK
- `/runtime/health`: SAFE_STOPPED
- `/dashboard/api/v2/fresh-market-identity`: `mock_data=false`
- `/system/power`: OFF, paper/shadow/live all disallowed

## Before / After Counts

| Metric | Before | After |
| --- | ---: | ---: |
| total candidates | 10440 | 10440 |
| candidates_with_market_id | 5236 | 5236 |
| candidates_with_condition_id | 3950 | 3950 |
| candidates_with_side | 3840 | 3840 |
| candidates_with_yes_token_id | 3950 | 3950 |
| candidates_with_no_token_id | 3950 | 3950 |
| candidates_with_expected_token | 3840 | 3840 |
| FRESH_VERIFIED | 0 | 0 |
| STALE_MARKET | 0 | 100 |
| MISSING_MARKET_ID | 0 | 0 |
| MISSING_CONDITION_ID | 0 | 0 |
| MISSING_SIDE | 0 | 0 |
| MISSING_TOKEN_MAPPING | 0 | 0 |
| AMBIGUOUS_MATCH | 0 | 0 |
| MARKET_CLOSED | 0 | 0 |
| ACCEPTING_ORDERS_FALSE | 0 | 0 |
| UNRECOVERABLE | 0 | 0 |
| paper_intents | 6 | 6 |
| paper_orders | 9 | 9 |
| paper_fills | 6 | 6 |
| paper_positions | 9 | 9 |
| paper_capital_ledger | 1 | 1 |
| live_orders | 0 | 0 |
| orders_v2 | 1 | 1 |
| fills_v2 | 1 | 1 |
| canonical positions | 0 | 0 |

## 100-Candidate Trace Summary

- checked: 100
- current Gamma lookup attempted: 100
- current Gamma result: `NOT_FOUND`
- final status: `STALE_MARKET`
- market: `824952`
- expected token: none trusted
- no CLOB book requested
- no paper artifacts created

## Sample Fresh Verified Candidate

No production candidate was fresh verified in the bounded smoke. Unit tests prove
the `FRESH_VERIFIED` path using current Gamma-backed identity.

## Sample Stale Market Candidate

Candidate:

- `eligibility_exit_risk_thesis_coord_88dbcb0406684db099c84ab0acccea9c`
- market_id: `824952`
- side: `YES`
- current Gamma lookup: `NOT_FOUND`
- identity_status: `STALE_MARKET`
- reason: current Gamma did not return market `824952`

## Safety Checklist

- live enabled: NO
- shadow enabled: NO
- real order created: NO
- paper intent created: NO
- paper order/fill/position created: NO
- CLOB order/write endpoint called: NO
- CLOB book verification implemented in this phase: NO
- fake market/condition/token created: NO
- ambiguous identity written: NO
- secrets printed: NO
- SYSTEM final state: OFF

## Remaining Risks

- Many candidates remain missing market id or side and need upstream deterministic
  source/link work.
- The dominant stale local market population is still tied to `824952`; Phase 2
  should not attempt CLOB `/book` for those rows until current identity is
  recovered or replaced.
- Security governance remains YELLOW accepted risk until operator rotates or
  formally accepts exposed credentials outside this build.
- The workspace is not a Git checkout, so file reporting is path-based.

## Phase Status

YELLOW.

The gate is implemented, tests passed, stale market detection worked, dashboard
truth exists, and no trading mutation occurred. Status is YELLOW because the
operator-accepted security governance risk remains and the bounded production
sample found no fresh verified candidates, only valid stale-market blocks.

## Can Move To Phase 2 CLOB Token Book Verification

YES, but only for candidates that pass `FRESH_VERIFIED`. Phase 2 should not use
market `824952` candidates until their current identity is recovered.
