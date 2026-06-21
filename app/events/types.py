from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    MARKET_DISCOVERED = "market.discovered"
    MARKET_SNAPSHOT_CREATED = "market.snapshot.created"
    MARKET_LIFECYCLE_UPDATED = "market.lifecycle.updated"
    ORDERBOOK_SNAPSHOT_CREATED = "orderbook.snapshot.created"
    RULES_SNAPSHOT_CREATED = "rules.snapshot.created"
    RULES_INGESTED = "rules.ingested"
    RULES_ANALYSIS_CREATED = "rules.analysis.created"
    RULES_WORDING_RISK_SCORED = "rules.wording_risk.scored"
    RULES_DISPUTE_RISK_SCORED = "rules.dispute_risk.scored"
    RULES_SOURCE_VERIFIED = "rules.source.verified"
    RULES_COMPLIANCE_BLOCKED = "rules.compliance.blocked"
    RULES_AI_ANALYZED = "rules.ai.analyzed"
    RULES_RECOMMENDATION_CREATED = "rules.recommendation.created"
    DATA_COMPLETENESS_UPDATED = "data.completeness.updated"
    LIQUIDITY_SNAPSHOT_CREATED = "liquidity.snapshot.created"
    FEE_SNAPSHOT_CREATED = "fee.snapshot.created"
    NEWS_EVENT_CREATED = "news.event.created"
    NEWS_SOURCE_REGISTERED = "news.source.registered"
    NEWS_RAW_COLLECTED = "news.raw.collected"
    NEWS_EVENT_NORMALIZED = "news.event.normalized"
    NEWS_EVENT_DEDUPED = "news.event.deduped"
    NEWS_MARKET_LINKED = "news.market.linked"
    NEWS_IMPACT_SCORED = "news.impact.scored"
    NEWS_AI_ANALYZED = "news.ai.analyzed"
    NEWS_SOURCE_RELIABILITY_UPDATED = "news.source.reliability.updated"
    SOCIAL_EVENT_CREATED = "social.event.created"
    SOCIAL_SOURCE_REGISTERED = "social.source.registered"
    SOCIAL_RAW_COLLECTED = "social.raw.collected"
    SOCIAL_EVENT_NORMALIZED = "social.event.normalized"
    SOCIAL_EVENT_DEDUPED = "social.event.deduped"
    SOCIAL_MARKET_LINKED = "social.market.linked"
    SOCIAL_SENTIMENT_SCORED = "social.sentiment.scored"
    SOCIAL_HYPE_SCORED = "social.hype.scored"
    SOCIAL_NOISE_SCORED = "social.noise.scored"
    SOCIAL_NARRATIVE_DETECTED = "social.narrative.detected"
    SOCIAL_AI_ANALYZED = "social.ai.analyzed"
    SOCIAL_SIGNAL_CREATED = "social.signal.created"
    WHALE_EVENT_CREATED = "whale.event.created"
    WHALE_SOURCE_REGISTERED = "whale.source.registered"
    WHALE_EVENT_COLLECTED = "whale.event.collected"
    WHALE_EVENT_NORMALIZED = "whale.event.normalized"
    WHALE_REGISTERED = "whale.registered"
    WHALE_PROFILE_UPDATED = "whale.profile.updated"
    WHALE_CATEGORY_ASSIGNED = "whale.category.assigned"
    WHALE_MARKET_SCORED = "whale.market.scored"
    WHALE_FOLLOW_DECIDED = "whale.follow.decided"
    WHALE_PERFORMANCE_UPDATED = "whale.performance.updated"
    WHALE_SIGNAL_CREATED = "whale.signal.created"
    WHALE_AI_ANALYZED = "whale.ai.analyzed"
    MARKET_TECHNICAL_SIGNAL_CREATED = "market.technical_signal.created"
    ORDERBOOK_SIGNAL_CREATED = "orderbook.signal.created"
    LIQUIDITY_SIGNAL_CREATED = "liquidity.signal.created"
    TIME_SIGNAL_CREATED = "time.signal.created"
    FEE_REWARD_SIGNAL_CREATED = "fee_reward.signal.created"
    MARKET_TECHNICAL_TRUTH_CREATED = "market.technical_truth.created"
    MARKET_TECHNICAL_TRUTH_BLOCKED = "market.technical_truth.blocked"
    MARKET_MEMORY_UPDATED = "market.memory.updated"
    MARKET_FAMILY_MEMORY_UPDATED = "market_family.memory.updated"
    ENGINE_PERFORMANCE_MEMORY_UPDATED = "engine_performance.memory.updated"
    SOURCE_RELIABILITY_MEMORY_UPDATED = "source_reliability.memory.updated"
    WHALE_MEMORY_UPDATED = "whale.memory.updated"
    SLIPPAGE_MEMORY_UPDATED = "slippage.memory.updated"
    RULES_RISK_MEMORY_UPDATED = "rules_risk.memory.updated"
    NO_TRADE_MEMORY_UPDATED = "no_trade.memory.updated"
    MARKET_MEMORY_INSUFFICIENT_DATA = "market.memory.insufficient_data"
    CONTEXT_BRAIN_RUN_STARTED = "context_brain.run.started"
    CONTEXT_BRAIN_OUTPUT_CREATED = "context_brain.output.created"
    CONTEXT_BRAIN_INSUFFICIENT_DATA = "context_brain.insufficient_data"
    CAPITAL_BRAIN_RUN_STARTED = "capital_brain.run.started"
    CAPITAL_BRAIN_OUTPUT_CREATED = "capital_brain.output.created"
    CAPITAL_BRAIN_BLOCKED = "capital_brain.blocked"
    CAPITAL_BRAIN_INSUFFICIENT_DATA = "capital_brain.insufficient_data"
    BRAIN_SNAPSHOT_CREATED = "brain.snapshot.created"
    OPPORTUNITY_RUN_STARTED = "opportunity.run.started"
    OPPORTUNITY_SCORE_CREATED = "opportunity.score.created"
    OPPORTUNITY_BLOCKED = "opportunity.blocked"
    OPPORTUNITY_WATCHLIST_CREATED = "opportunity.watchlist.created"
    OPPORTUNITY_HIGH_SCORE_CREATED = "opportunity.high_score.created"
    OPPORTUNITY_INSUFFICIENT_DATA = "opportunity.insufficient_data"
    STRATEGY_ROUTE_RUN_STARTED = "strategy.route.run.started"
    STRATEGY_ROUTE_CREATED = "strategy.route.created"
    STRATEGY_ROUTE_NO_TRADE = "strategy.route.no_trade"
    STRATEGY_ENGINE_DECISION_CREATED = "strategy.engine.decision.created"
    STRATEGY_ENGINE_REJECTED = "strategy.engine.rejected"
    STRATEGY_ENGINE_COOLDOWN_CREATED = "strategy.engine.cooldown.created"
    STRATEGY_ROUTE_INSUFFICIENT_DATA = "strategy.route.insufficient_data"
    CAPITAL_STATE_CREATED = "capital.state.created"
    CAPITAL_STATE_UPDATED = "capital.state.updated"
    ENGINE_BUDGET_CREATED = "engine.budget.created"
    ENGINE_BUDGET_UPDATED = "engine.budget.updated"
    CAPITAL_ALLOCATION_CREATED = "capital.allocation.created"
    CAPITAL_ALLOCATION_BLOCKED = "capital.allocation.blocked"
    CAPITAL_ALLOCATION_REDUCED = "capital.allocation.reduced"
    REINVEST_PROFIT_POCKET_UPDATED = "reinvest.profit_pocket.updated"
    REINVEST_ATTACK_BANK_UPDATED = "reinvest.attack_bank.updated"
    CAPITAL_EVENT_RECORDED = "capital.event.recorded"
    CAPITAL_INSUFFICIENT_DATA = "capital.insufficient_data"
    RISK_GATE_RUN_STARTED = "risk.gate.run.started"
    RISK_GATE_APPROVED = "risk.gate.approved"
    RISK_GATE_BLOCKED = "risk.gate.blocked"
    RISK_GATE_REDUCED = "risk.gate.reduced"
    RISK_GATE_INSUFFICIENT_DATA = "risk.gate.insufficient_data"
    RISK_GOVERNOR_STATE_UPDATED = "risk.governor.state.updated"
    RISK_GOVERNOR_BLOCKED = "risk.governor.blocked"
    RISK_LIMIT_CREATED = "risk.limit.created"
    RISK_LIMIT_UPDATED = "risk.limit.updated"
    RISK_BREACH_DETECTED = "risk.breach.detected"
    RISK_COOLDOWN_CREATED = "risk.cooldown.created"
    RISK_COOLDOWN_EXPIRED = "risk.cooldown.expired"
    RISK_MANUAL_OVERRIDE_CREATED = "risk.manual_override.created"
    RISK_ATTACK_MODE_ALLOWED = "risk.attack_mode.allowed"
    RISK_ATTACK_MODE_BLOCKED = "risk.attack_mode.blocked"
    EXECUTION_ORDER_CREATED = "execution.order.created"
    EXECUTION_ORDER_BLOCKED = "execution.order.blocked"
    EXECUTION_ORDER_SUBMITTED_PAPER = "execution.order.submitted_paper"
    EXECUTION_ORDER_PLANNED_SHADOW = "execution.order.planned_shadow"
    EXECUTION_ORDER_PARTIALLY_FILLED = "execution.order.partially_filled"
    EXECUTION_ORDER_FILLED = "execution.order.filled"
    EXECUTION_ORDER_FAILED = "execution.order.failed"
    EXECUTION_ORDER_CANCELLED = "execution.order.cancelled"
    EXECUTION_CANCEL_CONDITION_TRIGGERED = "execution.cancel_condition.triggered"
    EXECUTION_FILL_CREATED = "execution.fill.created"
    EXECUTION_QUALITY_RECORDED = "execution.quality.recorded"
    EXECUTION_ERROR_RECORDED = "execution.error.recorded"
    EXECUTION_LIVE_BLOCKED = "execution.live.blocked"
    EXIT_PLAN_CREATED = "exit.plan.created"
    EXIT_PLAN_BLOCKED = "exit.plan.blocked"
    EXIT_PLAN_UPDATED = "exit.plan.updated"
    EXIT_TRIGGER_DETECTED = "exit.trigger.detected"
    EXIT_TAKE_PROFIT_TRIGGERED = "exit.take_profit.triggered"
    EXIT_PARTIAL_TAKE_PROFIT_TRIGGERED = "exit.partial_take_profit.triggered"
    EXIT_STOP_LOSS_TRIGGERED = "exit.stop_loss.triggered"
    EXIT_MAX_HOLD_TRIGGERED = "exit.max_hold.triggered"
    EXIT_NEWS_INVALIDATED_TRIGGERED = "exit.news_invalidated.triggered"
    EXIT_SPREAD_EXIT_TRIGGERED = "exit.spread_exit.triggered"
    EXIT_MOMENTUM_DECAY_TRIGGERED = "exit.momentum_decay.triggered"
    EXIT_EMERGENCY_TRIGGERED = "exit.emergency.triggered"
    EXIT_INTENT_BLOCKED = "exit.intent.blocked"
    EXIT_QUALITY_RECORDED = "exit.quality.recorded"
    EXIT_FAILURE_RECORDED = "exit.failure.recorded"
    EXIT_LIVE_BLOCKED = "exit.live.blocked"
    NO_TRADE_LOGGED = "no_trade.logged"
    NO_TRADE_REASON_CREATED = "no_trade.reason.created"
    NO_TRADE_POST_FACT_REVIEW_CREATED = "no_trade.post_fact_review.created"
    NO_TRADE_REGRET_SCORED = "no_trade.regret_scored"
    NO_TRADE_CANONICAL_MEMORY_UPDATED = "no_trade.memory_updated"
    NO_TRADE_INSUFFICIENT_DATA = "no_trade.insufficient_data"
    NO_TRADE_HIGH_REGRET = "no_trade.high_regret"
    NO_TRADE_GOOD_DECISION = "no_trade.good_decision"
    SIGNAL_CREATED = "signal.created"
    OPPORTUNITY_SCORED = "opportunity.scored"
    STRATEGY_ROUTED = "strategy.routed"
    RISK_APPROVED = "risk.approved"
    RISK_REJECTED = "risk.rejected"
    ORDER_INTENT_CREATED = "order.intent.created"
    ORDER_CREATED = "order.created"
    POSITION_OPENED = "position.opened"
    EXIT_INTENT_CREATED = "exit.intent.created"
    TRADE_CLOSED = "trade.closed"
    LEARNING_UPDATED = "learning.updated"
    LEARNING_TRADE_REVIEW_CREATED = "learning.trade_review.created"
    LEARNING_SIGNAL_PERFORMANCE_UPDATED = "learning.signal_performance.updated"
    LEARNING_ENGINE_UPDATED = "learning.engine.updated"
    LEARNING_SOURCE_UPDATED = "learning.source.updated"
    LEARNING_WHALE_UPDATED = "learning.whale.updated"
    LEARNING_AI_UPDATED = "learning.ai.updated"
    LEARNING_NO_TRADE_UPDATED = "learning.no_trade.updated"
    LEARNING_MODEL_ADJUSTMENT_RECOMMENDED = "learning.model_adjustment.recommended"
    LEARNING_MEMORY_UPDATE_APPLIED = "learning.memory_update.applied"
    LEARNING_INSUFFICIENT_DATA = "learning.insufficient_data"
    RUNTIME_CYCLE_STARTED = "runtime.cycle.started"
    RUNTIME_CYCLE_FINISHED = "runtime.cycle.finished"
    RUNTIME_MODE_CHANGED = "runtime.mode.changed"
    RUNTIME_SERVICE_HEALTH_UPDATED = "runtime.service.health.updated"
    EVENT_DLQ_CREATED = "event.dlq.created"
    EVENT_REPLAY_REQUESTED = "event.replay.requested"
    AI_REQUEST_CREATED = "ai.request.created"
    AI_CACHE_HIT = "ai.cache.hit"
    AI_BUDGET_BLOCKED = "ai.budget.blocked"
    AI_LOCAL_COMPLETED = "ai.local.completed"
    AI_CLOUD_ESCALATED = "ai.cloud.escalated"
    AI_CLOUD_COMPLETED = "ai.cloud.completed"
    AI_DECISION_LOGGED = "ai.decision.logged"
    AI_COST_RECORDED = "ai.cost.recorded"
    AI_MODEL_PERFORMANCE_UPDATED = "ai.model.performance.updated"


