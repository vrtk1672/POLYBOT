# POLYBOT V3.2 Shared Awareness Layer

## Purpose

V3.2 adds a shared awareness object for each mesh session. It builds on:

- V3.0 Neural Event Bus
- V3.1 Mesh Sessions

Shared Awareness is derived truth. It summarizes real evidence currently known
for a session and preserves source references back to source records. It does
not replace neural events, mesh sessions, risk, exit, eligibility, capital,
paper, live, order, fill, position, memory, or neuron source tables.

## Tables

Migration `0103_v3_shared_awareness_layer.sql` adds:

- `mesh_shared_awareness`
- `mesh_awareness_sources`

`mesh_shared_awareness` stores one awareness row per session.
`mesh_awareness_sources` stores source refs per awareness domain.

## Domains

Every awareness row supports:

- `NEWS`
- `WHALE`
- `SOCIAL`
- `RULES`
- `LIQUIDITY`
- `ORDERBOOK`
- `FEES`
- `TIME`
- `RISK`
- `EXIT`
- `CAPITAL`
- `PNL`
- `MEMORY`
- `POSITION`
- `CANDIDATE`

Each domain state includes:

- `status`: `PRESENT`, `MISSING`, `STALE`, `PARTIAL`, or `ERROR`
- `summary`
- `confidence`
- `source_count`
- `latest_source_at`
- `source_refs`

Missing evidence remains `MISSING`. No domain is invented.

## Freshness Rules

Simple V3.2 thresholds:

- Orderbook and liquidity: 5 minutes
- Fees: 6 hours
- Risk, exit, candidate, position, capital, PnL, news, whale, social, time: 24 hours
- Rules and memory: 30 days

News impact TTL is honored when a source row provides `ttl_seconds`.

## Builder

`SharedAwarenessService` can:

- refresh one session
- refresh a list of sessions
- process active/open/stale sessions
- return dashboard summary truth
- return session detail truth

The builder reads:

- linked `neural_events`
- `neuron_intelligence_evidence`
- `trusted_orderbook_evidence_links`
- `orderbook_snapshots`
- `rules_analysis`
- `fee_snapshots`
- `news_impact_scores`
- `whale_events`
- `market_memory_v2`
- `risk_decisions`
- `exit_plans`
- `paper_eligibility_candidates`
- `paper_accounts`
- `paper_capital_ledger`
- `paper_positions`
- `paper_trade_ledger`
- `paper_daily_pnl`

Only existing rows are summarized.

## Runtime Integration

Flow:

```text
Neural Event published
-> Mesh Session resolved
-> Shared Awareness refreshed for linked session
```

If the shared awareness tables do not exist yet, the integration returns
`MISSING_TABLES` and does not block V3.0/V3.1 behavior.

SYSTEM OFF blocks new event publishing, which blocks runtime awareness mutation.
Dashboard reads remain allowed.

## Dashboard

Added endpoints:

- `GET /dashboard/api/v2/shared-awareness`
- `GET /dashboard/api/v2/shared-awareness/{session_id}`

Both return `mock_data=false`.

## Dialogue

Brain Dialogue materializes source-backed awareness messages from
`mesh_shared_awareness`.

Examples:

- `Shared Awareness: Updated MARKET_SESSION awareness with ORDERBOOK/CAPITAL evidence.`
- `Shared Awareness: NEWS, WHALE, SOCIAL... missing for session; domains remain MISSING.`
- `Shared Awareness: Capital state attached to position session.`

## Safety Boundary

Shared Awareness does not:

- build brain reaction handlers
- evolve the coordinator
- alter Risk, Exit, or Eligibility decisions
- create paper/live orders
- create fills
- create positions
- mutate paper capital
- invent news, whale, social, or memory evidence
- enable live or shadow
