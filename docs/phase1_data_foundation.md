# POLYBOT Phase 1: Data Foundation Build Package

## A. Executive Assessment

### What is strong

- The current runtime already has a real, verified execution spine: ingestion -> scoring -> Claude recommendation -> adaptive universe filtering -> ranking -> safety policy -> order intent -> live submission. Phase 1 does not need to invent a new operating model.
- The system already has typed domain models in `app.models`, deterministic ranking logic in `app.stage4.ranking`, and a known cycle orchestrator in `brain.py`. That is enough structure to add durable memory cleanly.
- Raw logging already exists in ad hoc form (`logs/scan_*.json`, `logs/ai_recommendations.jsonl`). That proves the operational need for persistence and gives us immediate artifact sources to formalize.
- Stage 3 already introduced the concept of a session-backed persistence layer. The design is too shallow, but the repo has already accepted the idea that the bot writes durable state.

### What is missing

- There is no root execution entity. Right now the runtime has a conceptual "cycle" but no persisted cycle identity. Without that, replay and audit remain weak.
- There is no canonical separation between:
  - raw ingest truth
  - normalized snapshot truth
  - ranking truth
  - decision truth
  - execution truth
  - artifact truth
- There is no immutable decision ledger. The live path currently prints reasons to terminal, but a future operator cannot reconstruct why a candidate was selected or skipped.
- There is no order state history. A single `live_orders` table is not enough if status changes over time.
- There is no position lifecycle contract for live trading. Phase 4 currently validates submission, but durable position semantics are not yet first-class.
- There is no schema/version discipline. That becomes dangerous the moment replay and ML are future requirements.

### What is weak in the current Phase 1 requirement

- `market_snapshots` as stated is underspecified without a cycle anchor. Timestamp alone is not sufficient for audit-grade replay because one cycle evaluates a set of markets together.
- `ranking_snapshots` needs both candidate inputs and rejection reasons. If rejection reasons are only stored inside `decision_ledger`, ranking becomes ambiguous for non-selected markets.
- `positions` without `position_events` is not enough, but you already included `position_events`; that is correct. The weak part is that position state transitions must be event-sourced enough to reconstruct state.
- `news_events` and `whale_profiles` are strategically correct but can become Phase 1 drag if they are treated as fully operational subsystems now. The storage contracts should exist; the ingestion logic should wait.

### Architectural risks

- If Phase 1 is implemented by extending Stage 3 SQLite helpers, the system will ossify into a local toy database with poor concurrency, weak JSON handling, weak indexing, and painful migration paths.
- If raw payloads are only saved to files and not registered in the database, replay will be fragmented and brittle.
- If recorder writes are scattered across the codepath without one persistence boundary, partial-write behavior will become nondeterministic.
- If Claude output is stored only as free text, explainability will degrade. We need structured recommendation and ranking payloads, not just a rendered reason string.
- If order submission and recording are not transactionally coordinated, the system can place real orders that the database does not know about. That is an operationally unacceptable gap.

### Hidden dependencies

- A persistent cycle id must be created before any market/ranking/decision write.
- Order persistence depends on stable external identifiers: exchange order id, market id, token id, and request correlation id.
- Position persistence depends on a clear rule for when a submitted order creates, updates, or closes a position.
- Artifact persistence depends on a path convention and content-addressability or deduplication policy.
- PostgreSQL migrations and connection management must exist before any serious Phase 1 recorder implementation lands.

### What to build first

- First build the cycle backbone, canonical market snapshots, ranking snapshots, and decision ledger.
- Second build live order memory and order status history.
- Third build positions and position events.
- Fourth add artifact registry and replay hooks.
- Fifth add intelligence-memory tables as dormant foundations with minimal writes only when real producers exist.

### What to delay

- Delay whale scoring logic, whale profiling logic, and sophisticated news-linking heuristics.
- Delay feature-store shaping, embeddings, ML feature extraction, and denormalized analytics marts.
- Delay operator UI. Phase 1 needs durable truth first.

## B. Phase 1 Architecture

Phase 1 should use a layered persistence architecture with strict write boundaries.

### 1. Raw ingest persistence

Purpose:
- Preserve source truth exactly as received.
- Support replay, parser debugging, and future re-normalization.

Scope:
- raw Gamma event payload batches
- raw market payloads when needed
- raw Claude request/response envelopes
- raw execution request/response envelopes
- raw external intelligence payloads later

Storage pattern:
- Artifact files on disk in structured paths
- Database registry row referencing artifact path, checksum, mime type, entity scope

Why boundary matters:
- Raw truth must remain immutable and separate from normalized truth so parsing bugs can be corrected without losing source evidence.

### 2. Canonical snapshots

Purpose:
- Store normalized, queryable state of markets at the time of a cycle.

Scope:
- cycle
- market_snapshots
- ranking_snapshots

Why boundary matters:
- Snapshot tables answer operational questions quickly without reparsing JSON artifacts.

### 3. Decision memory

Purpose:
- Persist the bot’s explainable choices and rejections.

Scope:
- decision_ledger
- optional rejection_ledger only if rejection volume becomes operationally noisy

Why boundary matters:
- Ranking and decision are not the same thing. Ranking says "how candidates compared." Decision says "what we did and why."

### 4. Execution memory

Purpose:
- Persist all external trading interactions and their lifecycle.

