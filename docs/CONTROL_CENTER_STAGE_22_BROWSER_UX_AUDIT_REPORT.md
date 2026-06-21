# POLYBOT Control Center V1.5 - Stage 22 Browser UX Audit Report

Date: 2026-06-08
Executor: Codex
Task Mode: READ_ONLY_BROWSER_AUDIT
Risk: LOW / MEDIUM
Product Code Changed: NO
Backend Behavior Changed: NO
Trading Logic Changed: NO

## 1. Executive Summary

Stage 22 completed a real browser-based audit of `http://127.0.0.1:8000/control-center` using regular Playwright.

Technical health is GREEN:

- `/control-center` returned HTTP 200.
- Docker `polybot_api` was healthy.
- Control Center assets loaded with HTTP 200.
- All observed Control Center API calls returned HTTP 200.
- Console errors: 0.
- Network failures: 0.
- Wrong-base-url requests: 0.
- Screenshots, raw evidence, accessibility snapshots, and trace were captured.

Operator UX is not GREEN:

- The Command Cockpit is technically rich but visually dense.
- The first screen contains many similarly weighted cards.
- The page still reads partly like a debug report.
- The Full Monitor Run action submitted successfully to the safe wrapper, but the operator-facing result was `LOCKED` and the run panel still said no run had started.
- The Command Cockpit said `No mesh dialogue events recorded yet`, while the Mesh Dialogues detail page showed `REAL`, `50` dialogue events from `brain_dialogue_events`.

Audit status is GREEN because the audit completed with evidence. Product readiness for the operator cockpit remains YELLOW and should move to Stage 23 planning.

## 2. Tools Used

- Node `v24.15.0`
- npm `11.14.1`
- Playwright `1.60.0`
- Chromium installed by `npx playwright install chromium`
- Docker Compose
- PowerShell `Invoke-WebRequest` / `Invoke-RestMethod`
- Custom audit script: `run_reports/control_center_ui_audit/audit-control-center.mjs`

## 3. Browser Setup

Playwright was initially available through `npx`, but the local audit script could not import the `playwright` package from `run_reports`.

Allowed remediation was used:

```powershell
cd C:\Server\apps\polybot\frontend\control-center
npm i -D @playwright/test
npx playwright install chromium
```

Files changed only for audit tooling:

- `frontend/control-center/package.json`
- `frontend/control-center/package-lock.json`

No product component, backend route, trading logic, Docker config, or UI behavior was changed.

## 4. Pages Audited

Audited pages / sections:

1. Command Cockpit
2. Decision
3. Money
4. Live
5. Controls
6. Advanced navigation group
7. Organ Health
8. Truth State
9. Risk Evidence Mesh
10. Lifecycle Governance
11. Mesh Dialogues
12. AI Brain
13. Logs & Errors
14. Positions
15. No-Trade

`Advanced` is a navigation group, not a standalone page. Screenshot `06-advanced.png` captures the advanced navigation state while still on the Controls view.

## 5. Screenshots Captured

Saved under `run_reports/control_center_ui_audit/screenshots/`:

- `01-command-cockpit.png`
- `02-decision.png`
- `03-money.png`
- `04-live.png`
- `05-controls.png`
- `06-advanced.png`
- `07-organ-health.png`
- `08-truth-state.png`
- `09-risk-evidence-mesh.png`
- `10-lifecycle-governance.png`
- `11-mesh-dialogues.png`
- `12-ai-brain.png`
- `13-logs-errors.png`
- `14-positions.png`
- `15-no-trade.png`
- `full-monitor-run-before.png`
- `full-monitor-run-after.png`

Trace captured:

- `run_reports/control_center_ui_audit/traces/control-center-ui-audit.zip`

## 6. Console Findings

Raw file:

- `run_reports/control_center_ui_audit/raw/console.json`

Observed:

