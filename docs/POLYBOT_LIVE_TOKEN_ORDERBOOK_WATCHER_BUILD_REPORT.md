# POLYBOT Live Token / Orderbook Watcher Build Report

Date: 2026-06-03

Executor: Codex

Task mode: `CONTROLLED_RUNTIME_FEATURE + LIVE_TOKEN_WATCHER + ORDERBOOK_WATCHER`

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Summary

Phase 3 is implemented as a bounded, read-only CLOB polling watcher. It builds a
watchlist from fresh Phase 2 market/token evidence, refreshes CLOB books by
outcome token id, writes operational traces, publishes source-backed neural
events, and lets the existing mesh/awareness path consume those events.

No live trading, shadow trading, order writes, or paper artifacts were created.

## Current Reality Found

Before implementation:

- `fresh_candidate_seeds`: 10
- `BOOK_VERIFIED` seeds: 10
- trusted fresh seed links: 10
- active/open markets available for watch: 12
- open paper positions: 3
- recent coordinator markets: 4
- watcher tables existed: no
- source-to-neuron repeatable polling tables: not present
- orderbook snapshots: 26084
- neural events: 99
- mesh sessions: 36
- shared awareness rows: 36
- brain opinions: 146
- coordinator decisions: 26

## Files Created

- `app/db/migrations/0114_live_token_orderbook_watcher.sql`
- `app/services/live_orderbook_watcher.py`
- `tests/test_live_orderbook_watcher.py`
- `docs/POLYBOT_LIVE_TOKEN_ORDERBOOK_WATCHER.md`
- `docs/POLYBOT_LIVE_TOKEN_ORDERBOOK_WATCHER_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/events/envelope.py`
- `app/neural_bus/types.py`
- `app/services/brain_dialogue.py`
- `app/shared_awareness/types.py`

## DB Migration

`0114_live_token_orderbook_watcher.sql` adds:

- `live_orderbook_watchlist`
- `live_orderbook_watcher_runs`
- `live_orderbook_watcher_traces`

It also extends the neural event source type constraint to allow
`CLOB_READ_ONLY`.

## Watchlist Model

The watcher stores operational watch state keyed by:

`market_id + side + token_id`

Each watch item records source provenance, priority, status, last poll result,
last snapshot id, bid/ask/spread/liquidity, and failure count.

## Selection Rules

The watcher selects only source-backed verified identities:

- Phase 2 `BOOK_VERIFIED` fresh seeds
- trusted orderbook links from fresh seeds
- `FRESH_VERIFIED` paper eligibility candidates

It excludes stale, closed, inactive, non-accepting, side-missing, condition-missing,
or token-missing rows.

## Polling Rules

Polling is bounded and read-only.

For each watch item:

- call CLOB `/book` with `token_id`
- require response `asset_id == token_id`
- require response `market == condition_id`
- require bids and asks
- persist an `orderbook_snapshot` only if valid

## Change Detection Rules

Events:

- `ORDERBOOK_REFRESHED`
- `SPREAD_CHANGED`
- `LIQUIDITY_CHANGED`
- `TOKEN_BOOK_UNAVAILABLE`
- `MARKET_RESOLVED`
- `MARKET_REPRICING`

Thresholds:

- spread absolute delta: `0.005`
- spread relative delta: `20%`
- liquidity absolute delta: `0.10`
- liquidity relative delta: `25%`
- mid price delta: `0.01`

## Event Publishing Rules

Watcher neural events use:

- `source_component='Live Token / Orderbook Watcher'`
- `source_type='CLOB_READ_ONLY'`
- `source_table='live_orderbook_watcher_traces'`
- payload fields include market id, condition id, token id, side, snapshot id,
  bid, ask, spread, liquidity, and reason.

The existing mesh path produced sessions, shared awareness, brain opinions, and
coordinator decisions during smoke.

## API / Dashboard

Added:

- `GET /dashboard/api/v2/live-orderbook-watcher`
- `POST /live-orderbook-watcher/run`

The endpoint returns `mock_data=false`.

Internal API-container route check returned HTTP 200. A host-side
`Invoke-RestMethod` call to `localhost:8000` timed out once, while the container
was healthy and the same route returned 200 internally.

## Dialogue

Added source-backed dialogue materialization for watcher traces:

- `ORDERBOOK_REFRESHED`
- `SPREAD_CHANGED`
- `LIQUIDITY_CHANGED`
- `TOKEN_BOOK_UNAVAILABLE`
- `MARKET_RESOLVED`
- generic watched/observed traces

## Redaction Adjustment

Public Polymarket identity fields are now preserved in event payloads:

- `token_id`
- `expected_token_id`
- `yes_token_id`
- `no_token_id`
- `asset_id`

Credential-like fields remain redacted.

## Tests Added

`tests/test_live_orderbook_watcher.py`

Covered:

- watchlist creation from `BOOK_VERIFIED` fresh seeds
- stale/closed market and missing token exclusion
- SYSTEM OFF block
- SYSTEM ON bounded polling
- valid book snapshot creation
- `ORDERBOOK_REFRESHED`
- `SPREAD_CHANGED`
- `LIQUIDITY_CHANGED`
- `TOKEN_BOOK_UNAVAILABLE`
- `MARKET_RESOLVED`
- event payload identity fields
- mesh session / shared awareness updates
- dashboard `mock_data=false`
- dialogue materialization
- no trading mutation

