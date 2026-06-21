# POLYBOT V2 Neural Mesh Part 4B: First Intelligence Dry Run

## 1. Purpose

Part 4B proves that POLYBOT can run a controlled, non-executing intelligence flow through the Neural Mesh:

```text
Signal -> Impact Link -> Brain Output -> Coordinator Decision -> No-Trade Explanation
```

This phase demonstrates explainable intelligence from existing truth. It does not enable Paper, Shadow, or Live trading.

## 2. Why Dry Run Matters

The Mesh Dashboard showed the system was alive but degraded: signals existed, while impact links, brain outputs, coordinator decisions, and thesis context were sparse or empty.

The First Intelligence Dry Run is the first safe producer that turns existing signals into linked, auditable mesh records without creating executable actions.

## 3. Flow

The dry run processes existing `neuron_signals` with explicit `market_id` values.

For each market group, it can write:

- `signal_market_links`
- `event_entities`, only from existing `neuron_signal_entities`
- `impact_links`
- advisory `brain_outputs`
- non-executing `coordinator_decisions`
- no-trade explanations as `no_trade` brain outputs and coordinator reasoning

The flow is deterministic and conservative. It does not infer profitable opportunity or execute anything.

## 4. Deterministic Producer Rules

Signal-to-market link:

- If `neuron_signals.market_id` is present, create a suggested `signal_market_links` row.
- Confidence is `1.0` because the market ID is explicit.
- `created_by='mesh_dry_run'`.

Signal entities:

- If `neuron_signal_entities` rows exist, create matching `event_entities`.
- No AI extraction is performed.

Impact links:

- Rules/resolution signals create market-scope review links.
- Degraded, stale, missing, or errored signals are adverse or review-oriented.
- Active signals can be linked as watch-only neutral impact.
- Cortex hints are non-executing, such as `WATCH`, `REVIEW`, `NO_TRADE_REVIEW`, or `RISK_REVIEW`.

Brain outputs:

- `context`: watch/caution
- `risk`: risk warning/caution
- `no_trade`: no-trade hint
- `opportunity`: insufficient data/watch only

Coordinator decisions:

- Created by the existing Brain Coordinator.
- `execution_allowed=false`.
- Conservative states are expected: `NO_TRADE`, `RISK_BLOCKED`, `REVIEW_REQUIRED`, `INSUFFICIENT_DATA`, or `WATCH`.

## 5. What Gets Written

Part 4B adds:

- `mesh_dry_runs`
- `mesh_dry_run_items`

The dry run can also write to existing non-executing mesh tables:

- `signal_market_links`
- `event_entities`
- `impact_links`
- `brain_outputs`
- `brain_output_dependencies`
- `coordinator_decisions`
- `coordinator_decision_inputs`
- `coordinator_decision_conflicts`, if conflicts are detected

## 6. What Is Explicitly Not Written

The dry run does not write:

- paper orders
- shadow orders
- live orders
- order intents
- position opens
- position closes
- cancels
- signed requests
- private key material
- Paper readiness approvals

## 7. Safety Rules

The dry run is non-executing by contract.

Required invariants:

- `execution_allowed=false`
- `orders_created=0`
- `paper_ready=false`
- no AI calls
- no live mutation
- no order/cancel/sign path
- no fake market data
- no fake dashboard data

The coordinator DB constraint still enforces `execution_allowed=false`.

## 8. API Routes

Added:

- `POST /mesh/dry-run/first-intelligence`
- `GET /mesh/dry-runs/recent`
- `GET /mesh/dry-runs/{dry_run_id}`
- `GET /dashboard/api/v2/mesh-dry-run`

The Mesh Dashboard also includes the dry-run layer:

- `GET /dashboard/api/v2/mesh`

## 9. Dashboard Fields

`GET /dashboard/api/v2/mesh-dry-run` returns:

- latest dry run
- recent dry runs
- signals processed
- impact links created
- brain outputs created
- coordinator decisions created
- no-trade explanations created
- safety counts

`GET /dashboard/api/v2/mesh` now includes:

- `layers.dry_run`
- `flow.latest_dry_run`
- `mesh_summary.dry_runs_24h`

## 10. Example Dry Run Output

Live dry run:

```json
{
  "status": "OK",
  "mock_data": false,
  "dry_run_id": "dry_9239a9561a5e4e6dbc3ffa8660be406f",
  "mode": "DATA_ONLY",
  "execution_allowed": false,
  "orders_created": 0,
  "markets_processed": 12,
  "signals_processed": 20,
  "signal_market_links_created": 20,
  "impact_links_created": 20,
  "brain_outputs_created": 48,
  "coordinator_decisions_created": 12,
  "no_trade_explanations_created": 12,
  "sample_count": 12,
  "sample_final_state": "RISK_BLOCKED"
}
```

This is a non-executing intelligence chain, not a trading approval.

## 11. How To Run Manually

```powershell
Invoke-RestMethod -Method POST `
  -ContentType "application/json" `
  -Body '{"limit":20,"dry_run_only":true}' `
  http://127.0.0.1:8000/mesh/dry-run/first-intelligence
```

Then inspect:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/mesh/dry-runs/recent
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/mesh-dry-run
Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/mesh
```

## 12. Readiness Impact

Part 4B reduces the “mesh is sitting there” problem by proving a controlled thought flow exists.

It does not make the system Paper-ready. Paper readiness remains false until a later evidence loop proves all required data, risk, exit, thesis, orderbook, and runtime controls.

## 13. What Is Explicitly Not Included

Part 4B does not include:

- Paper trading
- Shadow Live
- Small Live
- order intents
- orders
- AI model calls
- full Opportunity Cortex
- full Risk Governor
- full Exit Cortex
- Strategy Router
- automatic thesis generation
- runtime scheduler loop
- Paper certification

## 14. Next Phase Recommendation

Recommended next phase:

V2 Neural Mesh Part 4C: Dry Run Quality Gates + Paper Readiness Evidence Loop.

Suggested scope:

- score dry-run completeness
- require impact and brain-output coverage by market
- detect missing orderbook/liquidity evidence
- verify thesis readiness coverage
- keep `paper_ready=false` until certification criteria are proven
