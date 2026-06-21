# POLYBOT Security Recovery + Polymarket Token Source Truth Build Report

Date: 2026-06-02
Executor: Codex
Task mode: SECURITY_RECOVERY + CONTROLLED_RUNTIME_FIX + POLYMARKET_TOKEN_TRUTH
Risk: VERY HIGH

## Summary

Implemented safe credential inspection guardrails and a Polymarket token truth
layer. The TOKEN_NOT_FOUND sample is now classified precisely as
`CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN` for stale local Gamma/source truth:
current CLOB rejects the locally stored tokens, and current Gamma lookup by the
old market id returns no market.

## Security Recovery Status

- Safe env audit created: YES
- Security endpoint created: YES
- Duplicate env keys found: none
- Dangerous duplicate overrides found: none
- Raw values returned: false
- Rotation recommended: true
- Governance status: `ROTATION_REQUIRED`

Rotate or explicitly accept risk for:

- `ANTHROPIC_API_KEY`
- `POLYMARKET_CLOB_API_KEY`
- `POLYMARKET_CLOB_SECRET`
- `POLYMARKET_CLOB_PASSPHRASE`
- `NEWS_API_KEY` if exposed
- `OPENAI_API_KEY` if exposed

## Token Reality Found

Before token truth recovery:

- candidates with market id: 5228
- candidates with condition id: 3942
- candidates with side: 3864
- candidates with expected token: 3864
- prior TOKEN_NOT_FOUND traces: 31, all sampled on market `824952`

Market `824952` local source truth:

- condition id present
- YES/NO token ids present
- local snapshot says active/open/accepting/orderbook-enabled
- stored tokens match the latest local Gamma snapshot

Current provider truth:

- CLOB `/book` for both local YES and NO tokens returned 404 with no orderbook.
- Current Gamma `/markets?id=824952` returned no market.

Root cause: local stored Gamma/source truth is stale for this market; the parser
did not use condition id or market id as token, and the YES/NO ordering was not
the cause for this sample.

## Files Created

- `app/security/__init__.py`
- `app/security/redaction.py`
- `app/security/env_audit.py`
- `app/services/security_secrets.py`
- `scripts/safe_env_audit.py`
- `scripts/safe_env_audit.ps1`
- `app/db/migrations/0111_polymarket_token_source_truth.sql`
- `app/services/polymarket_token_truth.py`
- `tests/test_security_secret_guard.py`
- `tests/test_polymarket_token_truth.py`
- `docs/POLYBOT_SECURITY_RECOVERY_AND_SECRET_GUARD.md`
- `docs/POLYBOT_CREDENTIAL_EXPOSURE_RECOVERY_PLAN.md`
- `docs/POLYBOT_POLYMARKET_TOKEN_SOURCE_TRUTH.md`
- `docs/POLYBOT_POLYMARKET_TOKEN_SOURCE_TRUTH_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/services/brain_dialogue.py`

## DB Migration

`0111_polymarket_token_source_truth.sql` adds:

- `polymarket_token_truth_runs`
- `polymarket_token_bindings`
- `polymarket_token_truth_traces`

No trading tables were altered.

## Token Source Truth Model

The service parses Gamma token fields, maps YES/NO deterministically, stores
token provenance in `polymarket_token_bindings`, and writes trace rows for every
checked candidate/market. It updates `markets_v2` token fields only when current
Gamma source data provides deterministic YES/NO token truth.

## CLOB Validation Rules

- Request `/book` by expected outcome token.
- Reject if response `asset_id` differs.
- Reject if response `market` differs from condition id.
- Reject empty bid/ask books.
- Persist no orderbook snapshot unless validation passes.
- Create no trusted link unless a candidate has a valid fresh book.

## API / Dashboard

- `GET /dashboard/api/v2/security/secrets`
- `GET /dashboard/api/v2/polymarket-token-truth`
- `POST /polymarket-token-truth/recover`

All return `mock_data=false`.

## Tests Run

- `tests/test_security_secret_guard.py tests/test_polymarket_token_truth.py -q`
  - Result: 14 passed, 1 warning
- `tests/test_trusted_orderbook_evidence_service.py tests/test_trusted_orderbook_runtime.py tests/test_dashboard_trusted_orderbook_truth.py -q`
  - Result: 15 passed, 1 warning
- `tests/test_v3_source_to_neuron_ingestion_wiring.py -q`
  - Result: 8 passed, 1 warning
- `tests/test_paper_lineage_consistency.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py -q`
  - Result: 9 passed
- `tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_exit_capital_release.py -q`
  - Result: 17 passed
- `python -m py_compile app/security/redaction.py scripts/safe_env_audit.py app/security/env_audit.py app/services/security_secrets.py app/services/polymarket_token_truth.py app/api/routes.py app/services/brain_dialogue.py`
  - Result: passed

The combined paper safety command timed out without a result, so it was rerun in
two smaller groups; both groups passed.

