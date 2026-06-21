# POLYBOT Payout / Odds / Resolution Value Model

## Purpose

This phase adds a derived economic truth layer for Polymarket binary outcome prices. POLYBOT can now represent a price as implied probability, stake-to-shares conversion, payout if the token resolves to 1.0, profit if win, max loss, risk/reward, break-even probability, and position hold-to-resolution value.

The model is observational. It does not create trades, force intents, alter risk or exit thresholds, mutate balances, or infer fake fair probability.

## Security Governance

`SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR`

This status does not block the phase. The implementation does not print secrets, raw environment, or raw Docker configuration.

## Data Model

Migration `0119_payout_odds_resolution_value.sql` adds:

- `payout_odds_evaluations`
- `payout_odds_sources`

Supported subjects:

- `FRESH_SEED`
- `PAPER_CANDIDATE`
- `PAPER_INTENT`
- `PAPER_POSITION`
- `PAPER_CLOSE`

Rows are derived truth only. They link to source tables through `source_refs_json` and `payout_odds_sources`.

## Formulas

For candidate/intent price `p`, where `0 < p < 1`, and stake `S`:

- `implied_probability = p`
- `shares_if_buy = S / p`
- `payout_if_win = shares_if_buy`
- `profit_if_win = payout_if_win - S`
- `max_loss = S`
- `risk_reward = profit_if_win / max_loss`
- `break_even_probability = p`

For a position:

- `cost_basis = entry_price * quantity`
- `payout_if_win = quantity`
- `profit_if_win_from_entry = payout_if_win - cost_basis`
- `max_loss_from_entry = cost_basis`
- `risk_reward = profit_if_win_from_entry / cost_basis`

`fair_probability` and `expected_value` remain `NULL` unless a real source-backed fair probability exists.

## Price Sources

Candidate/seed/intents use the best available executable buy price:

1. `paper_intents.intended_price`
2. `evidence.orderbook_best_ask`
3. `evidence.source_evidence.orderbook_best_ask`
4. `orderbook_snapshots.best_ask`
5. seed verified price, if present
6. mid price fallback only when no ask is available

Positions use `paper_positions.avg_entry` and quantity for entry payout. Current exit value is included when a current same-side best bid exists; otherwise `EXIT_PRICE_UNAVAILABLE` is recorded.

## Stake Rules

- Actual intended notional/cost is used when available.
- Paper intents use `evidence.intended_notional`.
- Position evaluations use entry cost basis.
- Seed/candidate evaluations without actual stake use `PAYOUT_EVAL_DEFAULT_STAKE_USD` or default `100`.

## Integrations

- Fresh Seed Paper Path invokes payout/odds evaluation after downstream candidates/intents are built.
- Paper Intent creation evaluates new intents after upsert.
- Paper Execution evaluates new positions after the capital lock has been created.
- Paper Trade Forensics exposes payout/odds lineage and fields.
- Capital Brain, Exit Foundation, and Mesh Coordinator expose payout/odds summaries as observational-only inputs.
- Brain Dialogue materializes source-backed payout/odds messages.

## API

- `GET /dashboard/api/v2/payout-odds`
- `GET /dashboard/api/v2/payout-odds/{evaluation_id}`
- `POST /payout-odds/evaluate`

`POST /payout-odds/evaluate` creates only derived reasoning rows. It is safe while SYSTEM is OFF and reports trading mutation checks in the response.

## Safety

The evaluator does not mutate:

- paper intents
- paper orders
- paper fills
- paper positions
- paper closes
- paper capital ledger
- live orders
- orders/fills v2
- canonical positions
- capital balances

Missing price produces `MISSING_PRICE`. Invalid price produces `INVALID_PRICE`. Neither fabricates payout or EV.
