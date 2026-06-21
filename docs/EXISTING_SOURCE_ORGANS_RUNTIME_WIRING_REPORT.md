# Existing Source Organs Runtime Wiring Report

## 1. Purpose

Wire existing POLYBOT source organs into the Full Mesh runtime decision path without creating paper/live/shadow artifacts and without faking source-backed edge.

## 2. Source organs discovered

- News/RSS/NewsAPI/CryptoPanic: `app/news_neuron/*`, `news_impact_scores`, `news_market_links`, source credential status rows.
- Whale: `app/whale_neuron/*`, `whale_events`.
- Signals: `app/services/neuron_signals.py`, `neuron_signals`, `neuron_signal_bindings`, `signal_quality_evaluations`.
- Market movement: `market_technical_signals`, `orderbook_signals`.
- Market memory: `app/market_memory/*`, `market_memory_v2`.
- Social: `app/social_neuron/*`, `social_market_links`, social provider credential status rows.
- Payout/odds: `app/services/payout_odds.py`, `payout_odds_evaluations`, `payout_odds_sources`.
- AI: `app/services/ai_context_router.py`, `app/services/ai_edge_reasoner.py`, `app/ai_brain/*`.
- Cross-market: registry-level organ exists, but no runtime connector/table was found.

## 3. Source organs registered

Registered/adapted source organs now include:

- `market_movement`
- `news`
- `whale`
- `social`
- `cross_market`
- `market_memory`
- `signal_quality`
- `signal_processing`
- `payout`
- `ai_reasoner`

## 4. Source organs connected to runtime

Connected read-only runtime adapters:

- `news`: reads existing news impact/link rows by market.
- `whale`: reads existing whale flow rows by market/token/side where available.
- `social`: reports missing provider config by key name only.
- `cross_market`: reports no connector.
- `market_memory`: reads existing memory rows when available.
- `market_movement`: reads market technical/orderbook movement rows.
- `signal_quality`: reads existing neuron signal + binding + quality rows.
- `signal_processing`: reads existing neuron signal + binding + quality rows.
- `payout`: reads existing payout odds rows by candidate, market, side, and token.

No external crawler, new API connector, or secret was added.

## 5. Source organs still passive/unavailable

Controlled run status:

- Active/candidate-scoped directional: `payout`, `signal_quality`, `signal_processing`.
- No data for current candidate scope: `news`, `whale`, `market_memory`, `market_movement`.
- Missing config: `social`.
- No connector: `cross_market`.
- AI: unavailable/fallback explicit; no source IDs or probabilities invented.

## 6. Missing config keys

Missing config key names surfaced without values:

- `CRYPTOPANIC_API_KEY`
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `TELEGRAM_API_HASH`
- `TELEGRAM_API_ID`
- `X_BEARER_TOKEN`

## 7. Existing data found

Before controlled run:

- `neuron_signals`: 25391
- `news_impact_scores`: 391
- `news_market_links`: 391
- `whale_events`: 14
- `social_market_links`: 0
- `market_memory_v2`: 0
- `payout_odds_evaluations`: 1947

## 8. Candidate-linking result

Full Mesh now exposes source organ candidate-linking state:

- `signal_quality`: `ACTIVE_CANDIDATE_SCOPED`, `CANDIDATE_LINKED_MARKET_SIDE`
- `signal_processing`: `ACTIVE_CANDIDATE_SCOPED`, `CANDIDATE_LINKED_MARKET_SIDE`
- `payout`: `ACTIVE_CANDIDATE_SCOPED`, `CANDIDATE_LINKED_TOKEN`
- `news`: no matching data or market-level only when present
- `whale`: no matching data in current scope
- `market_movement`: no matching data in current scope
- `market_memory`: no matching data
- `social`: missing config
- `cross_market`: no connector

Market-level data is not treated as candidate-actionable.

## 9. Edge Engine integration result

The Source-Backed Edge Engine now receives source organ status and source responses from Full Mesh Inquiry.

New/extended edge visibility:

- source organs queried
- source organs unavailable
- no-data organs
- missing source organs
- directional sources found
- candidate-scoped source organ names
- `EDGE_SOURCE_ORGANS_UNAVAILABLE` when every source organ is unavailable

Controlled run result:

- `EDGE_SUPPORTED`: 0
- `EDGE_WATCH`: 48
- `EDGE_STALE`: 2
- `source_backed`: 0
- `risk_usable`: 0

The system did not fake edge. Existing directional source evidence reached watch/stale levels only.

## 10. Risk / actionability result

Risk continues to block source-weak candidates. Paper Actionability exposes source organ status and remains non-actionable:

