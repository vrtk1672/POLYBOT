# Decision / Trade / Blocker Autopsy Report

## Purpose

Build a read-only forensic layer for POLYBOT PAPER runtime decisions, trades, blockers, no-trade outcomes, supervisor degradation, and paper activity deltas.

The goal is not to make more trades. The goal is to show which Full Mesh organ or gate stopped each candidate, why it stopped there, whether that stop is expected or suspicious, and what must change before the candidate can become actionable.

## Current Problem

PAPER runtime can create normal paper intents, orders, fills, positions, closes, and PnL while Live and Shadow stay blocked. Most candidates still stop at WATCH or BLOCK, and normal paper activity deltas were sometimes surfaced as latest errors. Operators needed a single truth view for:

- who blocked each candidate
- where the lifecycle stopped
- why no paper intent was created
- whether ENTER decisions completed the paper ledger lifecycle
- whether supervisor DEGRADED has a real cause
- whether paper row deltas are expected PAPER activity or suspicious behavior

## Tables Audited

- Paper runtime decisions: `paper_runtime_decisions`
- Policy reviews: `paper_observation_policy_reviews`
- No-trade reasons: `no_trade_log`
- Paper sessions: `paper_sessions`
- Paper intents: `paper_intents`
- Paper orders: `paper_orders`
- Paper fills: `paper_fills`
- Paper positions: `paper_positions`
- Paper position closes: `paper_position_closes`
- Supervisor/service health: `service_health`
- Runtime cycles: `runtime_cycles_v2`
- Delta/run ledgers: `candidate_eligibility_recovery_runs`, `fresh_seed_paper_path_runs`, `side_evidence_recovery_runs`, `post_side_risk_exit_recovery_runs`, `paper_execution_runs`, `paper_exit_loop_runs`
- Runtime mode: `system_state`

## Services Audited

- `PaperRuntimeDecisionService`: policy-to-runtime decision surface and ENTER/WATCH/BLOCK decision rows.
- `PaperIntentGateService`: paper intent gate and rejection reasons.
- Paper execution adapter/services: paper order, fill, position, and close lifecycle.
- Paper session reset/status services: active paper session and session-scoped counts.
- System overview/report surfaces: runtime, execution, paper session, and latest error visibility.

## Blocker Source Map

| Blocker | Owner / Gate | Meaning |
| --- | --- | --- |
| `EXISTING_HARD_BLOCKERS_PRESENT` | Observation Policy / Paper Runtime Decision | Upstream hard blockers remain present. |
| `OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD` | Paper Runtime Decision | Observed opportunity score is below the configured paper threshold. |
| `DECISION_BAND_NOT_PAPER_OBSERVATION` | Opportunity Score / Observation Policy | Candidate did not reach the paper observation decision band. |
| `EDGE_NOT_SUPPORTED` | Source-Backed Edge Mesh | Edge evidence is missing or unsupported. |
| `THESIS_NOT_SUPPORTED` | Trade Thesis Mesh | Thesis is missing, watch-only, or unsupported. |
| `EXIT_NOT_READY` | Exit Mesh | Exit plan, time stop, or invalidation is not ready. |
| `OBSERVATION_POLICY_NOT_ALLOWED` | Paper Observation Policy | Policy did not allow observation entry. |
| `DUPLICATE_OPEN_PAPER_EXPOSURE` | Paper Runtime Decision / Same Market-Side Guard | Same market/side exposure already exists. |
| `SAME_MARKET_DUPLICATE_DECISION` | Paper Runtime Decision Selector | Duplicate market/side decision was suppressed or blocked. |
| `DUPLICATE_ACTIVE_PAPER_INTENT` | Paper Intent Gate | Active intent already exists for the same exposure. |
| `ORDERBOOK_NOT_FRESH` | Orderbook / Last-Mile Refresh | Fresh matching orderbook is required. |

## Decision Lifecycle Map

The autopsy service reconstructs lifecycle from existing DB truth:

1. Policy review / opportunity evidence.
2. `paper_runtime_decisions` ENTER/WATCH/BLOCK row.
3. `paper_intents` row by `evidence.paper_runtime_decision_id`.
4. `paper_orders` row by `payload_json.source_intent_id`.
5. `paper_fills` row by `source_intent_id`.
6. `paper_positions` row by `payload_json.source_intent_id`.
7. `paper_position_closes` row by position id.

ENTER decisions that do not produce paper intents are flagged as `ENTER_WITHOUT_INTENT` unless an expected lifecycle reason exists, such as duplicate exposure, duplicate active intent, or already processed state.

## Supervisor Degraded Explanation

`/dashboard/api/v2/control/supervisor-autopsy` now reads `service_health`, `runtime_cycles_v2`, and latest failed run ledgers. It reports:

- current supervisor status
- degraded reasons from service health details
- latest runtime cycles
- latest failed or degraded run records
- whether paper entries are blocked by the current supervisor state

This makes DEGRADED visible as a reasoned condition instead of a bare status label.

## Paper Delta Classification

`/dashboard/api/v2/control/paper-delta-autopsy` classifies paper row deltas:

- `EXPECTED_ACTIVITY`: paper deltas occurred while runtime mode is PAPER.
- `SUSPICIOUS_ACTIVITY`: paper deltas occurred outside PAPER-compatible modes.
- `ERROR`: paper deltas occurred in OFF, DATA_ONLY, KILL, COOLDOWN, or another unsafe mode.
- `NO_CHANGE`: no paper deltas detected.

