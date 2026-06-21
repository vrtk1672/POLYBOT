# Trade Thesis Dynamic Capital Efficiency Report

## Purpose

This pass adds a DATA_ONLY Trade Thesis Intelligence layer so POLYBOT can distinguish hold-to-resolution opportunities from evidence-backed early-exit trades before Risk-Capital evaluates capital efficiency.

The prior capital model was mathematically consistent, but it used market-resolution hold time for every candidate. That made long-dated tactical opportunities look capital-inefficient even when the intended trade was an early exit.

## Trade Thesis Architecture

Implemented:

- `app/services/trade_thesis_engine.py`
- `trade_thesis_evaluations` DATA_ONLY table
- deterministic thesis classifier
- safe AI fallback marker (`ai_review_state=UNAVAILABLE`)
- dynamic hold-time trace in `capital_efficiency_evaluations.metadata_json`
- Control Center endpoint: `GET /dashboard/api/v2/control/trade-thesis`

The classifier writes only evidence/thesis rows. It does not create intents, orders, fills, positions, capital reservations, or balance mutations.

## Thesis Types

Supported thesis types:

- `HOLD_TO_RESOLUTION`
- `CATALYST_EARLY_EXIT`
- `NEWS_REACTION`
- `EVENT_WINDOW_TRADE`
- `MISPRICING_REVERSION`
- `ORDERBOOK_PRESSURE_TRADE`
- `MOMENTUM_CONTINUATION`
- `REVERSAL_OVERREACTION`
- `WHALE_FOLLOW`
- `LIQUIDITY_SPREAD_OPPORTUNITY`
- `NO_VALID_THESIS`
- `UNKNOWN`

## Exit Intent Model

Supported exit intents:

- `HOLD_TO_RESOLUTION`
- `EARLY_EXIT`
- `PRICE_TARGET_EXIT`
- `TIME_STOP_EXIT`
- `CATALYST_REACTION_EXIT`
- `EVENT_WINDOW_EXIT`
- `MOMENTUM_EXIT`
- `REVERSAL_EXIT`
- `WHALE_FOLLOW_EXIT`
- `LIQUIDITY_EXIT`
- `UNKNOWN_EXIT`

Early-exit hold time is only used when the thesis status is `THESIS_SUPPORTED` and exit intent is not `UNKNOWN_EXIT`.

## Dynamic Hold-Time Logic

Capital efficiency now records:

- original resolution hold time
- thesis expected hold time
- hold-time source
- dynamic hold-time applied true/false
- original reward-per-dollar-hour
- dynamic reward-per-dollar-hour

The formula remains unchanged:

`reward_per_dollar_hour = potential_reward / (capital_locked * hold_time_hours)`

Only the hold-time input can change, and only when backed by a supported thesis.

## AI Review Usage

AI is not used as a fake source. In this pass the system uses deterministic fallback and marks:

- `ai_review_state=UNAVAILABLE`
- `no_ai_sources_added=true`
- `no_probability_fabricated=true`

## Capital Efficiency Integration

`CapitalEfficiencyService` now reads the latest `trade_thesis_evaluations` row for the same subject. If it is supported, the service uses `expected_hold_time_hours`; otherwise it keeps resolution hold time.

Risk still blocks when capital efficiency remains weak under existing policy.

## Endpoint Result

Added:

- `/dashboard/api/v2/control/trade-thesis`
- `/dashboard/api/v2/trade-thesis`

Updated trace surfaces:

- `/dashboard/api/v2/control/paper-actionability`
- `/dashboard/api/v2/control/decision-propagation-trace`

## Tests Run

Initial local results:

- `tests/test_trade_thesis_classification.py tests/test_dynamic_hold_time_capital_efficiency.py tests/test_early_exit_intent_engine.py tests/test_trade_thesis_actionability_trace.py -q`: 9 passed
- related risk/actionability tests: 31 passed
- broad selector: 41 passed, 14 skipped, 2017 deselected
- compileall: passed

## Controlled Verification

Completed.

Deployment and restart:

