# POLYBOT Current Reality Audit

> **SUPERSEDED** — This file was generated on 2026-05-09 against the legacy path `C:\Users\harel\Desktop\polybot` (pre-Docker, pre-V2 runtime). It describes a legacy architecture that no longer reflects the current server.
> Current repo truth is in `docs/V2_CURRENT_ACTIVATION_STATUS.md` (2026-05-21).
> Current context map is in `docs/POLYBOT_CONTEXT_INDEX.md`.
> Do not act on the paths, migration counts, test results, or architecture descriptions below.

Generated on: 2026-05-09
Repository root: `C:\Users\harel\Desktop\polybot`
Audited runtime context: Windows / PowerShell / Python 3.11 / `uv`

## A. Executive Summary

### What exists now

POLYBOT is currently a Python monorepo with one real integrated runtime path:

- FastAPI app bootstrapped by [app/main.py](/Users/harel/Desktop/polybot/app/main.py) and started canonically through [scripts/start_runtime.ps1](/Users/harel/Desktop/polybot/scripts/start_runtime.ps1)
- A synchronous in-process market refresh loop that:
  - fetches Polymarket Gamma events
  - normalizes and scores markets
  - persists cycle / market / ranking snapshots into Postgres
  - synchronously fans into runtime intelligence and runtime trading services
- A Postgres-backed phase ledger architecture spanning:
  - paper trading
  - shadow live
  - live execution memory
  - external intelligence
  - whale scoring
  - ranking / invalidation / advisory / command intent / orchestration
- A read-only operator dashboard served as one HTML page from FastAPI, backed by DB query services
- Telegram command endpoints that mostly expose status and audit logging, with limited live-cage control semantics

### What actually works

- Gamma market fetch, normalization, deterministic scoring, top-market API
- Canonical FastAPI startup path with background scheduler
- Postgres migration framework and large schema footprint
- Runtime persistence of `cycles`, `market_snapshots`, `ranking_snapshots`
- Postgres-backed paper pipeline:
  - signal generation
  - execution-aware paper orders
  - paper positions
  - paper exit lifecycle updates from staged command intents
- Runtime intelligence refresh:
  - source registry
  - news ingestion
  - enrichment
  - cognition handoff
  - whale scoring
  - AI digest alerting
- Shadow-live persistence path
- Live execution memory persistence path
- DB-backed dashboard panels using real query results, not hardcoded mock payloads

### What is only visual, legacy, or partial

- The `/dashboard` UI is real data, but it is a thin HTML shell with no control widgets and no frontend app/framework
- `PAUSE` is audit-only; no runtime state changes are wired in [app/services/operator_control.py:25](/Users/harel/Desktop/polybot/app/services/operator_control.py:25)
- Stage 3 legacy paper trading in [app/stage3](/Users/harel/Desktop/polybot/app/stage3) is a separate SQLite implementation and is not the canonical runtime paper engine
- Controlled orchestration exists as a service and schema, but it is not invoked by the canonical runtime loop
- Strategy engines `SAFE`, `STRIKE`, `CONVEX`, `MAKER`, `HUNT`, `MOONSHOT_BASKET` do not exist as first-class modules/services
- Target operating modes such as `DATA_ONLY`, `SMALL_LIVE`, `ATTACK_MODE`, `COOLDOWN` do not exist as actual system modes

### What is dangerous

- `.env` contains real credentials and live-trading-related values; secrets are present locally and the code auto-loads `.env` at import time
- Stage 4 config auto-loads `.env` on import [app/stage4/config.py:14](/Users/harel/Desktop/polybot/app/stage4/config.py:14), [app/stage4/config.py:17](/Users/harel/Desktop/polybot/app/stage4/config.py:17), causing environment bleed into tests and execution behavior
- `pytest` currently fails 3 Stage 4 tests, all around live auth / live execution expectations
- Startup performs one immediate refresh, then the scheduler loop immediately performs another refresh, so boot likely causes a double scan [app/main.py:46](/Users/harel/Desktop/polybot/app/main.py:46), [app/scheduler.py:31](/Users/harel/Desktop/polybot/app/scheduler.py:31)
- Stage 3 legacy paper exits are explicitly temporary and not resolution-aware [app/stage3/paper_trader.py:345](/Users/harel/Desktop/polybot/app/stage3/paper_trader.py:345)
- No real event bus, queue durability, retry worker, or DLQ exists; the integrated runtime is synchronous and process-local

### What is missing

- True event bus
- dedicated no-trade ledger
- formal state/mode governor
- real strategy engine modules matching the target engine list
- real rules/wording ingestion from market resolution criteria
- social ingestion
- live orchestration of command intents into an executor loop
- compliance/rules guard as a distinct module
- live-ready exit settlement and reconciliation flow

### What should not be touched yet

- The Postgres phase schema should not be replaced; it is the main continuity asset
- The canonical runtime path in [scripts/start_runtime.ps1](/Users/harel/Desktop/polybot/scripts/start_runtime.ps1) should remain the single operator path
- The integrated runtime fan-out in `MarketService.refresh()` should be stabilized before any rewrite of architecture names or service boundaries
- The Stage 3 SQLite path should be treated as legacy reference, not extended

## B. Repository Discovery

### Top-level structure

```text
polybot/
  app/                          Main Python application
    api/                        FastAPI routes and embedded dashboard HTML
    db/                         Postgres config, connection, migrations
    domain/contracts/           Pydantic-like contract dataclasses for persistence layers
    ingestion/                  Gamma API fetch and runtime market service
    models/                     Core normalized market and score models
    repositories/              Table-level Postgres repositories
    scoring/                    Deterministic opportunity scoring
    services/                   Phase services, runtime services, alerts, Telegram, recorders
    stage2/                     Legacy Stage 2 WebSocket + Claude analysis support
    stage3/                     Legacy SQLite paper trader and terminal dashboard
    stage4/                     Guarded live execution foundation
    utils/                      Shared helpers
    config.py                   App settings
    env_runtime.py              Import-time .env loader
    main.py                     FastAPI app entrypoint
    scheduler.py                In-process refresh scheduler
  artifacts/                    Audit/run output directories from previous work
  docs/                         Phase docs and canonical runtime note
  logs/                         Runtime logs and Stage 3 SQLite DB location
  scripts/                      Canonical PowerShell operator scripts
  tests/                        Pytest suite
  brain.py                      Legacy stage runner / operator CLI
  gamma_crawler.py              Standalone scanner CLI
  docker-compose.grafana.yml    Grafana-only compose file
  pyproject.toml                Python packaging and scripts
  uv.lock                       Locked dependencies
  .env                          Local runtime secrets/config (contains real secrets)
  .env.example                  Safe template
```

### What is absent

- No `package.json`
- No Node/React/Vite/Next frontend
- No Dockerfile
- No repo-local Postgres/Redis compose file other than Grafana
- No Redis client code in `app/`
- No Kafka/RabbitMQ/Celery/RQ/Dramatiq usage in `app/`

