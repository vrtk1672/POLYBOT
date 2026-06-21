# POLYBOT Polymarket Binding Recovery Build Report

Date: 2026-06-02
Executor: Codex
Task mode: CONTROLLED_RUNTIME_FIX + POLYMARKET_IDENTITY_BINDING + TOKEN_BOOK_RECOVERY
Risk: VERY HIGH

## Current Reality Found

Before implementation/runtime smoke:

- total candidates: 10420
- candidates with market id: 5228
- candidates missing market id: 5192
- candidates with condition id: 3942
- candidates missing condition id among market candidates: 1286
- candidates with side: 3864
- candidates missing side: 6556
- candidates with YES/NO token mapping: 3942
- candidates with expected token for side: 3864
- candidates with historical CLOB book for expected token: 3864
- candidates with fresh expected-token orderbook: 0
- trusted orderbook links: 193

The dominant blocker is identity coverage, not generic orderbook trust:

- `NO_MARKET_ID`: 5192
- `NO_SIDE`: 6556
- `NO_CONDITION_ID`: 1286
- `NO_YES_NO_TOKEN_MAPPING`: 1286
- `MISSING_FRESH_ORDERBOOK`: 6579

The no-market candidates sampled from production were generic source-status
signals and had no deterministic `signal_market_links` match. They cannot be
backfilled safely by this phase.

## Mapping Assumptions Implemented

- CLOB `/book` is requested by outcome token id.
- `asset_id` must equal expected token id.
- `market` must equal expected condition id when known.
- YES side maps to `yes_token_id`.
- NO side maps to `no_token_id`.
- best ask is the buy-side executable price reference.
- best bid is the sell-side executable price reference.
- spread is `best_ask - best_bid`.

## Files Created

- `app/db/migrations/0110_polymarket_identity_binding_recovery.sql`
- `app/services/polymarket_binding.py`
- `tests/test_polymarket_binding_recovery.py`
- `docs/POLYBOT_POLYMARKET_BINDING_RECOVERY.md`
- `docs/POLYBOT_POLYMARKET_BINDING_RECOVERY_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

Migration `0110_polymarket_identity_binding_recovery.sql` adds:

- `polymarket_binding_recovery_runs`
- `polymarket_binding_candidate_traces`

No trading tables were altered.

## Binding Model

The resolver backfills only when deterministic:

- candidate `market_id`: one trusted signal-market link for candidate signal ids
- candidate `side`: one trusted matched side from link evidence
- market identity: stored Gamma snapshot raw payload with condition and two
  YES/NO token ids

Ambiguous links, missing signal links, missing side, missing condition, missing
token mapping, and unavailable CLOB books remain blocked.

## CLOB Validation Rules

Book request:

- endpoint: read-only `/book`
- parameter: `token_id=<expected_token_id>`

Validation:

- `asset_id == expected_token_id`
- `market == condition_id` when condition id exists
- bids and asks are present
- normalized best bid/ask/mid/spread are valid
- spread <= trusted orderbook max spread
- liquidity score >= trusted minimum when present
- market is active/open and accepting orders

If any validation fails, no trusted link is created.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/polymarket-binding`
- `POST /polymarket-binding/recover`

Dashboard returns `mock_data=false`.

## Dialogue

`BrainDialogueService` now materializes source-backed `Polymarket Binding`
dialogue from `polymarket_binding_candidate_traces`.

Examples:

- candidate resolved expected side token and trusted orderbook
- candidate cannot request CLOB because side is missing
- candidate requested CLOB book by token and received a precise rejection

No dashboard reads create fake dialogue.

## Tests Added

`tests/test_polymarket_binding_recovery.py` covers:

- YES side maps to expected YES token
- NO side maps to expected NO token
- missing side blocks CLOB request
- missing token mapping blocks CLOB request
- asset id mismatch rejection
- condition id mismatch rejection
- valid book creates snapshot/trusted link
- CLOB no book / token not found remains blocked
- closed market blocks trust
- deterministic Gamma snapshot backfill
- ambiguous backfill does not write fake market id
- SYSTEM OFF blocks recovery
- dashboard route returns `mock_data=false`
- source-backed Polymarket Binding dialogue
- no trading mutation

## Tests Run

- `tests/test_polymarket_binding_recovery.py -q`
  - Result: 15 passed, 1 warning
