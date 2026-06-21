# POLYBOT V2 Neural Mesh Part 2B Brain Mesh / Cognitive Coordinator

## 1. Purpose

V2 Neural Mesh Part 2B adds the first Cognitive Coordinator layer.

The Coordinator reads advisory Brain Outputs and creates a coordinated, non-executing decision record. It reconciles conflicts and makes the current cognitive state auditable without creating orders, order intents, paper positions, live positions, or execution approvals.

## 2. Why Brains Need Coordination

Individual brains can disagree. Opportunity can see an edge while risk sees a hard block. AI can be optimistic while rules are ambiguous. Capital can be constrained while strategy is interested.

The Coordinator prevents isolated interpretations from becoming misleading by recording one conservative reconciliation state.

## 3. Signals vs Brain Outputs vs Coordinator Decisions

Signal:

Neutral structured information from a neuron.

Brain Output:

Advisory interpretation from a brain.

Coordinator Decision:

Non-executing reconciliation of Brain Outputs. It can block, request review, or mark no-trade/watch. It cannot execute.

Governor:

Future/higher safety layer for actual action approval.

Execution:

Future phase only.

## 4. Coordinator Decision Contract Fields

Canonical model:

- `coordinator_decision_id`
- `market_id`
- `position_id`
- `final_state`
- `primary_reason`
- `confidence`
- `urgency`
- `conflicts_detected`
- `governor_required`
- `execution_allowed`
- `approved_actions`
- `blocked_actions`
- `required_reviews`
- `risk_flags`
- `source_brain_count`
- `input_output_count`
- `conflict_count`
- `correlation_id`
- `ttl_seconds`
- `expires_at`
- `status`
- `metadata`
- `created_at`
- `updated_at`

`execution_allowed` is always `false` in this phase and is also protected by a DB check constraint.

## 5. Final State Definitions

Allowed final states:

- `NO_TRADE`
- `WATCH`
- `REVIEW_REQUIRED`
- `PAPER_CANDIDATE_BLOCKED`
- `EXIT_REVIEW_REQUIRED`
- `RISK_BLOCKED`
- `INSUFFICIENT_DATA`
- `CONFLICT_REVIEW`
- `DATA_DEGRADED`

Explicitly rejected executable states:

- `BUY`
- `SELL`
- `ENTER_TRADE`
- `EXIT_TRADE`
- `PLACE_ORDER`
- `CANCEL_ORDER`
- `LIVE_APPROVED`
- `EXECUTE`

## 6. Approved And Blocked Actions

Allowed approved actions:

- `NONE`
- `WATCH`
- `REVIEW`
- `REQUEST_MORE_DATA`
- `MARK_NO_TRADE`
- `SEND_TO_RISK_REVIEW`
- `SEND_TO_EXIT_REVIEW`
- `SEND_TO_HUMAN_REVIEW`

Allowed blocked actions:

- `PAPER_ENTRY`
- `LIVE_ENTRY`
- `ORDER_CREATION`
- `POSITION_OPEN`
- `POSITION_CLOSE`
- `EXECUTION`
- `AI_OVERRIDE`
- `OPPORTUNITY_OVERRIDE_RISK`

Approved actions are review/watch/no-trade workflow states only. Executable actions are allowed only in `blocked_actions`.

## 7. Coordination Rules

Implemented deterministic rules:

1. Risk blocks Opportunity.
2. Rules ambiguity/compliance risk blocks entry.
3. Capital insufficiency limits action scope.
4. Exit review overrides hold/watch interpretation.
5. AI cannot override Risk.
6. No-Trade is a valid final state.
7. Execution cannot proceed.
8. Missing Brain Outputs become `INSUFFICIENT_DATA`.
9. Conflicts are persisted.
10. Conservative default is `WATCH`, `REVIEW_REQUIRED`, or `NO_TRADE`.

## 8. Conflict Model

Coordinator conflicts are persisted in `coordinator_decision_conflicts`.

Implemented conflict keys include:

- `opportunity_positive_vs_risk_high`
- `ai_positive_vs_risk_block`
- `capital_insufficient_vs_opportunity_candidate`
- `exit_review_vs_hold`
- `rules_ambiguous_vs_opportunity_candidate`
- `no_trade_vs_opportunity_candidate`