## Tests Run

- `python -m py_compile app/services/live_orderbook_watcher.py app/api/routes.py app/services/brain_dialogue.py app/neural_bus/types.py app/shared_awareness/types.py`
- `python -m py_compile app/events/envelope.py app/neural_bus/contracts.py`
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_live_orderbook_watcher.py`: 9 passed
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_fresh_market_identity_gate.py`: 11 passed
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_clob_token_book_verification.py`: 7 passed
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_trusted_orderbook_evidence_service.py tests/test_trusted_orderbook_runtime.py tests/test_dashboard_trusted_orderbook_truth.py`: 15 passed
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_v3_source_to_neuron_ingestion_wiring.py`: 8 passed
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_paper_execution_service.py tests/test_paper_execution_capital_guards.py tests/test_paper_capital_account.py tests/test_paper_lineage_quarantine.py tests/test_paper_trade_forensics.py tests/test_v2_paper_eligibility_safety.py tests/test_v2_paper_intent_safety.py`: 28 passed
- `docker compose --profile test run --rm -e PYTHONPATH=/app test pytest -q tests/test_security_secret_guard.py`: 3 passed

An earlier combined regression command timed out before returning useful output,
so suites were rerun in smaller groups.

## Runtime Smoke

Steps:

1. SYSTEM OFF.
2. Captured baseline dashboard/safety.
3. Verified watcher run blocked while OFF.
4. SYSTEM ON for bounded watcher smoke.
5. Ran watcher with `limit=10`, `max_seconds=45`.
6. SYSTEM OFF in `finally`.
7. Materialized watcher dialogue under bounded SYSTEM ON, then SYSTEM OFF again.

Smoke result:

- status: OK
- watch items checked: 10
- orderbooks refreshed: 10
- snapshots created: 10
- neural events published: 10
- errors: 0
- blocker counts: `{"OK": 10}`
- SYSTEM final state: OFF

## Before / After Counts

Before active watcher smoke:

- watchlist_count: 0
- active_watch_items: 0
- degraded_watch_items: 0
- token_unavailable_count: 0
- watcher_traces: 0
- orderbook_snapshots: 26084
- neural_events: 99
- `ORDERBOOK_REFRESHED`: 0
- `SPREAD_CHANGED`: 0
- `LIQUIDITY_CHANGED`: 0
- `TOKEN_BOOK_UNAVAILABLE`: 0
- `MARKET_RESOLVED`: 0
- mesh_sessions: 36
- shared_awareness: 36
- brain_opinions: 146
- coordinator_decisions: 26

After active watcher smoke:

- watchlist_count: 10
- active_watch_items: 10
- degraded_watch_items: 0
- token_unavailable_count: 0
- watcher_traces: 10
- orderbook_snapshots: 26094
- neural_events: 109
- `ORDERBOOK_REFRESHED`: 10
- `SPREAD_CHANGED`: 0
- `LIQUIDITY_CHANGED`: 0
- `TOKEN_BOOK_UNAVAILABLE`: 0
- `MARKET_RESOLVED`: 0
- mesh_sessions: 37
- shared_awareness: 37
- brain_opinions: 151
- coordinator_decisions: 27

Safety counts before and after:

- live_orders: 0 -> 0
- paper_intents: 6 -> 6
- paper_orders: 9 -> 9
- paper_fills: 6 -> 6
- paper_positions: 9 -> 9
- paper_capital_ledger: 1 -> 1
- orders_v2: 1 -> 1
- fills_v2: 1 -> 1
- canonical positions: 0 -> 0

## Sample Watched Market

Market `2169995`, side `YES`:

- condition id: `0x3733a1b647e7364095736ab0966465d896a84cf3b6bc1695ca1f26c3239b3868`
- token id: `25714007960293389110960044475283546872601238755063051359394740854408462452120`
- best bid: `0.002`
- best ask: `0.003`
- spread: `0.001`
- liquidity score: `0.9955`
- snapshot id: `26094`
- event: `ORDERBOOK_REFRESHED`

## Observed / Not Observed Events

Observed:

- `ORDERBOOK_REFRESHED`: 10

Not observed in bounded smoke:

- `SPREAD_CHANGED`
- `LIQUIDITY_CHANGED`
- `TOKEN_BOOK_UNAVAILABLE`
- `MARKET_RESOLVED`

Those paths are covered by tests.

## Safety Checklist

- live not enabled
- shadow not enabled
- no order/write endpoints called
- no real orders created
- no paper intents/orders/fills/positions created
- no stale candidates watched
- `/book` called by outcome token id
- CLOB `asset_id` validated
- CLOB `market` condition id validated
- no fake books
- no fake liquidity
- secrets not printed
- SYSTEM ended OFF

## Remaining Risks

- Security governance remains `YELLOW_ACCEPTED_BY_OPERATOR` until the operator
  rotates or formally accepts previously exposed credentials.
- Spread/liquidity change and token-unavailable conditions were not naturally
  observed in the short smoke window.
- Host-side `localhost:8000` dashboard request timed out once, though container
  health and internal HTTP route check were OK.
- Phase 4 position token lock/watchdog is not implemented yet.

## Phase Status

YELLOW.

Reason: watcher works and safety is clean, but security governance remains
accepted-risk YELLOW and no material spread/liquidity changes were naturally
observed during the short smoke.

Can move to Phase 4 Position Token Lock + Open Position Watchdog: YES.