Scope:
- live_orders
- order_status_history
- positions
- position_events

Why boundary matters:
- Execution state changes after initial submission. A single mutable row is not sufficient for audit or reconciliation.

### 5. Intelligence memory

Purpose:
- Persist external informational inputs in a future-safe way without entangling them with execution truth.

Scope:
- news_events
- market_event_links
- whale_events
- whale_profiles

Why boundary matters:
- Intelligence data has a different trust model, cadence, and schema volatility than market/execution data.

### 6. Artifact persistence

Purpose:
- Persist supporting files and payload blobs referenced by all other layers.

Scope:
- cycle-level raw payload files
- request/response debug files
- submission bodies
- replay bundles

Why boundary matters:
- Large payloads should not bloat hot relational tables, but they must remain discoverable from the database.

## C. Mandatory Core Entities

### Additional root entity: `cycles`

Required: yes.

Reason:
- Every persisted record in Phase 1 hangs off a runtime evaluation cycle.
- Without `cycles`, you cannot replay the bot’s observation and decision timeline coherently.

### Additional table decisions

#### `order_status_history`

Required: yes.

Reason:
- `live_orders.status` is current state.
- `order_status_history` is the audit trail.

#### `run_artifacts`

Required: yes.

Reason:
- Raw JSONL logs and payload files must be queryable and attached to cycles/orders/decisions.

#### `schema_versions`

Do not implement as an app table if a proper migration framework is used.

Reason:
- The migration tool already owns schema versioning. Duplicating that in a table is noise unless the repo lacks migration discipline entirely.

#### `source_registry`

Phase 1 optional.

Reason:
- Useful for intelligence feeds, but not required to land core memory.

#### `ingestion_runs`

Implement as part of `cycles`, not a separate table for now.

Reason:
- Right now one runtime cycle already is the ingest/rank/decision run. Splitting that early is unnecessary bloat.

#### `rejection_ledger`

Do not create a separate table now.

Reason:
- Rejections belong in `decision_ledger` with `decision_type='SKIP'` or `selected=false`.
- Separate rejection tables usually create double bookkeeping.

## D. Full Database Schema Spec

PostgreSQL-oriented. Timestamps should be `TIMESTAMPTZ`. Flexible payloads should be `JSONB`. Monetary and price values should use `NUMERIC`, not float.

### Core now

#### `cycles`

Purpose:
- Root runtime unit for one end-to-end evaluation and optional submission attempt.

Columns:
- `id UUID NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `completed_at TIMESTAMPTZ NULL`
- `status TEXT NOT NULL`
- `mode TEXT NOT NULL`
- `trigger_source TEXT NOT NULL`
- `session_id TEXT NULL`
- `top_n INTEGER NOT NULL`
- `pages_requested INTEGER NULL`
- `markets_fetched_count INTEGER NOT NULL DEFAULT 0`
- `markets_scored_count INTEGER NOT NULL DEFAULT 0`
- `markets_ranked_count INTEGER NOT NULL DEFAULT 0`
- `decisions_count INTEGER NOT NULL DEFAULT 0`
- `selected_market_id TEXT NULL`
- `selected_decision_id UUID NULL`
- `error_count INTEGER NOT NULL DEFAULT 0`
- `last_error TEXT NULL`
- `runtime_ms INTEGER NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Indexes:
- `idx_cycles_started_at (started_at desc)`
- `idx_cycles_status_started_at (status, started_at desc)`
- `idx_cycles_selected_market_id (selected_market_id)`

Enums/code values:
- `status`: `OPEN`, `COMPLETED`, `FAILED`, `PARTIAL`
- `mode`: `SCAN_ONLY`, `PAPER`, `LIVE_DRY_RUN`, `LIVE_SUBMIT`

#### `market_snapshots`

Purpose:
- Canonical normalized market state at cycle time.

Columns:
- `id BIGSERIAL NOT NULL`
- `cycle_id UUID NOT NULL`
- `market_id TEXT NOT NULL`
- `event_id TEXT NULL`
- `question TEXT NOT NULL`
- `slug TEXT NULL`
- `captured_at TIMESTAMPTZ NOT NULL`
- `yes_price NUMERIC(10,6) NULL`
- `no_price NUMERIC(10,6) NULL`
- `last_trade_price NUMERIC(10,6) NULL`
- `best_bid NUMERIC(10,6) NULL`
- `best_ask NUMERIC(10,6) NULL`
- `spread NUMERIC(10,6) NULL`
- `tick_size NUMERIC(10,6) NULL`
- `liquidity NUMERIC(18,4) NULL`
- `volume NUMERIC(18,4) NULL`
- `volume_24h NUMERIC(18,4) NULL`
- `open_interest NUMERIC(18,4) NULL`
- `comment_count INTEGER NULL`
- `competitive NUMERIC(10,6) NULL`
- `neg_risk BOOLEAN NULL`
- `orderbook_enabled BOOLEAN NULL`
- `accepting_orders BOOLEAN NOT NULL DEFAULT false`
- `time_to_close_seconds INTEGER NULL`
- `raw_payload JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `cycle_id -> cycles(id)`

Unique constraints:
- `(cycle_id, market_id)`

Indexes:
- `idx_market_snapshots_cycle_id (cycle_id)`
- `idx_market_snapshots_market_id_captured_at (market_id, captured_at desc)`
- `idx_market_snapshots_question_gin` as full text only later if needed

#### `ranking_snapshots`

Purpose:
- Persist candidate ranking outputs and ranking breakdown for every evaluated market.

Columns:
- `id BIGSERIAL NOT NULL`
- `cycle_id UUID NOT NULL`
- `market_snapshot_id BIGINT NOT NULL`
- `market_id TEXT NOT NULL`
- `rank_position INTEGER NULL`
- `base_score NUMERIC(10,4) NULL`
- `adaptive_rank NUMERIC(10,4) NULL`
- `selected_flag BOOLEAN NOT NULL DEFAULT false`
- `eligible_flag BOOLEAN NOT NULL DEFAULT true`
- `reject_reason TEXT NULL`
- `ranking_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb`
- `recommendation_action TEXT NULL`
- `recommendation_confidence NUMERIC(10,6) NULL`
- `recommendation_reason TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `cycle_id -> cycles(id)`
- `market_snapshot_id -> market_snapshots(id)`