- `candidate_scoped_bundles`: 16
- `ACTIONABLE_SMALL_PAPER`: 0
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`: 0
- `BLOCKED_BY_LIFECYCLE`: 30
- `BLOCKED_BY_RISK`: 20
- top blockers: `BLOCKED_BY_LIFECYCLE`, `BLOCKED_BY_RISK`, `NO_SOURCE_BACKED_EDGE`, `MISSING_CANDIDATE_EVENT_LINK`, `EDGE_STALE`

## 11. Tests run

- Focused: `.venv\Scripts\python.exe -m pytest tests/test_existing_source_organs_runtime_wiring.py tests/test_full_mesh_source_organ_status.py tests/test_source_backed_edge_source_organs.py -q`
  - Result: `11 passed in 0.66s`
- Related: `.venv\Scripts\python.exe -m pytest tests/test_full_mesh_ecosystem_contract.py tests/test_mesh_inquiry_orchestrator.py tests/test_neuron_registry.py tests/test_mesh_organ_adapters.py tests/test_source_backed_edge_integration.py tests/test_ai_edge_reasoner_contract.py tests/test_paper_actionability_contract.py -q`
  - Result: `37 passed in 2.86s`
- Broad: `.venv\Scripts\python.exe -m pytest tests -q -k "source or news or whale or signal or cross_market or memory or ai or full_mesh or mesh or edge or paper_actionability"`
  - Result: `1 failed, 339 passed, 455 skipped, 1223 deselected in 14.90s`
  - Failure: `tests/test_v2_21_source_status.py::test_source_status_persists_only_to_docker_test_database`
  - Cause: local test environment had no `POLYBOT_DATABASE_URL` or `DATABASE_URL` containing `polybot_test`.
- Compile: `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed.

## 12. Controlled SYSTEM ON run

Deployment:

- `docker compose build api`: success
- `docker compose up -d --no-deps api`: success

GET verification:

- `/healthz`: `ok`, ready true
- `/runtime/health` after cleanup: `SAFE_STOPPED`, runtime `STOPPED`, system power `OFF`, supervisor `STOPPED`, mode `DATA_ONLY`

Controlled run:

- POST `/system/power/on`: accepted, supervisor `RUNNING`, Paper Simulation disabled.
- Waited through 6 supervisor cycles.
- Supervisor during run: `ALIVE`
- Candidate-scoped events endpoint during run:
  - `events_checked`: 50
  - `candidate_event_scoped`: 2
  - `token_side_mismatch`: 48
- Full Mesh during run:
  - `sessions`: 50
  - `blocked`: 50
  - `error`: 0
  - `source_organs_active`: 150
  - `candidate_scoped_source_organs`: 54
  - `directional_source_organs`: 54
- POST `/system/power/off`: accepted, supervisor `STOPPED`, Paper Simulation disabled.

## 13. SOURCE_RUNTIME_WIRING_STATE

`SOURCE_ORGANS_PARTIAL`

Reason: existing source organs are now queried and visible, with active candidate-scoped payout/signals, but news/whale/memory/movement have no matching data, social is missing config, cross-market has no connector, and AI remains unavailable/fallback.

## 14. FULL_MESH_STATE

`FULL_MESH_PARTIAL`

Reason: Full Mesh inquiry runs without source-organ errors, but no candidate reaches source-backed risk-usable edge.

## 15. READY_FOR_PHASE_10

`NO`

Exact reason: no candidate reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`. Remaining blockers are current and explicit:

- `NO_SOURCE_BACKED_EDGE`
- `EDGE_STALE`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_LIFECYCLE`
- `MISSING_CANDIDATE_EVENT_LINK` on some checked bundles
- expected operational blocker: `PAPER_SIMULATION_OFF`

## 16. Safety result

Forbidden artifact counts before -> after:

- `paper_intents`: 20 -> 20
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `paper_position_closes`: 9 -> 9
- `live_orders`: 0 -> 0
- `positions`: 0 -> 0

DATA_ONLY evidence rows increased as expected:

- `event_log`: 556591 -> 556873
- `orderbook_snapshots`: 53219 -> 53401
- `brain_outputs`: 32147 -> 33077
- `coordinator_decisions`: 23075 -> 23277
- `risk_evidence_mesh_evaluations`: 2125 -> 2215

No Paper Simulation activation, live/shadow activation, orders, fills, positions, fake sources, or secret printing occurred.

## 17. Next required action

Populate or configure real candidate-linked source evidence:

- provide social/news provider config if those organs should run,
- add or enable a cross-market connector,
- materialize fresh market movement rows for candidate markets,
- improve candidate linking for source rows where the source can support it,
- keep Risk blocking until a source-backed, non-stale, candidate-linked edge exists.

