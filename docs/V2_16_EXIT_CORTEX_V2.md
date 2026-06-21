# V2.16 Exit Cortex V2

## Purpose

V2.16 makes every internal paper/shadow entry born with a measurable exit plan. It adds exit planning, trigger evaluation, internal paper/shadow exit intents, exit events, exit quality, exit failures, and orphan order detection.

This phase is internal only. It does not send live exits, create live orders, mutate external balances, or certify live trading.

## Architecture

- `app/exit_cortex/contracts.py`: canonical exit contracts.
- `app/exit_cortex/exit_plan_builder.py`: builds complete or insufficient-data plans.
- `app/exit_cortex/exit_trigger_evaluator.py`: evaluates take profit, partial take profit, stop loss, max hold, news invalidation, spread, momentum decay, and emergency triggers.
- `app/exit_cortex/exit_intent_builder.py`: creates internal paper/shadow exit intents only.
- `app/exit_cortex/liquidity_exit_checker.py`: blocks fake exit success when exit liquidity is missing or too expensive.
- `app/exit_cortex/position_monitor.py`: reports internal V2 execution orders missing active exit plans.
- `app/exit_cortex/service.py`: DB-backed orchestration, event publication, and runtime safety checks.
- `app/api/exit_routes.py`: read-only and safe analysis endpoints.

## DB Tables

Migration: `app/db/migrations/0054_v2_16_exit_cortex_v2.sql`

- `exit_plans`: canonical exit plans for internal paper/shadow orders and positions.
- `exit_intents`: internal paper/shadow exit intents, constrained to `PAPER_SIM_EXIT` and `SHADOW_EXIT_PLAN`.
- `exit_events`: exit trigger, plan, intent, failure, and audit events.
- `exit_quality`: expected and actual exit-quality metrics.
- `exit_failures`: liquidity, runtime, and data failures.

## API Routes

- `GET /exits/health`
- `GET /exits/plans/recent`
- `GET /exits/plans/{exit_plan_id}`
- `GET /exits/intents/recent`
- `GET /exits/events/recent`
- `GET /exits/failures/recent`
- `GET /exits/quality/recent`
- `GET /exits/orphans`
- `POST /exits/plan`
- `POST /exits/evaluate`
- `POST /exits/emergency`

## Event Types

- `exit.plan.created`
- `exit.plan.blocked`
- `exit.plan.updated`
- `exit.trigger.detected`
- `exit.take_profit.triggered`
- `exit.partial_take_profit.triggered`
- `exit.stop_loss.triggered`
- `exit.max_hold.triggered`
- `exit.news_invalidated.triggered`
- `exit.spread_exit.triggered`
- `exit.momentum_decay.triggered`
- `exit.emergency.triggered`
- `exit.intent.created`
- `exit.intent.blocked`
- `exit.quality.recorded`
- `exit.failure.recorded`
- `exit.live.blocked`

## Exit Plan Logic

An exit plan must include target exit, stop loss, max hold seconds, liquidity exit checks, and at least one invalidation or emergency condition. If data is missing, V2.16 creates an `INSUFFICIENT_DATA`/blocked plan instead of inventing values.

## Trigger Logic

- Take profit fires when current price reaches `target_exit`.
- Partial take profit fires when current price reaches `partial_take_profit`.
- Stop loss fires when current price reaches or falls below `stop_loss`.
- Max hold fires when position age exceeds `max_hold_seconds`.
- News invalidation fires when current context contradicts the entry thesis.
- Spread exit fires when spread exceeds configured threshold.
- Momentum decay fires when momentum falls below configured threshold.
- Emergency exit fires on KILL/governor block, severe adverse movement, or explicit emergency signal.

## Intent Logic

Exit intents are internal records only:

- `PAPER_SIM_EXIT` in PAPER-compatible mode.
- `SHADOW_EXIT_PLAN` in SHADOW_LIVE-compatible mode.

No `LIVE_EXIT`, `LIVE_SEND`, external venue submit, or external balance mutation exists in V2.16.

## Liquidity And Failure Behavior

Before an exit intent is created, V2.16 checks bid/ask, exit depth, expected slippage, and exit liquidity score. Missing liquidity creates an `exit_failures` row and event. It never fakes exit success.

## Orphan Detection

`GET /exits/orphans` reports internal `orders_v2` in open-like statuses with no matching exit plan by `order_id` or `exit_plan_id`.

## Dashboard Fields

The dashboard query service exposes real DB-backed exit fields:

- `exit_status`
- `active_exit_plans`
- `exit_intents_today`
- `triggers_today`
- `failures_today`
- `orphan_orders_count`
- `avg_exit_quality`
- `recent_exit_plans`
- `recent_exit_intents`
- `recent_exit_failures`
- `common_exit_reasons`
- `live_certified=false`

## Safety Boundaries

- No live exits.
- No live orders.
- No external sends.
- No external balance mutation.
- DATA_ONLY blocks persisted executable exit intents.
- PAPER allows internal `PAPER_SIM_EXIT` only.
- SHADOW_LIVE allows internal `SHADOW_EXIT_PLAN` only.
- SMALL_LIVE and ATTACK_MODE return live-not-certified behavior.
- Emergency exits create internal intent/planning records only.

## Remaining Risks

V2.16 does not yet perform real exit execution. V2.15 execution can require an `exit_plan_id`, but full closed-loop paper exit fills remain for future integration. Real live exits remain explicitly uncertified.

## Next Phase

V2.17 No-Trade Intelligence may consume V2.16 exit failures and orphan reports, but must not be implemented inside V2.16.
