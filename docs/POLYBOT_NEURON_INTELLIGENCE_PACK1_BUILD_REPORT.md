# POLYBOT Neuron Intelligence Pack 1 Build Report

## Current Reality Found

POLYBOT already had source tables and partial neuron primitives for rules, market/orderbook/liquidity, fees, time, and news. Runtime order already included Trusted Orderbook Evidence before downstream recompute, making it the correct insertion point for Pack 1.

Existing runtime state during smoke:

- `paper_intents=6`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`

## Files Created

- `app/db/migrations/0100_neuron_intelligence_pack1.sql`
- `app/services/neuron_intelligence.py`
- `tests/test_neuron_intelligence_pack1_service.py`
- `tests/test_dashboard_neuron_intelligence.py`
- `tests/test_neuron_intelligence_runtime_order.py`
- `docs/POLYBOT_NEURON_INTELLIGENCE_PACK1.md`
- `docs/POLYBOT_NEURON_INTELLIGENCE_PACK1_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`
- `tests/brain_dialogue_fixtures.py`

## DB Migrations

Migration `0100_neuron_intelligence_pack1.sql` adds:

- `neuron_intelligence_runs`
- `neuron_intelligence_evidence`

No trading-state tables were changed.

## Runtime Integration

`MarketService.refresh()` now runs `NeuronIntelligenceService.run_pack()` after `TrustedOrderbookEvidenceService.resolve()` and before `DownstreamEvidenceRecomputeService.run_recompute()`.

SYSTEM OFF blocks normal Pack 1 execution. SYSTEM ON permits Pack 1 only through `SystemPowerService` and `StateGovernor.can_execute(RUN_INTELLIGENCE)`.

## Dashboard / API

Added:

- `GET /dashboard/api/v2/neuron-intelligence`

Extended:

- Brain Dialogue materialization now turns `neuron_intelligence_evidence` rows into source-backed neuron dialogue.

## Neuron Results

Smoke produced:

- Rules / Wording: `CLEAR`, wording risk `0.200`, resolution clarity `0.650`
- Liquidity: `GOOD_LIQUIDITY`, spread `0.0200`, exit liquidity `0.862`
- Fees / Rewards: `EDGE_ERASED_BY_COSTS`, estimated cost `0.0200`, net edge after costs `-0.0200`
- Time: `LONG_CAPITAL_LOCK`, time to resolution about `18,515,798` seconds
- News: `UNVERIFIED`, blocker `NO_NEWS_EVIDENCE`

News remained source-safe: no news impact was invented.

## Tests Added

- SYSTEM OFF blocks Pack 1 evidence generation
- SYSTEM ON creates all five neuron evidence outputs
- missing rules analysis blocks Rules / Wording without fake scores
- low liquidity source flags LOW_DEPTH
- missing news remains UNVERIFIED
- Brain Dialogue materializes Pack 1 messages without duplicates
- Pack 1 does not create paper artifacts
- dashboard truth returns `mock_data=false`
- runtime order is Trusted Orderbook -> Pack 1 -> Downstream Recompute

## Tests Run

All commands used `PYTHONPATH=/app` in the Docker test profile because the repo’s runtime imports top-level `gamma_crawler.py`.

New targeted tests:

```text
docker compose --profile test run --rm test sh -lc "PYTHONPATH=/app pytest tests/test_neuron_intelligence_pack1_service.py tests/test_dashboard_neuron_intelligence.py tests/test_neuron_intelligence_runtime_order.py -q"
9 passed, 1 warning
```

System / trusted orderbook / dialogue regressions:

```text
docker compose --profile test run --rm test sh -lc "PYTHONPATH=/app pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_trusted_orderbook_evidence_service.py tests/test_dashboard_trusted_orderbook_truth.py tests/test_brain_dialogue_service.py tests/test_dashboard_brain_dialogue_api.py tests/test_system_life_screen_api.py tests/test_neuron_dialogue_coverage_service.py tests/test_dashboard_neuron_dialogue_api.py tests/test_system_life_neuron_coverage.py -q"
33 passed, 1 warning
```

Paper / capital / lineage safety regressions:

```text
docker compose --profile test run --rm test sh -lc "PYTHONPATH=/app pytest tests/test_paper_execution_service.py tests/test_paper_position_ledger.py tests/test_paper_execution_safety.py tests/test_dashboard_paper_execution_truth.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_dashboard_paper_exit_pnl_truth.py tests/test_paper_capital_account.py tests/test_paper_execution_capital_guards.py tests/test_paper_exit_capital_release.py tests/test_dashboard_paper_capital_truth.py tests/test_paper_lineage_consistency.py tests/test_paper_no_live_safety.py tests/test_paper_no_orphans_duplicates.py -q"
41 passed, 1 warning
```

Downstream / risk / exit regressions:

```text
docker compose --profile test run --rm test sh -lc "PYTHONPATH=/app pytest tests/test_post_side_risk_exit_readiness_service.py tests/test_post_side_risk_exit_runtime.py tests/test_dashboard_risk_exit_readiness_truth.py tests/test_candidate_eligibility_recovery_service.py tests/test_downstream_evidence_recompute_service.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_dashboard_downstream_recompute_truth.py -q"
16 passed, 1 warning
```

## Runtime Smoke

Deployed migration and API image:

```text
docker compose build api migrate
docker compose up -d migrate api
```

OFF smoke:

- `SYSTEM OFF`
- direct Pack 1 run returned `SYSTEM_POWER_OFF`
- evidence rows remained unchanged at `0` before the ON run
- paper/live/real counts unchanged

ON smoke:

- SYSTEM ON for one scheduler window
- scheduler-integrated Pack 1 generated `500` evidence rows
- Brain Dialogue materialized `50` Pack 1 dialogue events
- direct ON Pack 1 run generated another `100` evidence rows for a controlled API/dashboard check
- SYSTEM returned to OFF after smoke

Final smoke counts:

- `neuron_intelligence_runs=4`
- `neuron_intelligence_evidence=600`
- Pack 1 dialogue events `50`
- `paper_intents=6`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`

Dashboard:

- `/dashboard/api/v2/neuron-intelligence` returned `200`
- `mock_data=false`
- latest successful run status `OK`

## Sample Dialogue

- Rules / Wording Neuron: decision=CLEAR; wording_risk=0.200, resolution_clarity=0.650 for market=824952.
- Liquidity Neuron: decision=GOOD_LIQUIDITY; spread=0.0200, exit_liquidity=0.862 for market=824952.
- Fees / Rewards Neuron: decision=EDGE_ERASED_BY_COSTS; estimated_cost=0.0200, net_edge_after_costs=-0.0200 for market=824952.
- Time Neuron: decision=LONG_CAPITAL_LOCK; time_to_resolution=18515798 seconds for market=824952.
- News Neuron: no source-backed news impact evidence found for market=824952; I remain UNVERIFIED.

## Safety Confirmation

- No live orders
- No real orders
- No canonical positions
- No execution code changed
- No risk approval logic changed
- No exit readiness logic changed
- No eligibility logic changed
- Missing news remained unverified
- Long capital lock remained blocked

## Remaining Risks

- News Neuron foundation is present, but runtime lacks source-backed `news_impact_scores` for current candidates, so News remains `UNVERIFIED`.
- Fees currently uses spread and fee snapshot evidence. Opportunity score integration is not implemented in this phase.
- Time evidence marks long-resolution markets as blocked, but downstream Opportunity / Alpha Scoring has not yet been built to consume this evidence.

## Phase Status

GREEN.

Can move to Opportunity / Alpha Scoring: YES, after ChatGPT review.