- Console entries: `[]`
- JavaScript errors: 0
- React errors: 0
- Page exceptions: 0
- Failed imports surfaced in console: 0
- Asset loading errors surfaced in console: 0

## 7. Network Findings

Raw file:

- `run_reports/control_center_ui_audit/raw/network.json`

Observed:

- Total requests: 52
- Total responses: 50
- Network failures: 0
- HTTP 404/500 responses: 0
- Wrong base URL / `:5173` requests: 0
- `/control-center`: 200
- JS asset `/control-center/assets/index-yxujyOPy.js`: 200
- CSS asset `/control-center/assets/index-CaUIQiqV.css`: 200
- All observed `/dashboard/api/v2/control/*` responses: 200
- Full Monitor Run action wrapper POST: 200

## 8. Visible Controls Matrix

Raw file:

- `run_reports/control_center_ui_audit/raw/control-buttons-matrix.json`

Observed on Command Cockpit first screen:

| Button | First Screen | Prominent | Requires Actor | Requires Reason | Protected | Dangerous | Disabled Initially |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SYSTEM ON | YES | YES | YES | YES | YES | YES | YES |
| SYSTEM OFF | YES | YES | YES | YES | YES | YES | YES |
| START FULL MONITOR RUN | YES | YES | YES | YES | YES | NO | YES |
| STOP CURRENT RUN | YES | YES | YES | YES | YES | NO | YES |
| KILL SWITCH | YES | YES | YES | YES | YES | YES | YES |
| REFRESH | YES | YES | UI still shows actor/reason nearby | UI still shows actor/reason nearby | YES/LOW-RISK | NO | NO |
| EXPORT REPORT | YES | YES | UI still shows actor/reason nearby | UI still shows actor/reason nearby | YES/LOW-RISK | NO | NO |

Evidence:

- Screenshot: `01-command-cockpit.png`
- Raw matrix: `control-buttons-matrix.json`

KILL SWITCH was not activated. Audit only verified that it is visible, disabled initially, and has a `KILL confirmation` field.

## 9. Full Monitor Run Flow

Raw file:

- `run_reports/control_center_ui_audit/raw/full-monitor-run-flow.json`

Operator flow result: PARTIAL

Technical request result:

- Button found: YES
- Initially disabled: YES
- Filled actor: `harel`
- Filled reason: `browser audit test`
- Filled duration: `1`
- Enabled after required fields: YES
- POST sent to: `/dashboard/api/v2/control/actions/start-full-monitor-run`
- Response status: 200

Observed UI after submit:

```text
Last action: start-full-monitor-run LOCKED State Governor does not allow monitoring/data collection in the current mode.
```

The Full Monitor Run panel still showed:

```text
No Full Monitor Run has been started in this process.
```

Evidence:

- Before screenshot: `screenshots/full-monitor-run-before.png`
- After screenshot: `screenshots/full-monitor-run-after.png`
- Raw request/response: `raw/full-monitor-run-flow.json`

Conclusion:

The safe action wrapper works and gives feedback, but the operator flow is not fully successful because the UI does not transition into a running/completed/latest run state. The lock reason is visible but not explained as a guided operator next step.

## 10. Live Feed Analysis

Raw file:

- `run_reports/control_center_ui_audit/raw/live-feed-analysis.json`

Dedicated Live page:

- Status: `REAL`
- Truth state: `ACTIVE_FRESH`
- Source: `event_log`
- Events returned: `50`
- Visible events include `runtime.cycle.finished` and `runtime.cycle.started`.
- Timestamps are visible.
- Event IDs are visible.
- Network endpoint `/dashboard/api/v2/control/live-flow` returned 200.

Command Cockpit live feed:

- Shows `Live System Feed`.
- Shows recent `runtime.cycle.finished` / `runtime.cycle.started`.
- Shows timestamps.
- Repeats generic text: `Source row returned without summary text.`

Observed issue:

The system is live at the data layer, but the feed reads like raw runtime logs. It does not yet narrate what POLYBOT is doing in operator language.