- `docker compose build api`: passed.
- `docker compose up -d --no-deps api`: API recreated and started.
- `GET /healthz`: `status=ok`, `ready=true`.
- `GET /runtime/health`: reachable.
- `GET /dashboard/api/v2/control/trade-thesis`: reachable.

Controlled SYSTEM ON run:

- SYSTEM ON was used only for DATA_ONLY verification.
- Paper Simulation remained OFF.
- Full Monitor Run was not started.
- Shadow and Live remained disabled.
- Source refresh cycles advanced from 88 to 95 during the measured run.
- Trade thesis evaluations increased from 220 to 380 during the measured run.
- Capital efficiency evaluations increased from 5507 to 5791 during the measured run.
- Risk evidence mesh evaluations increased from 4928 to 5372 during the measured run.
- Lifecycle decisions increased from 14006 to 14290 during the measured run.

Trade thesis endpoint after the run reported:

- `total_evaluations`: 380
- `supported_count`: 229
- `watch_count`: 40
- `rejected_count`: 111
- `early_exit_supported_count`: 225
- `ai_unavailable_count`: 380
- thesis distribution: `MISPRICING_REVERSION=265`, `NO_VALID_THESIS=111`, `HOLD_TO_RESOLUTION=4`

The final SYSTEM ON window produced candidates with `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`. A representative qualifying candidate was:

- candidate_id: `eligibility_exit_risk_thesis_coord_b473155cdb6e49c5b5d8b5db23ca32b9`
- market_id: `691547`
- side: `YES`
- edge_state: `EDGE_SUPPORTED`
- edge_score: `1.0`
- source_backed: `true`
- risk_usable: `true`
- capital opinion: `CAPITAL_OK`
- lifecycle opinion: `LIFECYCLE_ALLOWED`
- operational paper execution state: `EXECUTION_DISABLED_PAPER_OFF`
- supporting source types: payout, signal quality, signal processing, orderbook context

After SYSTEM OFF cleanup, `/runtime/health` reported:

- `system_power`: `OFF`
- `runtime_life_state`: `STOPPED`
- `supervisor_state`: `STOPPED`
- `current_mode`: `DATA_ONLY`

After SYSTEM OFF, actionability endpoints correctly returned no currently actionable runtime candidate because runtime work was blocked by SYSTEM OFF. The Phase 10 readiness finding is based on the controlled SYSTEM ON window before cleanup.

## Counts Before / After

Forbidden artifact counts:

| Table | Before | After |
|---|---:|---:|
| paper_intents | 20 | 20 |
| paper_orders | 12 | 12 |
| paper_fills | 9 | 9 |
| paper_positions | 12 | 12 |
| paper_position_closes | 9 | 9 |
| live_orders | 0 | 0 |
| positions | 0 | 0 |

DATA_ONLY decision counts:

| Table | Before | After |
|---|---:|---:|
| source_refresh_cycles | 88 | 96 |
| trade_thesis_evaluations | 220 | 400 |
| capital_efficiency_evaluations | 5507 | 5811 |
| risk_evidence_mesh_evaluations | 4928 | 5412 |
| lifecycle_governance_decisions | 14006 | 14310 |
| exit_plans | 20913 | 20942 |
| brain_outputs | 45777 | 46992 |
| coordinator_decisions | 26025 | 26284 |

The extra post-run increments occurred as the final supervisor cycle completed before SYSTEM OFF took full effect. All increments are DATA_ONLY evidence/report rows.

## READY_FOR_PHASE_10

YES.

At least one candidate reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED` during the controlled DATA_ONLY SYSTEM ON window. Paper Simulation OFF remained the operational execution blocker. No paper, shadow, or live artifacts were created.

## Safety Result

Safety result: GREEN.

- No Paper/Shadow/Live activation was introduced by the implementation.
- The new rows are DATA_ONLY.
- No fake trade thesis, early-exit thesis, hold time, exit target, reward, or probability was introduced.
- AI did not invent sources or probabilities.
- Risk, Exit, Lifecycle, and Capital thresholds were not loosened.
- Capital balances were not mutated.
- No historical data was deleted.
- No destructive DB action was performed.
- SYSTEM OFF cleanup completed successfully.
