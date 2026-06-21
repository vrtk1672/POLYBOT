# POLYBOT PAPER Runtime Last-Mile Orderbook Refresh Repair

## Purpose

Repair the current autonomous PAPER runtime blocker where a valid PAPER candidate was blocked by `STALE_ORDERBOOK` even though the system could safely refresh the exact market/token/side orderbook before intent creation.

This remains a unified runtime repair. PAPER is still only the execution adapter.

## Current STALE_ORDERBOOK Root Cause

The current PAPER runtime decision builder selected the newest matching non-stale orderbook snapshot and then blocked if its age exceeded the PAPER freshness TTL. It did not attempt a targeted CLOB refresh before finalizing the blocker.

The selector also had a 10 minute recent-decision skip, so a recent stale decision could remain stale until the skip window expired.

Root cause:

- PAPER decision creation selected stale-but-valid historical snapshots.
- No pre-intent last-mile refresh was attempted for `STALE_ORDERBOOK`.
- Freshness TTL diagnostics were not persisted on `paper_runtime_decisions`.
- Runtime overview/CLI did not expose refresh-attempt truth.

## Current Top PAPER Candidate Audit

Initial blocked decision:

- `decision_id`: `paper_runtime_decision_386d1a9d254e81f4eed6352a92ce68d9`
- `market_id`: `691547`
- `condition_id`: `0xced0cb8725bad43d78fda0cd0e5fa9e31804625cb3502b2c7897f8e8f7fa9e1f`
- `side`: `YES`
- `token_id`: `34626184950254225208692030156208941308358060420950772251072421141618169142241`
- `score`: `61.99`
- `blocker`: `STALE_ORDERBOOK`
- `source`: PAPER observation policy / proactive seed Mesh lineage

Initial selected snapshot:

- `orderbook_snapshot_id`: `60414`
- `snapshot_ref`: `ob_3e42a69d9b604604876dc2fcbf4a13a1`
- `source`: `polymarket_clob_candidate_recovery`
- `best_bid`: `0.29`
- `best_ask`: `0.37`
- `spread`: `0.08`
- `snapshot_at`: `2026-06-18T10:19:43.565740Z`
- `age_seconds` at audit: about `8573`
- TTL: `180`

Fresh matching snapshot existed before repair: `NO`.

The latest exact matching YES token snapshot during refresh was snapshot `60416`, also stale at about `6102` seconds. No exact matching snapshot was within the 180 second PAPER TTL.

## Last-Mile Refresh Architecture

Added `LastMileOrderbookRefreshService`.

Behavior:

1. Select exact current orderbook by `market_id`, `token_id`, and `side`.
2. If exact snapshot is fresh within TTL, record `FRESH_ALREADY_AVAILABLE`.
3. If missing/stale, call the read-only Polymarket CLOB `/book?token_id=...` path.
4. Verify token and market/condition if present in the payload.
5. Normalize and persist a real `orderbook_snapshots` row.
6. Re-select exact snapshot and verify age against TTL.
7. Record attempt in `last_mile_orderbook_refresh_attempts`.
8. Return exact failure reason if refresh fails.

The service never creates intents, orders, fills, positions, live orders, or shadow orders.

## Hook Location

Hooked inside `PaperRuntimeDecisionService.build_paper_runtime_decision`, before final blocker computation and before `PaperIntentGate` consumes current decisions.

Flow:

PAPER observation policy row
→ paper runtime decision builder
→ exact orderbook selected
→ if stale/missing, last-mile refresh
→ reselect exact orderbook
→ decide `ENTER` or keep exact blocker
→ PaperIntentGate
→ PaperExecutionAdapter

## TTL Policy

PAPER pre-intent orderbook TTL remains `180` seconds.

This aligns with the existing trusted orderbook freshness constant and does not alter live execution TTLs.

## Orderbook Selection Rules

For candidates with a `token_id`, the selector now requires exact token match. It does not fall back to market-level or side-only snapshots when a token is present.

Rules:

- exact `market_id` required
- exact `token_id` required when available
- side must match or source side may be null
- snapshot status must be `OK` or `PARTIAL`
- `is_stale` must be false
- freshness is separately checked against TTL

Wrong token and wrong market snapshots are rejected.

## Fixes Made