### Main folders explained

- `app/api`: HTTP surface. Real endpoints plus an embedded HTML dashboard shell.
- `app/db`: Postgres-only runtime persistence. The integrated runtime depends on this for canonical operation.
- `app/domain/contracts`: Persistence DTO layer; most services build these contracts before recorder/repository writes.
- `app/repositories`: Thin table repositories. This is where real DB reads/writes are formalized.
- `app/services`: The real business layer. This contains paper, shadow, live, intelligence, ranking, invalidation, exit, command intent, orchestration, alerts, and recorders.
- `app/stage3`: Legacy SQLite paper trading path. Important for history; non-canonical now.
- `app/stage4`: Guarded live-execution foundation reused by paper, shadow, and live paths.
- `scripts`: Operational wrappers that enforce canonical env and DB selection.

## C. Runtime Architecture Mapping

### Startup files and entrypoints

- Python package entrypoint: `polybot = "app.main:run"` in [pyproject.toml](/Users/harel/Desktop/polybot/pyproject.toml)
- Canonical operator start: [scripts/start_runtime.ps1](/Users/harel/Desktop/polybot/scripts/start_runtime.ps1)
- Canonical migration path: [scripts/migrate_runtime.ps1](/Users/harel/Desktop/polybot/scripts/migrate_runtime.ps1)
- Smoke check: [scripts/smoke_runtime.ps1](/Users/harel/Desktop/polybot/scripts/smoke_runtime.ps1)
- Legacy operator CLI: [brain.py](/Users/harel/Desktop/polybot/brain.py)
- Standalone scanner CLI: [gamma_crawler.py](/Users/harel/Desktop/polybot/gamma_crawler.py)

### Actual canonical runtime flow

