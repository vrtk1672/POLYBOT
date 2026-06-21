# Market Universe Memory Stage 1 Report

## 1. Purpose

Stage 1 adds a DATA_ONLY Market Universe Memory foundation so POLYBOT can keep a living, queryable record of known Polymarket markets without depending only on candidates already flowing through execution-oriented pipelines.

The layer stores market identity, condition IDs, outcome token IDs, status, liquidity/volume/spread metadata, freshness, verification state, and research priority. It does not create execution candidates, paper intents, orders, fills, positions, shadow orders, or live orders.

## 2. Money Machine Vision Fit

The Money Machine needs a stable market universe before later event recall and proactive opportunity hunting can be reliable. This stage answers: what markets exist, what IDs identify them, what tokens represent YES/NO, whether the metadata is fresh, and which markets are useful for future recall.

Recommended Stage 2 remains: Source Event Memory + Event-to-Market Recall.

## 3. Existing Repo Audit

- Existing market ingestion is centered on `app/ingestion/gamma_client.py`, `app/ingestion/market_service.py`, and `DataFoundationService.process_markets()`.
- `markets_v2` already stores Gamma/Polymarket market identity, slugs, questions, condition IDs, active/closed/archive flags, close/resolution times, raw metadata, and YES/NO token IDs.
- `market_snapshots_v2` and `orderbook_snapshots` provide liquidity, volume, price, and spread evidence.
- Current CLOB/orderbook truth uses token-level snapshots and trusted orderbook evidence.
- Candidate, thesis, risk, exit, lifecycle, actionability, and opportunity scoring surfaces depend on `market_id`, `condition_id`, `side`, and `token_id`.
- Existing source refresh orchestration has a registry pattern and is safe for DATA_ONLY refresh hooks.

## 4. Architecture

Added a canonical projection service:

- `MarketUniverseMemoryService` reads existing verified local market truth from `markets_v2`, `market_snapshots_v2`, and `orderbook_snapshots`.
- It upserts into `market_universe_memory`.
- It records refresh runs in `market_universe_refresh_runs`.
- It exposes manual refresh, lookup, summary counts, samples, and integration field lookups.
- Source refresh orchestration can call the service at a conservative cadence without blocking runtime.

## 5. Data Model

Migration `0132_market_universe_memory.sql` creates:

- `market_universe_memory`
- `market_universe_refresh_runs`

The memory table stores stable identity fields, YES/NO tokens, metadata, status, freshness, verification states, liquidity/volume/spread, best bid/ask fields, source payload hash, first seen, last seen, verified timestamps, and research priority.

## 6. Identity Normalization

The service normalizes:

- `market_id`
- `condition_id`
- `clob_market_id`
- `slug`
- `question` / `title`
- YES/NO token IDs
- outcome token map

Lookup supports `market_id`, `condition_id`, `token_id`, `slug`, and normalized title/question.

Missing identifiers are marked `PARTIAL` or `UNRESOLVED`; they are not invented.

## 7. Token Verification

Token verification states:

- `TOKENS_VERIFIED`
- `TOKENS_PARTIAL`
- `TOKENS_MISSING`
- `TOKENS_MISMATCH`

Token conflicts are marked mismatch and not silently overwritten.

## 8. Refresh Strategy

Stage 1 supports:

- Universe snapshot refresh via control endpoint.
- Targeted refresh foundation through service lookup/refresh methods.
- Conservative SYSTEM ON hook through source refresh orchestration.

The refresh is DATA_ONLY and records safety before/after counts in refresh metadata.

## 9. Research Priority Model

Research priority is deterministic:

- `HIGH` for active markets with meaningful liquidity/volume, near close, or current candidate pipeline presence.
- `MEDIUM`, `LOW`, and `DORMANT` for progressively weaker active markets.
- `ARCHIVED` for closed/resolved markets.

No activity is fabricated.

## 10. API Endpoints

Added:

- `GET /dashboard/api/v2/control/market-universe-memory`
- `POST /dashboard/api/v2/control/market-universe-memory/refresh`
- `GET /dashboard/api/v2/control/market-universe-memory/lookup`

Updated read-only integration surfaces:

- `GET /dashboard/api/v2/control/trade-opportunity-score`
- `GET /dashboard/api/v2/control/paper-actionability`
- `GET /dashboard/api/v2/control/decision-propagation-trace`

## 11. Integration Surfaces

Opportunity score, paper actionability, and decision propagation trace now expose:

- `market_memory_id`
- `market_memory_status`
- `market_memory_freshness`
- `market_identity_verification_state`
- `token_verification_state`
- `market_memory_research_priority`

These are visibility fields in Stage 1 and do not loosen any Risk, Capital, Exit, Lifecycle, or Paper Actionability gate.

## 12. Tests Run

Focused host no-DB guard:

- `.venv\Scripts\python.exe -m pytest tests/test_market_universe_memory.py tests/test_market_identity_normalization.py tests/test_market_memory_refresh.py tests/test_market_memory_integration_surfaces.py -q`
- Result: `2 passed, 11 skipped`

Focused Postgres-backed:

- `.venv\Scripts\python.exe -m pytest tests/test_market_universe_memory.py tests/test_market_identity_normalization.py tests/test_market_memory_refresh.py tests/test_market_memory_integration_surfaces.py -q`
- Result: `13 passed in 6.73s`

Related:

- `.venv\Scripts\python.exe -m pytest tests/test_candidate_event_scope_orderbook_selection.py tests/test_opportunity_score_hard_blocker_reconciliation.py tests/test_actionability_score_trace_alignment.py tests/test_trade_opportunity_scoring.py -q`
- Result: `18 passed in 2.66s`

Broad:

- `.venv\Scripts\python.exe -m pytest tests -q -k "market_universe or market_memory or identity_normalization or token_verification or paper_actionability or opportunity_score"`
- Result: `56 passed, 2090 deselected in 59.69s`

Compile:

- `.venv\Scripts\python.exe -m compileall app tests`
- Result: passed

## 13. DATA_ONLY Verification

Deployment:

- `docker compose build api`: passed
- `docker compose build migrate`: passed
- `docker compose run --rm migrate`: applied non-destructive migrations through `0132_market_universe_memory.sql`
- `docker compose up -d --no-deps api`: passed

Verification:

- `/healthz`: ok / ready
- Runtime before run: `OFF`, `STOPPED`, `DATA_ONLY`
- Triggered market universe memory refresh with Paper Simulation OFF.
- Refresh completed with status `OK`.
- Started SYSTEM ON in DATA_ONLY only.
- Supervisor ran 4 cycles, 0 failed cycles.
- Source refresh status remained ACTIVE.
- SYSTEM OFF cleanup completed.
- Runtime after cleanup: `OFF`, `STOPPED`, supervisor `STOPPED`, mode `DATA_ONLY`.

## 14. Market Counts

Latest refresh:

- total markets: 14
- active markets: 11
- closed markets: 0
- resolved markets: 0
- archived markets: 0
- markets seen: 14
- markets new: 14
- markets updated: 0
- markets changed: 0
- markets closed: 0
- markets resolved: 0

## 15. Token Verification Counts

- token verified: 14
- token missing: 0
- token mismatch: 0

## 16. Stale / Unresolved Counts

- stale markets: 4
- unresolved markets: 0
- latest refresh errors: 0

## 17. Safety Result

Artifact counts before and after verification were unchanged:

- paper_intents: 21 -> 21
- paper_orders: 12 -> 12
- paper_fills: 9 -> 9
- paper_positions: 12 -> 12
- paper_position_closes: 9 -> 9
- live_orders: 0 -> 0
- positions: 0 -> 0
- shadow_orders: 0 -> 0

No Paper Simulation activation occurred. No execution candidates were created by this stage.

## 18. Limitations

- Stage 1 currently projects from existing local verified market truth instead of independently crawling the full external market universe.
- It prepares targeted refresh lookup foundations but does not implement full Source Event Memory or event-to-market recall.
- Market memory fields are visibility fields in actionability/score/trace; Stage 1 does not add new hard blockers unless existing token/identity conflict logic already applies.

## 19. Recommended Stage 2

Build Source Event Memory + Event-to-Market Recall:

- store source/news/whale/event observations,
- link events to market memory by entity/topic/time/condition/token evidence,
- target-refresh affected markets,
- generate DATA_ONLY proactive candidate recall inputs for later Mesh review.
