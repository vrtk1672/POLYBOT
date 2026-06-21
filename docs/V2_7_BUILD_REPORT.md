# V2.7 Build Report - Whale Neuron

## Summary

V2.7 Whale Neuron is implemented as a non-trading intelligence layer. It supports source registration, manual/mockable scanning, event normalization, whale registry updates, classification, profiles, categories, market scoring, follow decisions, performance history, optional AI enrichment, API routes, dashboard truth, event publication, and tests.

## Files Created

- `app/whale_neuron/*`
- `app/api/whale_routes.py`
- `app/repositories/whale_source_repository.py`
- `app/repositories/whale_event_repository.py`
- `app/repositories/whale_profile_repository.py`
- `app/repositories/whale_category_repository.py`
- `app/repositories/whale_market_score_repository.py`
- `app/repositories/whale_performance_repository.py`
- `app/repositories/whale_follow_decision_repository.py`
- `tests/test_v2_7_whale_*.py`
- `docs/V2_7_WHALE_NEURON.md`
- `docs/V2_7_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/events/types.py`
- `app/repositories/whale_registry_repository.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration Added

- `app/db/migrations/0045_v2_whale_neuron.sql`

The migration extends existing Phase 5 whale tables and adds missing V2.7 tables. It preserves legacy UUID primary keys.

## API Routes Added

- `GET /whales`
- `GET /whales/{whale_id}`
- `GET /whales/market/{market_id}`
- `GET /whales/events/recent`
- `GET /whales/scores/top`
- `GET /whales/sources`
- `POST /whales/scan`
- `POST /whales/manual`

## Dashboard Changes

The dashboard overview and HTML now include a read-only Whale Neuron panel backed by real database queries.

## Events Published

`whale.source.registered`, `whale.event.collected`, `whale.event.created`, `whale.event.normalized`, `whale.registered`, `whale.profile.updated`, `whale.category.assigned`, `whale.market.scored`, `whale.follow.decided`, `whale.performance.updated`, `whale.signal.created`, and `whale.ai.analyzed`.

## Tests Added

17 V2.7 test files covering contracts, source registry, scanner, normalizer, registry, classifier, profiles, categories, market scores, follow value, noise, performance history, follow decisions, AI analyzer, API, integration, and safety.

## Test Results

- V2.7 targeted without DB env: `16 passed, 3 skipped`.
- Explicit local DB smoke: registry and service integration passed after migration.
- V2.6 regression: `4 skipped`.
- V2.5 regression: `1 passed, 4 skipped`.
- V2.4 regression: `1 passed, 5 skipped`.
- V2.3 regression: `6 passed, 5 skipped`.
- V2.2 regression: `5 passed, 3 skipped`.
- V2.1 regression: `11 skipped`.
- Runtime/safety regression: `59 passed, 7 skipped`.

Full suite: `201 passed, 352 skipped`.

## Runtime Verification

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: `No pending migrations.`
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`: runtime started on port 8000. The foreground script exceeded the tool timeout because it runs the server process, but port 8000 became responsive.
- Existing endpoints verified: `/healthz`, `/runtime/state`, `/runtime/health`, `/events/lag`, `/data/coverage`, `/ai/health`, `/news/recent`, `/rules/coverage`, `/social/recent`.
- New endpoints verified: `/whales`, `/whales/events/recent`, `/whales/scores/top`, `/whales/manual_whale_test_1`.
- Manual whale ingestion verified with market id `2169995`; event persisted, whale registered, profile/category/follow decision generated, market score generated, and whale events published.
- Runtime remained `DATA_ONLY`; live permissions remained false.

## Fully Implemented

- Whale source registry
- Manual/mockable scanner abstraction
- Event normalizer and idempotent repository path
- Whale registry update path
- Event classifier
- Profile builder
- Category engine
- Market score and whale signal contract
- Follow decision logger
- Noise penalty
- Performance history proxy recording
- Optional AI context analyzer
- API endpoints
- Dashboard truth fields
- Event bus integration
- Tests and docs

## Partial

- External whale feed adapters are stubs by design.
- Performance history uses honest proxies unless later outcomes are available.
- News/Social awareness is reserved for future scoring refinements.

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Whale cannot create orders: YES
- Whale cannot create order intents: YES
- Whale cannot trigger exits: YES
- Whale cannot bypass State Governor: YES
- Whale cannot bypass AI Budget Governor: YES
- Unknown whale not auto-followed: YES
- Bad whale penalized: YES
- Whale dump creates signal only: YES
- Dashboard uses real data only: YES

## Remaining Risks

- Local DB migrations are relatively slow in isolated test schemas.
- External whale sources need adapters and credentials in a later phase.
- Runtime orderbook completeness remains partial from earlier known limitations.

## Recommendation

Can move to V2.8: YES.
