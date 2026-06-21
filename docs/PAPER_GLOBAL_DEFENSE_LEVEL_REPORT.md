# Paper Global Defense Level Report

## Purpose

Implement a unified PAPER-only protection dial:

`paper_defense_level = 0..100`

The dial applies to the normal PAPER runtime. It does not create a separate trading mode, does not touch live/shadow/real execution, and does not fabricate trades.

## User Principle

PAPER is the learning and simulation environment. Defense 100 preserves strict behavior. Lower defense levels let strategic PAPER blockers become warnings, ignored blockers, or fallback requirements while integrity blockers remain hard.

## Audit Findings

- Paper threshold was defined in `app/services/paper_runtime_decisions.py` as `PAPER_OBSERVATION_SCORE_THRESHOLD = 60`.
- `OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD` was produced in `build_paper_runtime_decision`.
- Runtime blockers were built as hard blockers and warnings in `PaperRuntimeDecisionService`.
- Display-only blocker metadata lived in `DecisionAutopsyService`.
- `EXISTING_HARD_BLOCKERS_PRESENT` was an umbrella blocker around upstream hard blockers.
- `THESIS_NOT_SUPPORTED`, `EXIT_NOT_READY`, `EDGE_NOT_SUPPORTED`, `DECISION_BAND_NOT_PAPER_OBSERVATION`, and `OBSERVATION_POLICY_NOT_ALLOWED` were PAPER runtime blockers.
- Duplicate/open exposure and same-market opposing side guards were session-aware and must remain protective.
- Paper capital limits came from `paper_accounts`; reset default was conservative.
- Session reset did not have a defense-level field before this change.
- Standardized session learning report did not exist before this change.

## Defense Level Design

Implemented `PaperDefenseGovernor` in `app/services/paper_defense.py`.

Default behavior is strict: existing sessions default to defense 100 unless explicitly set lower.

Defense profile includes:

- base threshold
- adjusted threshold
- max deployed percent
- max single trade percent
- max open positions
- cash reserve
- fallback exit enabled/disabled
- strategic blocker behavior
- integrity blocker behavior

## Blocker Category Map

Categories:

- `SYSTEM_INTEGRITY`: never ignored.
- `EXECUTION_VALIDITY`: remains hard unless a safe existing fallback exists.
- `STRATEGIC_PROTECTION`: can soften or be ignored for learning.
- `EXIT_REQUIREMENT`: can become fallback learning exit at low defense.

## Hard At Defense 0

Examples:

- invalid/missing market
- missing token
- invalid side
- closed market
- no active paper session
- missing executable price
- missing quantity
- broken paper account
- insufficient paper balance
- live/shadow/real forbidden markers
- duplicate active same-session exposure
- same-market opposing ENTER conflict
- stale/missing trusted orderbook unless a safe execution fallback is explicitly supported

## Softened At Defense 20

Examples:

- opportunity score below strict threshold
- thesis not supported
- edge not supported
- observation policy not allowed
- decision band not paper observation
- existing hard blockers when underlying blockers are strategic
- exit not ready, if fallback learning exit is recorded

## Threshold Scaling

Implemented profile bands:

- 100: 60
- 80: 57
- 60: 53
- 40: 48
- 20: 42
- 0: 30

Each decision records base threshold, adjusted threshold, strict verdict, and effective verdict.

## Capital Scaling

Implemented PAPER account scaling on session reset / defense update:

- 100: max deployed 20%, max single trade 2%, max open positions 2
- 60: max deployed 50%, max single trade 5%, max open positions 5
- 20: max deployed 80%, max single trade 15%, max open positions 15
- 0: max deployed 95%, max single trade 20%, max open positions 25

The existing paper capital guard remains active and still blocks impossible or underfunded accounting.

## Fallback Exit Rules

At defense <= 40, `EXIT_NOT_READY` can become a `FALLBACK_LEARNING` exit requirement instead of a hard blocker.

Fallback exit metadata includes:

- max hold minutes
- emergency stop loss
- take profit target
- score decay exit
- liquidity exit
- stale data exit

