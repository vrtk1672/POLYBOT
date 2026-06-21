# POLYBOT V2 Neural Mesh Part 3B Position Thesis Profile

## 1. Purpose
V2 Neural Mesh Part 3B turns `position_thesis_profiles` from the Part 3A impact graph table into the canonical, non-executing Position Thesis Profile contract.

Every future Paper, Shadow, or Live position must have a thesis before entry. This phase creates the contract, validation, readiness scoring, APIs, and dashboard truth. It does not create positions, orders, order intents, exits, or live permissions.

## 2. Why Every Position Needs Thesis
POLYBOT is built around defined downside. A position without a thesis cannot explain why it exists, what supports it, what invalidates it, or when risk should be reviewed.

The thesis profile answers:
- why the position exists
- what must happen for profit
- what invalidates the thesis
- which entities and signals should be watched
- what profit, partial exit, and emergency review rules exist
- whether the profile is complete enough for future Paper or Live use

## 3. Thesis vs Signal vs Impact Link vs Coordinator Decision
- Signal: neutral structured information from neurons.
- Impact Link: non-executing graph link between signal/event/entity and market/position/thesis.
- Coordinator Decision: non-executing reconciliation of brain outputs.
- Position Thesis Profile: structured explanation and monitoring contract for a position.

Readiness flags are informational. They do not approve execution.

## 4. Thesis Profile Contract Fields
Canonical fields:
- `thesis_id`
- `position_id`
- `market_id`
- `side`
- `entry_thesis`
- `profit_drivers`
- `invalidation_drivers`
- `watch_entities`
- `danger_signals`
- `take_profit_rules`
- `partial_exit_rules`
- `emergency_exit_rules`
- `status`
- `completeness_score`
- `paper_ready`
- `live_ready`
- `coordinator_decision_id`
- `brain_output_id`
- `source_signal_ids`
- `risk_flags`
- `thesis_version`
- `created_by`
- `reviewed_by`
- `reviewed_at`
- `expires_at`
- `metadata`
- `created_at`
- `updated_at`

## 5. Status Definitions
Allowed statuses:
- `DRAFT`: saved but not ready.
- `ACTIVE`: eligible for readiness scoring.
- `NEEDS_REVIEW`: must be reviewed before use.
- `INVALIDATED`: thesis is broken.
- `EXPIRED`: thesis is no longer current.
- `ARCHIVED`: historical only.

Allowed sides:
- `YES`
- `NO`
- `UNKNOWN`

## 6. Paper Readiness Rules
`paper_ready=true` requires:
- status is `ACTIVE`
- `position_id` present
- `market_id` present
- `entry_thesis` present
- at least one `profit_driver`
- at least one `invalidation_driver`
- at least one `danger_signal`
- at least one `take_profit_rule` or `partial_exit_rule`
- at least one `emergency_exit_rule`
- no executable order language

`UNKNOWN` side is allowed for paper readiness because this phase is a contract foundation, not an execution phase.

## 7. Live Readiness Rules
`live_ready=true` requires all paper readiness requirements plus:
- side is `YES` or `NO`
- at least one `watch_entity`
- at least one `take_profit_rule`
- at least one `partial_exit_rule`
- at least one `emergency_exit_rule`
- `completeness_score >= 0.85`
- `reviewed_by` and `reviewed_at`

This flag is computed only. It is not connected to live execution.

## 8. Completeness Scoring
Completeness is deterministic. The score counts satisfied thesis criteria across position, market, side, thesis text, drivers, watch entities, danger signals, exit review rules, and review fields.

Statuses other than `ACTIVE` prevent paper/live readiness even if content is otherwise complete.

## 9. DB Schema
Migration:
- `app/db/migrations/0066_v2_neural_mesh_position_thesis_contract.sql`

Existing table extended:
- `position_thesis_profiles`

Columns added:
- `completeness_score`
- `paper_ready`
- `live_ready`
- `coordinator_decision_id`
- `brain_output_id`
- `source_signal_ids_json`
- `risk_flags_json`
- `thesis_version`
- `created_by`
- `reviewed_by`
- `reviewed_at`
- `expires_at`
- `metadata_json`

New validation event table:
- `position_thesis_validation_events`

## 10. Repository / Service Behavior
Repository:
- `app/repositories/position_thesis_repository.py`

Service:
- `app/services/position_thesis.py`

Capabilities:
- create/update thesis profile
- get by thesis id
- get by position id
- list profiles
- validate profile
- mark `NEEDS_REVIEW`
- mark `INVALIDATED`
- summarize dashboard truth
- check whether a position has a required thesis

## 11. API Routes
Router:
- `app/api/position_thesis_routes.py`

Routes:
- `GET /thesis/profiles`
- `GET /thesis/profiles/{thesis_id}`
- `GET /thesis/positions/{position_id}`
- `GET /thesis/positions/{position_id}/validation`
- `GET /thesis/summary`
- `POST /thesis/profiles`
- `PUT /thesis/profiles/{thesis_id}`
- `POST /thesis/profiles/{thesis_id}/validate`
- `POST /thesis/profiles/{thesis_id}/needs-review`
- `POST /thesis/profiles/{thesis_id}/invalidate`

All routes return DB/runtime truth with `mock_data=false`.

## 12. Dashboard Fields
Dashboard route:
- `GET /dashboard/api/v2/thesis`

Dashboard V2 page:
- `thesis`

Fields:
- `total_thesis_profiles`
- `active_thesis_profiles`
- `draft_thesis_profiles`
- `needs_review`
- `invalidated`
- `paper_ready`
- `live_ready`
- `avg_completeness_score`
- `positions_without_thesis`
- `latest_thesis_profiles`
- `missing_required_fields_summary`

## 13. Safety Rules
- Thesis does not approve trades.
- Thesis readiness does not execute anything.
- Executable rule language such as `BUY`, `SELL`, `PLACE_ORDER`, `CANCEL_ORDER`, `EXECUTE`, and `LIVE_APPROVED` is rejected.
- No orders are created.
- No positions are opened or closed.
- No private keys are used.
- No signed requests are sent.
- Missing thesis data is allowed and visible.

## 14. Examples
Paper-ready example:

```json
{
  "position_id": "pos_123",
  "market_id": "market_123",
  "side": "UNKNOWN",
  "entry_thesis": "Market may reprice after verified information.",
  "profit_drivers": ["verified resolution path"],
  "invalidation_drivers": ["resolution wording becomes ambiguous"],
  "danger_signals": ["rules_degraded"],
  "take_profit_rules": ["review profit if edge closes"],
  "emergency_exit_rules": ["review immediately if source invalidates thesis"],
  "status": "ACTIVE"
}
```

Live-ready requires side `YES` or `NO`, watch entities, partial exit rules, and explicit review metadata. It remains non-executing.

## 15. What Is Explicitly Not Included
This phase does not include:
- Paper trading
- Shadow Live
- Small Live
- order creation
- order intents
- position opening/closing
- Exit Cortex implementation
- Risk Governor implementation
- Strategy Router
- AI thesis generation
- automatic thesis generation

## 16. Next Phase Recommendation
Recommended next phase: V2 Neural Mesh Part 3C, thesis-aware non-executing impact review helpers for Exit/Risk/No-Trade preparation. Keep it observational until governors and execution phases are explicitly activated.
