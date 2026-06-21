# Continuous Source Refresh Orchestrator Report

## 1. Purpose

Build and wire a DATA_ONLY Continuous Source Refresh Orchestrator so POLYBOT sources no longer remain silently stale. The runtime now records per-source refresh attempts, freshness, blockers, and derived signal production, and exposes that truth to Control Center.

This phase did not enable Paper Simulation, Shadow, Live, Full Monitor Run, paper action, execution action, or manual trade.

## 2. Source Refresh Architecture

The implementation adds a source refresh registry and orchestrator around existing safe source producers. It runs during retained Runtime Supervisor cycles while SYSTEM ON is allowed to collect DATA_ONLY evidence.

Runtime flow:

```text
Runtime Supervisor cycle
-> SourceRefreshOrchestrator.run_cycle()
-> source producer refresh / classification
-> derived signal production
-> source_refresh_cycles + source_refresh_status
-> Control Center source-refresh-status
-> Full Mesh / Edge / Actionability surfaces consume freshness state
```

## 3. Source Refresh Contract

Each source is represented as a refresh contract with:

- source name and type
- refresh mode
- candidate-scoped / market-level support
- directional support
- last attempt / last success / latest data timestamps
- refresh interval and TTL
- refresh state
- total and fresh row counts
- candidate-linked and directional row counts
- required and missing config key names
- blocker code and required_to_pass

Supported states include `FRESH`, `REFRESHING_NO_NEW_DATA`, `REFRESHING_BUT_NOT_CANDIDATE_LINKED`, `REFRESHING_BUT_NOT_DIRECTIONAL`, `STALE_BY_TTL`, `MISSING_CONFIG`, `NO_CONNECTOR`, `FAILED_WITH_ERROR`, and `KNOWN_NOT_IMPLEMENTED`.

## 4. Source Refresh Registry

Registered sources:

| Source | Type | Refresh Result |
|---|---|---|
| `clob_orderbook` | ORDERBOOK | Fresh via existing orderbook/runtime path |
| `candidate_price_path` | ORDERBOOK | Fresh candidate path rows |
| `liquidity` | MARKET | Fresh via derived market neuron output |
| `orderbook_signals` | MARKET_MOVEMENT | Produced from orderbook snapshots |
| `market_movement` | MARKET_MOVEMENT | Produced but not candidate-linked |
| `market_technical_signals` | TECHNICAL | Produced but not candidate-linked |
| `market_memory_v2` | MEMORY | Rebuilt one DATA_ONLY row; no invented history |
| `neuron_signals` | SIGNAL | Fresh, not directional enough for Edge |
| `signal_quality` | SIGNAL | Fresh, not directional enough for Edge |
| `payout` | PAYOUT | Freshened from existing payout service |
| `news` | NEWS | Refreshes rows, but remains not directional enough |
| `whale` | WHALE | Refresh attempted, no new rows |
| `cross_market` | CROSS_MARKET | No connector |
| `social` | SOCIAL | Known not implemented / missing external config |
| `ai_reasoner` | AI | Missing usable AI config in this path; deterministic fallback remains |

## 5. Supervisor Integration

`RuntimeSupervisorService` now accepts the orchestrator from canonical runtime wiring and calls it during supervisor cycles. Supervisor records now include source refresh fields:

- `source_refresh_orchestrator_state`
- `source_refresh_cycles_completed`
- `sources_refreshed_this_cycle`
- `sources_failed_this_cycle`
- `sources_no_new_data_this_cycle`
- `derived_signals_created_this_cycle`
- `latest_source_refresh_at`

## 6. Per-Source Refresh State

Latest verified source-refresh endpoint state:

- `source_refresh_orchestrator_state`: `ACTIVE`
- `cycles_completed`: 13
- latest cycle checked 15 sources
- sources refreshed: 12
- sources failed: 0
- sources no-new-data: 4
- derived signals created in latest cycle: 40

Current important states:

- Fresh: `clob_orderbook`, `candidate_price_path`, `liquidity`, `orderbook_signals`, `market_memory_v2`, `payout`
- Not candidate-linked: `market_movement`, `market_technical_signals`
- Not directional enough: `neuron_signals`, `signal_quality`, `news`
- No new data: `whale`
- No connector: `cross_market`
- Known not implemented: `social`
- Missing AI config: `ai_reasoner`

Missing config key names only:

- `CRYPTOPANIC_API_KEY`
- `OLLAMA_BASE_URL`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- social connector keys where relevant: `X_BEARER_TOKEN`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`

No secret values were printed.

## 7. Payout / Odds Refresh Result

Payout refresh is now wired through `PayoutOddsService.evaluate_recent()` in DATA_ONLY mode. A freshness bug was corrected by using `updated_at` rather than only `created_at` for payout freshness in:

- source refresh registry
- source organ runtime adapter
- source-backed edge direct payout contribution lookup

Latest payout state is fresh in `source-refresh-status`. Payout rows increased from 1,947 before the first controlled run to 2,004 after the final verification snapshot.

## 8. News Refresh Result

News refresh is wired through `NewsNeuronService.collect_and_process_sources()`. Rows increased from 391 impact/link rows before the controlled run to 430 after final verification. News remains not directional enough for source-backed Edge in the latest status, and `CRYPTOPANIC_API_KEY` remains missing by key name only.

## 9. Whale Refresh Result

Whale refresh is wired through `WhaleNeuronService.scan_and_process_sources()`. It ran safely and returned `REFRESHING_NO_NEW_DATA`; whale rows remained 14. No whale flow was fabricated.

## 10. Derived Signal Production Result

Derived signal production is active through existing `MarketNeuronService.analyze_market()`:

| Table | Before | After Final Snapshot |
|---|---:|---:|
| `orderbook_signals` | 0 | 260 |
| `market_technical_signals` | 0 | 260 |
| `liquidity_signals` | 0 | 260 |
| `time_signals` | 0 | 260 |
| `fee_reward_signals` | 0 | 260 |

These signals are DATA_ONLY evidence. They do not create paper artifacts and do not force Edge/Risk approval.

## 11. Market Memory Result

`MarketMemoryService.rebuild()` is wired conservatively. It produced one memory row where existing data allowed it. No hit rates or historical outcomes were invented.

## 12. AI Reachability Result

AI remains fallback/unavailable in this path. The refresh status reports missing AI config keys by name only and does not block source refresh. No AI-generated sources, source IDs, or probabilities were introduced.

## 13. Endpoint Result

Added:

- `GET /dashboard/api/v2/control/source-refresh-status`

Updated:

- `GET /dashboard/api/v2/control/paper-actionability` now exposes source refresh state, source refresh counts, stale source blockers, missing source blockers, and source refresh source map.

Verified active server endpoints:

- `/healthz`
- `/runtime/health`
- `/dashboard/api/v2/control/source-refresh-status`
- `/dashboard/api/v2/control/full-mesh-inquiry`
- `/dashboard/api/v2/control/source-backed-edge`
- `/dashboard/api/v2/control/paper-actionability`
- `/dashboard/api/v2/control/pre-paper-safety`
- `/dashboard/api/v2/control/paper-readiness`

## 14. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_source_refresh_orchestrator.py tests/test_derived_signal_production.py tests/test_source_refresh_status_endpoint.py -q -rs
2 passed, 5 skipped
```