Unique constraints:
- `(cycle_id, market_id)`

Indexes:
- `idx_ranking_snapshots_cycle_id (cycle_id)`
- `idx_ranking_snapshots_market_id_created_at (market_id, created_at desc)`
- `idx_ranking_snapshots_selected_flag (selected_flag)`

Enums/code values:
- `recommendation_action`: `BUY_YES`, `BUY_NO`, `SKIP`

#### `decision_ledger`

Purpose:
- Immutable record of system decisions, including non-selection.

Columns:
- `id UUID NOT NULL`
- `cycle_id UUID NOT NULL`
- `market_snapshot_id BIGINT NOT NULL`
- `ranking_snapshot_id BIGINT NULL`
- `market_id TEXT NOT NULL`
- `decision_type TEXT NOT NULL`
- `selected BOOLEAN NOT NULL`
- `reason TEXT NOT NULL`
- `confidence NUMERIC(10,6) NULL`
- `trade_type TEXT NULL`
- `bucket_type TEXT NULL`
- `expected_edge_proxy NUMERIC(10,4) NULL`
- `invalidation_rules JSONB NOT NULL DEFAULT '{}'::jsonb`
- `policy_checks JSONB NOT NULL DEFAULT '{}'::jsonb`
- `execution_eligibility JSONB NOT NULL DEFAULT '{}'::jsonb`
- `artifacts JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `cycle_id -> cycles(id)`
- `market_snapshot_id -> market_snapshots(id)`
- `ranking_snapshot_id -> ranking_snapshots(id)`

Indexes:
- `idx_decision_ledger_cycle_id (cycle_id)`
- `idx_decision_ledger_market_id_created_at (market_id, created_at desc)`
- `idx_decision_ledger_selected_created_at (selected, created_at desc)`

Enums/code values:
- `decision_type`: `SELECT`, `SKIP`, `BLOCK`, `SUBMIT_ATTEMPT`, `NO_ACTION`

#### `live_orders`

Purpose:
- Current canonical order row per exchange/client order.

Columns:
- `id UUID NOT NULL`
- `cycle_id UUID NULL`
- `decision_id UUID NULL`
- `market_id TEXT NOT NULL`
- `position_id UUID NULL`
- `exchange_order_id TEXT NULL`
- `client_order_id TEXT NOT NULL`
- `token_id TEXT NOT NULL`
- `side TEXT NOT NULL`
- `action TEXT NOT NULL`
- `price NUMERIC(10,6) NOT NULL`
- `size NUMERIC(18,6) NOT NULL`
- `notional NUMERIC(18,6) NOT NULL`
- `status TEXT NOT NULL`
- `submission_mode TEXT NOT NULL`
- `submitted_at TIMESTAMPTZ NOT NULL`
- `last_status_at TIMESTAMPTZ NULL`
- `raw_request JSONB NOT NULL DEFAULT '{}'::jsonb`
- `raw_response JSONB NOT NULL DEFAULT '{}'::jsonb`
- `error_text TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `cycle_id -> cycles(id)`
- `decision_id -> decision_ledger(id)`
- `position_id -> positions(id)` deferred until positions exist

Unique constraints:
- `(client_order_id)`
- `(exchange_order_id)` where not null

Indexes:
- `idx_live_orders_market_id_submitted_at (market_id, submitted_at desc)`
- `idx_live_orders_status_submitted_at (status, submitted_at desc)`
- `idx_live_orders_decision_id (decision_id)`

Enums/code values:
- `side`: `BUY`, `SELL`
- `action`: `BUY_YES`, `BUY_NO`, `SELL_YES`, `SELL_NO`
- `status`: `CREATED`, `SUBMITTED`, `LIVE`, `FILLED`, `CANCELLED`, `REJECTED`, `ERROR`, `UNKNOWN`
- `submission_mode`: `DRY_RUN`, `LIVE`

#### `order_status_history`

Purpose:
- Append-only order lifecycle events.