- `tests/test_trusted_orderbook_evidence_service.py tests/test_trusted_orderbook_runtime.py tests/test_dashboard_trusted_orderbook_truth.py -q`
  - Result: 15 passed, 1 warning
- `tests/test_v3_source_to_neuron_ingestion_wiring.py -q`
  - Result: 8 passed, 1 warning
- `tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q`
  - Result: 26 passed

One paper safety run initially passed all tests but failed while writing pytest
cache due container memory; rerun with cache disabled exited cleanly.

## Runtime Smoke

SYSTEM OFF:

- `POST /polymarket-binding/recover`
- status: `BLOCKED`
- error: `SYSTEM_POWER_OFF`
- candidates checked: 0
- live/real order delta: 0

SYSTEM ON bounded smoke:

- cycle id: `polymarket_binding_100_candidate_smoke`
- candidates checked: 100
- expected tokens resolved: 31
- CLOB book attempts: 31
- market ids backfilled: 0
- sides backfilled: 0
- market identity backfilled: 0
- snapshots created: 0
- trusted links created/refreshed: 0
- rejected count: 100
- blocker counts: `TOKEN_NOT_FOUND=31`, `NO_MARKET_ID=69`
- live/real order delta: 0

SYSTEM was returned OFF after smoke.

## Before / After Counts

Before:

- total candidates: 10420
- candidates with market id: 5228
- candidates with condition id: 3942
- candidates with side: 3864
- candidates with expected token: 3864
- candidates with fresh orderbook: 0
- candidates with trusted orderbook: 193
- risk approved: 1360
- exit ready: 1360
- eligible candidates: 1357
- paper intents: 6
- paper orders: 9
- paper fills: 6
- paper positions: 9
- live orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0

After:

- total candidates: 10420
- candidates with market id: 5228
- candidates with condition id: 3942
- candidates with side: 3864
- candidates with expected token: 3864
- candidates with fresh orderbook: 0
- candidates with trusted orderbook: 193
- risk approved: 1360
- exit ready: 1360
- eligible candidates: 1357
- paper intents: 6
- paper orders: 9
- paper fills: 6
- paper positions: 9
- live orders: 0
- orders_v2: 1
- fills_v2: 1
- canonical positions: 0

## 100-Candidate Trace Summary

- `TOKEN_NOT_FOUND`: 31
- `NO_MARKET_ID`: 69

Sample rejected binding:

- market id: `824952`
- condition id: `0x8213d395e079614d6c4d7f4cbb9be9337ab51648a21cc2a334ae8f1966d164b4`
- side: YES
- expected token:
  `111128191581505463501777127559667396812474366956707382672202929745167742497287`
- CLOB check attempted: true
- CLOB status: `TOKEN_NOT_FOUND`
- snapshot: none
- trusted link: none

No successful production binding occurred in the smoke because the CLOB endpoint
did not return a valid book for the checked expected tokens.

## Safety Checklist

- live enabled: no
- shadow enabled: no
- real order created: no
- paper intent created: no
- paper order/fill/position created: no
- fake market id created: no
- fake condition id created: no
- fake token id created: no
- fake orderbook created: no
- stale or wrong token trusted: no
- SYSTEM final state: OFF

## Secret Exposure Check

No new secrets were printed in this phase.

Important carry-forward: the previous phase exposed compose-resolved credential
values via `docker compose config` output. Those values are not repeated here.
Operator rotation is still recommended before declaring operational GREEN.

## Remaining Risks

- Most `NO_MARKET_ID` candidates are generic source-status signals, not
  market-specific signals.
- 31 expected-token CLOB checks returned `TOKEN_NOT_FOUND`; these candidates
  remain correctly blocked.
- No production candidate improved during the bounded smoke because source truth
  did not contain deterministic new identity for the sampled blockers.
- The workspace is not a Git checkout, so changed file reporting is path-based.

## Phase Status

YELLOW for this phase’s implementation and runtime safety:

- Mapping is implemented.
- Tests pass.
- Dashboard truth exists.
- Blockers are more precisely traced.
- No trading mutation occurred.
- Many candidates still lack source data or usable CLOB books.

Operational status remains RED-adjacent until the prior exposed credentials are
rotated or explicitly accepted by the operator.

## Can Run Another 30m Active Observation

NO as a clean operational phase until credential rotation/acceptance is handled.

From a trading-mutation perspective, the final state is safe and OFF.

