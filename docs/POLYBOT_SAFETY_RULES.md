# POLYBOT Safety Rules

POLYBOT safety is mandatory.

## Core Rules

- Live trading must remain disabled unless explicitly approved.
- KILL blocks all trading.
- DATA_ONLY cannot create orders.
- PAPER cannot send live orders.
- SHADOW_LIVE cannot send live orders.
- Missing data leads to NO_TRADE.
- No entry without exit plan.
- Risk Gate cannot be bypassed.
- State Governor cannot be bypassed.
- AI cannot execute trades.
- Secrets must never be printed.

## Forbidden Without Explicit Approval

- editing live trading path
- editing order/fill/position creation logic
- editing Risk Governor core
- editing State Governor core
- destructive DB migration
- disabling tests
- weakening safety checks
- mock dashboard data pretending to be live
- printing .env values

## Review Status

GREEN:
Safety intact.

YELLOW:
Possible issue, needs human review.

RED:
Safety broken or unclear.
Do not continue.