Columns:
- `id BIGSERIAL NOT NULL`
- `order_id UUID NOT NULL`
- `exchange_order_id TEXT NULL`
- `status TEXT NOT NULL`
- `status_at TIMESTAMPTZ NOT NULL`
- `reason TEXT NULL`
- `raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `order_id -> live_orders(id)`

Indexes:
- `idx_order_status_history_order_id_status_at (order_id, status_at asc)`
- `idx_order_status_history_status_status_at (status, status_at desc)`

#### `positions`

Purpose:
- Current canonical position state per market-side thesis.

Columns:
- `id UUID NOT NULL`
- `market_id TEXT NOT NULL`
- `token_id TEXT NULL`
- `side TEXT NOT NULL`
- `status TEXT NOT NULL`
- `opened_at TIMESTAMPTZ NOT NULL`
- `closed_at TIMESTAMPTZ NULL`
- `size NUMERIC(18,6) NOT NULL DEFAULT 0`
- `avg_entry NUMERIC(10,6) NULL`
- `avg_exit NUMERIC(10,6) NULL`
- `realized_pnl NUMERIC(18,6) NOT NULL DEFAULT 0`
- `unrealized_pnl NUMERIC(18,6) NOT NULL DEFAULT 0`
- `thesis_state TEXT NOT NULL`
- `invalidation_state TEXT NOT NULL`
- `decision_id UUID NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `decision_id -> decision_ledger(id)`

Indexes:
- `idx_positions_market_id_status (market_id, status)`
- `idx_positions_opened_at (opened_at desc)`

Enums/code values:
- `side`: `YES`, `NO`
- `status`: `OPEN`, `PARTIALLY_CLOSED`, `CLOSED`, `INVALIDATED`
- `thesis_state`: `ACTIVE`, `WEAKENED`, `BROKEN`, `RESOLVED`
- `invalidation_state`: `NONE`, `WATCH`, `TRIGGERED`

#### `position_events`

Purpose:
- Append-only lifecycle stream for positions.

Columns:
- `id BIGSERIAL NOT NULL`
- `position_id UUID NOT NULL`
- `cycle_id UUID NULL`
- `order_id UUID NULL`
- `event_type TEXT NOT NULL`
- `event_at TIMESTAMPTZ NOT NULL`
- `reason TEXT NOT NULL`
- `details JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `position_id -> positions(id)`
- `cycle_id -> cycles(id)`
- `order_id -> live_orders(id)`

Indexes:
- `idx_position_events_position_id_event_at (position_id, event_at asc)`
- `idx_position_events_cycle_id (cycle_id)`

Enums/code values:
- `event_type`: `OPENED`, `INCREASED`, `DECREASED`, `MARKED`, `INVALIDATION_TRIGGERED`, `CLOSED`, `RECONCILED`

#### `run_artifacts`

Purpose:
- Registry of large payloads and structured files associated with runtime entities.

Columns:
- `id UUID NOT NULL`
- `cycle_id UUID NULL`
- `decision_id UUID NULL`
- `order_id UUID NULL`
- `artifact_type TEXT NOT NULL`
- `storage_kind TEXT NOT NULL`
- `relative_path TEXT NOT NULL`
- `content_sha256 TEXT NOT NULL`
- `mime_type TEXT NULL`
- `size_bytes BIGINT NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Foreign keys:
- `cycle_id -> cycles(id)`
- `decision_id -> decision_ledger(id)`
- `order_id -> live_orders(id)`

Unique constraints:
- `(content_sha256, relative_path)`

Indexes:
- `idx_run_artifacts_cycle_id (cycle_id)`
- `idx_run_artifacts_artifact_type_created_at (artifact_type, created_at desc)`

Enums/code values:
- `artifact_type`: `RAW_GAMMA_BATCH`, `RAW_CLAUDE_REQUEST`, `RAW_CLAUDE_RESPONSE`, `RAW_ORDER_REQUEST`, `RAW_ORDER_RESPONSE`, `CYCLE_SUMMARY`, `REPLAY_BUNDLE`
- `storage_kind`: `FILE`, `JSONL`

### Phase 1 optional

#### `news_events`

Purpose:
- Canonical external news/intelligence item store.

Columns:
- `id UUID NOT NULL`
- `source TEXT NOT NULL`
- `external_id TEXT NULL`
- `title TEXT NOT NULL`
- `url TEXT NOT NULL`
- `published_at TIMESTAMPTZ NOT NULL`
- `ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `summary TEXT NULL`
- `raw_content JSONB NOT NULL`
- `trust_score NUMERIC(10,6) NULL`
- `tags JSONB NOT NULL DEFAULT '[]'::jsonb`
- `entities JSONB NOT NULL DEFAULT '[]'::jsonb`

Primary key:
- `id`

Unique constraints:
- `(source, url)`

Indexes:
- `idx_news_events_published_at (published_at desc)`
- `idx_news_events_source_published_at (source, published_at desc)`

#### `market_event_links`

Purpose:
- Soft linkage between markets and intelligence events.

Columns:
- `id BIGSERIAL NOT NULL`
- `market_id TEXT NOT NULL`
- `news_event_id UUID NOT NULL`
- `relevance_score NUMERIC(10,6) NOT NULL`
- `directness TEXT NOT NULL`
- `contradiction_score NUMERIC(10,6) NULL`
- `linked_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

Primary key:
- `id`

Foreign keys:
- `news_event_id -> news_events(id)`

Unique constraints:
- `(market_id, news_event_id)`

Indexes:
- `idx_market_event_links_market_id (market_id)`
- `idx_market_event_links_news_event_id (news_event_id)`

#### `whale_events`

