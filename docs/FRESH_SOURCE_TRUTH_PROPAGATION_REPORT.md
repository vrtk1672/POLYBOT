# Fresh Source Truth Propagation Report

## Purpose

Fix the downstream propagation gap from Continuous Source Refresh into Source-Backed Edge, Risk Evidence Mesh, Lifecycle Governance, and Paper Actionability.

## Root Cause Found

Fresh source refresh and derived signals were being produced, but downstream decision truth stayed stale for two reasons:

1. Risk/Edge read surfaces ordered by `created_at`, so existing upserted Risk Evidence rows updated via `updated_at` were hidden behind older rows.
2. Source-organ lookup errors inside `RiskEvidenceMeshService.evaluate_recent()` aborted the shared Postgres transaction. The errors were converted to mesh ERROR responses, but the transaction remained aborted, so downstream recompute failed with `InFailedSqlTransaction`.
3. Source refresh persisted the refresh cycle after downstream recompute, so Risk/Edge could not attach the current `source_refresh_cycle_id`.
4. Edge stale handling let stale directional payout poison the thesis even when fresh source-backed evidence existed.

## Propagation Contract

Decision metadata now carries:

- `source_refresh_cycle_id`
- `candidate_id`
- `market_id`
- `condition_id`
- `side`
- `token_id`
- `event_id`
- `correlation_id`
- `edge_thesis_id`
- `risk_evidence_id`
- `propagation_context`

## Supervisor Order Result

`SourceRefreshOrchestrator.run_cycle()` now persists `source_refresh_cycles` before triggering downstream DATA_ONLY Risk/Lifecycle recompute. The downstream outcome is persisted back into cycle metadata.

## Edge Engine Stale Handling Result

`SourceBackedEdgeEngine` now separates:

- `fresh_sources_used`
- `stale_sources_ignored`
- `stale_sources_blocking`
- `directional_sources_used`
- `watch_only_sources`
- `derived_signal_ids`

Stale payout blocks only when it is the only directional support. Fresh source-backed support can produce `EDGE_SUPPORTED`; fresh derived/watch-only context remains watch-level and does not fake edge.

## Risk Selection Result

Risk Evidence now:

- orders latest rows by `updated_at DESC NULLS LAST, created_at DESC`
- records `source_refresh_cycle_id`
- records `edge_thesis_id`
- records propagation context
- isolates source-organ DB failures with nested transaction/savepoint boundaries

## Lifecycle And Actionability Selection Result

Lifecycle planning now prefers updated lifecycle plans where schema supports it and carries Risk propagation metadata forward. Paper Actionability exposes propagation context, source refresh cycle, Edge/Risk IDs, stale/fresh source lists, and propagation breakpoints.

## API Result

Updated:

- `GET /dashboard/api/v2/control/source-refresh-status`
- `GET /dashboard/api/v2/control/source-backed-edge`
- `GET /dashboard/api/v2/control/paper-actionability`

Added:

- `GET /dashboard/api/v2/control/decision-propagation-trace`

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_fresh_source_truth_propagation.py tests/test_decision_propagation_trace.py tests/test_edge_stale_handling.py -q`: 6 passed
- `.venv\Scripts\python.exe -m pytest tests/test_source_refresh_orchestrator.py tests/test_derived_signal_production.py tests/test_source_refresh_status_endpoint.py tests/test_source_backed_edge_integration.py tests/test_source_organ_effectiveness_audit.py tests/test_paper_actionability_contract.py tests/test_mesh_inquiry_orchestrator.py -q`: 29 passed, 5 skipped
- `.venv\Scripts\python.exe -m pytest tests -q -k "source_refresh or propagation or edge_stale or decision_trace or derived_signal or source or mesh or edge or risk or lifecycle or paper_actionability"`: 184 passed, 272 skipped, 1583 deselected
- `.venv\Scripts\python.exe -m compileall app tests`: passed

## Deployment Result

- `docker compose build api`: passed
- `docker compose up -d --no-deps api`: passed
- Active API verified healthy on port 8000.

## Controlled SYSTEM ON Propagation Run

SYSTEM ON ran in DATA_ONLY only. Paper Simulation remained OFF. Runtime supervisor completed cycles and source refresh stayed ACTIVE.

During run:

- `source-refresh-status`: propagation `ACTIVE`
- `source-backed-edge`: `EDGE_SUPPORTED=6`, later `EDGE_SUPPORTED=23`
- `risk_usable=6`, later `risk_usable=23`
- `decision-propagation-trace`: propagation `ACTIVE`, missing source refresh context `0`
- `paper-actionability`: still `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`

## Counts Before/After Final Controlled Run

Forbidden artifacts before:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`

Forbidden artifacts after:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`

DATA_ONLY rows increased as expected:

- `source_refresh_cycles=19 -> 21`
- `orderbook_signals=380 -> 440`
- `market_technical_signals=380 -> 440`
- `liquidity_signals=380 -> 440`
- `time_signals=380 -> 440`
- `fee_reward_signals=380 -> 440`
- `payout_odds_evaluations=2050 -> 2084`
- `news_impact_scores=448 -> 456`
- `news_market_links=448 -> 456`
- `risk_evidence_mesh_evaluations=2430 -> 2506`
- `lifecycle_governance_decisions=11728 -> 11804`

## Current Decision

`PROPAGATION_STATE = ACTIVE`

`EDGE_DECISION_STATE = EDGE_SUPPORTED exists, but actionability remains blocked`

`READY_FOR_PHASE_10 = NO`

Exact current blocker:

- `BLOCKED_BY_LIFECYCLE`
- top current lifecycle stacks still include `RISK_BLOCKED`, `RISK_BLOCKED_STALE_CRITICAL_SOURCE`, `STALE_CAPITAL_EVALUATION`, `STALE_ORDERBOOK`, and `STALE_SAME_MARKET_GUARD` on recent lifecycle decisions
- candidates with `EDGE_SUPPORTED` and `risk_usable=true` are still `RISK_REVIEW_LINEAGE_PARTIAL`, not `RISK_OK`

## Safety Result

No Paper/Shadow/Live activation occurred. No paper intents/orders/fills/positions or live/shadow artifacts were created. No source data was faked. No thresholds or gates were loosened.
