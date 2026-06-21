# POLYBOT Trusted Orderbook Evidence Hardening

## Purpose

This phase makes candidate orderbook evidence deterministic, side-aware, token-aware, fresh, auditable, and safe for Risk, Exit, Eligibility, Paper Intent, and Paper Execution consumers.

It does not approve risk, complete exits, force eligibility, create paper artifacts, or enable live/shadow execution.

## Runtime Contract

Trusted orderbook resolution runs only when:

- `SYSTEM ON` is active.
- `StateGovernor` allows `RUN_INTELLIGENCE`.
- Candidate has a deterministic side (`YES` or `NO`).
- Candidate has a trusted signal-market binding.

`SYSTEM OFF` returns `BLOCKED` and checks zero candidates.

## Trust Criteria

An orderbook snapshot is trusted only when all criteria pass:

- candidate `market_id` exists.
- candidate `side` is `YES` or `NO`.
- market has deterministic `yes_token_id` and `no_token_id`.
- side expected token is known.
- signal-market link is confirmed/suggested, runtime-safe, not review-required, and confidence >= `0.8`.
- latest orderbook is for candidate `market_id` and expected side token.
- orderbook `snapshot_status = OK`.
- orderbook is not stale.
- orderbook age is <= `180` seconds.
- `best_bid` and `best_ask` exist.
- `mid_price` exists or is deterministically calculated from bid/ask.
- `spread` exists or is deterministically calculated from bid/ask.
- spread <= `0.08`.
- liquidity score is either absent or >= `0.25`.

## Rejection Reasons

The resolver records exact reasons:

- `MISSING_MARKET_ID`
- `MISSING_SIDE`
- `MISSING_YES_NO_TOKEN_MAPPING`
- `MISSING_EXPECTED_TOKEN`
- `NO_ORDERBOOK_FOR_MARKET`
- `NO_ORDERBOOK_FOR_TOKEN`
- `ORDERBOOK_STALE`
- `TOKEN_SIDE_MISMATCH`
- `MISSING_BEST_BID`
- `MISSING_BEST_ASK`
- `MISSING_MID_PRICE`
- `MISSING_SPREAD`
- `SPREAD_TOO_WIDE`
- `LIQUIDITY_TOO_LOW`
- `WEAK_BINDING`
- `OTHER_EXACT_REASON`

## Persistence

New canonical evidence tables:

- `trusted_orderbook_evidence_links`
- `trusted_orderbook_evidence_runs`

Trusted links preserve:

- candidate id
- market id
- side
- expected token
- orderbook snapshot id/ref
- orderbook token
- bid/ask/mid/spread/liquidity
- age and freshness threshold
- trust status and reason
- source evidence JSON

## Runtime Order

`MarketService.refresh()` now runs:

1. Brain Mesh Activation
2. Evidence Refresh
3. Deterministic Side Evidence Recovery
4. Trusted Orderbook Evidence Hardening
5. Downstream Evidence Recompute
6. Post-Side Risk/Exit Readiness
7. Candidate Eligibility Recovery
8. Paper Intent Gate
9. Safe Paper Execution
10. Paper Exit/PnL
11. Brain Dialogue

## Dashboard

New endpoint:

- `GET /dashboard/api/v2/trusted-orderbook`

Manual diagnostic endpoint:

- `POST /trusted-orderbook/resolve`

Dashboard truth includes mock-free status, latest run, trusted match counts, rejected reason counts, sample trusted/rejected links, candidate trace, and live/real order safety counts.

## Dialogue

`Orderbook Neuron` now emits source-backed dialogue for:

- trusted orderbook linked to candidate
- orderbook evidence rejected with reason

Repeated dashboard reads do not create events; dialogue remains source-record deduplicated.

## Safety

No live/shadow enablement was added.
No real orders, fills, or canonical positions are created.
Paper state is not mutated by the resolver; only evidence/linkage/run records are written.

