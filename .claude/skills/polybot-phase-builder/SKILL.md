---
name: polybot-phase-builder
description: Build a strict implementation prompt for one POLYBOT V2 phase. Use when preparing work for Claude Code, Codex, or another coding agent.
---

# POLYBOT Phase Builder

Generate an implementation prompt with:

1. Mission
2. Project Identity
3. Mandatory Context Files
4. Current Phase
5. Current Reality step
6. Scope
7. Out of Scope
8. Preserve
9. Files to inspect
10. Files to create
11. Files to modify
12. DB requirements
13. API requirements
14. Dashboard requirements
15. Runtime integration
16. Safety requirements
17. Tests required
18. Verification commands
19. Self-review
20. Documentation
21. Final output format
22. GREEN/YELLOW/RED rule

Rules:
- one phase only
- no open-ended prompts
- no future phases
- no live trading
- no fake dashboard data
- no bypass of State Governor or Risk Gate
- do not create duplicate DB truth