Skips were due the local test DB env precondition: `POLYBOT_DATABASE_URL is not configured`.

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_source_backed_edge_integration.py tests/test_source_backed_edge_source_organs.py tests/test_paper_actionability_contract.py -q
24 passed
```

Additional related source/mesh slice:

```text
39 passed
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
passed
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "source_refresh or derived_signal or source or news or whale or signal or market_movement or technical or orderbook or payout or ai or full_mesh or mesh or edge or paper_actionability"
1 failed, 355 passed, 517 skipped, 1160 deselected
```

The single failure was an environment guard in `tests/test_v2_21_source_status.py::test_source_status_persists_only_to_docker_test_database`; it requires `DATABASE_URL` / `POLYBOT_DATABASE_URL` to point at a `polybot_test` database. The local env did not provide that value.

## 15. Controlled SYSTEM ON Refresh Run

Procedure:

1. Captured forbidden artifact counts and source counts.
2. Rebuilt and recreated only the API container.
3. POSTed SYSTEM ON.
4. Waited for six source refresh/supervisor cycles.
5. Did not enable Paper Simulation.
6. Did not start Full Monitor Run.
7. POSTed SYSTEM OFF.
8. Verified runtime stopped and Paper Simulation remained OFF.

Final runtime cleanup:

- `runtime_state`: `STOPPED`
- `system_power`: `OFF`
- `supervisor_state`: `STOPPED`
- `current_mode`: `DATA_ONLY`

## 16. Source Counts Before / After

Forbidden artifact counts:

| Table | Before | After |
|---|---:|---:|
| `paper_intents` | 20 | 20 |
| `paper_orders` | 12 | 12 |
| `paper_fills` | 9 | 9 |
| `paper_positions` | 12 | 12 |
| `paper_position_closes` | 9 | 9 |
| `live_orders` | 0 | 0 |
| `positions` | 0 | 0 |

Source and DATA_ONLY counts:

| Table | Before | After Final Snapshot |
|---|---:|---:|
| `orderbook_snapshots` | 53,816 | 53,972 |
| `orderbook_signals` | 0 | 260 |
| `market_technical_signals` | 0 | 260 |
| `liquidity_signals` | 0 | 260 |
| `time_signals` | 0 | 260 |
| `fee_reward_signals` | 0 | 260 |
| `market_memory_v2` | 0 | 1 |
| `payout_odds_evaluations` | 1,947 | 2,004 |
| `news_impact_scores` | 391 | 430 |
| `news_market_links` | 391 | 430 |
| `whale_events` | 14 | 14 |
| `neuron_signals` | 25,451 | 25,471 |
| `neuron_signal_bindings` | 25,393 | 25,413 |
| `signal_quality_evaluations` | 22,301 | 22,321 |
| `risk_evidence_mesh_evaluations` | 2,425 | 2,425 |
| `source_refresh_cycles` | 0 | 13 |
| `source_refresh_status` | 0 | 15 |

## 17. Edge Impact

The source refresh problem is materially improved: stale payout/source status is now refreshed and derived signals are live.

Remaining Edge/Risk result:

- `EDGE_SUPPORTED`: 0
- `EDGE_STALE`: 50
- `risk_usable`: 0
- `source_backed`: 0
- latest source-backed-edge result still reports stale persisted Risk/Edge rows.

Root remaining issue:

Source refresh is active, but downstream persisted `risk_evidence_mesh_evaluations` did not increase or update during the verification run. The latest source-backed-edge endpoint still reads older Edge theses whose payout contribution freshness is stale. This means source refresh is working, but Risk/Edge recomputation after refresh remains partial and must be corrected before Phase 10 readiness can be claimed.

## 18. READY_FOR_PHASE_10

`READY_FOR_PHASE_10 = NO`

Exact reason:

- No candidate reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`.
- Source refresh is active, but downstream Risk/Edge rows still show `EDGE_STALE`.
- `risk_usable = 0`.
- Some sources remain real non-paper blockers or non-edge contributors: market movement/technical rows are not candidate-linked, signals/news are not directional enough, whale has no new data, cross-market has no connector, AI is fallback/unavailable, social is not implemented.

## 19. Safety Result

No paper orders, fills, positions, live orders, or live positions were created. Paper Simulation remained OFF. Shadow and Live remained disabled. The work stayed in DATA_ONLY source/evidence/audit paths.

## 20. Recommended Next Action

Implement the narrow downstream recomputation correction:

1. After source refresh, re-run Source-Backed Edge and Risk Evidence Mesh for the same candidate IDs refreshed by payout/news/signals.
2. Ensure Edge/Risk selects the fresh `payout_odds_evaluations.updated_at` rows and fresh source status rows.
3. Persist updated risk evidence and lifecycle decisions.
4. Re-run the controlled source refresh run.

Do not change thresholds or fake edge. The next fix is propagation of refreshed source truth into Edge/Risk, not a readiness bypass.