Purpose:
- Individual notable wallet actions.

Columns:
- `id UUID NOT NULL`
- `wallet TEXT NOT NULL`
- `market_id TEXT NOT NULL`
- `observed_at TIMESTAMPTZ NOT NULL`
- `side TEXT NOT NULL`
- `size NUMERIC(18,6) NOT NULL`
- `price NUMERIC(10,6) NULL`
- `transaction_reference TEXT NOT NULL`
- `raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `id`

Unique constraints:
- `(transaction_reference)`

Indexes:
- `idx_whale_events_wallet_observed_at (wallet, observed_at desc)`
- `idx_whale_events_market_id_observed_at (market_id, observed_at desc)`

#### `whale_profiles`

Purpose:
- Current rollup profile per wallet.

Columns:
- `wallet TEXT NOT NULL`
- `category TEXT NULL`
- `reliability_score NUMERIC(10,6) NULL`
- `historical_hit_rate NUMERIC(10,6) NULL`
- `average_hold_time_seconds INTEGER NULL`
- `specialization JSONB NOT NULL DEFAULT '[]'::jsonb`
- `last_seen TIMESTAMPTZ NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `wallet`

Indexes:
- `idx_whale_profiles_last_seen (last_seen desc)`

### Future-ready but do not implement yet

- Materialized views for analytics
- Feature tables for ML
- Embedding stores
- Cross-market relationship tables
- Actor/entity knowledge graph tables

## E. Domain Contracts

Contracts should be implemented as typed Python models in a dedicated contracts layer. They define what producers must emit before repositories persist anything.

### `CycleContract`

Required fields:
- `cycle_id`
- `started_at`
- `mode`
- `trigger_source`
- `session_id`
- `parameters`

Invariants:
- `cycle_id` immutable
- one cycle opens once and closes once
- `completed_at >= started_at` when present

Ownership:
- runtime orchestrator

Producer:
- `brain.py` cycle runner or a new orchestration service wrapping it

Consumers:
- snapshot recorders
- decision recorder
- execution recorder
- replay engine

Failure handling:
- if cycle open persisted but close fails, cycle remains `OPEN` or `PARTIAL` and is repairable

### `MarketSnapshotContract`

Required fields:
- `cycle_id`
- `market_id`
- `question`
- `captured_at`
- `accepting_orders`
- `raw_payload`

Invariants:
- one snapshot per market per cycle
- raw payload is required even if some normalized fields are null

Ownership:
- ingestion normalization layer

Producer:
- `MarketService` / Stage 1 normalization path

Consumers:
- ranking recorder
- replay engine
- analytics queries

Failure handling:
- invalid market payload should be skipped with cycle-level error count increment and optional artifact reference

### `RankingSnapshotContract`

Required fields:
- `cycle_id`
- `market_id`
- `base_score`
- `adaptive_rank` or `eligible_flag=false`
- `ranking_breakdown`

Invariants:
- every market that reaches ranking stage gets exactly one ranking snapshot per cycle
- selected candidate must have `selected_flag=true`

Ownership:
- ranking engine

Producer:
- Stage 1 scorer + Stage 2 recommendation + Stage 4 ranker integration

Consumers:
- decision recorder
- replay engine
- operator audit

Failure handling:
- markets excluded before ranking should either be absent from ranking or recorded with `eligible_flag=false`; choose one convention and keep it strict. Recommendation: record eligible-universe outcomes only, and let decision ledger capture skips/blocks.

### `DecisionContract`

Required fields:
- `decision_id`
- `cycle_id`
- `market_id`
- `decision_type`
- `selected`
- `reason`

Invariants:
- exactly one terminal selection decision per cycle at most
- skip/block decisions must include machine-readable policy or rejection detail

Ownership:
- execution orchestrator

Producer:
- Stage 4 selection and safety path

Consumers:
- order recorder
- replay engine
- future dashboard

Failure handling:
- if decision persistence fails, order submission must not proceed in live mode

### `OrderContract`

Required fields:
- `order_id`
- `client_order_id`
- `market_id`
- `token_id`
- `side`
- `action`
- `price`
- `size`
- `notional`
- `submission_mode`
- `submitted_at`

Invariants:
- client order id unique
- every live submission attempt writes an order row before external submit or at minimum in the same operation boundary with a durable recovery artifact

Ownership:
- execution service

Producer:
- Stage 4 execution client wrapper

Consumers:
- reconciliation
- replay engine
- position service

Failure handling:
- if exchange submit succeeds but DB write fails, system must emit a durable emergency artifact and mark cycle `PARTIAL`

### `PositionLifecycleContract`

Required fields:
- `position_id`
- `market_id`
- `side`
- `status`
- `opened_at`

Invariants:
- current row reflects latest state
- every state change also emits a position event
- size cannot be negative

Ownership:
- execution/portfolio service

Producer:
- order fill/reconciliation logic

Consumers:
- dashboard
- replay engine
- exit engine later

Failure handling:
- if current-state update fails after event insert, transaction must roll back

### `PositionEventContract`

Required fields:
- `position_id`
- `event_type`
- `event_at`
- `reason`
- `details`

Invariants:
- append-only
- event order per position is time-consistent

Ownership:
- position service

Producer:
- position manager

Consumers:
- replay engine
- audit

Failure handling:
- no silent drops; if event write fails, enclosing position mutation fails

