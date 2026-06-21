# V2.17 No-Trade Intelligence

## Purpose

V2.17 makes `NO_TRADE` a formal, stored, reviewable, and learnable decision. It records why a candidate was not traded, which layer blocked it, which engine was considered, whether the decision later looked correct, and whether future scoring should learn from it.

This phase does not create orders, order intents, live exits, external requests, or external balance mutations.

## Architecture

- `app/no_trade/contracts.py`: canonical no-trade, reason, review, and regret contracts.
- `app/no_trade/reason_classifier.py`: maps raw block/rejection signals into normalized no-trade reasons.
- `app/no_trade/candidate_tracker.py`: validates candidate engine, source layer, reason, and explanation.
- `app/no_trade/no_trade_logger.py`: builds canonical no-trade decisions.
- `app/no_trade/post_fact_reviewer.py`: computes post-fact evidence only when later data exists.
- `app/no_trade/regret_scorer.py`: scores regret without overriding hard risk blocks.
- `app/no_trade/memory_updater.py`: safe memory-update eligibility only.
- `app/no_trade/service.py`: DB persistence, dedupe, backfill, APIs, and events.
- `app/api/no_trade_routes.py`: `/no-trade/*` API surface.

## DB Tables

Migration: `app/db/migrations/0055_v2_17_no_trade_intelligence.sql`

- `no_trade_log`: canonical decision log.
- `no_trade_reasons`: normalized reason rows for aggregation.
- `no_trade_post_fact_review`: later evidence reviews.
- `no_trade_regret_score`: regret/good-no-trade scoring.

## API Routes

- `GET /no-trade/health`
- `GET /no-trade/recent`
- `GET /no-trade/{no_trade_id}`
- `GET /no-trade/reasons/top`
- `GET /no-trade/by-engine`
- `GET /no-trade/by-market-family`
- `GET /no-trade/regret`
- `GET /no-trade/reviews/pending`
- `POST /no-trade/log`
- `POST /no-trade/review`
- `POST /no-trade/rebuild`

## Event Types

- `no_trade.logged`
- `no_trade.reason.created`
- `no_trade.post_fact_review.created`
- `no_trade.regret_scored`
- `no_trade.memory_updated`
- `no_trade.insufficient_data`
- `no_trade.high_regret`
- `no_trade.good_decision`

## No-Trade Log Logic

Every explicit `NO_TRADE`, `BLOCKED`, `REJECTED`, `INSUFFICIENT_DATA`, or `WATCHLIST_ONLY` candidate can be logged with source layer, reason, candidate engine when available, confidence, and explanation.

Reasons are required. Source layer is required. Unknown reasons become `unknown_reason` and mark the decision insufficient.

The service dedupes exact source-layer/source-run/source-record/status/reason matches.

## Reason Classifier

The classifier maps raw signals to normalized reasons:

- `low_edge`
- `low_liquidity`
- `wide_spread`
- `bad_rules`
- `high_wording_risk`
- `high_correlation`
- `no_capital`
- `bad_exit_quality`
- `already_priced_in`
- `high_slippage`
- `governor_block`
- `ai_uncertainty`
- `missing_exit_plan`
- `missing_risk_approval`
- `cooldown`
- `kill_switch`
- `stale_data`
- `insufficient_data`
- `unknown_reason`

## Candidate Tracking

Candidate engine is stored when available. This phase treats V2.11 candidate engines and V2.12 selected engines as evidence, not executable routes.

## Post-Fact Review Logic

Post-fact review requires later price and liquidity evidence. If later data is missing, review status is `INSUFFICIENT_DATA` and regret is not guessed.

When evidence exists, the reviewer computes ROI, drawdown, exit possibility, and decision correctness.

## Regret Score Logic

`HIGH_REGRET` requires:

- enough data,
- favorable later move,
- plausible exit liquidity,
- and no hard original safety block.

Hard risk blocks prevent naive high regret even when price later moves favorably.

`GOOD_NO_TRADE` records avoided loss or poor later liquidity. `INSUFFICIENT_DATA` remains explicit when evidence is weak.

## Memory Update Boundary

V2.17 emits a memory-update hook only when regret confidence is high enough and the regret band is not insufficient. It does not overwrite V2.9 aggregate memory with low-confidence evidence.

## Dashboard Fields

The dashboard query service exposes:

- `no_trade_status`
- `logged_today`
- `top_no_trade_reasons`
- `no_trade_by_engine`
- `no_trade_by_market_family`
- `pending_reviews`
- `high_regret_count`
- `good_no_trade_count`
- `insufficient_data_count`
- `regret_analysis`
- `recent_no_trade_logs`
- `recent_high_regret`

## Safety Boundaries

- No orders.
- No order intents.
- No live exits.
- No external execution.
- No external balance mutation.
- Dry-run writes nothing.
- Dashboard uses DB truth only.
- No fake regret without evidence.

## Remaining Risks

Historical backfill depends on existing V2.11-V2.16 block records. If source layers are sparse, V2.17 stores sparse/insufficient data honestly.

## Next Phase

V2.18 Dashboard V2 can use the no-trade summaries as operator truth. It must not fake panels or controls.