Focused test coverage includes redaction, duplicate env detection, security
endpoint truth, JSON token parsing, YES/NO mapping, condition/market id not used
as token, outcome mismatch, ambiguous mapping, valid CLOB validation,
condition mismatch, TOKEN_NOT_FOUND classification, closed market blocking,
stale token backfill, SYSTEM OFF blocking, dashboard truth, and no trading
mutation.

## Runtime Smoke

Safe env audit:

- raw values printed: false
- duplicate env keys: none
- dangerous duplicates: none
- compose config used: false

SYSTEM OFF:

- `POST /polymarket-token-truth/recover`
- status: `BLOCKED`
- blocker: `SYSTEM_POWER_OFF`
- candidates checked: 0

SYSTEM ON bounded token truth rerun:

- candidates checked: 100
- Gamma markets checked: 20
- tokens resolved: 51
- CLOB checks attempted: 51
- verified token books: 20
- TOKEN_NOT_FOUND candidates: 31
- token parse errors: 0
- ambiguous tokens: 0
- trusted links created: 0
- orderbook snapshots created by token truth: 0
- live order delta: 0
- real order delta: 0

Blocker counts:

- `CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN`: 31
- `NO_SIDE`: 50
- `NO_CONDITION_ID`: 19
- `VERIFIED_BY_CLOB_BOOK`: 20

SYSTEM was returned OFF.

Smoke caveat: an earlier SYSTEM ON window allowed the normal runtime loop to
wake and write source/AI/orderbook evidence rows. Trading tables remained
unchanged, but this is why final source evidence counts differ from the first
baseline.

## Before / After Counts

Final tight smoke before -> after:

- live_orders: 0 -> 0
- paper_intents: 6 -> 6
- paper_orders: 9 -> 9
- paper_fills: 6 -> 6
- paper_positions: 9 -> 9
- paper_capital_ledger: 1 -> 1
- orders_v2: 1 -> 1
- fills_v2: 1 -> 1
- canonical positions: 0 -> 0
- trusted_orderbook_links: 293 -> 293
- orderbook_snapshots: 26074 -> 26074
- token truth traces: 120 -> 240
- token bindings: 10 -> 11

Final dashboard coverage:

- candidates_with_market_id: 5236
- candidates_with_condition_id: 3950
- candidates_with_side: 3840
- candidates_with_yes_token_id: 3950
- candidates_with_no_token_id: 3950
- candidates_with_expected_token: 3840
- candidates_verified_by_clob: 0
- TOKEN_NOT_FOUND: 31
- NO_MARKET_ID: 5204
- NO_SIDE: 6600
- NO_YES_NO_TOKEN_MAPPING: 1286
- MISSING_FRESH_ORDERBOOK: 6591
- trusted_orderbook_links: 193 trusted
- fresh_orderbook_snapshots: 0

## Sample Successful Token Verification

Gamma market `2169995`:

- side checked: YES
- source field: `clobTokenIds`
- CLOB `/book`: OK
- classification: `VERIFIED_BY_CLOB_BOOK`
- no candidate trusted link created because this was a Gamma-market sample, not
  a paper candidate trace.

## Sample Rejected Token

Candidate `eligibility_exit_risk_thesis_coord_a16943a6f15647b1ba3d95d8cfe1bf20`:

- market id: `824952`
- side: YES
- expected token: source-backed local YES token
- CLOB status: `TOKEN_NOT_FOUND`
- classification: `CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN`
- snapshot: none
- trusted link: none

## Safety Checklist

- live enabled: no
- shadow enabled: no
- real order created: no
- paper intent/order/fill/position created by this phase: no
- fake token created: no
- fake orderbook created: no
- wrong token trusted: no
- raw secret printed: no
- final SYSTEM state: OFF

## Remaining Operator Actions

- Rotate exposed credential categories or explicitly accept governance risk.
- Prefer `127.0.0.1` over `localhost` for local API smoke commands in this
  environment; `localhost` intermittently timed out.

## Remaining Engineering Actions

- Add a scheduler-safe/manual-only runtime mode for bounded recovery so SYSTEM
  ON does not wake unrelated runtime loops.
- Add live Gamma refresh/backfill for stale local market ids before candidate
  token checks.
- Improve upstream candidate side recovery; many candidates still stop at
  `NO_SIDE`.
- Improve market identity production for candidates with `NO_CONDITION_ID`.

## Phase Status

YELLOW.

The secret guard and token truth layer work, tests pass, source-backed CLOB
verification works for current Gamma markets, stale TOKEN_NOT_FOUND candidates
are precisely classified, and no trading mutation occurred. Status remains
YELLOW until credential rotation/accepted risk is complete and bounded recovery
can run without waking unrelated runtime loops.

## Can Run Another 30m Active Observation

NO as a clean operational phase until credential rotation/accepted risk is
handled. Trading safety is currently clean and SYSTEM is OFF.
