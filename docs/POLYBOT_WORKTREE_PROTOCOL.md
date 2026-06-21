# POLYBOT Worktree Protocol

## Current Status

**Git worktree is currently PAUSED (as of 2026-05-28).**

Worktree setup was attempted but created operational friction and has been set aside temporarily.
All Claude Code work is currently being done in Direct Mode inside:
```
C:\Server\apps\polybot
```

Direct Mode requires stricter per-task scope definition. See `docs/POLYBOT_CLAUDE_DIRECT_MODE_PROTOCOL.md`.

Worktree remains the recommended isolation strategy. It can be re-enabled when the team is ready.
Re-enable worktree when: Claude Code and Codex need to work in parallel, or any task touches more than 5 files across different domains.

---

## 1. Purpose

Git worktree allows Claude Code and Codex to work in parallel on isolated branches without touching the main working directory.

This prevents:
- Conflicting file edits between Claude Code and Codex running simultaneously.
- Accidental overwrite of in-progress Codex work by a Claude Code audit.
- Main repo instability during a long-running agent task.

Use worktrees whenever Claude Code and Codex are working in parallel, or when a task is risky enough to deserve isolation before review and merge.

---

## 2. Recommended Structure

```
C:\Server\apps\polybot                         ← main repo (always stable)
C:\Server\apps\polybot-claude-link-coverage    ← Claude Code: link coverage hardening
C:\Server\apps\polybot-claude-docs             ← Claude Code: docs sync, protocol updates
C:\Server\apps\polybot-claude-signal-quality   ← Claude Code: signal quality work
C:\Server\apps\polybot-codex-core              ← Codex: core architecture work
C:\Server\apps\polybot-codex-risk-fix          ← Codex: risk governor fix
```

Each worktree is a real checkout of the repo with its own branch.
Changes in one worktree do not affect another until merged.

---

## 3. When to Use Worktree

Use worktree when:
- Claude Code and Codex are working in parallel on the same repository.
- A task is risky enough that you want to isolate it before review.
- A long-running agent task (e.g., coverage hardening) needs its own branch.
- You want to do an isolated review of a branch without touching main.
- Codex is paused but Claude Code can continue safely on a parallel branch.

Do not use worktree for quick single-file documentation changes that carry no risk.
Do use worktree for any task that modifies more than 3 files or runs for more than one agent session.

---

## 4. Branch Naming

### Claude Code branches
```
claude/link-coverage-hardening
claude/signal-quality-gates
claude/lineage-coverage-hardening
claude/dry-run-provenance
claude/mesh-blockers-dashboard
claude/producer-health-accuracy
claude/docs-sync
claude/dashboard-truth-[feature]
claude/test-writer-[phase]
```

### Codex branches
```
codex/risk-core-fix
codex/execution-core-fix
codex/exit-foundation
codex/capital-allocator-fix
codex/state-governor-update
codex/dangerous-migration-[name]
```

### Convention
- Always prefix with the agent name.
- Always use a descriptive slug.
- Never use `main`, `master`, or `production` as a worktree branch name.

---

## 5. Safety Rules

- The main repo stays stable at all times. No direct commits to main from a worktree without review.
- No production migrations may be run from a worktree without explicit ChatGPT approval.
- No LIVE, SHADOW_LIVE, or PAPER activation from a worktree.
- Before merging a worktree branch: run `git diff main...[branch]` and review all changes.
- ChatGPT must review all worktree output before merge.
- If Codex built the worktree content, Codex reviews Claude Code's worktree output before merge, if relevant.
- Delete the worktree after the branch is merged or abandoned. Do not leave stale worktrees.

---

## 6. Commands

**For reference only. Do not run these without task context and approval.**

Check current worktrees:
```
git worktree list
```

Create a new Claude Code worktree:
```
git worktree add ..\polybot-claude-link-coverage -b claude/link-coverage-hardening
```

Create a new Codex worktree:
```
git worktree add ..\polybot-codex-core -b codex/risk-core-fix
```

Check status inside a worktree:
```
cd ..\polybot-claude-link-coverage
git status
git branch
```

Remove a worktree after merge:
```
git worktree remove ..\polybot-claude-link-coverage
```

View all local branches:
```
git branch
```

View diff between worktree branch and main before merge:
```
git diff main...claude/link-coverage-hardening --stat
```

---

## 7. Merge Protocol

1. Claude Code completes work in worktree.
2. Claude Code runs final verification inside the worktree.
3. Claude Code produces final output (summary, files, tests, status).
4. ChatGPT reviews the output.
5. If GREEN: ChatGPT approves merge.
6. Merge the branch into main (or the target integration branch).
7. Remove the worktree.
8. Update docs/POLYBOT_CONTEXT_INDEX.md to reflect the completed phase.

Never merge a YELLOW or RED worktree output without explicit ChatGPT approval and a documented remediation plan.
