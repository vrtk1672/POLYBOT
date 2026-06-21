# POLYBOT CLOB Token Book Verification Build Report

## Current Reality Found

- `FRESH_VERIFIED` paper candidates before implementation: 0.
- `STALE_MARKET` candidates before implementation: 100.
- Phase 2 eligible paper candidates before implementation: 0.
- Existing stale candidate population should not be sent to CLOB.
- Current Gamma read-only sample returned active/open markets with deterministic YES/NO CLOB tokens, so fresh seed verification is the correct Phase 2 path.

## Model

Phase 2 flow:

Current Gamma market -> condition id -> YES/NO token ids -> seed side -> expected token id -> CLOB `/book(expected_token_id)` -> asset/condition validation -> normalized orderbook snapshot -> trusted orderbook link.

For existing paper candidates, the service only processes `identity_status='FRESH_VERIFIED'`.

For insufficient fresh paper candidates, the service creates isolated `fresh_candidate_seeds`; it does not create paper candidates or eligibility rows.

## Files Created

- `app/db/migrations/0113_clob_token_book_verification.sql`
- `app/services/clob_token_book_verification.py`
- `tests/test_clob_token_book_verification.py`
- `docs/POLYBOT_CLOB_TOKEN_BOOK_VERIFICATION.md`
- `docs/POLYBOT_CLOB_TOKEN_BOOK_VERIFICATION_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## API

- `GET /dashboard/api/v2/clob-token-book-verification`
- `POST /clob-token-book-verification/run`

## Tests Run

- `python -m pytest tests/test_clob_token_book_verification.py -q` -> 7 passed.
- `python -m pytest tests/test_fresh_market_identity_gate.py -q` -> 11 passed.
- `python -m pytest tests/test_polymarket_token_truth.py -q` -> 11 passed.
- `python -m pytest tests/test_trusted_orderbook_runtime.py -q` -> 1 passed.
- `python -m pytest tests/test_trusted_orderbook_evidence_service.py -q` -> 11 passed.
- `python -m pytest tests/test_dashboard_trusted_orderbook_truth.py -q` -> 3 passed.
- `python -m pytest tests/test_v3_source_to_neuron_ingestion_wiring.py tests/test_source_to_neuron_yellow_fixes.py -q` -> 12 passed.
- `python -m pytest tests/test_paper_execution_safety.py tests/test_paper_no_live_safety.py tests/test_paper_exit_safety.py -q` -> 3 passed.
- `python -m pytest tests/test_paper_lineage_consistency.py tests/test_paper_lineage_quarantine.py -q` -> 5 passed.
- `python -m pytest tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_paper_exit_capital_release.py -q` -> 11 passed.

The initial combined regression command timed out before emitting pytest results. The same suites were rerun in smaller groups and passed.

## Runtime Smoke

Performed:

- `SYSTEM OFF`.
- Captured safety baseline.
- Verified mutating verification was blocked while OFF.
- `SYSTEM ON`.
- Ran bounded Phase 2 verification with `limit=20`, `seed_threshold=5`, `seed_limit=10`, `verify_seeds=true`.
- `SYSTEM OFF`.

Smoke result:

- OFF-block status: `BLOCKED`, reason `SYSTEM_POWER_OFF`.
- FRESH_VERIFIED candidates processed: 0.
- STALE_MARKET candidates skipped: 100 total, 20 sample traces written in the smoke run.
- Fresh candidate seeds created: 10.
- Seed candidates checked: 10.
- CLOB checks attempted: 10.
- CLOB books verified: 10.
- Snapshots created: 10.
- Trusted links created: 10.
- TOKEN_NOT_FOUND: 0.
- CLOB_NO_BOOK: 0.
- ASSET_ID_MISMATCH: 0.
- CONDITION_ID_MISMATCH: 0.
- EMPTY bid/ask: 0.
- SPREAD_TOO_WIDE: 0.
- LIQUIDITY_TOO_LOW: 0.
- Live/order deltas: 0.
- Final system power: OFF.

Sample verified book:

- market `2169995`
- side `YES`
- token `25714007960293389110960044475283546872601238755063051359394740854408462452120`
- condition `0x3733a1b647e7364095736ab0966465d896a84cf3b6bc1695ca1f26c3239b3868`
- best bid `0.003`
- best ask `0.004`
- spread `0.001`
- trusted link `trusted_orderbook_fresh_seed_2169995_YES`

Sample rejected/skipped candidate:

- candidate `eligibility_exit_risk_thesis_coord_3e59704f0c6a4f77bc3ba8929638b94a`
- market `824952`
- reason `STALE_MARKET`
- CLOB book attempted: false

Sample fresh seed:

- seed `fresh_seed_2354064_NO`
- market `2354064`
- side `NO`
- source current Gamma

## Dialogue

Source-backed dialogue now materializes:

- verified CLOB token book rows
- rejected CLOB token book rows
- skipped stale candidates
- fresh Gamma seed creation

## Safety Checklist

- Live/shadow not enabled.
- No Polymarket order/write endpoint is called.
- No paper intents/orders/fills/positions are created by Phase 2.
- Stale candidates are skipped.
- Fresh seeds are isolated from paper eligibility.
- Secrets are not printed.
- Safety counts before/after smoke were unchanged:
  - `paper_intents=6`
  - `paper_orders=9`
  - `paper_fills=6`
  - `paper_positions=9`
  - `paper_capital_ledger=1`
  - `live_orders=0`
  - `orders_v2=1`
  - `fills_v2=1`
  - canonical `positions=0`

## Remaining Risks

- Security governance remains `YELLOW_ACCEPTED_BY_OPERATOR` until operator rotates or accepts credential exposure permanently.
- Fresh seeds are verification inputs only; Phase 3 must decide watcher behavior.
- Current Gamma/CLOB availability can change between smoke runs.

## Phase Status

YELLOW.

Reason: Phase 2 verification works, real current Gamma seeds were verified by CLOB, tests passed, and no trading mutation occurred. Overall phase remains YELLOW because security governance is explicitly `YELLOW_ACCEPTED_BY_OPERATOR` and fresh seeds are not yet a Paper path by design.

Can move to Phase 3 Live Token / Orderbook Watcher: YES, after ChatGPT/operator review.
