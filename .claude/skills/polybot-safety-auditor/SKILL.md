---
name: polybot-safety-auditor
description: Audit POLYBOT safety rules, State Governor, Risk Gate, execution blocks, live-disabled behavior, and NO_TRADE defaults.
---

# POLYBOT Safety Auditor

Check:
- KILL blocks trading
- DATA_ONLY blocks orders
- PAPER blocks live orders
- SHADOW_LIVE blocks live orders
- live disabled by default
- no secrets printed
- missing data leads to NO_TRADE
- no entry without exit plan
- AI cannot execute trades
- State Governor respected
- Risk Gate not bypassed
- Execution cannot create unsafe orders

Return:
- Findings
- Violations
- Required fixes
- Status: GREEN/YELLOW/RED
