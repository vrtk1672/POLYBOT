# Source Organ Effectiveness Audit Report

## 1. Purpose

Measure what each connected source organ actually contributes to Full Mesh decisions and identify whether `EDGE_SUPPORTED=0` is caused by missing data, stale data, weak/noisy evidence, candidate-linking gaps, or a consumption bug.

This was an audit and measurement pass with one narrow wiring fix. Paper Simulation was not activated and no execution artifacts were created.

## 2. Source organs audited

- `payout`
- `signal_quality`
- `signal_processing`
- `news`
- RSS / NewsAPI / CryptoPanic-backed news status
- `whale`
- smart wallet / wallet flow tables
- `social`
- `market_memory`
- `market_movement`
- market activity / orderbook technical signal tables
- `cross_market`
- payout / odds evidence
- AI / model router / deterministic fallback
- registered source organs in Full Mesh Registry

## 3. Data counts per source

Measured before the controlled audit run:

| Source table | Rows | Latest timestamp | Fresh by current TTL |
|---|---:|---|---|
| `news_impact_scores` | 391 | 2026-06-10T22:32:01Z | NO |
| `news_market_links` | 391 | 2026-06-10T22:32:01Z | NO |
| `whale_events` | 14 | 2026-06-07T11:39:21Z | NO |
| `social_market_links` | 0 | none | NO |
| `market_memory_v2` | 0 | none | NO |
| `market_technical_signals` | 0 | none | NO |
| `orderbook_signals` | 0 | none | NO |
| `neuron_signals` | 25411 | 2026-06-15T14:38:50Z | near/fell stale by audit read |
| `neuron_signal_bindings` | 25353 | 2026-06-15T14:38:50Z | near/fell stale by audit read |
| `signal_quality_evaluations` | 22261 | 2026-06-15T14:39:11Z | near/fell stale by audit read |
| `payout_odds_evaluations` | 1947 | 2026-06-07T11:44:43Z | NO |
| `risk_evidence_mesh_evaluations` | 2215 | 2026-06-15T14:40:12Z | near/fell stale by audit read |

## 4. Freshness per source

- News: stale, about 404k seconds old at baseline.
- Whale: stale, about 703k seconds old at baseline.
- Payout: stale, about 703k seconds old at baseline.
- Signals: produced recently, but TTL is short (`900s`) and rows fell stale if not refreshed continuously.
- Social: no rows and missing config.
- Market memory: no rows.
- Market movement / orderbook technical signals: no rows.
- Cross-market: no connector.
- AI: deterministic fallback / unavailable; not blocking alone.

## 5. Candidate-linking per source

- `payout`: candidate-linked and token-linked when matching `PAPER_CANDIDATE`/candidate rows exist.
- `signal_quality`: candidate-scoped by market/side through signal binding response.
- `signal_processing`: candidate-scoped by market/side through signal binding response.
- `news`: market-linked only in stored rows; no current candidate-scoped directional rows in latest candidate scope.
- `whale`: market/token rows exist historically, but no current side-linked rows for latest candidates.
- `social`: no candidate-linked rows.
- `market_memory`: no rows.
- `market_movement`: no rows.
- `cross_market`: no connector.

## 6. Directionality per source

- `signal_quality`: directional in current Mesh responses.
- `signal_processing`: directional in current Mesh responses.
- `payout`: directional in current Mesh responses, but stale.
- `news`: stored rows are not directional under current schema/content.
- `whale`: stored rows are token-linked but not side-directional.
- `market_movement`: no data.
- `market_memory`: no directional rows.
- `social`: no data.
- `cross_market`: no data/connector.

## 7. Mesh response per source

During the controlled run, Full Mesh Inquiry requested source organs and returned Universal Mesh Contract responses:

- Active candidate-scoped source organs: `payout`, `signal_quality`, `signal_processing`
- Directional source organs: `payout`, `signal_quality`, `signal_processing`
- No-data organs: `market_memory`, `market_movement`, `news`, `whale`
- Missing-config organ: `social`
- No-connector organ: `cross_market`
- AI organ: unavailable / deterministic fallback, no invented source records