## 9. DB Schema

Migration:

`0063_v2_neural_mesh_brain_coordinator.sql`

Tables:

| Table | Purpose |
| --- | --- |
| `coordinator_decisions` | Non-executing coordinated decision records. |
| `coordinator_decision_inputs` | Brain Outputs used as inputs. |
| `coordinator_decision_conflicts` | Conflicts detected during coordination. |

Important DB guarantees:

- `execution_allowed=false` enforced by check constraint.
- Confidence/urgency/conflict severity are `0..1` when present.
- Final state is constrained to non-executing values.

## 10. Repository And Service Behavior

Repository:

`app/repositories/coordinator_repository.py`

Service:

`app/services/brain_coordinator.py`

Implemented behavior:

- Create coordinator decision.
- Coordinate by market.
- Coordinate by position.
- Coordinate explicit Brain Output IDs.
- Apply deterministic rules.
- Detect conflicts.
- Persist decision inputs.
- Persist decision conflicts.
- Read recent decisions.
- Read one decision with inputs/conflicts.
- List by market.
- List by position.
- List conflicts.
- Produce dashboard summary.

## 11. API Routes

Added:

- `GET /coordinator/decisions/recent`
- `GET /coordinator/decisions/{coordinator_decision_id}`
- `GET /coordinator/market/{market_id}`
- `GET /coordinator/position/{position_id}`
- `GET /coordinator/conflicts/recent`
- `POST /coordinator/coordinate/market/{market_id}`
- `POST /coordinator/coordinate/position/{position_id}`
- `POST /coordinator/coordinate/outputs`
- `GET /dashboard/api/v2/coordinator`

POST routes are safe, non-executing, and only create coordinator decision audit records.

## 12. Dashboard Fields

Dashboard coordinator truth includes:

- `total_decisions_24h`
- `decisions_by_state`
- `recent_decisions`
- `recent_conflicts`
- `conflicts_detected_24h`
- `no_trade_decisions_24h`
- `risk_blocked_24h`
- `review_required_24h`
- `execution_allowed_count`
- `decisions_requiring_governor`
- `blocked_actions_summary`

Dashboard V2 overview includes compact coordinator truth.

## 13. Safety Rules

- Coordinator decisions are non-executing.
- `execution_allowed` is always false.
- Coordinator does not create order intents.
- Coordinator does not place orders.
- Coordinator does not cancel orders.
- Coordinator does not sign requests.
- Coordinator does not open or close positions.
- Coordinator does not approve live trading.
- Coordinator does not bypass Risk or State Governor.
- AI cannot override Risk.
- Opportunity cannot override Risk.
- Empty coordinator state is valid and reported truthfully.
- Dashboard uses DB truth with `mock_data=false`.

## 14. Example

```json
{
  "coordinator_decision_id": "coord_abc",
  "market_id": "824952",
  "position_id": null,
  "final_state": "RISK_BLOCKED",
  "primary_reason": "Risk brain output blocks opportunity or entry candidate.",
  "approved_actions": ["SEND_TO_RISK_REVIEW"],
  "blocked_actions": [
    "PAPER_ENTRY",
    "LIVE_ENTRY",
    "ORDER_CREATION",
    "POSITION_OPEN",
    "EXECUTION",
    "OPPORTUNITY_OVERRIDE_RISK"
  ],
  "conflicts_detected": true,
  "governor_required": true,
  "execution_allowed": false
}
```

## 15. Explicitly Not Included

- Paper trading
- Shadow Live
- Small Live
- Order intents
- Orders
- Cancels
- Signing
- Private key usage
- Full Risk Governor
- Full Strategy Router
- Full Opportunity scoring
- Full Exit Cortex
- AI model calls
- News/Social/Whale connectors
- Background scheduler

## 16. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Activation Part 2C, Brain Output Producer Adapters.

That phase should map existing context/capital/risk/no-trade/exit advisory module outputs into canonical `brain_outputs` so the Coordinator can reconcile real subsystem Brain Outputs without creating execution actions.