1. `scripts/start_runtime.ps1` loads `.env`, then force-sets:
   - `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
   - `PHASE1_PERSISTENCE_ENABLED=true`
   - `PHASE1_AUTO_MIGRATE=false`
   - `POLYBOT_RUNTIME_MODE=paper_safe` if unset
   - `POLYBOT_EXECUTION_BACKEND=paper` if unset
   - `LIVE_TRADING_ENABLED=false` if unset
   - `LIVE_KILL_SWITCH=true` if unset
   - `POLYBOT_API_HOST=127.0.0.1`
   - `POLYBOT_API_PORT=8000`
2. `python -m uv run polybot` calls `app.main:run`
3. [app/main.py](/Users/harel/Desktop/polybot/app/main.py) creates:
   - `Settings`
   - `GammaClient`
   - `MarketService`
   - FastAPI app
4. App lifespan:
   - logs startup context
   - calls `await market_service.refresh()`
   - starts `RefreshScheduler`
5. `RefreshScheduler` loops forever in-process and calls `market_service.refresh()` every configured interval
6. `market_service.refresh()`:
   - fetches active Gamma events
   - normalizes markets
   - scores and ranks them
   - persists cycle / market / ranking snapshots to Postgres
   - calls `RuntimeIntelligenceService.refresh(...)`
   - calls `RuntimePaperTradingService.process_cycle(...)`
7. HTTP endpoints read either:
   - in-memory `MarketService` state for `/health`, `/markets/*`
   - Postgres query services for `/dashboard/api/*`

### Service startup order

- There is no service orchestrator or multi-container dependency graph in the repo.
- Effective startup order is:
  - environment load
  - optional DB migration
  - FastAPI app creation
  - one immediate market refresh
  - background refresh scheduler
  - HTTP serving

### Ports

- FastAPI API/dashboard: `127.0.0.1:8000`
- Grafana container: `3001 -> 3000`
- Canonical Postgres runtime target: `127.0.0.1:55432`

### Docker and containers actually detected

Detected via `docker ps` during audit:

- `polybot_grafana` on `3001`
- `polybot_phase1_pg` on `55432`
- `wh_v2_postgres` on `5432`
- `wh_v2_redis` on `6379`

Repo-local Docker definition found:

- [docker-compose.grafana.yml](/Users/harel/Desktop/polybot/docker-compose.grafana.yml)

Important:

- The repo does not contain a compose file for the canonical Postgres DB.
- Redis is running on the machine, but the POLYBOT codebase does not use it.

### Environment variables that actually affect runtime

App/runtime:

- `POLYBOT_DATABASE_URL`
- `DATABASE_URL` compatibility only
- `PHASE1_PERSISTENCE_ENABLED`
- `PHASE1_AUTO_MIGRATE`
- `POLYBOT_RUNTIME_MODE`
- `POLYBOT_EXECUTION_BACKEND`
- `POLYBOT_REFRESH_INTERVAL_SECONDS`
- `POLYBOT_TOP_N`
- `POLYBOT_API_HOST`
- `POLYBOT_API_PORT`
- `POLYBOT_LOG_LEVEL`
- `ANTHROPIC_API_KEY`

Stage 4 / paper / live:

- `LIVE_TRADING_ENABLED`
- `LIVE_KILL_SWITCH`
- `LIVE_MAX_ORDER_USD`
- `LIVE_MAX_DAILY_LOSS`
- `LIVE_MARKET_WHITELIST`
- `LIVE_USE_ADAPTIVE_SELECTOR`
- `LIVE_ALLOWED_UNIVERSE_TOP_N`
- `LIVE_MIN_TOTAL_RANK`
- `LIVE_MIN_CONFIDENCE`
- `LIVE_MAX_CONCURRENT_POSITIONS` / `LIVE_MAX_OPEN_POSITIONS`
- `LIVE_MAX_SAME_MARKET_EXPOSURE`
- `LIVE_COOLDOWN_SECONDS`
- `LIVE_REQUIRE_ORDERBOOK`
- `LIVE_REQUIRE_TRADABLE_MARKET`
- `LIVE_OPTIONAL_WHITELIST_MODE`
- `ALLOW_SCALING`
- `PAPER_STARTING_CAPITAL_USD`
- `PAPER_MIN_CASH_RESERVE_PCT`
- `PAPER_MAX_ALLOC_PER_TRADE_PCT`
- `PAPER_MAX_TOTAL_DEPLOYMENT_PCT`
- `PAPER_SAFE_MAX_CONCURRENT_POSITIONS`

Venue credentials:

- `POLY_PRIVATE_KEY`
- `POLY_FUNDER`
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`
- `POLY_CLOB_HOST`
- `POLY_CHAIN_ID`
- `POLY_SIGNATURE_TYPE`

Telegram:

- `POLYBOT_TELEGRAM_BOT_TOKEN` equivalent field name in app settings is `telegram_bot_token`
- `POLYBOT_TELEGRAM_DEFAULT_CHAT_ID`
- `POLYBOT_TELEGRAM_WEBHOOK_SECRET`

## D. Current Architecture Diagram

```text
Gamma API
  ->
GammaClient.fetch_active_events()
  ->
MarketService.refresh()
  ->
normalize markets
  ->
OpportunityScorer
  ->
in-memory top markets
  ->
Postgres:
  cycles
  market_snapshots
  ranking_snapshots
  ->
RuntimeIntelligenceService
  -> intelligence_sources / ingestion_runs / external events / enrichments / handoff / whale scores / alert_events
  ->
RuntimePaperTradingService
  -> signal_paper
  -> execution_aware_paper OR shadow_live OR live_runtime
  -> trade_classification
  -> bucket_allocation
  -> ranking_v2
  -> ranking_policy
  -> invalidation_exit_policy
  -> exit_advisory
  -> advisory_resolution
  -> command_intent_staging
  -> paper lifecycle updates
  ->
FastAPI routes
  -> /health and /markets/* from in-memory state
  -> /dashboard/api/* from Postgres query services
  -> /dashboard embedded HTML fetches /dashboard/api/overview
  -> /telegram/* status + audit + limited live-cage control
```

## E. Existing Pipeline Mapping

| Stage | Input | Output | Code Location | Persistence | Status | Notes |
|---|---|---|---|---|---|---|
| Market discovery | Gamma `/events` pages | raw event list | [app/ingestion/gamma_client.py](/Users/harel/Desktop/polybot/app/ingestion/gamma_client.py) | none | IMPLEMENTED | Retry on 5xx/429/request error |
| Market scanner | raw events | normalized market list | [app/ingestion/market_service.py](/Users/harel/Desktop/polybot/app/ingestion/market_service.py) | `cycles`, `market_snapshots`, `ranking_snapshots` | IMPLEMENTED | Filters inactive/closed/non-accepting markets |
| Market snapshots | scored markets | persisted market snapshot rows | `MarketService._persist_runtime_snapshot()` | `market_snapshots` | IMPLEMENTED | Top N only |
| Orderbook snapshots | token id | transient order book summary | Stage 4 execution client calls via paper/shadow/live services | none | PARTIAL | Lookups happen ad hoc; no dedicated orderbook snapshot table |
| Rules ingestion | expected market rules / wording | structured rules | not found | none | MISSING | No dedicated resolution criteria ingestion |
| News ingestion | enabled intelligence sources | normalized external events | [app/services/runtime_intelligence.py](/Users/harel/Desktop/polybot/app/services/runtime_intelligence.py), [app/services/external_intelligence.py](/Users/harel/Desktop/polybot/app/services/external_intelligence.py) | `intelligence_sources`, `intelligence_ingestion_runs`, `external_raw_events`, `external_events_normalized` | IMPLEMENTED | Real DB-backed path |
| Social ingestion | social feeds | social signals | not found | none | MISSING | No X/Telegram/social collector |
| Whale ingestion | recent market ids / event supply | whale registry/events/profiles/categories/scores | `whale_*` services under [app/services](/Users/harel/Desktop/polybot/app/services) | `whale_*` tables | PARTIAL | Scoring path exists; no 24/7 queue worker |
| Signal generation | ranked candidates + policy/guard/orderbook/capital | paper signals | [app/services/signal_paper.py](/Users/harel/Desktop/polybot/app/services/signal_paper.py) | `paper_runs`, `paper_signals` | IMPLEMENTED | Produces `WOULD_ENTER`, `WOULD_BLOCK`, etc. |
| Opportunity scoring | normalized markets | scored markets | [app/scoring/opportunity_score.py](/Users/harel/Desktop/polybot/app/scoring/opportunity_score.py) | in ranking snapshots | IMPLEMENTED | Deterministic, not neural |
| Strategy routing | classified markets | primary trade type | [app/services/trade_classification.py](/Users/harel/Desktop/polybot/app/services/trade_classification.py) | `trade_classification_runs`, `trade_classifications` | PARTIAL | Contains `NO_TRADE`, but no named engine router |
| Capital allocation | paper capital snapshot + rank/confidence | allocation decision | [app/services/capital_allocator.py](/Users/harel/Desktop/polybot/app/services/capital_allocator.py) | embedded in signal payloads and bucket allocation tables | PARTIAL | Real for paper; not a full cross-mode allocator |
| Risk gate | Stage 4 execution policy + live guard | allow/block decision | [app/stage4/execution_policy.py](/Users/harel/Desktop/polybot/app/stage4/execution_policy.py), [app/stage4/live_guard.py](/Users/harel/Desktop/polybot/app/stage4/live_guard.py) | mostly event/order payloads | IMPLEMENTED | Shared across paper/shadow/live |
| Risk governor | operator kill override + live runtime cage | runtime block reasons | [app/services/live_runtime.py](/Users/harel/Desktop/polybot/app/services/live_runtime.py) | `operator_control_actions`, `live_orders`, `positions` | PARTIAL | Exists only for live path |
| Paper execution | paper signals | paper orders + positions | [app/services/execution_aware_paper.py](/Users/harel/Desktop/polybot/app/services/execution_aware_paper.py) | `paper_orders`, `paper_order_events`, `paper_positions`, `paper_position_events` | IMPLEMENTED | Canonical paper path |
| Live execution | selected live intent | live order submission and memory | [app/services/live_runtime.py](/Users/harel/Desktop/polybot/app/services/live_runtime.py), [app/services/recorders/execution_memory.py](/Users/harel/Desktop/polybot/app/services/recorders/execution_memory.py) | `live_orders`, `order_status_history`, `positions`, `position_events` | PARTIAL / FRAGILE | Exists, but tests fail and env bleed is dangerous |
| Position tracking | paper/shadow/live order results | position rows and events | paper/shadow/live services | `paper_positions`, `shadow_positions`, `positions` and event tables | IMPLEMENTED | Different codepaths per mode |
| Exit logic | invalidation + exit advisory + command intents | exit/update/cancel/prepare commands | `invalidation_exit_policy.py`, `exit_advisory.py`, `advisory_resolution.py`, `command_intent_staging.py` | phase 8 tables | IMPLEMENTED | Rich persistence, not yet fully orchestrated |
| Feedback loop | current cycle -> later policy tables | rankings, advisories, intents | `RuntimePaperTradingService.process_cycle()` | many phase tables | PARTIAL | DB feedback exists; learning loop does not |
| Market memory | cycle snapshots + decisions + live/paper memory | persisted history | Postgres phase schema | many tables | IMPLEMENTED | This is the strongest existing architectural asset |
| Dashboard | DB query services | HTML + JSON panels | [app/api/routes.py](/Users/harel/Desktop/polybot/app/api/routes.py), query services | none beyond DB reads | IMPLEMENTED | Real data, no frontend app |
| Observability | health, KPI query views, alerts | JSON panels and logs | dashboard queries + alert service | `alert_events`, query reads | PARTIAL | No metrics backend integration beyond Grafana container presence |
| No-trade logging | blocked/skip decisions | scattered reasons | `paper_signals`, `rejection_ledger`, ranking policy | no dedicated `no_trade_log` table | PARTIAL | `NO_TRADE` concept exists, dedicated log does not |
| Compliance / rules guard | explicit compliance subsystem | guard actions | not found as standalone subsystem | none | MISSING | Some safety checks live in Stage 4 guards |

## F. Database Audit

### Databases in use

1. Canonical integrated runtime: Postgres on `127.0.0.1:55432`
2. Legacy Stage 3 path: SQLite at `logs/paper_trading.db`

### Postgres schema inventory

Tables created by migrations:

- Phase 1: `cycles`, `market_snapshots`, `ranking_snapshots`, `decision_ledger`, `live_orders`, `order_status_history`, `positions`, `position_events`, `run_artifacts`, `rejection_ledger`
- Phase 2: `paper_runs`, `paper_signals`, `paper_orders`, `paper_order_events`, `paper_positions`, `paper_position_events`, `shadow_runs`, `shadow_orders`, `shadow_order_events`, `shadow_positions`, `shadow_position_events`
- Phase 3: `event_interpretation_runs`, `event_interpretations`, `market_link_runs`, `market_link_candidates`, `resolution_analysis_runs`, `resolution_analyses`, `invalidation_reasoning_runs`, `invalidation_reasonings`, `cognition_summary_runs`, `cognition_summaries`
- Phase 4: `intelligence_sources`, `intelligence_ingestion_runs`, `external_raw_events`, `external_events_normalized`, `external_event_enrichment_runs`, `external_event_enrichments`, `cognition_handoff_runs`, `cognition_handoff_candidates`
- Phase 5: `whale_scan_runs`, `whale_events`, `whale_registry`, `whale_profile_runs`, `whale_profiles`, `whale_category_runs`, `whale_categories`, `whale_scoring_runs`, `whale_market_scores`
- Phase 6: `trade_classification_runs`, `trade_classifications`, `bucket_allocation_runs`, `bucket_allocations`
- Phase 7: `ranking_v2_runs`, `ranking_v2_candidates`, `ranking_policy_runs`, `ranking_policy_candidates`
- Phase 8: `invalidation_policy_runs`, `invalidation_policy_records`, `exit_advisory_runs`, `exit_advisory_records`, `advisory_resolution_runs`, `advisory_resolution_records`, `command_intent_runs`, `command_intent_records`
- Phase 9: `orchestration_gate_runs`, `orchestration_packets`, `orchestration_gate_records`, `operator_control_actions`, `alert_events`

### Schema quality observations

- Migration naming has a collision:
  - `0017_phase3d_invalidation_reasoning_lite.sql`
  - `0017_shadow_status_expansion.sql`
  This does not break the repo-local migration runner because it keys on full filename, but it is version-order confusing.
- `scripts/start_runtime.ps1` forces DB URL and enables persistence, while `get_database_settings().enabled` is `False` by default outside that script.
- Many tables are well-related through foreign keys and run-record patterns; the schema is significantly more mature than the runtime wiring.

### Table usage map

Status legend used here:

- `ACTIVE`: definitely written and read in current code paths
- `PARTIAL`: written or read, but not fully wired in canonical runtime
- `LEGACY`: used only by old path
- `UNKNOWN_RUNTIME`: schema exists, service exists, but canonical runtime invocation is absent

| Table | Purpose | Created where | Written by | Read by | Status | Issues |
|---|---|---|---|---|---|---|
| `cycles` | runtime cycle envelope | `0001_phase1_cycles.sql` | `CycleRecorder`, `Phase1CyclePersistenceService` | dashboard queries, replay | ACTIVE | mode vocabulary lags target modes |
| `market_snapshots` | persisted market state | `0002_phase1_market_snapshots.sql` | `MarketSnapshotRecorder` | dashboard, replay | ACTIVE | no dedicated orderbook snapshot history |
| `ranking_snapshots` | persisted top-N ranking | `0003_phase1_ranking_snapshots.sql` | `RankingSnapshotRecorder` | dashboard, replay | ACTIVE | fallback ranking source only |
| `decision_ledger` | selection decisions | `0004_phase1_decision_ledger.sql` | legacy phase1 persistence / brain path | dashboard, multiple services | PARTIAL | canonical runtime scanner does not populate decisions_count |
| `live_orders` | live execution memory | `0005_phase1_execution_memory.sql` | `ExecutionMemoryPersistenceService`, `LiveTradingService` | dashboard, live runtime, telegram summaries | PARTIAL | live path exists but is fragile |
| `order_status_history` | live order status trail | `0005_phase1_execution_memory.sql` | `ExecutionMemoryPersistenceService` | dashboard | PARTIAL | depends on live path |
| `positions` | live positions | `0005_phase1_execution_memory.sql` | `ExecutionMemoryPersistenceService` | dashboard, live runtime, cognition/trade services | PARTIAL | not a full reconciliation engine |
| `position_events` | live position events | `0005_phase1_execution_memory.sql` | `ExecutionMemoryPersistenceService` | dashboard | PARTIAL | depends on live path |
| `run_artifacts` | artifact references | `0006_phase1_run_artifacts.sql` | artifact recorder | repository only | PARTIAL | not surfaced in runtime/dashboard |
| `rejection_ledger` | rejection reasons | `0007_phase1_rejection_ledger.sql` | phase1 persistence helpers | dashboard | PARTIAL | no dedicated no-trade log |
| `paper_runs` | canonical paper cycle run | `0008_phase2_signal_paper.sql` | `SignalPaperService`, `ExecutionAwarePaperService` | dashboard, paper query service | ACTIVE | main paper runtime ledger |
| `paper_signals` | paper entry/block signals | `0008_phase2_signal_paper.sql` | `SignalPaperService` | execution-aware paper, dashboard | ACTIVE | doubles as implicit no-trade signal store |
| `paper_orders` | paper orders | `0010_phase2_execution_aware_paper.sql` | `ExecutionAwarePaperService`, paper lifecycle updates | dashboard, paper query | ACTIVE | simulation semantics depend on adapter backend |
| `paper_order_events` | paper order event trail | `0010_phase2_execution_aware_paper.sql` | `ExecutionAwarePaperService`, lifecycle service | dashboard | ACTIVE | healthy audit trail |
| `paper_positions` | canonical paper positions | `0010_phase2_execution_aware_paper.sql` | `ExecutionAwarePaperService`, lifecycle service | dashboard, capital allocator, paper query | ACTIVE | strongest canonical paper truth source |
| `paper_position_events` | paper position event trail | `0010_phase2_execution_aware_paper.sql` | `ExecutionAwarePaperService`, lifecycle service | dashboard | ACTIVE | healthy audit trail |
| `shadow_runs` | shadow-live run | `0012_phase2_shadow_live.sql` | `ShadowLiveService` | repository/query | PARTIAL | canonical runtime only uses if mode/backend select it |
| `shadow_orders` | shadow orders | `0012_phase2_shadow_live.sql` | `ShadowLiveService` | dashboard, telegram summaries | PARTIAL | good audit path, no execution |
| `shadow_order_events` | shadow order events | `0012_phase2_shadow_live.sql` | `ShadowLiveService` | dashboard | PARTIAL | useful dry-run evidence |
| `shadow_positions` | shadow positions | `0012_phase2_shadow_live.sql` | `ShadowLiveService` | dashboard, telegram summaries | PARTIAL | pending-submission only |
| `shadow_position_events` | shadow position events | `0012_phase2_shadow_live.sql` | `ShadowLiveService` | dashboard | PARTIAL | good audit trail |
| `event_interpretation_runs` / `event_interpretations` | phase 3 interpretation | `0014_*` | `event_interpreter.py` service | query service | UNKNOWN_RUNTIME | not invoked by canonical runtime |
| `market_link_runs` / `market_link_candidates` | phase 3b link candidates | `0015_*` | `market_link_candidate.py` | query service | UNKNOWN_RUNTIME | not invoked by canonical runtime |
| `resolution_analysis_runs` / `resolution_analyses` | phase 3c resolution analysis | `0016_*` | `resolution_analyzer_lite.py` | query services | UNKNOWN_RUNTIME | not invoked by canonical runtime |
| `invalidation_reasoning_runs` / `invalidation_reasonings` | phase 3d invalidation reasoning | `0017_phase3d_*` | `invalidation_reasoning_lite.py` | repositories | UNKNOWN_RUNTIME | not in canonical loop |
| `cognition_summary_runs` / `cognition_summaries` | phase 3e cognition summary | `0018_*` | `cognition_summary.py` | dashboard intelligence panel, trade classification references | PARTIAL | data can exist, but upstream pipeline is not canonical |
| `intelligence_sources` | source registry | `0019_*` | `RuntimeIntelligenceService._ensure_default_sources()` | runtime intelligence, dashboard | ACTIVE | source enablement is real |
| `intelligence_ingestion_runs` | ingestion runs | `0019_*` | `ExternalIntelligenceFoundationService` | dashboard | ACTIVE | good provenance |
| `external_raw_events` | raw fetched source events | `0019_*` | external intelligence foundation | repositories | ACTIVE | canonical source audit layer |
| `external_events_normalized` | normalized news/events | `0019_*` | external intelligence foundation | runtime intelligence, dashboard | ACTIVE | real news truth layer |
| `external_event_enrichment_runs` / `external_event_enrichments` | enrichment | `0020_*` | enrichment service | repositories/query | ACTIVE | canonical runtime invokes it |
| `cognition_handoff_runs` / `cognition_handoff_candidates` | news-to-cognition handoff | `0021_*` | handoff service | dashboard | ACTIVE | canonical runtime invokes it |
| `whale_scan_runs`, `whale_events`, `whale_registry`, `whale_profile_runs`, `whale_profiles`, `whale_category_runs`, `whale_categories`, `whale_scoring_runs`, `whale_market_scores` | whale pipeline | `0022_*` through `0025_*` | whale services | dashboard/query services | PARTIAL | scoring invoked; full upstream scan cadence is not obvious from canonical runtime |
| `trade_classification_runs` / `trade_classifications` | trade type classification | `0026_*` | `TradeClassificationService` | dashboard | ACTIVE | includes `NO_TRADE`, not dedicated engine routing |
| `bucket_allocation_runs` / `bucket_allocations` | bucket assignment | `0027_*` | `BucketAllocationService` | dashboard | ACTIVE | not the same as target capital allocator |
| `ranking_v2_runs` / `ranking_v2_candidates` | enriched ranking | `0028_*` | `RankingV2Service` | dashboard | ACTIVE | canonical runtime invokes |
| `ranking_policy_runs` / `ranking_policy_candidates` | policy gating | `0029_*` | `RankingPolicyService` | dashboard | ACTIVE | primary candidate truth for UI |
| `invalidation_policy_runs` / `invalidation_policy_records` | invalidation / exit policy | `0030_*` | `InvalidationExitPolicyService` | dashboard, advisories | ACTIVE | real exit precursor |
| `exit_advisory_runs` / `exit_advisory_records` | exposure advisories | `0031_*` | `ExitAdvisoryService` | dashboard, resolution, command intent staging | ACTIVE | real advisory layer |
| `advisory_resolution_runs` / `advisory_resolution_records` | resolved advisory action | `0032_*` | `AdvisoryResolutionService` | dashboard, command intent staging | ACTIVE | real bridge into action staging |
| `command_intent_runs` / `command_intent_records` | staged execution intents | `0033_*` | `CommandIntentStagingService` | dashboard, paper lifecycle, orchestration | ACTIVE | important seam |
| `orchestration_gate_runs` / `orchestration_packets` / `orchestration_gate_records` | controlled orchestration | `0034_*` | `ControlledOrchestrationGateService` | query services only | UNKNOWN_RUNTIME | service exists but not called from canonical runtime |
| `operator_control_actions` | operator actions / kill overrides | `0035_*` | `OperatorControlService` | live runtime, dashboard | PARTIAL | `PAUSE` is placeholder only |
| `alert_events` | alerts and AI digest | `0035_*` + `0037_*` | `AlertEventService`, runtime intelligence | dashboard, alert API | ACTIVE | real DB-backed alert truth |

### Legacy SQLite tables

In [app/stage3/database.py](/Users/harel/Desktop/polybot/app/stage3/database.py):

- `scans`
- `signals`
- `paper_trades`
- `portfolio`

Status: `LEGACY`

Issues:

- completely separate from canonical Postgres paper truth
- still used by `brain.py --paper`
- exit logic is temporary and not market-resolution-aware

## G. Event Bus / Queue Audit

### Current reality

There is no actual event bus implementation in the POLYBOT repository.

What exists instead:

- synchronous in-process service calls inside `MarketService.refresh()`
- Postgres tables used as durable handoff ledgers between later-stage services
- HTTP endpoints
- external Telegram webhook ingress

### Redis / queues

- Redis container exists on the machine (`wh_v2_redis` on `6379`)
- no Redis client usage was found in `app/*.py`
- no stream names, consumer groups, pending-entry handling, DLQ logic, or queue ack behavior exists in the codebase

### Queue map

| Stream/Queue | Producer | Consumer | Payload | Status | Risk |
|---|---|---|---|---|---|
| NONE | NONE | NONE | NONE | MISSING | All phase fan-out is synchronous and process-local |

### Architectural implication

The current system uses Postgres as the durable memory fabric, not Redis/streams. That is workable for auditability, but it is not an event bus and does not satisfy the target architecture's bus/mesh expectations.

## H. API and Dashboard Audit

### Existing API routes

Real routes in [app/api/routes.py](/Users/harel/Desktop/polybot/app/api/routes.py):

- `GET /health`
- `GET /markets/top`
- `GET /markets/raw-count`
- `GET /markets/last-refresh`
- `GET /dashboard`
- `GET /dashboard/api/overview`
- `GET /dashboard/api/health`
- `GET /dashboard/api/kpi-quality`
- `GET /dashboard/api/ranking`
- `GET /dashboard/api/positions-orders`
- `GET /dashboard/api/invalidation`
- `GET /dashboard/api/intelligence`
- `GET /dashboard/api/audit`
- `GET /dashboard/api/alerts`
- `POST /telegram/command`
- `POST /telegram/webhook`

### Frontend/dashboard implementation

- Single embedded HTML document returned by `/dashboard`
- No SPA framework
- No frontend build tooling
- Dashboard fetches `/dashboard/api/overview?limit=6` every refresh interval
- Panels are text `pre` blocks containing raw JSON

### UI truth map

| UI/API Element | Classification | Why |
|---|---|---|
| `/health` | REAL | reads live in-memory market service state |
| `/markets/top` | REAL | returns current scored markets from runtime memory |
| `/markets/raw-count` | REAL | returns current counts from runtime memory |
| `/markets/last-refresh` | REAL | returns current runtime memory refresh state |
| `/dashboard` page shell | REAL | HTML is real, but only a shell |
| System Health panel | REAL | Postgres-backed query service |
| KPI/Quality panel | REAL | Postgres-backed aggregates |
| Ranking panel | REAL | Postgres-backed, with runtime snapshot fallback |
| Positions / Orders panel | REAL | reads live/paper/shadow DB tables |
| Invalidation / Exit panel | REAL | reads phase 8 tables |
| Intelligence panel | REAL | reads whale/news/cognition/alert tables |
| Audit / Alerts panel | REAL | reads decision/rejection/control/alert/event histories |
| Dashboard controls/buttons | MISSING | no buttons or toggles exist |
| "Remote controls remain audited placeholders" message | REAL / WARNING | explicitly states controls are not wired [app/api/routes.py:212](/Users/harel/Desktop/polybot/app/api/routes.py:212) |
| `POST /telegram/command` `/status` `/health` `/top` `/positions` `/orders` `/pnl` `/whales` `/news` | REAL | query DB and format responses |
| Telegram `/pause` | PARTIAL / PLACEHOLDER | only inserts audit row, no runtime change |
| Telegram `/kill` and `/resume` | PARTIAL | writes operator control row; live runtime reads it as cage override |

### Frontend/backend communication

- Browser fetches only `/dashboard/api/overview`
- No WebSocket server for dashboard
- No client-side mutation actions

## I. Config and Environment Audit

### Files inspected

- [app/config.py](/Users/harel/Desktop/polybot/app/config.py)
- [app/stage4/config.py](/Users/harel/Desktop/polybot/app/stage4/config.py)
- [.env.example](/Users/harel/Desktop/polybot/.env.example)
- [.env](/Users/harel/Desktop/polybot/.env)
- [scripts/load_env.ps1](/Users/harel/Desktop/polybot/scripts/load_env.ps1)
- [scripts/start_runtime.ps1](/Users/harel/Desktop/polybot/scripts/start_runtime.ps1)

### Important findings

- `.env.example` is safe
- `.env` contains real secrets and live venue credentials
- config is loaded in multiple ways:
  - Pydantic `env_file=".env"`
  - import-time `load_env_file_into_process()`
  - PowerShell env injection in runtime scripts
- this creates duplicate precedence paths and test contamination risk

### Secret handling assessment

Do not print secret values. Secret-bearing variable names present:

- `ANTHROPIC_API_KEY`
- `POLY_PRIVATE_KEY`
- `POLY_FUNDER`
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`

Status:

- present in local `.env`
- actively usable by runtime
- dangerous to keep in a developer workstation file without stronger isolation

### Variable audit

| Variable / Group | Status | Notes |
|---|---|---|
| `POLYBOT_DATABASE_URL` | USED / REQUIRED for canonical runtime | injected by script, absent from local `.env` |
| `DATABASE_URL` | COMPATIBILITY ONLY | explicitly removed by start script |
| `PHASE1_PERSISTENCE_ENABLED` | USED | canonical runtime forces `true` |
| `PHASE1_AUTO_MIGRATE` | USED | canonical runtime forces `false` |
| `POLYBOT_RUNTIME_MODE` | USED | canonical mapping only yields `LISTEN_ONLY`, `PAPER`, `LIVE` |
| `POLYBOT_EXECUTION_BACKEND` | USED | values seen: `paper`, `shadow_live`, `live` |
| `LIVE_KILL_SWITCH` | USED | dangerous when leaked from `.env` into tests |
| `LIVE_TRADING_ENABLED` | USED | guardrail variable |
| `PAPER_*` capital vars | USED | canonical paper sizing uses them |
| `POLYBOT_TELEGRAM_*` settings | USED if configured | optional |
| `POLYBOT_GAMMA_*` settings | USED | scanner runtime |
| `POLYBOT_INTELLIGENCE_*` settings | USED | runtime intelligence cadence |

### Naming inconsistencies

- `MAX_NOTIONAL_PER_ORDER` aliases `LIVE_MAX_ORDER_USD`
- `MAX_CONCURRENT_POSITIONS` aliases `LIVE_MAX_CONCURRENT_POSITIONS` and `LIVE_MAX_OPEN_POSITIONS`
- `MAX_SAME_MARKET_EXPOSURE` aliases `LIVE_MAX_SAME_MARKET_EXPOSURE`
- `MAX_DAILY_LOSS` aliases `LIVE_MAX_DAILY_LOSS`
- Stage 3 legacy uses `PAPER_STARTING_BALANCE` / `POLYBOT_PAPER_STARTING_BALANCE`
- Canonical paper path uses `PAPER_STARTING_CAPITAL_USD`

### Dangerous defaults

- `.env` auto-loading at import time [app/stage4/config.py:17](/Users/harel/Desktop/polybot/app/stage4/config.py:17)
- canonical start script defaults `LIVE_KILL_SWITCH=true` [scripts/start_runtime.ps1:16](/Users/harel/Desktop/polybot/scripts/start_runtime.ps1:16)
- DB is silently disabled outside canonical runtime because `POLYBOT_DATABASE_URL` is not in local `.env`

## J. Code Quality and Risk Audit

### Confirmed issues

1. Import-time env loading contaminates tests and runtime isolation
   - [app/stage4/config.py:14](/Users/harel/Desktop/polybot/app/stage4/config.py:14)
   - [app/stage4/config.py:17](/Users/harel/Desktop/polybot/app/stage4/config.py:17)
   - Impact: local `.env` values leak into tests and live-path behavior

2. Stage 4 tests are currently failing
   - `tests/test_stage4.py::test_auth_validation_flags_missing_wallet_requirements`
   - `tests/test_stage4.py::test_live_mode_submits_only_best_candidate_once`
   - `tests/test_stage4.py::test_live_mode_falls_back_when_top_candidate_fails_minimum_size`
   - Likely root cause: env bleed causing `LIVE_KILL_SWITCH` and wallet credentials to appear unexpectedly

3. Startup likely double-refreshes
   - first refresh in [app/main.py:46](/Users/harel/Desktop/polybot/app/main.py:46)
   - scheduler immediately refreshes again in [app/scheduler.py:31](/Users/harel/Desktop/polybot/app/scheduler.py:31)
   - Impact: duplicate load, duplicate writes, duplicate intelligence/paper cycles at startup

4. Legacy Stage 3 paper path has temporary exit logic
   - [app/stage3/paper_trader.py:345](/Users/harel/Desktop/polybot/app/stage3/paper_trader.py:345)
   - Impact: not valid for real execution correctness

5. Operator control surface is partly ceremonial
   - [app/services/operator_control.py:35](/Users/harel/Desktop/polybot/app/services/operator_control.py:35)
   - Impact: users may think controls exist when they only write audit rows

6. No real event bus
   - Impact: every downstream phase is coupled to one process and one refresh call

7. Paper/live confusion risk still exists
   - canonical runtime is safe-by-default
   - but Stage 4 settings, env aliases, and real credentials co-exist locally
   - brain/legacy operator flows can hit Stage 4 directly

8. No dedicated no-trade log
   - current evidence of non-entry is spread across `paper_signals`, `rejection_ledger`, ranking policy candidates, and trade classifications

9. Orchestration phase is not wired into canonical runtime
   - command intents are generated
   - controlled orchestration service exists
   - no runtime call from `RuntimePaperTradingService.process_cycle()`

10. Legacy dual-database paper architecture
   - Postgres canonical paper path
   - SQLite legacy Stage 3 path
   - Impact: truth fragmentation

### Test result summary

`python -m uv run pytest`

- Collected: `306`
- Passed: `61`
- Failed: `3`
- Skipped: `245`

Interpretation:

- base unit scaffolding exists
- a large portion of tests are skip-gated
- Stage 4 has real correctness regressions right now

## K. Architecture Fit Score

| Component | Score | Current reality |
|---|---|---|
| Scanner | GREEN | Gamma fetch + scoring + refresh loop work |
| Market Data | GREEN | real Gamma ingestion and snapshots |
| Orderbook | YELLOW | used ad hoc through Stage 4 client, not persisted as a feed |
| Rules / Wording | RED | no real resolution wording ingestion |
| News | YELLOW | real ingestion path exists |
| Social | GREY | not started |
| Whales | YELLOW | real scoring path exists, not full runtime engine |
| Signals | GREEN | canonical paper signal path is real |
| Opportunity Score | GREEN | deterministic scorer is solid |
| Strategy Router | RED | no target engine router; only trade classification |
| Capital Allocator | YELLOW | paper allocator exists, broader allocator does not |
| Risk Gate | GREEN | Stage 4 policy + guard are real |
| Risk Governor | YELLOW | live cage exists, not system-wide governor |
| Execution Cortex | YELLOW | paper strong, live partial |
| Exit Cortex | YELLOW | invalidation + advisory + command intent layers exist |
| Paper Trading | GREEN | canonical Postgres path exists |
| Live Trading | RED | partial implementation, failing tests, env fragility |
| Market Memory | GREEN | large durable schema exists |
| Feedback Learning | RED | no learning loop, only persistence loop |
| Observability | YELLOW | dashboard/query truth exists, metrics stack weak |
| Dashboard | YELLOW | real data, but minimal shell and no controls |
| Compliance Guard | RED | no standalone module |
| State Control / Modes | RED | only coarse `LISTEN_ONLY`/`PAPER`/`LIVE` mapping |
| Kill Switch | YELLOW | env kill switch + live-cage override exist |
| No Trade Log | RED | no dedicated subsystem |
| Tests | YELLOW | decent breadth, many skipped, live path failing |
| Docker Runtime | RED | only Grafana compose in repo |
| Database Schema | GREEN | richest part of the system |
| Event Bus | RED | absent |

## L. Target vs Current Gap Analysis

| Target Component | Current Implementation | Status | Gap | Priority |
|---|---|---|---|---|
| Market Scanner | `GammaClient` + `MarketService.refresh()` | GOOD | none at base level | High keep |
| Event Bus | none | MISSING | add real async bus / work queue later | High |
| Neural Mesh | none | NOT STARTED | only deterministic scoring + optional Anthropic digest | Medium |
| Market Memory | Postgres phase schema | GOOD | unify around it and remove split truth | High |
| Context Brain | phase 3/4 cognition services exist but not fully canonical | PARTIAL | wire phase 3 cognition path into runtime or retire | High |
| Opportunity Cortex | deterministic ranking + ranking_v2/policy | PARTIAL | not yet architecture-separated, but substantial | High |
| Strategy Router | trade classification only | PARTIAL | no SAFE/STRIKE/etc engines | High |
| Capital Allocator | paper allocator + bucket allocation | PARTIAL | unify per-mode allocation truth | High |
| Risk Gate | Stage 4 policy/guard | GOOD | extend beyond execution path | High |
| Risk Governor | live cage only | PARTIAL | add cross-mode governor and mode/state semantics | High |
| Execution Cortex | paper/shadow/live services | PARTIAL | live correctness and orchestration incomplete | High |
| Exit Cortex | invalidation/advisory/resolution/intents | PARTIAL | add actual orchestration and settlement correctness | High |
| Feedback / Learning Loop | DB persistence only | WEAK | no learning model or adaptive tuning loop | Medium |
| Dashboard / Observability | real DB query dashboard | PARTIAL | enrich truth, add control safety, add metrics | High |
| Compliance / Rules Guard | not a standalone layer | MISSING | add rules/wording/compliance checks | High |

## M. API/UI Truth Map

### Real vs fake summary

- Real:
  - market endpoints
  - dashboard API panels
  - alerts listing
  - Telegram status commands
  - `/kill` and `/resume` audit rows affecting live cage reads

- Partial:
  - Telegram operator controls
  - live readiness representation
  - intelligence influence on current trade context

- Broken:
  - none in the UI shell itself, but the app is not currently running on port `8000`
  - Stage 4 execution correctness is broken at test level

- Dangerous:
  - any operator assumption that `/pause` changes runtime state
  - any assumption that live path is production-safe because real credentials are present

## N. Risk Register

| Severity | Risk | Why it matters |
|---|---|---|
| Critical | Import-time `.env` loading leaks secrets/config into tests and live behavior | causes non-deterministic safety behavior and failing tests |
| Critical | Real secrets are present locally in `.env` | accidental live misuse risk |
| Critical | Live path failing tests | cannot trust live execution semantics |
| High | No dedicated no-trade truth layer | violates core principle that NO_TRADE is a first-class decision |
| High | Double refresh at startup | duplicate writes and duplicate downstream actions |
| High | Legacy SQLite and canonical Postgres paper systems coexist | split truth and operator confusion |
| High | Controlled orchestration not wired into canonical runtime | action staging ends before controlled execution seam |
| High | No rules/wording ingestion | prediction market execution can ignore actual resolution criteria |
| Medium | No real event bus | limits 24/7 resilience and recoverability |
| Medium | Dashboard is read-only JSON shell | observability exists but operator ergonomics are weak |

## O. Build Continuation Plan

This is a continuation plan from the existing system, not a rewrite plan.

### Immediate stabilization

- Freeze the canonical path around `app/main.py`, `MarketService`, Postgres schema, and dashboard query layer
- Remove env leakage from Stage 4 config behavior before touching live logic
- Make tests deterministic

### Architecture alignment

- Treat Postgres as the current memory backbone
- Explicitly map each phase service to target architecture names
- Add a dedicated system mode/state model without replacing current services

### Data truth layer

- Promote one canonical truth per surface:
  - market truth: `market_snapshots` / `ranking_snapshots`
  - paper truth: `paper_*`
  - shadow truth: `shadow_*`
  - live truth: `live_orders` / `positions`
  - intelligence truth: `external_*`, `whale_*`, `cognition_*`
- quarantine Stage 3 SQLite path as legacy

### Paper trading correctness

- keep current Postgres paper engine
- strengthen its fill simulation assumptions
- make no-trade and blocked-trade reasoning explicit and queryable

### Risk / exit correctness

- keep phase 8 tables
- wire orchestration phase after command intent staging
- ensure exits have explicit execution state transitions

### Neural modules expansion

- do not add “neural mesh” abstractions until phase 3/4/5 data truth is stable
- expand from current cognition/news/whale tables instead of adding a parallel memory layer

### Live-readiness later

- only after:
  - Stage 4 tests are green
  - env isolation is fixed
  - live execution memory is reconciled
  - operator controls are explicit and verified

## P. Exact Next 10 Actions

| # | Objective | Files likely involved | Expected output | Test command | Definition of done |
|---|---|---|---|---|---|
| 1 | Remove import-time Stage 4 env contamination | `app/stage4/config.py`, `app/env_runtime.py`, `tests/test_stage4.py`, `tests/test_env_runtime.py` | deterministic settings resolution | `python -m uv run pytest tests/test_stage4.py tests/test_env_runtime.py` | Stage 4 settings no longer inherit hidden `.env` state during tests |
| 2 | Make Stage 4 failing tests green without loosening safety | `app/stage4/auth.py`, `app/stage4/config.py`, `brain.py`, `tests/test_stage4.py` | passing Stage 4 auth/live selection tests | `python -m uv run pytest tests/test_stage4.py -q` | all current Stage 4 tests pass |
| 3 | Stop duplicate startup refreshes | `app/main.py`, `app/scheduler.py`, `tests/test_market_service.py` | one initial refresh per boot | `python -m uv run pytest tests/test_market_service.py -q` | boot path performs a single intended first-cycle refresh |
| 4 | Declare one canonical paper truth and deprecate legacy Stage 3 runtime path | `README.md`, `docs/runtime_canonical.md`, `brain.py`, `app/stage3/*` | operator-visible separation of legacy vs canonical | `python -m uv run pytest tests/test_stage3.py tests/test_phase2_execution_aware_paper.py -q` | docs and code comments clearly mark SQLite Stage 3 as legacy |
| 5 | Add dedicated no-trade ledger/truth view on top of existing decisions | likely `app/db/migrations/*`, `app/services/trade_classification.py`, `app/services/query/operator_dashboard_query_service.py` | explicit NO_TRADE storage/query path | `python -m uv run pytest tests/test_phase6a_trade_classification.py tests/test_phase9_dashboard_telegram.py -q` | no-trade outcomes are queryable without inference from multiple tables |
| 6 | Wire controlled orchestration after command intent staging in canonical runtime | `app/services/runtime_paper_trading.py`, `app/services/controlled_orchestration_gate.py`, query services/tests | phase 9 tables populated from runtime cycles | `python -m uv run pytest tests/test_phase8d_command_intent_staging.py tests/test_phase9a_controlled_orchestration_gate.py -q` | canonical runtime calls orchestration gate when command intents are produced |
| 7 | Add explicit market rules / wording ingestion seam | new phase service + schema around current market snapshots | persisted rules/criteria truth linked to markets | `python -m uv run pytest` targeted new tests | each tradable market can carry rules text / resolution criteria context |
| 8 | Tighten live-vs-paper boundary and operator controls | `app/services/operator_control.py`, `app/services/live_runtime.py`, `app/services/telegram_bot.py`, dashboard query service | unambiguous runtime control semantics | `python -m uv run pytest tests/test_phase9_dashboard_telegram.py tests/test_stage4.py -q` | `/pause`, `/kill`, `/resume` semantics are explicit, tested, and reflected in health views |
| 9 | Add queue/event-bus design seam without replacing Postgres memory | likely new `app/bus/` package plus runtime integration | minimal durable event contract for cycle fan-out | targeted new tests | market refresh can emit typed events rather than directly calling every downstream service |
| 10 | Create live-readiness certification checklist from current code paths | `docs/`, `README.md`, tests around live runtime and execution memory | concrete go/no-go checklist | `python -m uv run pytest tests/test_stage4.py tests/test_phase2_shadow_live.py -q` | live path cannot be considered ready unless checklist is satisfied and green |

## Q. Verification Commands

### Install dependencies

```powershell
python -m uv sync --extra dev
```

### Run migrations against canonical local runtime DB

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1
```

### Start canonical runtime

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1
```

### Smoke-check runtime

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_runtime.ps1
```

### Run tests

```powershell
python -m uv run pytest
python -m uv run pytest tests\test_stage4.py -q
```

### Inspect Postgres tables

```powershell
python -m uv run python -c "import os, psycopg; conn=psycopg.connect('postgresql://polybot:polybot@127.0.0.1:55432/polybot'); cur=conn.cursor(); cur.execute(\"select table_name from information_schema.tables where table_schema='public' order by table_name\"); print([r[0] for r in cur.fetchall()])"
```

### Inspect local SQLite legacy paper DB

```powershell
python -m uv run python -c "import sqlite3; c=sqlite3.connect('logs/paper_trading.db'); print(c.execute(\"select name from sqlite_master where type='table' order by name\").fetchall())"
```

### Inspect Docker containers

```powershell
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
```

### Inspect Redis presence on host

```powershell
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}" | Select-String redis
```

### Confirm app health when running

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/health
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/overview
```

### Confirm ports

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
Get-NetTCPConnection -LocalPort 55432 -State Listen
```

## R. Current Reality Conclusion

POLYBOT already has a substantial durable architecture, but the durable architecture is the Postgres phase schema and the synchronous runtime fan-out, not the target named components yet. The codebase should be continued from its current strengths:

- the canonical FastAPI runtime
- the rich Postgres memory model
- the canonical Postgres paper execution path
- the real dashboard query layer
- the existing invalidation/advisory/command-intent phases

It should not be reframed as if the missing event bus, mode governor, rules ingestion, strategy engines, and compliance guard already exist. They do not.

The most important truth is this:

- current POLYBOT is a functioning scanner-plus-persistence-plus-paper-intelligence runtime
- not yet a fully adaptive 24/7 asymmetric money engine
- and definitely not yet safe to treat as live-ready without stabilization
