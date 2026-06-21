# V2.19 Feedback / Learning Loop

## Purpose

V2.19 turns POLYBOT outcomes into reviewable, evidence-backed learning records. It answers what the system thought, what happened after internal paper/shadow decisions, which engines and sources helped or hurt, and which model changes should be recommended for human review.

It is a review and learning layer only. It does not create orders, order intents, exit intents, live exits, external requests, or balance mutations.

## Architecture

- `app/learning/trade_reviewer.py` reviews completed internal paper/shadow outcomes and marks incomplete evidence as `PENDING` or `INSUFFICIENT_DATA`.
- `app/learning/signal_performance_analyzer.py` scores signal direction/strength against observed movement.
- `app/learning/engine_learning_builder.py` creates engine reward/penalty records.
- `app/learning/source_learning_builder.py`, `whale_learning_builder.py`, and `ai_learning_builder.py` create source-specific learning records.
- `app/learning/no_trade_learning_builder.py` converts V2.17 no-trade regret evidence into learning.
- `app/learning/model_adjustment_recommender.py` creates recommendation-only adjustments.
- `app/learning/memory_update_coordinator.py` gates memory updates by evidence and confidence.
- `app/learning/service.py` orchestrates dry-run, persistence, events, APIs, summaries, and safe rebuild.

## DB Tables

Migration: `app/db/migrations/0056_v2_19_feedback_learning_loop.sql`

- `trade_reviews`
- `signal_performance`
- `engine_learning`
- `source_learning`
- `whale_learning`
- `ai_learning`
- `no_trade_learning`
- `model_adjustments`

All tables are internal review/learning truth. No order, live order, order intent, live exit, or external balance table is written by V2.19.

## API Routes

- `GET /learning/health`
- `GET /learning/trade-reviews/recent`
- `GET /learning/signals`
- `GET /learning/engines`
- `GET /learning/sources`
- `GET /learning/whales`
- `GET /learning/ai`
- `GET /learning/no-trade`
- `GET /learning/model-adjustments`
- `GET /learning/snapshot`
- `POST /learning/review/trade`
- `POST /learning/review/no-trade`
- `POST /learning/rebuild`

Dashboard V2 also exposes:

- `GET /dashboard/api/v2/learning`

## Event Types

- `learning.trade_review.created`
- `learning.signal_performance.updated`
- `learning.engine.updated`
- `learning.source.updated`
- `learning.whale.updated`
- `learning.ai.updated`
- `learning.no_trade.updated`
- `learning.model_adjustment.recommended`
- `learning.memory_update.applied`
- `learning.insufficient_data`

Events are redacted and contain IDs, types, statuses, and learning signals only.

## Trade Review Logic

Completed trade review requires at least market, entry price, exit price, and size evidence. When a completed internal order/exit cycle is supplied, V2.19 computes realized PnL, ROI, ROI per hour, hold time, slippage accuracy, and engine result.

If outcome evidence is missing, V2.19 records `PENDING` or `INSUFFICIENT_DATA`. It does not fake closed trade reviews.

## Signal Performance Logic

Signals are compared to observed direction and movement magnitude. Directional misses become false positives where appropriate. Missing or weak evidence reduces confidence instead of inventing learning.

## Engine Learning Logic

Winning reviewed outcomes create `reward_engine`; losing outcomes create `penalize_engine`. SAFE and HUNT losses are treated with stronger confidence because those engines have tighter safety expectations. Incomplete reviews create `insufficient_data`.

## Source Learning Logic

Sources are rewarded only when usefulness and confidence are sufficient. Stale, false, or low-usefulness source evidence is penalized. Low confidence produces insufficient learning rather than reliability mutation.

## Whale Learning Logic

Whale follow value improves only from outcome evidence. Noisy or false-positive whale behavior is penalized. Large size alone is not treated as intelligence.

## AI Learning Logic

AI learning tracks usefulness, accuracy, cost, and cost efficiency. Bad calls are penalized; useful calls are rewarded. If AI evidence is absent, no AI learning is fabricated.

## No-Trade Learning Logic

V2.19 consumes V2.17 `no_trade_regret_score` rows. `HIGH_REGRET` can recommend `loosen_filter` or `improve_data`; `GOOD_NO_TRADE` keeps the filter; `INSUFFICIENT_DATA` recommends data improvement.

## Model Adjustment Policy

`model_adjustments` are recommendations only. They start as `RECOMMENDED` or `REVIEW_REQUIRED`. V2.19 does not apply parameter changes automatically and does not rewrite historical facts.

## Memory Update Boundary

Memory updates require evidence and confidence at or above the memory threshold. Low-confidence learning records are stored, but aggregate memory update is skipped.

## Insufficient Data Behavior

Missing outcomes, missing no-trade regret evidence, weak source evidence, or incomplete trade cycles produce `PENDING` or `INSUFFICIENT_DATA`. V2.19 never guesses learning from absent outcomes.

## Dashboard Fields

Dashboard V2 and the operator query service now include:

- `learning_status`
- `trade_reviews_today`
- `pending_reviews`
- `engine_learning_summary`
- `source_learning_summary`
- `whale_learning_summary`
- `ai_learning_summary`
- `no_trade_learning_summary`
- `model_adjustments_pending`
- `insufficient_data_count`
- `latest_review`
- `recent_learning_events`
- `errors`

The dashboard uses DB/runtime truth only.

## Safety Boundaries

- Learning cannot create orders.
- Learning cannot create order intents.
- Learning cannot create live exits.
- Learning cannot mutate external balances.
- Model adjustments are recommendation-only.
- Closed trade review requires completed outcome evidence.
- No-trade learning requires V2.17 regret evidence.
- Dry-run writes nothing.
- State Governor remains the runtime authority.

## Tests

V2.19 adds unit, service, API, dashboard, and safety tests under `tests/test_v2_19_*.py`.

## Remaining Risks

Real completed internal trade history can be sparse. Sparse sources are represented as `NO_DATA`, `PENDING`, or `INSUFFICIENT_DATA`; this is honest and expected until V2.20 full paper system runs generate richer closed-cycle evidence.

## Next Recommended Phase

V2.20 Paper Full System Run.

