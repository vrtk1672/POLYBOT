# POLYBOT Neuron Dialogue Coverage Build Report

## Purpose

Add independent, real source-backed neuron voices to the existing Brain Dialogue Feed and System Life Screen.

## Current Reality Found

- `brain_dialogue_events` already existed and was the correct dialogue truth table.
- `neuron_registry` had 22 registered neurons.
- Recent runtime source rows existed for Market, Orderbook, Liquidity, Time, Fees, AI/Context via brain outputs, and paper Position.
- News and Social source tables existed but registry entries were disabled and runtime rows were absent.
- Whale source tables existed but runtime rows were absent.
- Capital source tables existed but runtime rows were absent.
- Rules source rows existed, with fresh `market_rules`/wording source state and older `rules_analysis` dialogue source rows.

## Files Created

- `tests/test_neuron_dialogue_coverage_service.py`
- `tests/test_neuron_dialogue_sources.py`
- `tests/test_dashboard_neuron_dialogue_api.py`
- `tests/test_system_life_neuron_coverage.py`
- `tests/test_neuron_dialogue_on_off_safety.py`
- `docs/POLYBOT_NEURON_DIALOGUE_COVERAGE.md`
- `docs/POLYBOT_NEURON_DIALOGUE_COVERAGE_BUILD_REPORT.md`

## Files Changed

- `app/services/brain_dialogue.py`
- `app/api/routes.py`
- `tests/brain_dialogue_fixtures.py`

## DB Changes

No migration was required. Existing `brain_dialogue_events` fields and unique dedupe constraint were reused.

## Runtime Integration

`BrainDialogueService.materialize_recent()` now runs `_materialize_neuron_dialogue()` under SYSTEM ON after existing component materializers. SYSTEM OFF still returns before normal component/neuron materialization.

## API / Dashboard Changes

- Added `component_type`, `status`, and `silent` filters to `/dashboard/api/v2/brain-dialogue`.
- Added `GET /dashboard/api/v2/neuron-dialogue`.
- Extended `/dashboard/api/v2/system-life` with `neuron_coverage` and top-level neuron coverage counts.

## Tests Run

- `tests/test_neuron_dialogue_coverage_service.py tests/test_neuron_dialogue_sources.py tests/test_dashboard_neuron_dialogue_api.py tests/test_system_life_neuron_coverage.py tests/test_neuron_dialogue_on_off_safety.py -q`: 14 passed.
- `tests/test_brain_dialogue_service.py tests/test_brain_dialogue_materialization.py tests/test_dashboard_brain_dialogue_api.py tests/test_system_life_screen_api.py tests/test_brain_dialogue_on_off_safety.py tests/test_component_silence_detection.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py -q`: 21 passed.
- `tests/test_deterministic_side_evidence_service.py tests/test_candidate_eligibility_recovery_service.py tests/test_post_side_risk_exit_readiness_service.py tests/test_post_side_risk_exit_runtime.py tests/test_paper_execution_service.py tests/test_paper_position_ledger.py tests/test_paper_execution_safety.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py -q`: 37 passed.
- `tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py -q`: 13 passed.

## Runtime Smoke

- API rebuilt/restarted with `docker compose build api` and `docker compose up -d api`.
- `/healthz`: 200.
- `/runtime/health`: 200.
- `/dashboard/api/v2/brain-dialogue?component_type=neuron`: 200, `mock_data=false`.
- `/dashboard/api/v2/neuron-dialogue`: 200, `mock_data=false`.
- `/dashboard/api/v2/system-life`: 200, `mock_data=false`.
- SYSTEM OFF smoke: neuron dialogue count stayed `277 -> 277`.
- SYSTEM ON smoke: neuron dialogue count moved `277 -> 447`.
- Dashboard duplicate read proof: neuron dialogue count stayed `447 -> 447`.

## Runtime Counts

Before ON smoke:
- `brain_dialogue_events=3883`
- `neuron_dialogue_events=277`
- `neuron_components_speaking=8`
- `paper_intents=3`
- `paper_orders=3`
- `paper_fills=3`
- `paper_positions=3`
- `live_orders=0`
- `real_orders=0`

After ON smoke:
- `brain_dialogue_events=4178`
- `neuron_dialogue_events=447`
- `neuron_components_speaking=8`
- `paper_intents=3`
- `paper_orders=3`
- `paper_fills=3`
- `paper_positions=3`
- `live_orders=0`
- `real_orders=0`

## Runtime Neuron Coverage

- `total_neurons=12`
- `neuron_components_speaking=7` in current System Life freshness window
- `neuron_components_silent=3`
- `neuron_components_missing=0`
- `neuron_components_disabled=2`

Disabled/silent examples:
- News Neuron: `DISABLED_IN_NEURON_REGISTRY`.
- Social / Hype Neuron: `DISABLED_IN_NEURON_REGISTRY`.
- Whale Neuron: `SILENT_NO_SOURCE_RECORD`.
- Capital Neuron: `SILENT_NO_SOURCE_RECORD`.
- Position Neuron: `SILENT_STALE_SOURCE_RECORD`.

## Sample Real Neuron Events

- Market Neuron from `market_snapshots`.
- Orderbook Neuron from `orderbook_snapshots`.
- Liquidity Neuron from `liquidity_snapshots`.
- Time Neuron from `market_snapshots`.
- Rules / Wording Neuron from `rules_analysis`.
- Fees / Rewards Neuron from `fee_snapshots`.
- AI / Context Neuron from `ai_decision_logs`.
- Position Neuron from `paper_positions`.

Additional recent source-backed events were present for multiple Market/Orderbook/Liquidity/Fees/Time rows.

## Safety Confirmation

- No live orders were created.
- No real orders were created.
- Paper intents/orders/fills/positions were unchanged during smoke.
- Dialogue generation did not mutate trading decisions or execution state.

## Remaining Risks

- Some registered neurons beyond the 12 supported voices still have gate/system dialogue rather than independent `component_type=neuron` adapters.
- News and Social are disabled in the registry and have no runtime source rows.
- Whale and Capital have source schemas but no current runtime source rows.

## Next Recommended Step

Paper Dashboard + Regression + Soak Readiness can proceed after review.
