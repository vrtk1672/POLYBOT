# POLYBOT Fresh Seed To Paper Path

Status: implemented as a controlled Paper-path bridge.

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`.

## Purpose

Fresh `BOOK_VERIFIED` market seeds now have a bounded path into the canonical Paper decision stack:

`fresh_candidate_seeds -> source-backed signal -> brain output -> coordinator decision -> thesis_profiles -> risk_decisions -> exit_plans -> paper_eligibility_candidates -> paper_intents`

The bridge does not execute trades. It stops at Paper Intent creation.

## Safety Rules

- Live and shadow are not enabled.
- No Polymarket order/write endpoint is called.
- No paper orders, fills, positions, PnL, capital balances, or capital ledger rows are created by this bridge.
- Paper Intents may be created only by `PaperIntentGateService`.
- Seeds are blocked when trusted orderbook evidence is missing, stale, too wide, illiquid, rejected, or not source-backed.

## Conversion Requirements

A seed may enter the Paper path only when:

- `fresh_candidate_seeds.status = 'BOOK_VERIFIED'`
- `market_id`, `condition_id`, `side`, and `expected_token_id` exist
- a trusted orderbook link exists
- a fresh OK orderbook snapshot exists
- spread and liquidity meet existing Risk constraints
- the conversion has not already been accounted

## Downstream Gates

The bridge writes source-backed lineage rows and then calls official services:

- `ThesisProfileService.build_profiles`
- `RiskCoreService.evaluate_risk`
- `ExitFoundationService.build_exit_plans`
- `PaperEligibilityService.evaluate_candidates`
- `PaperIntentGateService.build_intents`

No service constructor is called with guessed dependencies.

## Statuses

Conversion rows live in `fresh_seed_candidate_conversions`.

Important statuses:

- `CANDIDATE_CREATED`
- `THESIS_CREATED`
- `RISK_CREATED`
- `EXIT_CREATED`
- `ELIGIBILITY_CREATED`
- `PAPER_INTENT_CREATED`
- `BLOCKED_NO_TRUSTED_ORDERBOOK`
- `BLOCKED_RISK`
- `BLOCKED_EXIT`
- `BLOCKED_ELIGIBILITY`
- `BLOCKED_STALE_MARKET`

## API

- `GET /dashboard/api/v2/fresh-seed-paper-path`
- `POST /fresh-seed-paper-path/run`

The run endpoint respects SYSTEM ON/OFF. Mutating conversion is blocked while SYSTEM OFF; dry-run may inspect without mutation.

## Runner Note

`scripts/run_active_30m_observation.py` now calls the bridge through the HTTP endpoint as part of the active cycle, after source/identity/CLOB/watcher refresh and before paper execution.
