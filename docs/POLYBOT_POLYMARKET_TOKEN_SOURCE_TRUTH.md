# POLYBOT Polymarket Token Source Truth

Date: 2026-06-02

## Purpose

This phase adds source-backed token truth for Polymarket outcome tokens and
precise classification for CLOB `/book` `TOKEN_NOT_FOUND`.

## Mapping Contract

- CLOB `/book` is requested by outcome token id / `asset_id`.
- Response `asset_id` must equal the requested token.
- Response `market` must equal the condition id when known.
- YES maps to `yes_token_id`.
- NO maps to `no_token_id`.
- `market_id`, `condition_id`, and outcome token id are stored separately.

## Token Source Rules

Gamma fields are parsed in this order:

- `clobTokenIds`
- `clob_token_ids`
- `tokenIds`
- `outcomeTokens`
- structured `tokens`

Outcome labels are used when present. If labels are ambiguous or do not map to
YES/NO, the token is blocked rather than trusted.

## Rejection Classes

- `NO_MARKET_ID`
- `NO_CONDITION_ID`
- `NO_SIDE`
- `NO_YES_NO_TOKEN_MAPPING`
- `TOKEN_JSON_ARRAY_PARSE_BUG`
- `TOKEN_OUTCOME_ORDER_MISMATCH`
- `AMBIGUOUS_TOKEN_MAPPING`
- `CONDITION_ID_USED_AS_TOKEN`
- `MARKET_ID_USED_AS_TOKEN`
- `MARKET_CLOSED`
- `ACCEPTING_ORDERS_FALSE`
- `NOT_CLOB_TRADABLE`
- `CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN`
- `INTERNAL_STALE_TOKEN`
- `CLOB_NO_BOOK`
- `CONDITION_ID_MISMATCH`
- `TOKEN_MISMATCH`

## API

- `GET /dashboard/api/v2/polymarket-token-truth`
- `POST /polymarket-token-truth/recover`

The recovery endpoint is blocked while SYSTEM is OFF. It is evidence-only and
does not create paper intents, orders, fills, positions, live orders, or real
orders.

