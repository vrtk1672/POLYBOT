# POLYBOT V3.3 Multi-Brain Consumption Layer

V3.3 adds a derived consumption layer on top of V3.0 Neural Events, V3.1 Mesh Sessions, and V3.2 Shared Awareness.

This layer does not create trading truth. It does not write `brain_outputs`, `coordinator_decisions`, `risk_decisions`, `exit_plans`, eligibility outcomes, paper intents, orders, fills, positions, or capital ledger rows.

## Model

Migration `0104_v3_multi_brain_consumption.sql` adds:

- `mesh_brain_opinions`
- `mesh_brain_consumption_sources`
- `mesh_coordinator_input_bundles`

Opinions are session-scoped, source-backed, and deterministic. Each opinion preserves consumed domains, missing domains, stale domains, supporting sources, opposing sources, and a stance.

Coordinator input bundles are observer artifacts. They collect session opinions and expose `source_brain_count`, stance summaries, and basic conflicts for future Coordinator Evolution.

## Brain Consumers

Initial consumers:

- `RISK_BRAIN`: RULES, LIQUIDITY, ORDERBOOK, FEES, TIME, NEWS, CAPITAL.
- `EXIT_BRAIN`: EXIT, RISK, LIQUIDITY, ORDERBOOK, TIME, POSITION, PNL.
- `CAPITAL_BRAIN`: CAPITAL, FEES, TIME, PNL, POSITION, RISK, EXIT.
- `CONTEXT_BRAIN`: NEWS, WHALE, SOCIAL, RULES, MEMORY, CANDIDATE.
- `POSITION_BRAIN`: POSITION, PNL, RISK, EXIT, NEWS, LIQUIDITY. Runs only when position context exists.
- `COORDINATOR_OBSERVER`: consumes stored opinions and creates a coordinator-visible bundle.

## Stances

Supported stances:

- `SUPPORT`
- `CAUTION`
- `BLOCK`
- `NO_SIGNAL`

Rules are intentionally simple:

- Missing key domains produce `NO_SIGNAL` or `CAUTION`.
- Missing news, whale, or social evidence does not block by itself.
- Stale orderbook or liquidity produces caution.
- Missing capital or zero available capital blocks the Capital Brain.
- Source-backed support and block stances in the same session create a basic conflict.

## Runtime Integration

Expected flow:

1. Neural event is published.
2. Mesh session is resolved.
3. Shared awareness is refreshed.
4. Multi-brain consumption runs for that session.
5. Brain opinions are upserted.
6. Coordinator input bundle is upserted.
7. Dialogue can materialize source-backed opinion and bundle messages.

`SharedAwarenessService.refresh_session_with_conn()` invokes `MultiBrainConsumptionService.consume_session_with_conn()` after awareness persistence. Public mutation methods still require SYSTEM ON.

## Dashboard

Routes:

- `GET /dashboard/api/v2/multi-brain-consumption`
- `GET /dashboard/api/v2/multi-brain-consumption/{session_id}`

Both return `mock_data=false`.

## Dialogue

`BrainDialogueService.materialize_recent()` materializes:

- `mesh_brain_opinions`
- `mesh_coordinator_input_bundles`

Messages are source-backed only.

Examples:

- `Risk Brain: Consumed CAPITAL and produced CAUTION.`
- `Capital Brain: Consumed CAPITAL, RISK and produced SUPPORT.`
- `Coordinator Observer: Collected 4 brain opinions.`
