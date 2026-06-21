# POLYBOT Prompt Operating System

Every implementation prompt for POLYBOT must act like a contract.

No open-ended agent work.
No vague "improve the system" tasks.
No future-phase implementation.
No safety bypass.

## Standard Prompt Structure

1. Mission
2. Project Identity
3. Mandatory Context Files
4. Current Phase
5. Current Reality
6. Exact Scope
7. Out of Scope
8. Existing Assets to Preserve
9. Files to Inspect
10. Files to Create
11. Files to Modify
12. DB Requirements
13. API Requirements
14. Dashboard Requirements
15. Runtime Integration
16. Safety Requirements
17. Tests Required
18. Verification Commands
19. Self-Review
20. Documentation / Build Report
21. Final Output Format
22. GREEN / YELLOW / RED Rule

## Project Identity

POLYBOT is a 24/7 Adaptive Asymmetric Money Engine for prediction markets.

It hunts measurable Edge.
It does not chase every trade.
It searches 24/7, but it does not have to trade 24/7.
NO_TRADE is a first-class decision.

Core principle:
Upside open.
Downside defined.

## Mandatory Safety Rules

- KILL blocks trading
- DATA_ONLY must not create orders
- PAPER must not send live orders
- SHADOW_LIVE must not send live orders
- live trading disabled by default
- no secrets printed
- missing data leads to NO_TRADE
- no entry without exit plan
- AI cannot execute trades
- every action respects State Governor
- Risk Gate cannot be bypassed
- Execution cannot create orders without required safety context

## GREEN / YELLOW / RED

GREEN:
Phase is complete, relevant tests passed, safety is intact.

YELLOW:
Phase is partially complete or has non-critical blockers. Human decision needed.

RED:
Phase is not ready. Do not continue.

Hard RED:
- phase tests failed
- safety tests failed
- live safety unclear
- secrets exposed
- State Governor bypassed
- Risk Gate bypassed
- fake dashboard data introduced

Do not claim success unless tests actually pass.