## 8. Edge contribution per source

Initial audit found a concrete breakpoint:

- Full Mesh Inquiry produced source-organ responses.
- Persisted Risk edge theses in `risk_evidence_mesh_evaluations.metadata_json.edge_thesis` had `source_organs_queried=0`, `support_score=0`, and no source organ status.
- This meant source organs were visible in the inquiry layer but were not feeding the canonical Risk edge thesis.

Fix applied:

- `risk_evidence_mesh._collect_evidence()` now includes source organ Mesh responses.
- Source organ lookup can now reuse the active DB connection through `query_source_organ_with_connection()`.
- Source organ lookup errors become explicit Mesh error responses instead of disappearing.

Post-fix latest 50 persisted Risk edge theses:

- `EDGE_STALE`: 50
- `source_organs_queried`: 500
- `directional_sources_found`: 146
- `source_organs_with_status`: 50
- `risk_usable`: 0
- `source_backed`: 0
- max `support_score`: 1.0
- max `edge_score`: 1.0

Interpretation: source contributions now reach Risk, but stale source evidence correctly prevents risk-usable edge.

## 9. Risk contribution per source

Risk now consumes source organ status and directional contributions.

The current Risk outcome remains blocked because:

- supporting signal evidence is fresh enough in some traces,
- payout is candidate/token-linked and directional but very stale,
- stale supporting source evidence causes `EDGE_STALE`,
- `EDGE_STALE` maps to non-risk-usable edge.

Risk did not loosen. It correctly rejected stale source-backed edge.

## 10. Breakpoints found

Fixed:

- Source organ responses were not included in Risk’s canonical edge thesis. This caused Risk to ignore valid Full Mesh source-organ responses even though the inquiry endpoint showed them.

Still present and valid:

- Payout is candidate-linked but stale.
- News has data but it is stale and not candidate-directional.
- Whale has data but it is stale and not side-directional for current candidates.
- Market movement and market memory produce no current rows.
- Social is missing config.
- Cross-market has no connector.
- Candidate-scoped event truth still shows token-side mismatch in the latest sampled event window.

## 11. Bugs fixed

One safe wiring bug was fixed:

- `risk_evidence_mesh` now passes source organ Mesh responses into the Source-Backed Edge Engine.

No thresholds were lowered. No source data was fabricated. No Risk, Exit, Lifecycle, Capital, or Actionability gate was loosened.

## 12. Tests run

- Focused: `.venv\Scripts\python.exe -m pytest tests/test_source_organ_effectiveness_audit.py -q`
  - Result: `3 passed in 0.25s`
- Related: `.venv\Scripts\python.exe -m pytest tests/test_existing_source_organs_runtime_wiring.py tests/test_full_mesh_source_organ_status.py tests/test_source_backed_edge_source_organs.py tests/test_full_mesh_ecosystem_contract.py tests/test_mesh_inquiry_orchestrator.py tests/test_source_backed_edge_integration.py tests/test_paper_actionability_contract.py -q`
  - Result: `39 passed in 2.88s`
- Broad: `.venv\Scripts\python.exe -m pytest tests -q -k "source or news or whale or signal or cross_market or memory or ai or full_mesh or mesh or edge or paper_actionability"`
  - Result: `1 failed, 342 passed, 455 skipped, 1223 deselected`
  - Failure: `tests/test_v2_21_source_status.py::test_source_status_persists_only_to_docker_test_database`
  - Cause: local test environment did not set `POLYBOT_DATABASE_URL` or `DATABASE_URL` to a value containing `polybot_test`.
