# Phase 2 Rules / Resolution Truth Report

## 1. Summary

Phase 2 is implemented as a rules/resolution truth and observability layer.

Final status: **YELLOW**

Reason: the system is safe and wired, all currently active markets now have rules analysis records, and the dashboard exposes rule risk truth. The live production source data still lacks explicit resolution source URLs for the current active markets, so `/dashboard/api/v2/rules` correctly reports `DEGRADED`.

## 2. Official First Market Families

Official first two market families:

1. `POLITICS_MACRO`
2. `SPORTS`

This is now represented in code through `PRIORITY_MARKET_FAMILIES` in `app/services/rules_resolution_truth.py` and surfaced in `/dashboard/api/v2/rules`.

## 3. Existing Rules Foundation Reused

Preserved and reused:

- `market_rules`
- `rules_analysis`
- `wording_risk_scores`
- `resolution_sources`
- `compliance_blocks`
- `rules_ai_analysis`
- `no_trade_log`
- `no_trade_reasons`
- `RulesNeuronService`
- deterministic ambiguity, deadline, source, dispute, compliance, and wording-risk modules

No schema migration was required.

## 4. Files Changed

- `app/services/rules_resolution_truth.py`
- `app/api/routes.py`
- `app/rules_neuron/service.py`
- `tests/test_v2_18_dashboard_v2_api.py`
- `tests/test_v2_22_rules_resolution_truth.py`
- `docs/PHASE2_RULES_RESOLUTION_TRUTH_REPORT.md`

## 5. What Was Added

Added Dashboard V2 endpoint:

`GET /dashboard/api/v2/rules`

The endpoint returns:

- `mock_data=false`
- selected families
- active market coverage
- missing rules count
- missing resolution source count
- rules analysis coverage
- wording risk
- dispute risk
- resolution clarity
- source verification status
- compliance blocks
- NO_TRADE blocked flag

Added rules to NO_TRADE bridge:

- If deterministic rules analysis produces `NO_TRADE`, POLYBOT logs a canonical `no_trade_log` row from `source_layer='rules'`.
- This is not execution. It is a safety/refusal record.
- Tests prove missing rules creates a blocking compliance block and a rules-sourced NO_TRADE record.

## 6. AI Policy

Current implementation:

- Deterministic rules analysis is the default.
- Existing `AIWordingAnalyzer` can use the hybrid AI brain when `allow_ai=true`.
- It uses local AI path first through the existing AI router.
- Cloud escalation is not enabled by this phase.

Policy for later:

- `qwen3:4b`: light rules summary, ambiguity precheck, wording triage.
- Claude/Anthropic: only difficult/high-impact ambiguity, resolution contradiction, or disputed wording cases.
- AI never gets direct trading authority.
- AI output must remain advisory and cache/budget governed.

## 7. Production Initialization Run

Command:

`Invoke-RestMethod -Method Post http://127.0.0.1:8000/rules/analyze/all -ContentType 'application/json' -Body '{"limit":50,"allow_ai":false,"reason":"phase2 rules resolution truth initialization"}'`

Result:

- `analyzed=10`
- `failed=0`
- all 10 active markets received rules analysis records
- all current production recommendations were `PENALIZE_HEAVILY`, not `NO_TRADE`
- no rules NO_TRADE rows were created in production because no current market crossed a hard block threshold

## 8. Dashboard Result

Endpoint:

`GET /dashboard/api/v2/rules`

Result after initialization:

- `status=DEGRADED`
- `mock_data=false`
- `stale=false`
- `active_markets=10`
- `with_rules=10`
- `missing_rules=0`
- `missing_resolution_source=10`
- `analyzed_markets=10`
- `analysis_coverage_pct=100.0`
- `no_trade_rule_blocks=0`
- warning: one or more active markets are missing resolution source

Interpretation:

The system is behaving correctly. Missing resolution source is visible as risk, not hidden.

## 9. Test Results

Commands:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_22_rules_resolution_truth.py tests/test_v2_5_rules_service_integration.py tests/test_v2_5_rules_api.py tests/test_v2_18_dashboard_v2_api.py -q`
- `.\scripts\test_in_docker.ps1 tests/test_v2_22_rules_resolution_truth.py -q`

Results:

- `13 passed in 29.65s`
- `5 passed in 15.84s`

Covered:

- Official market-family selection.
- Missing rules creates blocking rules risk.
- Missing rules can create canonical rules-sourced NO_TRADE.
- Missing resolution source warns without crashing.
- Ambiguous wording increases wording risk.
- Dashboard rules endpoint shows real rule risk with `mock_data=false`.
- Existing Rules V2.5 API/service regressions still pass.
- Dashboard V2 route registry still passes.

## 10. Runtime Verification

Commands and results:

- `docker compose config`: passed
- `docker compose --profile test config`: passed
- `docker compose build api migrate`: passed
- `docker compose --profile test build test`: passed
- `docker compose up -d`: passed
- `docker compose run --rm migrate`: `No pending migrations.`
- `docker compose ps`: api/postgres/postgres_test/redis healthy
- `/healthz`: `status=ok`, `ready=true`
- `/runtime/health`: `overall_status=HEALTHY`
- `/dashboard/api/v2/overview`: `status=OK`, `mock_data=false`, `stale=false`
- `/dashboard/api/v2/source-status`: `status=OK`, `mock_data=false`, source checks active
- `/dashboard/api/v2/rules`: `status=DEGRADED`, `mock_data=false`, because resolution sources are missing

## 11. Safety Verification

API environment:

- `MODE=PAPER`
- `BACKEND=paper`
- `LIVE=false`
- `KILL=true`

DB checks:

- `live_orders=0`
- `orders_v2=1` pre-existing row remains; this phase did not place orders
- `rules_analysis=10`
- `active compliance_blocks=10`
- `rules_no_trade_logs=0` in production because no current production market produced `NO_TRADE`

No live trading was enabled. No order, cancel, signed CLOB, private-key, scoring, or execution logic was added.

## 12. Remaining Gaps

- Current active markets have rules text but no explicit `resolution_source`/`resolution_source_url`.
- Dashboard rules status is correctly `DEGRADED` until resolution source truth is improved.
- Rules analysis is manually triggered through `/rules/analyze/all`; it is not yet part of the scheduled runtime cycle.
- qwen3/Claude rules escalation policy is documented, but cloud escalation was intentionally not implemented.
- The endpoint exposes rule risk but the main opportunity/paper path is not yet fully consuming it.

## 13. Recommended Next Step

Next Phase 2B:

1. Improve extraction of Polymarket resolution source fields from Gamma/raw market metadata.
2. Add a scheduled rules analysis refresh for active `POLITICS_MACRO` and `SPORTS` markets.
3. Feed latest `rules_analysis.recommendation` into opportunity/no-trade prechecks.
4. Add qwen3:4b summary-only rules precheck behind `allow_ai`.
5. Add Claude escalation only for high-impact ambiguous cases after budget/cache guard verification.

## 14. Final Status

Final status: **YELLOW**

Can continue development: **YES**

Can go live: **NO**

Reason:

The phase is safe and functionally wired, but resolution source truth is incomplete in current live market data and must be improved before Paper or Live decisions trust rules risk as a hard gate.
