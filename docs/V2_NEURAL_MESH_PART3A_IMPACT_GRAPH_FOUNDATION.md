# POLYBOT V2 Neural Mesh Part 3A Impact Graph Foundation

## 1. Purpose

Part 3A adds the non-executing Impact Graph foundation for linking events, entities, Signals, markets, positions, thesis profiles, and Cortex action hints.

The goal is explainability and traceability. A Signal or event can now be linked to what it mentions, what market or position it may relate to, and what later brain/coordinator interpretation may reference it.

## 2. Why Event-Entity-Market-Position-Thesis Links Matter

Raw events are noisy until they are connected to the objects POLYBOT cares about. This foundation lets the system answer:

- Which entities are mentioned in an event or Signal?
- Which Signals have market links?
- Which Signals have position links?
- Which positions have thesis profiles?
- Which impact records exist and why?
- Which Signals remain unlinked?

## 3. Signals vs Impact Links vs Coordinator Decisions

Signals are neutral structured information emitted by neurons.

Impact Links are stored interpretations or links between a Signal/event/entity and a market, position, thesis, or system scope.

Coordinator Decisions reconcile Brain Outputs into a non-executing state such as `NO_TRADE`, `WATCH`, or `RISK_BLOCKED`.

Impact Links do not replace Coordinator Decisions and do not create execution approval.

## 4. Neurons Do Not Decide Impact

Neurons may provide neutral entities and source facts. Neurons do not decide whether an event is good or bad for a position. Impact Links may be created by brains, coordinator records, future impact services, or manual audit tooling, but they remain observational.

## 5. DB Schema

Migrations:

- `0064_v2_neural_mesh_impact_graph_foundation.sql`
- `0065_v2_neural_mesh_impact_graph_delete_semantics.sql`

Tables:

- `event_entities`: entities attached to events or Signals.
- `entity_market_links`: links entities to markets.
- `signal_market_links`: links Signals to markets.
- `signal_position_links`: links Signals to positions.
- `position_thesis_profiles`: stores position thesis profiles.
- `impact_links`: stores non-executing impact records.

`0065` makes Signal/entity/thesis deletion cascade to dependent `impact_links`, preserving the subject/target integrity checks during test cleanup and future archival flows.

## 6. Repository / Service Behavior

`ImpactGraphRepository` provides persistence for entities, links, thesis profiles, impact links, unlinked Signals, and graph summaries.

`ImpactGraphService` validates references and serializes API-safe output. It rejects:

- invalid confidence, strength, or urgency values
- empty entity names
- impact links without a subject
- impact links without a target
- executable Cortex hints

## 7. API Routes

Read routes:

- `GET /impact/entities`
- `GET /impact/entities/{entity_id}`
- `GET /impact/signals/{signal_id}/markets`
- `GET /impact/signals/{signal_id}/positions`
- `GET /impact/markets/{market_id}`
- `GET /impact/positions/{position_id}`
- `GET /impact/positions/{position_id}/thesis`
- `GET /impact/links/{impact_link_id}`
- `GET /impact/unlinked-signals`

Safe non-executing write routes:

- `POST /impact/entities`
- `POST /impact/link/entity-market`
- `POST /impact/link/signal-market`
- `POST /impact/link/signal-position`
- `POST /impact/positions/{position_id}/thesis`
- `POST /impact/links`

## 8. Dashboard Fields

`GET /dashboard/api/v2/impact-graph` returns:

- `entities_total`
- `signal_market_links_total`
- `signal_position_links_total`
- `impact_links_total`
- `unlinked_signals`
- `links_by_status`
- `impacts_by_direction`
- `cortex_action_hints`
- `latest_impacts`
- `positions_with_thesis`
- `signals_without_market_link`

The V2 overview also includes compact Impact Graph counts. All dashboard responses use real DB truth and `mock_data=false`.

## 9. Link Status Definitions

- `suggested`: possible link, not confirmed.
- `confirmed`: accepted link.
- `rejected`: reviewed and rejected.
- `expired`: stale link.
- `unknown`: status not established.

## 10. Impact Direction / Status Definitions

Directions:

- `favorable`
- `adverse`
- `neutral`
- `mixed`
- `unknown`

Statuses:

- `suggested`
- `confirmed`
- `rejected`
- `expired`
- `needs_review`
- `unknown`

## 11. Cortex Action Hint Definitions

Allowed non-executing hints:

- `WATCH`
- `REVIEW`
- `NO_TRADE_REVIEW`
- `EXIT_REVIEW`
- `OPPORTUNITY_REVIEW`
- `RISK_REVIEW`
- `IGNORE`
- `MEMORY_ONLY`
- `UNKNOWN`

Executable hints such as `BUY`, `SELL`, `PLACE_ORDER`, `CANCEL_ORDER`, `EXECUTE`, and `LIVE_APPROVED` are rejected.

## 12. Safety Rules

- Impact Graph never creates orders.
- Impact Graph never creates order intents.
- Impact Graph never opens or closes positions.
- Impact Graph never signs requests.
- Impact Graph never enables live trading.
- Impact Links do not imply trade approval.
- Empty graph state is valid and truthful.

## 13. Examples

Signal-market link:

```json
{
  "signal_id": "signal_abc",
  "market_id": "824952",
  "link_type": "exact_match",
  "link_status": "confirmed",
  "confidence": 0.9,
  "reason": "Signal carried market_id."
}
```

Impact link:

```json
{
  "signal_id": "signal_abc",
  "market_id": "824952",
  "position_id": "position_1",
  "thesis_id": "thesis_1",
  "impact_scope": "thesis",
  "impact_direction": "neutral",
  "impact_status": "needs_review",
  "cortex_action_hint": "REVIEW"
}
```

## 14. What Is Explicitly Not Included

- No real News/Social/Whale connector work.
- No AI entity extraction.
- No automatic impact interpretation loop.
- No Opportunity scoring.
- No Risk decision logic.
- No Exit decision logic.
- No Paper, Shadow Live, or Small Live.
- No order, cancel, signing, or live mutation path.

## 15. Next Phase Recommendation

Recommended next phase: V2 Neural Mesh Part 3B, a minimal Impact Graph producer/backfill layer that safely converts existing `neuron_signal_entities` and Signal `market_id` fields into suggested graph links, still without AI extraction or trading behavior.
