# V2.5 Build Report - Rules / Wording / Compliance Neuron

## Summary

V2.5 is implemented and GREEN. POLYBOT now has a durable, auditable rules-risk layer that ingests market rules, parses wording risk signals, stores analyses, creates compliance blocks, publishes redacted events, exposes rules APIs, and adds dashboard truth fields.

The phase stayed intelligence-only: no orders, order intents, positions, risk approvals, or live trading behavior were added.

## Files Created

- `app/rules_neuron/*`
- `app/api/rules_routes.py`
- `app/repositories/rules_analysis_repository.py`
- `app/repositories/wording_risk_repository.py`
- `app/repositories/compliance_block_repository.py`
- `app/repositories/resolution_source_repository.py`
- `app/repositories/rules_ai_analysis_repository.py`
- `app/db/migrations/0043_v2_rules_wording_compliance_neuron.sql`
- `tests/test_v2_5_*.py`
- `docs/V2_5_RULES_WORDING_COMPLIANCE_NEURON.md`
- `docs/V2_5_BUILD_REPORT.md`

## Files Changed

- `app/events/types.py`
- `app/main.py`
- `app/api/routes.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Migration Added

`0043_v2_rules_wording_compliance_neuron.sql`

The migration extends `market_rules` safely and adds `rules_analysis`, `wording_risk_scores`, `compliance_blocks`, `resolution_sources`, and `rules_ai_analysis`.

## API Routes Added

- `GET /rules/market/{market_id}`
- `GET /rules/analysis/recent`
- `GET /rules/blocks`
- `GET /rules/coverage`
- `POST /rules/analyze`
- `POST /rules/analyze/all`

## Dashboard Changes

The operator dashboard now includes real DB-backed Rules / Compliance fields:

- rules coverage percent
- markets with rules analysis
- missing rules count
- high wording risk count
- high dispute risk count
- compliance block count
- average resolution clarity
- latest rules analysis timestamp
- top compliance blocks
- top wording-risk markets

## Events Published

- `rules.ingested`
- `rules.analysis.created`
- `rules.wording_risk.scored`
- `rules.dispute_risk.scored`
- `rules.source.verified`
- `rules.compliance.blocked`
- `rules.ai.analyzed`
- `rules.recommendation.created`

Event payloads are redacted and do not include full rules text or secrets.

## Tests Added

- `tests/test_v2_5_rules_contracts.py`
- `tests/test_v2_5_rules_ingestion.py`
- `tests/test_v2_5_resolution_source_parser.py`
- `tests/test_v2_5_deadline_parser.py`
- `tests/test_v2_5_edge_case_detector.py`
- `tests/test_v2_5_wording_risk_scorer.py`
- `tests/test_v2_5_dispute_risk_scorer.py`
- `tests/test_v2_5_compliance_guard.py`
- `tests/test_v2_5_source_verification_guard.py`
- `tests/test_v2_5_jurisdiction_guard.py`
- `tests/test_v2_5_ai_wording_analyzer.py`
- `tests/test_v2_5_rules_api.py`
- `tests/test_v2_5_rules_service_integration.py`
- `tests/test_v2_5_rules_safety_guards.py`

## Tests Run

Targeted V2.5 no-DB runs:

- `python -m uv run pytest tests/test_v2_5_rules_contracts.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_rules_ingestion.py -q` -> 2 skipped without DB
- `python -m uv run pytest tests/test_v2_5_resolution_source_parser.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_deadline_parser.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_edge_case_detector.py -q` -> 1 passed
- `python -m uv run pytest tests/test_v2_5_wording_risk_scorer.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_dispute_risk_scorer.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_compliance_guard.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_source_verification_guard.py -q` -> 1 passed
- `python -m uv run pytest tests/test_v2_5_jurisdiction_guard.py -q` -> 1 passed
- `python -m uv run pytest tests/test_v2_5_ai_wording_analyzer.py -q` -> 2 passed
- `python -m uv run pytest tests/test_v2_5_rules_api.py -q` -> 1 skipped without DB
- `python -m uv run pytest tests/test_v2_5_rules_service_integration.py -q` -> 2 skipped without DB
- `python -m uv run pytest tests/test_v2_5_rules_safety_guards.py -q` -> 1 passed, 1 skipped without DB

Explicit DB V2.5 focused runs:

- `tests/test_v2_5_rules_ingestion.py::test_rules_loaded_from_data_foundation_hash_stable` -> 1 passed
- `tests/test_v2_5_rules_ingestion.py::test_missing_rules_handled` -> 1 passed
- `tests/test_v2_5_rules_api.py::test_rules_api_endpoints_and_analyze` -> 1 passed
- `tests/test_v2_5_rules_service_integration.py::test_active_market_rules_analyzed_and_persisted` -> 1 passed
- `tests/test_v2_5_rules_service_integration.py::test_missing_rules_creates_no_trade_or_review` -> 1 passed
- `tests/test_v2_5_rules_safety_guards.py::test_kill_blocks_rules_analysis_jobs` -> 1 passed

Regression batch:

- V2.4 key regressions -> passed/skipped as expected
- V2.3 key regressions -> passed/skipped as expected
- V2.2 key regressions -> passed/skipped as expected
- V2.1 key regressions -> skipped where DB was not configured
- runtime/safety regressions -> passed/skipped as expected

Full suite:

- `python -m uv run pytest` -> 176 passed, 338 skipped

## Runtime Verification

Commands run:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`

Verified endpoints:

- `/healthz` responsive
- `/runtime/state` returned DATA_ONLY, kill false, live permissions false
- `/runtime/health` responsive and honest; status DEGRADED due stale scheduler health, with `rules_neuron` RUNNING
- `/events/lag` returned metrics with zero failed/open DLQ events
- `/data/coverage` returned real market coverage
- `/ai/health` returned local unavailable/cloud disabled truth
- `/news/recent` responded
- `/rules/coverage` responded
- `/rules/analysis/recent` responded
- `/rules/blocks` responded
- `POST /rules/analyze` persisted analysis for market `666655`
- `/rules/market/666655` returned stored rules analysis, wording risk, compliance warnings, and recommendation
- `/events/recent` showed V2.5 rules events

## Fully Implemented

- deterministic rules ingestion
- resolution source parsing and source verification guard
- deadline, settlement, ambiguous term, and edge-case analysis
- wording risk, dispute risk, and resolution clarity scoring
- compliance block creation and recommendation logic
- optional AI wording analysis path
- persistence, API, dashboard truth, events, and tests

## Partial / Future

- source verification remains non-networked by design
- compliance classification is not legal advice
- Opportunity Cortex consumption is future-phase work

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Rules cannot create orders: YES
- Rules cannot create order intents: YES
- Rules cannot bypass State Governor: YES
- Rules cannot bypass AI Budget Governor: YES
- missing rules blocks or forces review: YES
- unclear deadline increases risk: YES
- ambiguous wording blocks or penalizes: YES
- verified source reduces risk: YES
- compliance block overrides all: YES
- wording risk persisted: YES
- dispute risk persisted: YES
- resolution clarity computed: YES
- AI wording optional and safe: YES
- no secrets printed: YES
- rules events redacted: YES
- dashboard uses real data only: YES

## Remaining Risks

Runtime orderbook ingestion remains partial from V2.2. Source verification is deterministic and does not prove real-world legal or factual correctness. Full legal compliance review remains outside POLYBOT automation.

## Recommendation

Can move to V2.6 Social / Hype Neuron: YES.
