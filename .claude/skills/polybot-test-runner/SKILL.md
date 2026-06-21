---
name: polybot-test-runner
description: Prepare and run scoped verification commands for POLYBOT phases. Use when validating implementation, Docker, DB, API, runtime, or tests.
---

# POLYBOT Test Runner

Always separate:

1. Targeted phase tests
2. Safety tests
3. Regression tests
4. Runtime smoke
5. DB verification
6. API verification

Rules:
- Never mark GREEN if targeted phase tests fail.
- Never hide failing commands.
- Report exact commands.
- Report exact results.
- If a failure is unrelated, mark YELLOW and explain.
- If safety fails, mark RED.

Return:
1. Commands run
2. Results
3. Failures
4. Likely root cause
5. Required fix
6. Status: GREEN/YELLOW/RED
