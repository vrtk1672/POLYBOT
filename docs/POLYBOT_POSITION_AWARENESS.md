# POLYBOT V3.6 Position Awareness

## Purpose

V3.6 makes paper positions first-class nervous-system entities without changing execution.

Position Awareness is derived truth. It reads existing source-backed records and writes position visibility for the brain mesh:

- `paper_positions`
- linked `neural_events`
- `mesh_shared_awareness`
- `capital_brain_evaluations`
- `mesh_coordinator_decisions`

It does not create orders, fills, positions, exits, paper intents, capital ledger entries, or live actions.

## Model

Migration: `0107_v3_position_awareness.sql`

Tables:

- `position_awareness`: one current derived awareness row per position.
- `position_reactions`: source-backed observations about changing position context.
- `position_context_sources`: source links proving where awareness/reactions came from.

## Reaction Types

Supported reactions:

- `ADVERSE_NEWS`
- `POSITIVE_NEWS`
- `WHALE_ENTRY`
- `WHALE_EXIT`
- `LIQUIDITY_DROP`
- `LIQUIDITY_IMPROVED`
- `SPREAD_WIDENED`
- `SPREAD_IMPROVED`
- `RISK_INCREASED`
- `RISK_DECREASED`
- `EXIT_DEGRADED`
- `EXIT_IMPROVED`
- `PNL_RISING`
- `PNL_FALLING`
- `CAPITAL_PRESSURE`
- `POSITION_AGING`
- `NO_REACTION`

Reactions are observations only.

## Runtime Integration

The V3 runtime chain is now:

1. Neural event published.
2. Mesh session resolved.
3. Shared awareness refreshed.
4. Capital Brain evaluates.
5. Position Awareness refreshes for position sessions.
6. Multi-Brain Consumption consumes awareness, including `POSITION_AWARENESS` for Position Brain.
7. Mesh Coordinator judges the opinion bundle.
8. Position Awareness refreshes again to attach coordinator visibility.

SYSTEM OFF blocks public Position Awareness mutation and Neural Event publishing. Dashboard reads remain allowed.

## Dashboard

Routes:

- `GET /dashboard/api/v2/positions-awareness`
- `GET /dashboard/api/v2/positions-awareness/{position_id}`

Both return `mock_data=false`.

## Dialogue

`BrainDialogueService` materializes source-backed messages from:

- `position_awareness`
- `position_reactions`

Example messages:

- `Position Awareness: Position <id> awareness updated.`
- `Position Awareness: Position <id> received ADVERSE_NEWS.`

## Safety

Position Awareness never writes:

- `live_orders`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_intents`
- `orders_v2`
- `fills_v2`
- canonical `positions`
- `risk_decisions`
- `exit_plans`
- `paper_eligibility_candidates`
- legacy `coordinator_decisions`
- `brain_outputs`