### `IntelligenceEventContract`

Required fields:
- `source`
- `title`
- `url`
- `published_at`
- `raw_content`

Invariants:
- dedupe by source/url or source/external id

Ownership:
- future intelligence ingest services

Producer:
- external news/whale ingestors

Consumers:
- ranking engine v2
- whale subsystem
- replay

Failure handling:
- ingestion can fail independently; it must not block core cycle execution in Phase 1

## F. Implementation Order

### Subphase 1A: Cycle backbone and PostgreSQL foundation

Goal:
- Add migration framework, DB config, `cycles`, and `run_artifacts`.

Likely files/modules:
- `app/db/config.py`
- `app/db/connection.py`
- `app/db/migrations/...`
- `app/domain/contracts/cycle.py`
- `app/repositories/cycle_repository.py`
- `app/services/recorders/cycle_recorder.py`
- `app/services/artifacts/artifact_store.py`

Services impacted:
- `brain.py`

Migrations required:
- create `cycles`
- create `run_artifacts`

Risks:
- dependency introduction for PostgreSQL driver and migration tool
- cycle id plumbing through current runtime

Definition of done:
- every runtime cycle creates and closes a `cycles` row
- raw cycle artifacts can be registered

### Subphase 1B: Market, ranking, and decision memory

Goal:
- Persist canonical market snapshots, ranking snapshots, and decision ledger entries for one cycle.

Likely files/modules:
- `app/domain/contracts/market_snapshot.py`
- `app/domain/contracts/ranking_snapshot.py`
- `app/domain/contracts/decision.py`
- `app/repositories/market_snapshot_repository.py`
- `app/repositories/ranking_snapshot_repository.py`
- `app/repositories/decision_repository.py`
- `app/services/recorders/market_snapshot_recorder.py`
- `app/services/recorders/ranking_recorder.py`
- `app/services/recorders/decision_recorder.py`

Services impacted:
- `app.ingestion.market_service`
- `brain.py`
- `app.stage4.universe`
- `app.stage4.ranking`
- `app.stage4.execution_policy`

Migrations required:
- create `market_snapshots`
- create `ranking_snapshots`
- create `decision_ledger`

Risks:
- mapping ranked candidate data back to source market snapshots
- deciding exact rejection recording semantics

Definition of done:
- every selected and non-selected market in the adaptive universe is explainable from DB rows

### Subphase 1C: Execution memory

Goal:
- Persist order attempts, status history, and minimal current positions.

Likely files/modules:
- `app/domain/contracts/order.py`
- `app/domain/contracts/position.py`
- `app/domain/contracts/position_event.py`
- `app/repositories/order_repository.py`
- `app/repositories/position_repository.py`
- `app/services/recorders/order_recorder.py`
- `app/services/recorders/position_recorder.py`
- `app/services/execution/reconciliation.py`

Services impacted:
- `app.stage4.execution_client`
- `brain.py`

Migrations required:
- create `live_orders`
- create `order_status_history`
- create `positions`
- create `position_events`

Risks:
- exchange submit / DB write recovery gap
- unclear fill semantics if only order acceptance is available

Definition of done:
- every live or dry-run submission attempt is durably recorded
- order status transitions are queryable

### Subphase 1D: Intelligence memory foundations

Goal:
- Add passive intelligence tables without making them mandatory runtime dependencies.

Likely files/modules:
- `app/domain/contracts/intelligence.py`
- `app/repositories/news_repository.py`
- `app/repositories/whale_repository.py`

Services impacted:
- none in critical path yet

Migrations required:
- create `news_events`
- create `market_event_links`
- create `whale_events`
- create `whale_profiles`

Risks:
- premature producer complexity

Definition of done:
- tables and repository contracts exist, but core runtime does not depend on them

### Subphase 1E: Artifacts and replay hooks

Goal:
- Add basic replay read service for a single cycle timeline.

Likely files/modules:
- `app/services/replay/basic_replay.py`
- `app/repositories/replay_repository.py`

Services impacted:
- none on hot path

Migrations required:
- no new mandatory tables beyond `run_artifacts`

Risks:
- replay can become coupled to transient runtime objects if contracts are weak

Definition of done:
- operator can reconstruct a cycle timeline from DB + artifacts

### Subphase 1F: Tests and verification

Goal:
- Prove persistence correctness, idempotency, and partial failure behavior.

Likely files/modules:
- `tests/test_phase1_migrations.py`
- `tests/test_cycle_recorder.py`
- `tests/test_market_snapshot_recorder.py`
- `tests/test_decision_recorder.py`
- `tests/test_order_recorder.py`
- `tests/test_basic_replay.py`

Services impacted:
- CI/test harness

Migrations required:
- none

Risks:
- inadequate failure injection

Definition of done:
- GREEN validation achieved against measurable criteria in section K

## G. Repository and Folder Structure

Recommended extension of current repo, not a rewrite:

- `app/db/`
- `app/db/migrations/`
- `app/domain/contracts/`
- `app/domain/enums/`
- `app/repositories/`
- `app/services/recorders/`
- `app/services/artifacts/`
- `app/services/replay/`
- `app/services/persistence/`
- `tests/persistence/`
- `tests/replay/`
- `artifacts/`
- `docs/`