- Added `app/services/last_mile_orderbook_refresh.py`.
- Added `0144_last_mile_orderbook_refresh.sql`.
- Updated `PaperRuntimeDecisionService` to refresh stale/missing orderbook before final blockers.
- Allowed recent stale-orderbook runtime decisions to re-enter refresh processing instead of waiting 10 minutes.
- Persisted orderbook age, TTL, last-mile attempt state, refresh error, and post-refresh state on `paper_runtime_decisions`.
- Extended `system-overview` decisions payload.
- Extended `tools/polybot.ps1 report/status` with last-mile refresh diagnostics.

## System Overview / CLI Diagnostics

`/dashboard/api/v2/control/system-overview` and `tools/polybot.ps1` now expose:

- stale orderbook blocker count
- last-mile refresh attempts
- last-mile refresh success/failure counts
- stale cleared count
- selected orderbook snapshot id
- orderbook age seconds
- orderbook TTL seconds
- last-mile refresh state/error
- post-refresh orderbook state

## Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_last_mile_orderbook_refresh.py tests/test_paper_decision_orderbook_refresh.py tests/test_orderbook_selection_for_paper_runtime.py tests/test_system_overview_orderbook_refresh.py -q
8 skipped in 2.98s
```

The focused tests are DB-fixture tests and skipped where the local test schema fixture was unavailable.

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_paper_runtime_execution_chain.py tests/test_runtime_health_truth.py tests/test_paper_decision_diversity.py tests/test_paper_execution_adapter_runtime.py tests/test_system_overview_paper_chain.py -q
5 passed, 9 skipped in 3.00s
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "last_mile_orderbook or orderbook_refresh or stale_orderbook or paper_runtime or paper_decision or paper_intent or system_overview"
15 passed, 57 skipped, 2243 deselected in 8.09s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
OK
```

## Controlled PAPER Runtime Verification

Before:

- paper runtime decisions: `73`
- current stale orderbook blockers: `1`
- last-mile refresh attempts: `0`
- paper intents/orders/fills/positions: `22 / 13 / 10 / 13`
- open paper positions: `0`
- live orders: `0`
- shadow orders: `0`
- `orders_v2`: `1` pre-existing

Action:

```text
.\tools\polybot.ps1 status
.\tools\polybot.ps1 on -mode paper -interval 30
.\tools\polybot.ps1 report
.\tools\polybot.ps1 off
```

Runtime result:

- last-mile refresh attempts: `1`
- refresh success: `1`
- refresh failed: `0`
- stale cleared: `1`
- `STALE_ORDERBOOK`: `1 -> 0`
- new snapshot created: `60431`
- new later selected fresh snapshot: `60466`
- current decision: `ENTER`
- paper intent created: yes
- paper order created: yes
- paper fill created: yes
- paper position opened: yes

After:

- paper runtime current decisions: `1`
- current paper ENTER decisions: `1`
- paper intents/orders/fills/positions: `23 / 14 / 11 / 14`
- open paper positions: `1`
- live orders: `0`
- shadow orders: `0`
- `orders_v2`: `1` unchanged
- system power: `OFF`
- runtime: `SAFE_STOPPED`
- active cycle: `none`

Latest paper lineage:

- intent: `paper_intent_paper_runtime_decision_e3e9f50c523f74156e1d3c4c81771089`
- order: `ad1849ae-2456-5a49-9551-226155572893`
- fill: `paper_fill_9f5535e8650f595d866c7ee9f7e22d9c`
- position: `1643390a-d35a-5e0c-abdb-6c3bcb79cb57`
- market: `691547`
- side: `YES`
- fill price: `0.39`
- quantity: `10`
- orderbook snapshot: `60466`

## Paper Ledger Result

The paper ledger advanced naturally through the normal pipeline after valid fresh orderbook evidence was produced.

No paper row was manually inserted.

## Live / Shadow Safety Result

- live orders remained `0`
- shadow orders remained `0`
- `orders_v2` remained `1` pre-existing and unchanged
- live adapter stayed blocked
- shadow stayed disabled

## Remaining Blockers

The last-mile stale orderbook blocker is repaired.

Remaining broader autonomy limits are still outside this fix:

- candidate diversity remains concentrated around market `691547` / `YES`
- one open PAPER position remains after the final verification
- some runtime status surfaces still mark historical services stale after SYSTEM OFF, but active runtime truth is correct

## Status

GREEN for this repair.

POLYBOT is autonomous in PAPER mode for the current path: YES, with broader market diversity still a future improvement.

## Recommended Next Action

Let PAPER mode continue for several cycles with the new last-mile refresh path, then repair candidate diversity beyond market `691547` if unique PAPER entries remain concentrated.
