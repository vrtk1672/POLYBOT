# POLYBOT Same-Market Side Coherence Guard Build Report

## Summary

Implemented a same-market side coherence guard for canonical Paper flow. Opposing YES/NO same-market Paper exposure is now blocked before Paper Intent creation and again before Paper Execution unless a source-backed strategic rationale is present.

## Current Reality Found

Production snapshot before this phase:

- open Paper positions: market `598936` YES only
- historical both-side Paper exposure: market `691547` had YES and NO positions
- market `691547` YES and NO opened in the same run cycle: `active_30m_observation_20260603T130348Z_cycle_1`
- both `691547` sides had local risk/exit approval and Paper intents
- no explicit hedge/arbitrage/repair/market-making rationale was found in intent evidence, risk decisions, exit plans, or coordinator decision
- current capital reconciliation remained OK from the prior phase

## Root Cause

The pipeline evaluated each side independently. The fresh-seed to Paper path could produce a YES candidate and a NO candidate for the same market, and the Paper Intent and Paper Execution services had no same-market opposing-side exposure check.

Root cause category: missing mesh decision coherence guard before Paper Intent and Paper Execution.

## Files Created

- `app/db/migrations/0118_same_market_side_coherence_guard.sql`
- `app/services/same_market_side_guard.py`
- `tests/test_same_market_side_guard.py`
- `docs/POLYBOT_SAME_MARKET_SIDE_COHERENCE_GUARD.md`
- `docs/POLYBOT_SAME_MARKET_SIDE_COHERENCE_GUARD_BUILD_REPORT.md`

## Files Changed

- `app/services/paper_intents.py`
- `app/services/paper_execution.py`
- `app/services/paper_trade_forensics.py`
- `app/services/brain_dialogue.py`
- `app/api/routes.py`

## Migration

`0118_same_market_side_coherence_guard.sql` creates `same_market_side_guard_decisions` with decision counts, exposure snapshot JSON, source-backed rationale fields, and audit metadata.

## Guard Rules

- opposing open position or opposing active intent without source-backed rationale: `BLOCK`
- opposing YES/NO candidates in the same batch without source-backed rationale: `BLOCK`
- same-side duplicate exposure: `REVIEW`
- recent same-run opposite-side close: `REVIEW`
- old closed opposite-side history alone: `ALLOW`
- explicit allowed rationale with verified source row: `ALLOW`

## API / Dashboard

Added:

- `GET /dashboard/api/v2/same-market-side-guard`
- `GET /dashboard/api/v2/same-market-side-guard/{market_id}`

The response includes mock status, guard status, blocked/review/allowed counts, markets with both sides, latest decisions, sample traces, and security governance status.

## Forensics / Dialogue

Paper forensics now surfaces guard lineage for positions and intents.

Brain dialogue now materializes `Same-Market Guard` messages directly from `same_market_side_guard_decisions`.

## Tests

Added `tests/test_same_market_side_guard.py` covering:

- YES blocked when open NO exists
- NO blocked when open YES exists
- same-batch YES/NO blocked
- source-backed hedge rationale allowed
- fake rationale rejected
- same-side duplicate review
- old closed opposite side allowed
- recent same-run opposite close review
- guard before Paper Intent creation
- guard before Paper Execution
- dashboard truth
- forensics truth
- dialogue visibility
- no order/fill/position/live mutation from guard

## Test Results

- `python -m py_compile ...`: passed
- `pytest tests/test_same_market_side_guard.py -q`: 14 passed
- `pytest tests/test_v2_paper_intent_service.py tests/test_paper_execution_service.py tests/test_paper_execution_safety.py tests/test_fresh_seed_paper_path.py tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_paper_trade_forensics.py -q`: 38 passed, 1 warning
- `pytest tests/test_paper_no_live_safety.py tests/test_paper_exit_loop.py tests/test_paper_exit_safety.py tests/test_paper_lineage_quarantine.py tests/test_paper_lineage_consistency.py tests/test_active_30m_observation_runner.py -q`: 19 passed, 1 warning

Older Docker test commands require `PYTHONPATH=/app` for legacy top-level imports such as `gamma_crawler.py`.

## Runtime Smoke

Completed with SYSTEM OFF.

Results:

- `/healthz`: OK
- `/dashboard/api/v2/system-power`: SYSTEM OFF, runtime work blocked, paper/live/shadow disabled
- `/dashboard/api/v2/same-market-side-guard`: OK, `mock_data=false`, historical `691547` both-side exposure detected
- `/dashboard/api/v2/same-market-side-guard/691547`: OK, YES and NO historical positions/intents visible, no source-backed rationale found
- dry-run service probe for proposed `598936 NO` against open `598936 YES`: `BLOCK`, `SAME_MARKET_OPPOSING_SIDE_BLOCK`
- dry-run wrote no guard decision row
- paper orders, fills, positions, closes, capital ledger, live orders, real orders, and capital balances unchanged
- capital reconciliation remained OK

## Phase Status

YELLOW.

The guard is implemented, tested, and smoke-verified. Status remains YELLOW because no real hedge/arbitrage/repair rationale strategy exists yet; the guard therefore blocks/reviews accidental opposing exposure by default.