Guidance:
- Keep execution logic in `app/stage4`.
- Do not bury persistence inside `stage3/database.py`; that file is a local paper-trading helper, not the platform data layer.
- The new persistence layer should be stage-agnostic because it will serve later phases too.

## H. Modules and Files to Build

Concrete implementation-oriented file list:

- `app/db/config.py`
- `app/db/connection.py`
- `app/db/migrations/0001_phase1_cycles.sql`
- `app/db/migrations/0002_phase1_market_ranking_decisions.sql`
- `app/db/migrations/0003_phase1_execution_memory.sql`
- `app/db/migrations/0004_phase1_intelligence_foundations.sql`
- `app/domain/contracts/cycle.py`
- `app/domain/contracts/market_snapshot.py`
- `app/domain/contracts/ranking_snapshot.py`
- `app/domain/contracts/decision.py`
- `app/domain/contracts/order.py`
- `app/domain/contracts/position.py`
- `app/domain/contracts/position_event.py`
- `app/domain/contracts/intelligence.py`
- `app/domain/enums/persistence.py`
- `app/repositories/base.py`
- `app/repositories/cycle_repository.py`
- `app/repositories/market_snapshot_repository.py`
- `app/repositories/ranking_snapshot_repository.py`
- `app/repositories/decision_repository.py`
- `app/repositories/order_repository.py`
- `app/repositories/position_repository.py`
- `app/repositories/artifact_repository.py`
- `app/repositories/replay_repository.py`
- `app/services/artifacts/file_artifact_store.py`
- `app/services/recorders/cycle_recorder.py`
- `app/services/recorders/market_snapshot_recorder.py`
- `app/services/recorders/ranking_recorder.py`
- `app/services/recorders/decision_recorder.py`
- `app/services/recorders/order_recorder.py`
- `app/services/recorders/position_recorder.py`
- `app/services/persistence/unit_of_work.py`
- `app/services/replay/basic_replay.py`
- `tests/persistence/test_migrations.py`
- `tests/persistence/test_cycle_recorder.py`
- `tests/persistence/test_market_snapshot_recorder.py`
- `tests/persistence/test_ranking_and_decision_recorders.py`
- `tests/persistence/test_order_recorder.py`
- `tests/replay/test_basic_replay.py`
- `brain.py`
- `pyproject.toml`
- `README.md`

## I. Write Path Design

### Normal runtime write order

1. Cycle opens.
2. Raw ingest artifact is written and registered.
3. Canonical `market_snapshots` are bulk inserted for the cycle.
4. Ranking outputs are bulk inserted into `ranking_snapshots`.
5. Decision rows are inserted into `decision_ledger`.
6. If no executable candidate exists, cycle closes as `COMPLETED`.
7. If executable candidate exists:
8. Order attempt row is created with status `CREATED` or `SUBMITTED_PENDING`.
9. Raw order request artifact is written and registered.
10. Exchange submission happens.
11. `live_orders` current row is updated with exchange identifiers and current status.
12. `order_status_history` append row is inserted.
13. If position state changes can be inferred, `positions` and `position_events` are updated in the same transaction.
14. Raw order response artifact is written and registered.
15. Cycle summary artifact is written and cycle closes.

### Failure behavior

#### If order submission succeeds but recorder fails

- This is the most dangerous failure.
- Required behavior:
  - write emergency artifact locally with request/response and correlation ids
  - mark process error loudly
  - mark cycle `PARTIAL`
  - retry DB reconciliation on next startup or explicit repair tool
- In live mode, this must page the operator eventually; silent tolerance is unacceptable.

#### If ranking exists but cycle close fails

- Acceptable partial state.
- Recovery path:
  - cycle remains `OPEN`
  - repair job or next startup can mark stale open cycles as `PARTIAL` or close them if all child writes exist

#### If raw artifact writing fails

- Do not block core decision persistence for non-critical artifacts.
- Persist a `run_artifacts` failure marker in metadata if DB is available.
- For order request/response artifacts in live mode, treat as high severity but not necessarily submission-blocking if DB write succeeds.

#### Idempotency expectations

- Cycle open is not idempotent by natural key; it creates a new cycle each run.
- Market snapshots are idempotent by `(cycle_id, market_id)`.
- Ranking snapshots are idempotent by `(cycle_id, market_id)`.
- Order writes are idempotent by `client_order_id`.
- Order status history can accept duplicate external statuses only if deduped by `(order_id, status, status_at)` or equivalent application logic.

#### Retry rules

- DB transient failures during snapshot insert: retry with bounded backoff before abandoning cycle.
- External exchange submit: do not blindly retry unless client order id semantics are well understood and dedupe-safe.
- Artifact writes: one immediate retry, then mark failure and continue where safe.

#### Partial write tolerance

- Snapshot/ranking/decision writes should happen in DB transactions grouped by phase.
- Order and position writes should happen in a transaction after external response is known, except for the minimal pre-submit order-attempt record if you implement it.

## J. Query and Replay Read Paths

Minimum supported read paths:

### Show all markets evaluated in cycle X

Pattern:
- `cycles -> market_snapshots`

### Show selected and rejected markets in cycle X

Pattern:
- `decision_ledger where cycle_id = ?`
- join `market_snapshots`
- join `ranking_snapshots` optionally

### Show reasoning breakdown for decision X