EVENT_TYPE_DESCRIPTIONS: dict[str, str] = {
    EventType.MARKET_DISCOVERED.value: "A market entered POLYBOT's known universe.",
    EventType.MARKET_SNAPSHOT_CREATED.value: "A persisted market snapshot was created.",
    EventType.MARKET_LIFECYCLE_UPDATED.value: "A market lifecycle state changed or was confirmed.",
    EventType.ORDERBOOK_SNAPSHOT_CREATED.value: "An orderbook snapshot was captured.",
    EventType.RULES_SNAPSHOT_CREATED.value: "A market rules or wording snapshot was captured.",
    EventType.RULES_INGESTED.value: "A market rules record was ingested for wording analysis.",
    EventType.RULES_ANALYSIS_CREATED.value: "A rules wording and compliance analysis was persisted.",
    EventType.RULES_WORDING_RISK_SCORED.value: "A wording risk score was persisted.",
    EventType.RULES_DISPUTE_RISK_SCORED.value: "A dispute risk score was computed.",
    EventType.RULES_SOURCE_VERIFIED.value: "A resolution source verification status was persisted.",
    EventType.RULES_COMPLIANCE_BLOCKED.value: "A compliance or rules block was created.",
    EventType.RULES_AI_ANALYZED.value: "Optional AI wording analysis was stored.",
    EventType.RULES_RECOMMENDATION_CREATED.value: "A rules recommendation was created.",
    EventType.DATA_COMPLETENESS_UPDATED.value: "A market data completeness score was computed.",
    EventType.LIQUIDITY_SNAPSHOT_CREATED.value: "A market liquidity snapshot was computed.",
    EventType.FEE_SNAPSHOT_CREATED.value: "A market fee or reward snapshot was computed.",
    EventType.NEWS_EVENT_CREATED.value: "A future news neuron observation was recorded.",
    EventType.NEWS_SOURCE_REGISTERED.value: "A news source was registered or enabled.",
    EventType.NEWS_RAW_COLLECTED.value: "A raw news item was collected.",
    EventType.NEWS_EVENT_NORMALIZED.value: "A news item was normalized.",
    EventType.NEWS_EVENT_DEDUPED.value: "A news item was assigned to a deduplication group.",
    EventType.NEWS_MARKET_LINKED.value: "A news item was linked to a market.",
    EventType.NEWS_IMPACT_SCORED.value: "A news impact signal was scored.",
    EventType.NEWS_AI_ANALYZED.value: "Optional AI context analysis was stored for a news item.",
    EventType.NEWS_SOURCE_RELIABILITY_UPDATED.value: "News source operational reliability was updated.",
    EventType.SOCIAL_EVENT_CREATED.value: "A canonical social or hype neuron observation was recorded.",
    EventType.SOCIAL_SOURCE_REGISTERED.value: "A social source was registered or enabled.",
    EventType.SOCIAL_RAW_COLLECTED.value: "A raw social item was collected.",
    EventType.SOCIAL_EVENT_NORMALIZED.value: "A social item was normalized.",
    EventType.SOCIAL_EVENT_DEDUPED.value: "A social item was assigned to a deduplication group.",
    EventType.SOCIAL_MARKET_LINKED.value: "A social item was linked to a market.",
    EventType.SOCIAL_SENTIMENT_SCORED.value: "A social sentiment score was stored.",
    EventType.SOCIAL_HYPE_SCORED.value: "A social hype pressure score was stored.",
    EventType.SOCIAL_NOISE_SCORED.value: "A social bot, spam, or noise score was stored.",
    EventType.SOCIAL_NARRATIVE_DETECTED.value: "A social narrative was created or updated.",
    EventType.SOCIAL_AI_ANALYZED.value: "Optional AI context analysis was stored for social data.",
    EventType.SOCIAL_SIGNAL_CREATED.value: "A final non-trading social signal was created.",
    EventType.WHALE_EVENT_CREATED.value: "A canonical whale neuron event was recorded.",
    EventType.WHALE_SOURCE_REGISTERED.value: "A whale data source was registered or enabled.",
    EventType.WHALE_EVENT_COLLECTED.value: "A raw whale event was collected.",
    EventType.WHALE_EVENT_NORMALIZED.value: "A whale event was normalized.",
    EventType.WHALE_REGISTERED.value: "A whale identity was registered.",
    EventType.WHALE_PROFILE_UPDATED.value: "A whale profile was updated.",
    EventType.WHALE_CATEGORY_ASSIGNED.value: "A whale category was assigned.",
    EventType.WHALE_MARKET_SCORED.value: "A whale market score was persisted.",
    EventType.WHALE_FOLLOW_DECIDED.value: "A whale follow/watch/ignore decision was logged.",
    EventType.WHALE_PERFORMANCE_UPDATED.value: "A whale performance history record was updated.",
    EventType.WHALE_SIGNAL_CREATED.value: "A non-trading whale signal was created.",
    EventType.WHALE_AI_ANALYZED.value: "Optional AI whale context analysis was stored.",
    EventType.MARKET_TECHNICAL_SIGNAL_CREATED.value: "A non-trading market technical signal was persisted.",
    EventType.ORDERBOOK_SIGNAL_CREATED.value: "A non-trading orderbook truth signal was persisted.",
    EventType.LIQUIDITY_SIGNAL_CREATED.value: "A non-trading liquidity truth signal was persisted.",
    EventType.TIME_SIGNAL_CREATED.value: "A non-trading time pressure signal was persisted.",
    EventType.FEE_REWARD_SIGNAL_CREATED.value: "A non-trading fee and reward truth signal was persisted.",
    EventType.MARKET_TECHNICAL_TRUTH_CREATED.value: "A combined market technical truth record was persisted.",
    EventType.MARKET_TECHNICAL_TRUTH_BLOCKED.value: "A market was technically blocked by data, orderbook, liquidity, time, or cost truth.",
    EventType.MARKET_MEMORY_UPDATED.value: "A market behavioral memory summary was updated.",
    EventType.MARKET_FAMILY_MEMORY_UPDATED.value: "A market family behavioral memory summary was updated.",
    EventType.ENGINE_PERFORMANCE_MEMORY_UPDATED.value: "An engine performance memory summary was updated.",
    EventType.SOURCE_RELIABILITY_MEMORY_UPDATED.value: "A source reliability memory summary was updated.",
    EventType.WHALE_MEMORY_UPDATED.value: "A whale behavioral memory summary was updated.",
    EventType.SLIPPAGE_MEMORY_UPDATED.value: "A slippage memory summary was updated.",
    EventType.RULES_RISK_MEMORY_UPDATED.value: "A rules risk memory summary was updated.",
    EventType.NO_TRADE_MEMORY_UPDATED.value: "A no-trade memory summary was updated.",
    EventType.MARKET_MEMORY_INSUFFICIENT_DATA.value: "A memory rebuild found insufficient data and recorded that truth.",
    EventType.CONTEXT_BRAIN_RUN_STARTED.value: "A non-trading Context Brain analysis run started.",
    EventType.CONTEXT_BRAIN_OUTPUT_CREATED.value: "A non-trading Context Brain output was persisted.",
    EventType.CONTEXT_BRAIN_INSUFFICIENT_DATA.value: "Context Brain analysis found insufficient context data.",
    EventType.CAPITAL_BRAIN_RUN_STARTED.value: "A non-trading Capital Brain analysis run started.",
    EventType.CAPITAL_BRAIN_OUTPUT_CREATED.value: "A non-trading Capital Brain recommendation was persisted.",
    EventType.CAPITAL_BRAIN_BLOCKED.value: "Capital Brain blocked capital recommendation due to constraints or missing data.",
    EventType.CAPITAL_BRAIN_INSUFFICIENT_DATA.value: "Capital Brain analysis found insufficient capital data.",
    EventType.BRAIN_SNAPSHOT_CREATED.value: "A combined Context and Capital Brain snapshot was created.",
    EventType.OPPORTUNITY_RUN_STARTED.value: "A non-trading Opportunity Cortex scoring run started.",
    EventType.OPPORTUNITY_SCORE_CREATED.value: "A reproducible non-trading opportunity score was persisted.",
    EventType.OPPORTUNITY_BLOCKED.value: "Opportunity Cortex marked a candidate blocked by hard scoring risk.",
    EventType.OPPORTUNITY_WATCHLIST_CREATED.value: "Opportunity Cortex created a watchlist scoring output.",
    EventType.OPPORTUNITY_HIGH_SCORE_CREATED.value: "Opportunity Cortex created a strong or high-conviction scoring output.",
    EventType.OPPORTUNITY_INSUFFICIENT_DATA.value: "Opportunity Cortex found insufficient data for scoring confidence.",
    EventType.STRATEGY_ROUTE_RUN_STARTED.value: "A non-trading Strategy Router run started.",
    EventType.STRATEGY_ROUTE_CREATED.value: "A non-trading strategy route contract was persisted.",
    EventType.STRATEGY_ROUTE_NO_TRADE.value: "Strategy Router selected the NO_TRADE engine.",
    EventType.STRATEGY_ENGINE_DECISION_CREATED.value: "A strategy engine eligibility decision was persisted.",
    EventType.STRATEGY_ENGINE_REJECTED.value: "A strategy engine was rejected with an auditable reason.",
    EventType.STRATEGY_ENGINE_COOLDOWN_CREATED.value: "A strategy engine cooldown record was created.",
    EventType.STRATEGY_ROUTE_INSUFFICIENT_DATA.value: "Strategy Router found insufficient data for routing confidence.",
    EventType.CAPITAL_STATE_CREATED.value: "An internal V2 capital state snapshot was created.",
    EventType.CAPITAL_STATE_UPDATED.value: "An internal V2 capital state snapshot was updated.",
    EventType.ENGINE_BUDGET_CREATED.value: "An internal engine budget was created.",
    EventType.ENGINE_BUDGET_UPDATED.value: "An internal engine budget was updated.",
    EventType.CAPITAL_ALLOCATION_CREATED.value: "A non-executable capital allocation decision was created.",
    EventType.CAPITAL_ALLOCATION_BLOCKED.value: "A capital allocation decision was blocked by policy.",
    EventType.CAPITAL_ALLOCATION_REDUCED.value: "A capital allocation decision was reduced by policy.",
    EventType.REINVEST_PROFIT_POCKET_UPDATED.value: "Profit pocket accounting was updated from realized profit.",
    EventType.REINVEST_ATTACK_BANK_UPDATED.value: "Attack bank accounting was updated from realized profit only.",
    EventType.CAPITAL_EVENT_RECORDED.value: "A capital audit event was recorded.",
    EventType.CAPITAL_INSUFFICIENT_DATA.value: "Capital allocation found insufficient capital data.",
    EventType.RISK_GATE_RUN_STARTED.value: "A non-executing Risk Gate evaluation started.",
    EventType.RISK_GATE_APPROVED.value: "Risk Gate approved a route/allocation as a policy record only.",
    EventType.RISK_GATE_BLOCKED.value: "Risk Gate blocked a route/allocation.",
    EventType.RISK_GATE_REDUCED.value: "Risk Gate reduced a route/allocation.",
    EventType.RISK_GATE_INSUFFICIENT_DATA.value: "Risk Gate found insufficient data.",
    EventType.RISK_GOVERNOR_STATE_UPDATED.value: "Risk Governor state was rebuilt or updated.",
    EventType.RISK_GOVERNOR_BLOCKED.value: "Risk Governor blocked new risk.",
    EventType.RISK_LIMIT_CREATED.value: "A risk limit was created.",
    EventType.RISK_LIMIT_UPDATED.value: "A risk limit was updated.",
    EventType.RISK_BREACH_DETECTED.value: "A risk breach was detected.",
    EventType.RISK_COOLDOWN_CREATED.value: "A risk cooldown was created.",
    EventType.RISK_COOLDOWN_EXPIRED.value: "A risk cooldown expired.",
    EventType.RISK_MANUAL_OVERRIDE_CREATED.value: "An audited manual risk override was created.",
    EventType.RISK_ATTACK_MODE_ALLOWED.value: "Risk Governor allowed attack mode eligibility.",
    EventType.RISK_ATTACK_MODE_BLOCKED.value: "Risk Governor blocked attack mode eligibility.",
    EventType.EXECUTION_ORDER_CREATED.value: "An internal V2 paper/shadow execution order contract was created.",
    EventType.EXECUTION_ORDER_BLOCKED.value: "Execution Cortex V2 blocked an internal paper/shadow execution request.",
    EventType.EXECUTION_ORDER_SUBMITTED_PAPER.value: "A PAPER_SIM order was simulated internally without live send.",
    EventType.EXECUTION_ORDER_PLANNED_SHADOW.value: "A SHADOW_PLAN order was planned internally without external send.",
    EventType.EXECUTION_ORDER_PARTIALLY_FILLED.value: "A PAPER_SIM order was partially filled by simulation.",
    EventType.EXECUTION_ORDER_FILLED.value: "A PAPER_SIM order was filled by simulation.",
    EventType.EXECUTION_ORDER_FAILED.value: "A PAPER_SIM order failed fill simulation.",
    EventType.EXECUTION_ORDER_CANCELLED.value: "An internal V2 order was cancelled by lifecycle rules.",
    EventType.EXECUTION_CANCEL_CONDITION_TRIGGERED.value: "An internal cancel condition triggered.",
    EventType.EXECUTION_FILL_CREATED.value: "A paper/shadow fill simulation record was created.",
    EventType.EXECUTION_QUALITY_RECORDED.value: "Execution quality metrics were recorded.",
    EventType.EXECUTION_ERROR_RECORDED.value: "An execution-layer block or error was recorded.",
    EventType.EXECUTION_LIVE_BLOCKED.value: "A live execution path was blocked because V2.15 is not live-certified.",
    EventType.EXIT_PLAN_CREATED.value: "An internal paper/shadow exit plan was created.",
    EventType.EXIT_PLAN_BLOCKED.value: "Exit Cortex V2 blocked or marked an exit plan insufficient.",
    EventType.EXIT_PLAN_UPDATED.value: "An internal exit plan was updated.",
    EventType.EXIT_TRIGGER_DETECTED.value: "Exit Cortex V2 detected an exit trigger.",
    EventType.EXIT_TAKE_PROFIT_TRIGGERED.value: "A take-profit exit trigger fired.",
    EventType.EXIT_PARTIAL_TAKE_PROFIT_TRIGGERED.value: "A partial take-profit exit trigger fired.",
    EventType.EXIT_STOP_LOSS_TRIGGERED.value: "A stop-loss exit trigger fired.",
    EventType.EXIT_MAX_HOLD_TRIGGERED.value: "A max-hold exit trigger fired.",
    EventType.EXIT_NEWS_INVALIDATED_TRIGGERED.value: "A news or context invalidation exit trigger fired.",
    EventType.EXIT_SPREAD_EXIT_TRIGGERED.value: "A spread-based exit trigger fired.",
    EventType.EXIT_MOMENTUM_DECAY_TRIGGERED.value: "A momentum-decay exit trigger fired.",
    EventType.EXIT_EMERGENCY_TRIGGERED.value: "An emergency internal exit trigger fired.",
    EventType.EXIT_INTENT_BLOCKED.value: "An internal exit intent was blocked by runtime, liquidity, or data constraints.",
    EventType.EXIT_QUALITY_RECORDED.value: "Exit quality metrics were recorded.",
    EventType.EXIT_FAILURE_RECORDED.value: "An exit failure was recorded instead of faking exit success.",
    EventType.EXIT_LIVE_BLOCKED.value: "A live exit request was blocked because V2.16 is not live-certified.",
    EventType.NO_TRADE_LOGGED.value: "A canonical no-trade or blocked candidate decision was logged.",
    EventType.NO_TRADE_REASON_CREATED.value: "A normalized no-trade reason row was created.",
    EventType.NO_TRADE_POST_FACT_REVIEW_CREATED.value: "A no-trade post-fact review was created from later evidence.",
    EventType.NO_TRADE_REGRET_SCORED.value: "A no-trade regret score was created.",
    EventType.NO_TRADE_CANONICAL_MEMORY_UPDATED.value: "A safe no-trade memory update hook was emitted.",
    EventType.NO_TRADE_INSUFFICIENT_DATA.value: "No-trade intelligence found insufficient evidence.",
    EventType.NO_TRADE_HIGH_REGRET.value: "A no-trade review found high regret with sufficient evidence.",
    EventType.NO_TRADE_GOOD_DECISION.value: "A no-trade review found a good no-trade decision.",
    EventType.SIGNAL_CREATED.value: "A non-live signal was created by a permitted runtime mode.",
    EventType.OPPORTUNITY_SCORED.value: "An opportunity score was produced.",
    EventType.STRATEGY_ROUTED.value: "A future strategy router decision was produced.",
    EventType.RISK_APPROVED.value: "A future risk gate approved a candidate.",
    EventType.RISK_REJECTED.value: "A future risk gate rejected a candidate.",
    EventType.ORDER_INTENT_CREATED.value: "An order intent was created; replay must not send live orders.",
    EventType.ORDER_CREATED.value: "An order record was created; replay must not send live orders.",
    EventType.POSITION_OPENED.value: "A position record opened.",
    EventType.EXIT_INTENT_CREATED.value: "An internal paper/shadow exit intent was created without live send.",
    EventType.TRADE_CLOSED.value: "A trade or position was closed.",
    EventType.LEARNING_UPDATED.value: "A future learning loop update was recorded.",
    EventType.LEARNING_TRADE_REVIEW_CREATED.value: "A completed internal paper/shadow outcome review was recorded.",
    EventType.LEARNING_SIGNAL_PERFORMANCE_UPDATED.value: "A signal performance learning record was created.",
    EventType.LEARNING_ENGINE_UPDATED.value: "An engine learning record was created.",
    EventType.LEARNING_SOURCE_UPDATED.value: "A source reliability learning record was created.",
    EventType.LEARNING_WHALE_UPDATED.value: "A whale learning record was created.",
    EventType.LEARNING_AI_UPDATED.value: "An AI usefulness/cost learning record was created.",
    EventType.LEARNING_NO_TRADE_UPDATED.value: "A no-trade regret learning record was created.",
    EventType.LEARNING_MODEL_ADJUSTMENT_RECOMMENDED.value: "A recommendation-only model adjustment was created.",
    EventType.LEARNING_MEMORY_UPDATE_APPLIED.value: "A safe aggregate memory update was applied from evidence.",
    EventType.LEARNING_INSUFFICIENT_DATA.value: "Learning could not score an outcome because evidence was insufficient.",
    EventType.RUNTIME_CYCLE_STARTED.value: "A runtime cycle started.",
    EventType.RUNTIME_CYCLE_FINISHED.value: "A runtime cycle finished.",
    EventType.RUNTIME_MODE_CHANGED.value: "Runtime mode changed through the governor.",
    EventType.RUNTIME_SERVICE_HEALTH_UPDATED.value: "Runtime service health was updated.",
    EventType.EVENT_DLQ_CREATED.value: "An event delivery moved to the DLQ.",
    EventType.EVENT_REPLAY_REQUESTED.value: "An event replay was requested.",
    EventType.AI_REQUEST_CREATED.value: "A non-executing AI interpretation request was accepted.",
    EventType.AI_CACHE_HIT.value: "AI cache prevented a duplicate model call.",
    EventType.AI_BUDGET_BLOCKED.value: "The AI Budget Governor blocked a model call.",
    EventType.AI_LOCAL_COMPLETED.value: "A local AI interpretation completed.",
    EventType.AI_CLOUD_ESCALATED.value: "A cloud escalation was requested or approved.",
    EventType.AI_CLOUD_COMPLETED.value: "A cloud AI interpretation completed.",
    EventType.AI_DECISION_LOGGED.value: "A structured AI interpretation decision was logged.",
    EventType.AI_COST_RECORDED.value: "An AI cost ledger entry was recorded.",
    EventType.AI_MODEL_PERFORMANCE_UPDATED.value: "AI model performance truth was updated.",
}


def normalize_event_type(value: EventType | str) -> str:
    if isinstance(value, EventType):
        return value.value
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("event_type is required")
    return normalized


def is_known_event_type(value: EventType | str) -> bool:
    normalized = normalize_event_type(value)
    return normalized in {event_type.value for event_type in EventType}


def validate_event_type(value: EventType | str, *, allow_custom: bool = False) -> str:
    normalized = normalize_event_type(value)
    if is_known_event_type(normalized) or allow_custom:
        return normalized
    raise ValueError(f"unknown event_type: {normalized}")