## 11. Neural Dialogue Analysis

Raw file:

- `run_reports/control_center_ui_audit/raw/neural-dialogue-analysis.json`

Command Cockpit:

```text
No mesh dialogue events recorded yet.
```

Dedicated Mesh Dialogues page:

- Status: `REAL`
- Truth state: `ACTIVE_FRESH`
- Source: `brain_dialogue_events`
- Events: `50`
- Dialogue invented: `false`
- Latest event: `2026-06-07T11:45:21.014603+00:00`
- Visible rows include:
  - `brain_dialogue.system.off`
  - `brain_dialogue.mesh_coordinator.conflict`
  - `brain_dialogue.mesh_coordinator.decision`
  - `brain_dialogue.multi_brain.bundle`
  - `brain_dialogue.multi_brain.opinion`

Observed issue:

The cockpit dialogue panel is disconnected from available dialogue data. This is evidence-backed because the dedicated page shows 50 real dialogue events during the same audit run.

## 12. Visual Hierarchy Analysis

Scores, 1 to 10:

| Dimension | Score | Evidence |
| --- | ---: | --- |
| Visual hierarchy | 5 | Command Cockpit screenshot shows many equally weighted cards and sections. |
| Operator clarity | 5 | Main controls are visible, but status and source/debug text compete with actions. |
| Live feeling | 6 | Live events exist, but read like logs with generic summaries. |
| Action visibility | 8 | Main action buttons are visible on first screen and large. |
| Decision clarity | 6 | Decision Summary exists, but deeper decision pages contain dense technical graphs/cards. |
| Money clarity | 6 | Money Truth shows ledger-backed values, but `WITHHELD` and `PARTIAL` require operator interpretation. |
| Noise level | 4 | Many small cards, status tokens, source names, and endpoint strings are visible. |
| Technical clutter | 4 | Endpoints, source names, and raw table-like vocabulary are first-screen visible. |
| Cockpit feeling | 5 | It has cockpit ingredients but still feels dashboard/debug-heavy. |
| First-screen usefulness | 6 | Operator can see state and controls quickly, but not a clear “what should I do now?” lane. |

Mandatory questions:

1. Can the operator understand system status within 5 seconds? PARTIAL. `BACKEND REAL`, `DATABASE REAL`, `PARTIAL`, `UNKNOWN`, and `NO ACTIVE RUN` appear together.
2. Can the operator understand what to press within 5 seconds? PARTIAL. Buttons are visible, but disabled until actor/reason and no primary “recommended next action” exists.
3. Are main action buttons large and clear? YES.
4. Is there too much technical text? YES: endpoints, source names, status tokens, table names.
5. Are there too many small cards? YES on Command Cockpit and advanced detail pages.
6. Does the screen look like a control room or a debug report? BOTH; current evidence leans debug-heavy.
7. Is there a clear center of gravity? PARTIAL. `Command Cockpit` headline is clear; below it, many panels compete.
8. First thing the eye sees: `Command Cockpit` hero/status band.
9. Second thing the eye sees: `Operator Controls`.
10. What should not be on the first screen: raw endpoint paths, dense source coverage, low-level table counts.
11. What should be promoted to first screen: actionable run state, lock reason, current body heartbeat, real dialogue summary.
12. What should move to Advanced: source coverage table, endpoint strings, latest source rows.
13. Confusing for non-developer operator: `PARTIAL`, `WITHHELD`, `RISK_NOT_APPROVED`, table/source names, process-local run wording.
14. What prevents the system from feeling alive: dialogue mismatch, runtime event rows without readable summaries, no animated/temporal “body pulse” story.

## 13. UX Clutter Analysis

Observed clutter on the first screen:

- 13 headings on Command Cockpit.
- 24 visible buttons including navigation and actions.
- Multiple status tokens: `UNKNOWN`, `REAL`, `PARTIAL`, `NO ACTIVE RUN`, `WITHHELD`, `GATED`.
- Endpoint paths visible near the top.
- Source/table names visible: `runtime_state_service_health_event_log`, `risk_evidence_mesh_evaluations`, `paper_pnl_ledger`, `paper_positions`.
- Advanced source coverage appears on the same first-screen flow after core cockpit sections.

Effect:

The cockpit answers many engineering questions, but the operator’s next move is not visually prioritized.

## 14. Missing Product Elements

Evidence-backed missing or weak elements:

- No single operator command recommendation after `LOCKED`.
- No concise body pulse / heartbeat summary.
- No cockpit-level neural dialogue despite real dialogue rows on the Mesh Dialogues page.
- No friendly explanation of `PARTIAL`, `WITHHELD`, or `RISK_NOT_APPROVED`.
- No clear separation between operator cockpit and engineering diagnostics.
- No strong Full Monitor Run timeline/state machine on the first screen.
- No transformation of runtime events into readable “what POLYBOT just did” messages.

## 15. Safety Findings

Safety remained intact.

- No live trading enabled.
- No orders created.
- No fills created.
- No positions created.
- No migrations run.
- No destructive DB commands run.
- No secrets printed.
- KILL SWITCH not fully activated.
- No fake dialogue invented.
- No fake PnL invented.
- Forbidden controls not observed:
  - manual trade
  - approve trade
  - override blocker
  - disable risk
  - disable governance
  - engine budget

## 16. Top 10 Problems

1. Cockpit dialogue mismatch: Command Cockpit says no dialogue, while Mesh Dialogues shows 50 real events.
2. Full Monitor Run flow ends in `LOCKED` with no guided next step and no run panel transition.
3. First screen is dense with many similarly weighted cards and no single operator priority lane.
4. Live feed is real but reads like raw event logs, not system expression.
5. Technical endpoint/source/table text appears too early.
6. Status vocabulary is truthful but not operator-explained (`PARTIAL`, `WITHHELD`, `UNKNOWN`, `RISK_NOT_APPROVED`).
7. Source Coverage / Latest Source Rows belong in Advanced, not in the main cockpit.
8. Money Truth exposes values and withholding but does not explain the ledger state in plain terms.
9. Advanced pages are data-rich but visually repetitive, with long lists and small cards.
10. `Advanced` is only a label, not a page or mode; operators may not understand where diagnostics begin/end.

## 17. Top 10 Fixes Required

1. Target: Command Cockpit / Neural Dialogue  
   Change: wire cockpit dialogue panel to the same source used by Mesh Dialogues.  
   Why: cockpit currently says no dialogue while real dialogue exists.  
   Benefit: POLYBOT feels alive and truthful.  
   Risk: LOW frontend/data mapping.  
   Proof: cockpit shows real dialogue rows and `raw/neural-dialogue-analysis.json` no longer reports mismatch.

2. Target: Command Cockpit / Full Monitor Run  
   Change: show locked-state cause, required precondition, and next safe action.  
   Why: POST returns 200 but operator sees no run.  
   Benefit: operator understands why run did not start.  
   Risk: LOW frontend copy/state mapping.  
   Proof: after locked run attempt, screenshot contains guided next step.

3. Target: First screen hierarchy  
   Change: create a primary “Body Status + Next Action” lane above all diagnostics.  
   Why: current page has many equal cards.  
   Benefit: status within 5 seconds.  
   Risk: MEDIUM UX redesign.  
   Proof: screenshot first viewport has one dominant status/action area.

4. Target: Live System Feed  
   Change: convert event rows into readable summaries when payload allows it.  
   Why: current repeated text says source row returned without summary.  
   Benefit: system feels alive.  
   Risk: LOW/MEDIUM frontend formatter.  
   Proof: live feed rows include operator-readable cycle messages.

5. Target: Source Coverage  
   Change: move source table counts and endpoint paths into Advanced.  
   Why: too technical for first screen.  
   Benefit: less clutter.  
   Risk: LOW.  
   Proof: Command Cockpit screenshot no longer shows endpoint paths/source table grid.

