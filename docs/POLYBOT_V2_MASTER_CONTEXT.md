# POLYBOT V2 Master Context

## What POLYBOT Is

POLYBOT is intended to become a 24/7 Adaptive Asymmetric Money Engine for prediction markets. It searches continuously for measurable Edge: mispriced contracts, repricing opportunities, fast price movement, cheap convex outcomes, chaos, stale consensus, and asymmetric setups.

It keeps upside open and downside defined. It does not need to trade constantly. `NO_TRADE` is strength, not weakness.

## What POLYBOT Is Not

POLYBOT is not a generic chatbot, gambling bot, market screener, or always-on trade spammer. It is not designed to win every bet. It is designed to avoid bad bets, preserve capital, and deploy only when the setup is good enough.

## Core Thesis

Prediction markets contain repeatable inefficiencies because information, liquidity, wording, social attention, market maker behavior, and settlement risk do not update at the same speed. POLYBOT should identify when price is wrong, when the wrongness can be monetized, and when the cost of waiting, exiting, or being trapped makes the trade unattractive.

## Prediction-Market Specific Risks

- Ambiguous rules or resolution wording.
- Delayed settlement and locked capital.
- Thin orderbooks and wide spreads.
- Adverse selection from informed counterparties.
- Liquidity cliffs.
- Market maker rewards and fee distortions.
- Social hype that moves price without durable edge.
- Correlated markets causing hidden concentration.
- News events that change faster than model refresh cycles.

## Settlement Profit vs Price Movement Profit

Settlement profit comes from holding a correctly priced contract to resolution. Price movement profit comes from buying before repricing and exiting before settlement. POLYBOT must score both, because many attractive trades are not attractive holds.

## Time-Adjusted ROI

A 20 percent profit in one day is not equivalent to a 20 percent profit over six months. Time-adjusted ROI matters because capital can recycle. POLYBOT must penalize long lockups unless the edge, convexity, or certainty justifies the capital duration.

## Neural Mesh

The Neural Mesh is the future event-driven intelligence layer. Each neuron observes a domain and emits structured truth or signals. The mesh lets the system combine independent evidence without turning every service into one large controller.

## Main Neurons

- News: detects fresh external events and repricing catalysts.
- Whale: tracks large traders, positions, and activity shifts.
- Market: reads price, probability, and market structure.
- Orderbook: evaluates depth, spread, slippage, and fill quality.
- Liquidity: identifies whether entry and exit are realistic.
- Time: scores duration, urgency, decay, and settlement horizon.
- Social / Hype: detects attention surges and narrative risk.
- Rules / Wording: evaluates resolution criteria and ambiguity.
- Fees / Rewards: accounts for maker incentives and transaction costs.
- Risk: identifies downside, concentration, and trap conditions.
- Capital: evaluates cash, allocation, recycling, and exposure.
- Position: monitors active holdings and thesis state.
- Exit: watches invalidation, profit-taking, and reduction triggers.
- Memory: stores historical behavior, outcomes, and learned patterns.

## Main Brains

- Context Brain: builds the full market context from all neurons.
- Capital Brain: decides whether capital should be deployed, reserved, recycled, or protected.
- Hybrid AI Brain: uses AI for interpretation and synthesis, but never for unguarded execution.

## Main Engines

- SAFE: conservative asymmetric setups.
- STRIKE: high-confidence time-sensitive repricing opportunities.
- CONVEX: cheap contracts with bounded downside and large upside.
- MAKER: liquidity-provision and reward-aware strategies.
- HUNT: active search mode for rare high-edge setups.
- MOONSHOT_BASKET: small diversified convex basket.
- REINVEST: recycles realized gains under strict rules.
- NO_TRADE: explicit decision to preserve capital.

## Opportunity Score Components

Positive components:

- Edge.
- Confidence.
- Trigger Strength.
- Repricing Potential.
- Time Efficiency.
- Liquidity Quality.
- Exit Probability.
- Capital Recycling Speed.
- Convexity.
- Balance Fit.
- Fee / Reward Advantage.

Penalties:

- Risk.
- Slippage.
- Lockup Penalty.
- Correlation Risk.
- Trap Risk.
- Wording Risk.
- Adverse Selection Risk.

## Market Memory

Market Memory V2 should remember how markets behave, how similar setups resolved, whether signals were early or late, whether exits were available, and whether prior assumptions held. Memory is not just storage; it is feedback for future scoring and risk.

## Execution Cortex Rules

Execution Cortex must never send orders without mode permission, risk approval, liquidity validation, and an exit plan. It must prefer no action over unsafe action. AI may inform execution context but cannot bypass guards.

## Exit Cortex Rules

Every entry must have an exit thesis. Exit Cortex should monitor profit targets, invalidation, time decay, liquidity loss, wording changes, news reversal, whale behavior, and opportunity cost.

## Risk Gate vs Risk Governor

Risk Gate is per-decision approval: can this action happen now? Risk Governor is system-wide authority: what mode, exposure, limits, and emergency constraints apply? Both are required before real trading.

## No-Trade Intelligence

`NO_TRADE` should be explainable and learned from. Reasons include missing data, weak edge, wide spread, poor liquidity, ambiguous wording, adverse selection, poor time-adjusted ROI, excessive correlation, or no viable exit.

## Observability / Dashboard Truth

Dashboard data must come from real runtime truth, DB state, or service output. No fake controls, mock runtime state, or invented health should appear in operator views.

## Final Operating Principle

The system searches 24/7. It does not have to trade 24/7. `NO_TRADE` is strength, not weakness.