## Ignored / Softened Blocker Ledger

Added `paper_learning_ledger`.

It records:

- paper session
- runtime decision
- strict/effective verdict
- strict/effective blockers
- ignored blockers
- softened blockers
- fallback requirements
- base/adjusted threshold
- score
- exit plan type
- entry metadata

## Session Learning Report Schema

Added report/export service with:

- session metadata
- result summary
- hunting summary
- trade table
- learning analysis
- stable machine learning export payload

Generated files:

- `paper_session_learning_report_<session_id>.json`
- `paper_session_learning_report_<session_id>.md`
- `paper_session_trades_<session_id>.csv`

## CLI Commands

Added:

- `.\tools\polybot.ps1 set-paper-defense 20`
- `.\tools\polybot.ps1 paper-defense`
- `.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20`
- `.\tools\polybot.ps1 reset-paper-session -balance 1000 -defense 20`
- `.\tools\polybot.ps1 paper-session-report`
- `.\tools\polybot.ps1 export-paper-session`

## API Endpoints

Added:

- `GET /dashboard/api/v2/control/paper-defense`
- `POST /dashboard/api/v2/control/paper-defense`
- `GET /dashboard/api/v2/control/paper-session/learning-report`
- `GET /dashboard/api/v2/control/paper-session/export`

## Tests Run

- Focused defense tests: `11 passed, 3 skipped`
- Related PAPER/session/autopsy regressions: `1 passed, 13 skipped`
- Focused post-safety-patch policy tests: `6 passed`
- Compile: `python -m compileall app tests` passed

Skipped tests required `POLYBOT_DATABASE_URL` in the local pytest shell. Docker-backed migration and API verification were run separately.

## Runtime Verification

Deployment:

- `docker compose build api`: passed
- `docker compose build migrate`: passed
- `docker compose run --rm migrate`: applied `0147_paper_global_defense_level.sql`
- `docker compose up -d --no-deps api`: passed
- `/healthz`: ok

Final low-defense smoke:

- Command: `.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20`
- Active session: `paper_session_20260619T212911Z_7cc207a2`
- Defense level: 20
- Adjusted threshold: 42
- Max deployed capital: 80%
- Max single trade: 15%
- Max open positions: 15
- Exit fallback: enabled
- Learning ledger entries after forced decision refresh: 17
- Ignored blockers: 15
- Softened blockers: 15
- Fallback exits: 15
- Runtime decisions after refresh: 17
- ENTER decisions after refresh: 1
- Current session paper intents/orders/fills/positions: 0/0/0/0 in final smoke
- Live/shadow/real: 0/0/0
- SYSTEM OFF cleanup: completed

A previous pre-final-container smoke produced one current-session paper intent after defense 20 refresh; final container smoke verified defense/ledger/report behavior but did not naturally run the intent gate into a new intent during the short window.

## Example Defense 20 Session

`paper-defense` output showed:

- Defense level: 20
- Base threshold: 60
- Adjusted threshold: 42
- Max deployed capital: 80
- Max single trade: 15
- Strategic blockers: WARNING_ONLY
- Integrity blockers: HARD

## Example Defense 0 Policy

Defense 0 lowers the threshold to 30 and permits strategic blockers to be ignored for learning. Integrity and execution-validity blockers remain hard.

## Remaining Risks

- The requested 30-minute runtime observation was not completed; only short controlled smoke verification was run after final deploy.
- Low defense can create many same-market opposing ENTER candidates; same-market conflict remains hard and currently blocks those logically conflicting entries.
- Execution can still block low-defense intents if trusted orderbook/executable price evidence is missing. This is intentional.
- Advanced report metrics such as max drawdown, MFE/MAE, and profit factor are scaffolded but need more closed trades for meaningful output.

## Status

YELLOW.

The defense system is implemented and verified at API/CLI/schema/decision-ledger level. A longer PAPER observation is still needed before calling it GREEN.

## Safe To Continue Paper Learning Sessions

YES for defense 20.

Defense 0 is implemented with integrity blockers preserved, but should be treated as experimental until a longer supervised PAPER observation is completed.