6. Target: Status vocabulary  
   Change: add operator tooltips or concise plain-language labels for `PARTIAL`, `WITHHELD`, `UNKNOWN`.  
   Why: truthful but cryptic.  
   Benefit: fewer misreads.  
   Risk: LOW.  
   Proof: accessibility/visible text includes plain explanations.

7. Target: Controls  
   Change: separate low-risk refresh/export from actor/reason-gated runtime actions.  
   Why: matrix currently sees actor/reason context near refresh/export, creating ambiguity.  
   Benefit: clearer safety model.  
   Risk: LOW.  
   Proof: control matrix marks refresh/export as no actor/reason required.

8. Target: Mesh Dialogues page  
   Change: show brain roles and actual message fields more prominently.  
   Why: rows currently contain many `UNKNOWN` fields.  
   Benefit: dialogue feels like conversation.  
   Risk: MEDIUM, depends on data shape.  
   Proof: screenshot shows roles/messages without repeated `UNKNOWN`.

9. Target: Navigation IA  
   Change: turn Advanced into a collapsible diagnostic mode or explicit page group.  
   Why: it is currently a label with many entries.  
   Benefit: cleaner cockpit.  
   Risk: LOW/MEDIUM UI shell.  
   Proof: screenshot shows primary nav separated from diagnostics.

10. Target: Money Truth  
    Change: add a single ledger verdict before detailed metrics.  
    Why: values exist but operator must infer meaning.  
    Benefit: faster financial truth read.  
    Risk: LOW frontend mapping.  
    Proof: Money panel begins with plain ledger state.

## 18. Recommended Stage 23 Plan

Do not implement in Stage 22.

Recommended Stage 23: Visual Cockpit Redesign v2 + Action Flow Fix.

Suggested scope:

1. Cockpit IA rewrite: one first-screen body status lane, one next-action lane, one live expression lane.
2. Full Monitor Run UX: locked/running/completed/stopped/failed state machine.
3. Cockpit dialogue fix: reuse Mesh Dialogues source in cockpit.
4. Live feed formatter: turn runtime events into readable operator messages.
5. Advanced mode cleanup: move raw endpoints/source tables/detail graphs out of primary cockpit.
6. Controls clarity: split low-risk refresh/export from audited runtime action controls.

## 19. Evidence Links

Audit folder:

- `run_reports/control_center_ui_audit/`

Raw evidence:

- `run_reports/control_center_ui_audit/raw/console.json`
- `run_reports/control_center_ui_audit/raw/network.json`
- `run_reports/control_center_ui_audit/raw/visible-elements.json`
- `run_reports/control_center_ui_audit/raw/accessibility-snapshots.json`
- `run_reports/control_center_ui_audit/raw/control-buttons-matrix.json`
- `run_reports/control_center_ui_audit/raw/full-monitor-run-flow.json`
- `run_reports/control_center_ui_audit/raw/live-feed-analysis.json`
- `run_reports/control_center_ui_audit/raw/neural-dialogue-analysis.json`
- `run_reports/control_center_ui_audit/raw/audit-summary.json`

Screenshots:

- `run_reports/control_center_ui_audit/screenshots/01-command-cockpit.png`
- `run_reports/control_center_ui_audit/screenshots/04-live.png`
- `run_reports/control_center_ui_audit/screenshots/11-mesh-dialogues.png`
- `run_reports/control_center_ui_audit/screenshots/full-monitor-run-after.png`

Trace:

- `run_reports/control_center_ui_audit/traces/control-center-ui-audit.zip`

## 20. Final Status

GREEN for Stage 22 audit completion.

YELLOW for operator UX readiness.

## 21. Can Continue

YES, to Stage 23 planning/review only.

Do not implement Stage 23 until ChatGPT/operator review accepts this audit.
