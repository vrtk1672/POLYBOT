# POLYBOT Agent Workflow

## Before Coding

- Read `AGENTS.md`.
- Read `docs/POLYBOT_CONTEXT_INDEX.md`.
- Read current phase docs and relevant build reports.
- Inspect existing code before changing it.
- Do not assume missing context.
- Check current git status and avoid reverting user or prior-agent work.

## During Coding

- Make small focused changes.
- Preserve existing assets, reports, migrations, and working paths.
- Avoid broad rewrites and unrelated refactors.
- Use existing repository, service, contract, API, and test patterns.
- Add tests with implementation.
- Keep runtime safety checks strict.
- Do not expose secrets or print raw environment values.

## After Coding

- Run targeted tests.
- Run regression tests when touching runtime, safety, paper, live, scheduler, API, or dashboard.
- Update docs.
- Produce a build report.
- List what remains partial.
- Include rollback notes when persistence or runtime behavior changes.

## Every Phase Must Include

- Implementation.
- Tests.
- Verification.
- Self-review.
- Report.

## Failure Handling

- Never hide failing tests.
- Never mark complete if critical phase tests fail.
- Distinguish unrelated legacy/environment failures from phase failures.
- If tests are skipped because DB or external services are missing, say that directly.
- If a safety test fails, stop and fix before claiming progress.

## Definition of Done Checklist

- Scope implemented and contained.
- No unrelated behavior changes.
- Required migrations added and verified.
- API/dashboard truth is real, not fake.
- Targeted tests run.
- Regressions run when relevant.
- Build report created.
- Remaining risks documented.
- Safe to proceed status stated.
