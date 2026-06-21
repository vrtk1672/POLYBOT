---
name: polybot-current-reality-auditor
description: Audit the current POLYBOT repository reality before implementing a phase. Use before coding or when checking what exists vs what is missing.
---

# POLYBOT Current Reality Auditor

Before implementation, inspect:
- related files
- existing tables
- existing APIs
- existing services
- existing tests
- existing safety mechanisms
- duplicate components
- stale docs
- broken assumptions

Return:

1. Existing assets
2. Missing assets
3. Conflicts
4. Safety concerns
5. Suggested implementation boundary
6. Files to inspect next
7. Status: GREEN/YELLOW/RED

Do not modify files unless explicitly asked.
