---
name: polybot-output-reviewer
description: Review Codex or Claude implementation output for POLYBOT. Use when the user pastes an agent build report, test output, changed files, or asks if a phase is GREEN/YELLOW/RED.
---

# POLYBOT Output Reviewer

Review the agent output against:
- scope
- current phase
- files changed
- DB migrations
- API truth
- dashboard truth
- safety
- tests
- verification
- build report honesty

Return:

1. Scope status: GREEN/YELLOW/RED
2. Architecture status: GREEN/YELLOW/RED
3. DB status: GREEN/YELLOW/RED
4. API status: GREEN/YELLOW/RED
5. Dashboard status: GREEN/YELLOW/RED
6. Safety status: GREEN/YELLOW/RED
7. Test status: GREEN/YELLOW/RED
8. Final status: GREEN/YELLOW/RED
9. Can continue: YES/NO
10. Required fixes

Hard RED:
- phase tests failed
- safety tests failed
- live safety unclear
- secrets exposed
- State Governor bypassed
- Risk Gate bypassed
- fake dashboard data introduced