Pattern:
- `decision_ledger`
- left join `ranking_snapshots`
- fetch linked artifacts

### Show order history for market X

Pattern:
- `live_orders where market_id = ?`
- join `order_status_history`

### Show position lifecycle for position X

Pattern:
- `positions`
- join `position_events`
- optional linked `live_orders`

### Replay a cycle timeline

Pattern:
- `cycles`
- all `run_artifacts`
- ordered `market_snapshots`
- ordered `ranking_snapshots`
- ordered `decision_ledger`
- linked `live_orders`
- linked `order_status_history`

### Reconstruct decision inputs for a selected market

Pattern:
- selected `decision_ledger`
- linked `ranking_snapshot`
- linked `market_snapshot`
- linked raw Claude response artifact
- linked raw Gamma batch artifact

### Minimum repository/query interfaces

- `get_cycle(cycle_id)`
- `list_market_snapshots_for_cycle(cycle_id)`
- `list_rankings_for_cycle(cycle_id)`
- `list_decisions_for_cycle(cycle_id)`
- `list_orders_for_market(market_id)`
- `get_position_timeline(position_id)`
- `replay_cycle(cycle_id)`

## K. Test Plan

### Migration tests

- all migrations apply cleanly to empty database
- all migrations are repeat-safe where appropriate
- expected indexes and constraints exist

### Schema integrity tests

- foreign keys enforce parent-child ordering
- unique constraints prevent duplicate market snapshots and client orders
- enum/code constraints reject invalid statuses if implemented as checks

### Recorder unit tests

- cycle recorder opens/closes cycles correctly
- market snapshot recorder bulk inserts normalized markets with raw payloads
- ranking recorder persists breakdown payloads correctly
- decision recorder persists selected and skipped decisions
- order recorder persists request/response and status transitions

### Idempotency tests

- same `(cycle_id, market_id)` snapshot upsert does not duplicate
- same `client_order_id` does not duplicate orders
- status-history dedupe behavior matches contract

### Transaction boundary tests

- if ranking batch fails, no partial ranking rows remain
- if decision write fails, live submission is not attempted
- if position event write fails, position state update rolls back

### Replay smoke tests

- a completed test cycle can be replayed into a single ordered timeline
- replay can reconstruct selected market inputs and output reasoning

### End-to-end persistence tests

- one synthetic cycle writes cycle + market snapshots + rankings + decisions + artifacts
- one synthetic live submit path writes order + order status + cycle close

### Failure injection tests

- force artifact store failure
- force order repository failure after mocked successful exchange response
- force cycle close failure

### Validation states

#### GREEN

- all core migrations apply and rollback on test DB
- every runtime cycle persists `cycles`, `market_snapshots`, `ranking_snapshots`, and `decision_ledger`
- every submission attempt persists `live_orders` and `order_status_history`
- replay of a synthetic cycle reconstructs market inputs, ranking, decision, and order timeline
- failure injection tests show deterministic partial-state behavior

#### YELLOW

- core writes work, but one of the following remains weak:
  - replay incomplete
  - order recovery gap not covered by test
  - stale open cycle repair missing
  - artifact registry inconsistent

#### RED

- any selected market can be submitted without a persisted decision row
- any live order can exist without a durable order row or recovery artifact
- cycle replay cannot explain why a market was selected or skipped
- duplicate writes are possible without constraints

## L. Definition of Done

Phase 1 is done only when all of the following are true:

- Every runtime cycle creates a durable `cycles` row with open and close timestamps.
- Every market evaluated in that cycle has a durable canonical `market_snapshots` row.
- Every ranked candidate in the adaptive universe has a durable `ranking_snapshots` row with ranking breakdown.
- Every selected or skipped outcome that matters operationally has a durable `decision_ledger` row with explicit reason.
- Every live or dry-run order attempt has a durable `live_orders` row and at least one `order_status_history` row.
- Any current position state shown by the system is reconstructable from `positions` plus `position_events`.
- Raw source payloads for ingest, reasoning, and execution are durably registered via `run_artifacts`.
- A basic replay command can reconstruct one cycle timeline end-to-end from persisted data.
- Automated tests prove idempotency, transaction boundaries, and failure handling.
- There is evidence, not assertion: migration logs, test output, and a persisted sample cycle and sample submit path.

If any of those is missing, Phase 1 is not done.

## M. Build First

Build first:

### Minimal correct vertical slice

- Introduce PostgreSQL configuration and migration plumbing.
- Implement `cycles`, `market_snapshots`, `ranking_snapshots`, and `decision_ledger`.
- Thread a persisted `cycle_id` through `brain.py` for one runtime cycle.
- Persist:
  - cycle open
  - canonical market snapshots for analyzed markets
  - ranking snapshots for adaptive candidates
  - decision rows for selected and blocked/skipped candidates
  - cycle close
- Add one replay smoke test that reconstructs a cycle summary from those four tables.

Why this slice first:
- It creates memory for the exact part of the system that is already validated and strategically irreplaceable: adaptive selection.
- It avoids premature complexity in positions, whales, and news.
- It gives immediate operator value: explainability of selection and rejection.
- It becomes the foundation every later execution and intelligence table can hang off cleanly.

Do not start with whales.
Do not start with news.
Do not start with dashboard work.
Do not start with fills/exit logic.
Start with cycle-backed market/ranking/decision memory.
