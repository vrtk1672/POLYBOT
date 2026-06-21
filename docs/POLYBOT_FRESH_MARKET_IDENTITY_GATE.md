# POLYBOT Fresh Market Identity Gate

Date: 2026-06-03

## Purpose

The Fresh Market Identity Gate prevents candidates from moving toward Paper on
stale or incomplete Polymarket identity.

Rule: no fresh market identity, no Paper.

This phase does not request or trust CLOB books. It prepares current
market/condition/side/token identity so the next phase can request `/book` by
the resolved outcome token.

## Security Governance

`SECURITY_GOVERNANCE_STATUS=YELLOW_ACCEPTED_BY_OPERATOR`

The prior credential exposure remains an accepted governance risk for this
phase. The gate still does not print secrets, does not read raw `.env`, and does
not require raw compose output.

## Fresh Identity Model

A candidate is `FRESH_VERIFIED` only when:

- `market_id` exists.
- Current Gamma returns exactly one market for that id.
- `condition_id` exists and remains separate from `market_id`.
- Candidate side is deterministic `YES` or `NO`.
- Current Gamma provides deterministic YES/NO token mapping.
- `expected_token_id` matches the candidate side.
- Market is active/open.
- `accepting_orders` is not false.

Any missing or unsafe input records a blocking status instead of inventing
identity.

## Status Values

- `FRESH_VERIFIED`
- `STALE_MARKET`
- `MISSING_MARKET_ID`
- `MISSING_CONDITION_ID`
- `MISSING_SIDE`
- `MISSING_TOKEN_MAPPING`
- `AMBIGUOUS_MATCH`
- `CLOSED_MARKET`
- `ACCEPTING_ORDERS_FALSE`
- `UNRECOVERABLE`

## Resolver Rules

- A local `markets_v2` row is not enough for freshness.
- Current Gamma lookup is required for a fresh verdict.
- Missing `market_id` may be recovered only from deterministic
  `signal_market_links`.
- Missing side may be recovered only from an existing deterministic side field
  on a trusted link.
- Ambiguous market links are not written.
- Gamma token fields are parsed through the existing token truth parser.
- YES maps to `yes_token_id`; NO maps to `no_token_id`.
- Current Gamma `NOT_FOUND` marks the candidate `STALE_MARKET`.

## API

- `GET /dashboard/api/v2/fresh-market-identity`
- `POST /fresh-market-identity/recover`

POST input:

- `limit`
- `dry_run`
- `include_stale`
- `cycle_id`

Mutation is blocked while SYSTEM is OFF. Dry-run can inspect without candidate
updates.

## Persistence

Migration `0112_fresh_market_identity_gate.sql` adds:

- `fresh_market_identity_runs`
- `fresh_market_identity_traces`
- candidate annotations:
  - `identity_status`
  - `identity_verified_at`
  - `identity_source`
  - `expected_token_id`
  - `identity_blocker_reason`

These are audit/gate fields, not paper artifacts.

## Dialogue

`BrainDialogueService` materializes source-backed dialogue from
`fresh_market_identity_traces`:

- verified current identity
- missing side
- stale market
- other precise blocker reasons

Dashboard reads do not create fake dialogue.

## Safety

The gate does not create:

- paper intents
- paper orders
- paper fills
- paper positions
- real orders
- live orders
- trusted orderbook links
- orderbook snapshots

It does not enable live or shadow.