Normal current-session paper activity in PAPER mode is no longer treated as a latest error by the autopsy surface.

During runtime verification, the first 10-minute PAPER run exposed a stale contract in `PaperIntentRun`: simulated `paper_orders` rows were still treated as forbidden executable artifacts. That was corrected narrowly so `paper_orders` activity is allowed as PAPER adapter ledger activity, while `order_intents`, real fills/positions, and live actions remain forbidden.

## APIs Added

- `GET /dashboard/api/v2/control/decision-autopsy`
- `GET /dashboard/api/v2/control/decision-autopsy/top-blockers`
- `GET /dashboard/api/v2/control/decision-autopsy/enter`
- `GET /dashboard/api/v2/control/decision-autopsy/closest-actionable`
- `GET /dashboard/api/v2/control/supervisor-autopsy`
- `GET /dashboard/api/v2/control/paper-delta-autopsy`

All endpoints are read-only.

## CLI Commands Added

- `.\tools\polybot.ps1 autopsy`
- `.\tools\polybot.ps1 blockers`
- `.\tools\polybot.ps1 enter-autopsy`
- `.\tools\polybot.ps1 closest-actionable`
- `.\tools\polybot.ps1 supervisor-autopsy`
- `.\tools\polybot.ps1 paper-delta-autopsy`

## Report Output Changes

`.\tools\polybot.ps1 report` now includes:

- paper delta classification
- ENTER lifecycle summary
- expected paper activity classification separate from latest errors
- current session and historical totals remain separated by the existing paper session status section

## Tests Run

Focused:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_decision_autopsy.py tests/test_blocker_autopsy.py tests/test_enter_lifecycle_autopsy.py tests/test_supervisor_autopsy.py tests/test_paper_delta_autopsy.py tests/test_report_autopsy_output.py -q
```

Result: `8 passed in 128.13s`.

Focused after PaperIntentRun delta classification correction:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_v2_paper_intent_contract.py tests/test_decision_autopsy.py tests/test_blocker_autopsy.py tests/test_enter_lifecycle_autopsy.py tests/test_supervisor_autopsy.py tests/test_paper_delta_autopsy.py tests/test_report_autopsy_output.py -q
```

Result: `12 passed in 94.66s`.

Related:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_session_reset.py tests/test_paper_session_status_report.py tests/test_paper_execution_adapter_runtime.py tests/test_system_overview_paper_chain.py -q
```

Result: `8 passed in 95.11s`.

Related after PaperIntentRun delta classification correction:

```powershell
$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot_local_password@localhost:55433/polybot_test'
.venv\Scripts\python.exe -m pytest tests/test_paper_session_reset.py tests/test_paper_session_status_report.py tests/test_paper_execution_adapter_runtime.py tests/test_system_overview_paper_chain.py -q
```

Result: `8 passed in 181.08s`.

Compile:

```powershell
.venv\Scripts\python.exe -m compileall app tests
```

Result: passed.

## Runtime Verification

Deployment commands run:

```powershell
docker compose build api
docker compose build migrate
docker compose run --rm migrate
docker compose up -d --no-deps api
.\tools\polybot.ps1 restart-paper-session -balance 1000
Start-Sleep -Seconds 600
.\tools\polybot.ps1 report
.\tools\polybot.ps1 autopsy
.\tools\polybot.ps1 blockers
.\tools\polybot.ps1 enter-autopsy
.\tools\polybot.ps1 supervisor-autopsy
.\tools\polybot.ps1 paper-delta-autopsy
```

Verification result:

- API health: OK.
- Runtime health: RUNNING.
- Runtime state: PAPER.
- Paper adapter: ENABLED.
- Live adapter: BLOCKED.
- Active paper session: `paper_session_20260619T170716Z_72bec045`.
- Current-session paper ledger after verification: intents `0`, orders `0`, fills `0`, positions `0`, open positions `0`.
- Historical paper ledger remained visible separately.
- Live orders: `0`.
- Shadow orders: `0`.
- Real orders: `0`.
- Latest errors: none reported.
- Paper delta classification after correction: `NO_CHANGE` for latest run rows, no expected paper activity surfaced as latest error.
- Supervisor autopsy after correction: `RUNNING_OR_IDLE`, no degraded reasons, does not block paper entries.
- Top blockers: `EXISTING_HARD_BLOCKERS_PRESENT`, `OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD`.
- ENTER lifecycle autopsy: ENTER decisions exist for market `691547`, but current-session intent/order/fill/position links are missing, so autopsy flags `ENTER_WITHOUT_INTENT` as bug-suspect.

## Remaining Risks

- Some blockers remain intentionally strict. This work exposes them; it does not loosen them.
- The autopsy service reconstructs lifecycle from existing rows. If a future ledger path uses a new linkage key, that source must be added to the autopsy mapper.
- Supervisor degradation can be real. The autopsy endpoint reports reasons but does not suppress genuine failures.

## Status

YELLOW.

The autopsy system, API, CLI, paper delta classification, tests, and deployment are working. Status is YELLOW because the new forensics exposed a real remaining lifecycle issue: ENTER decisions are present but current-session paper intents are not being created for those decisions. That is now visible and should be the next focused repair.