- Compile: `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed.

## 13. Controlled SYSTEM ON audit run

Deployment:

- `docker compose build api`: success
- `docker compose up -d --no-deps api`: success

Run:

- POST `/system/power/on`: accepted.
- Mode: `DATA_ONLY`
- Supervisor: `ALIVE`
- Cycles completed before cleanup: 8
- Paper Simulation: OFF throughout
- POST `/system/power/off`: accepted.
- Final runtime: `SAFE_STOPPED`, supervisor `STOPPED`, mode `DATA_ONLY`.

## 14. Source effectiveness classification table

| Source | Classification | Evidence |
|---|---|---|
| `signal_quality` | `CANDIDATE_LINKED_WATCH_ONLY` | Fresh candidate-linked directional responses reach Risk, but do not overcome stale supporting source context. |
| `signal_processing` | `CANDIDATE_LINKED_WATCH_ONLY` | Same signal lineage as `signal_quality`; reaches Risk after fix. |
| `payout` | `PRODUCES_DATA_STALE` | Candidate/token-linked and directional, but latest payout row is about 704k seconds old against 900s TTL. |
| `news` | `PRODUCES_DATA_STALE` / `PRODUCES_DATA_NOT_DIRECTIONAL` | 391 rows exist, all stale and not candidate-directional for latest candidates. |
| `whale` | `PRODUCES_DATA_STALE` / `PRODUCES_DATA_NOT_DIRECTIONAL` | 14 rows exist, token/market-linked historically, but stale and not side-linked. |
| `social` | `CONFIGURED_BUT_INACTIVE` | No rows; missing provider config keys. |
| `market_memory` | `PRODUCES_NO_DATA` | Table exists, zero rows. |
| `market_movement` | `PRODUCES_NO_DATA` | Technical/orderbook signal tables exist, zero rows. |
| `cross_market` | `UNKNOWN_NEEDS_INSPECTION` / no connector | Registry organ exists but no runtime connector/table. |
| `AI` | `CONNECTED_BUT_NOT_CONSUMED` as external model; fallback safe | Deterministic fallback is used; no AI source invention. |

## 15. Why EDGE_SUPPORTED is 0

After the fix, source contributions reach Risk. `EDGE_SUPPORTED` is still zero because latest canonical Risk edge theses are `EDGE_STALE`.

Observed top candidate trace:

- Candidate source organs active: `payout`, `signal_quality`, `signal_processing`
- Signal freshness: about 170s in sampled trace
- Payout freshness: about 704k seconds in sampled trace
- News/whale/memory/movement: no current matching data
- Social: missing config
- Cross-market: no connector
- Edge state: `EDGE_STALE`
- Risk result: `RISK_BLOCK`
- Lifecycle result: `LIFECYCLE_DENIED`
- Paper actionability: `BLOCKED_BY_LIFECYCLE`

The stale payout contribution is sufficient to make the edge thesis source-aware, but it is too old for Risk to use.

## 16. What is needed to get EDGE_SUPPORTED

Minimum next correction:

1. Refresh or recompute candidate-specific payout/odds evidence during DATA_ONLY candidate-scoped cycles, or stop treating stale payout as active supporting evidence until refreshed.
2. Restore/fix market movement signal production so `market_technical_signals` / `orderbook_signals` produce current rows.
3. Add candidate-directional linking for news/whale if those source rows are meant to support risk.
4. Provide missing social config only if social is expected to participate.
5. Add a real cross-market connector or keep it explicitly unavailable.

Do not lower the edge threshold. The current block is freshness/source quality, not scoring strictness.

## 17. READY_FOR_PHASE_10

`NO`

Exact reason: no candidate reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`. Current minimum blockers:

- `EDGE_STALE`
- `BLOCKED_BY_RISK`
- `BLOCKED_BY_LIFECYCLE`
- `MISSING_CANDIDATE_EVENT_LINK` / latest-window candidate event mismatch on sampled endpoint
- expected operational blocker: `PAPER_SIMULATION_OFF`

## 18. Safety result

Forbidden artifact counts before -> after:

- `paper_intents`: 20 -> 20
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `paper_position_closes`: 9 -> 9
- `live_orders`: 0 -> 0
- `positions`: 0 -> 0

DATA_ONLY evidence rows increased as expected:

- `event_log`: 556913 -> 557255
- `orderbook_snapshots`: 53401 -> 53643
- `risk_evidence_mesh_evaluations`: 2215 -> 2351
- `brain_outputs`: 33077 -> 34307
- `coordinator_decisions`: 23277 -> 23539

No Paper Simulation activation, live/shadow activation, order/fill/position creation, fake source data, fake AI evidence, or destructive DB action occurred.

