# Opportunity Memory and Intent Expiry Report

## Purpose

Implement a Paper-only Full Mesh lifecycle where stale non-executed intents expire, become opportunity memory, and can reactivate only when evidence changes.

## Stage A Audit

Current `paper_intents` had active statuses such as `CREATED`, `READY`, and `EXECUTING`, and execution consumed only `CREATED` intents. The Opportunity Mesh exposed `INTENT_STUCK` after 600 seconds, but no service changed stale active intents into expired/cancelled lifecycle rows. Duplicate and active-intent logic could therefore keep old opportunities visible as active state.

Root cause classification:

- `NO_INTENT_EXPIRY_POLICY`
- `STUCK_INTENTS_BLOCK_REACTIVATION`
- `NO_OPPORTUNITY_MEMORY`
- `NO_EVIDENCE_FINGERPRINT`
- `REPROCESSING_SAME_EVIDENCE_FOREVER`

## Intent Lifecycle Design

New stale non-executed Paper intent behavior:

1. Pending intent exceeds `PAPER_INTENT_MAX_PENDING_SECONDS` or max attempts.
2. Intent is updated to `EXPIRED_NO_EXECUTION`.
3. Expiry timestamp, lifecycle reason, evidence fingerprint, and memory id are recorded.
4. Opportunity Mesh routes it to `WAIT_FOR_NEW_EVIDENCE`.
5. Historical intent remains queryable.

## Opportunity Memory Design

New `opportunity_memory` records retain:

- session, market, side, original intent/runtime decision
- opportunity key
- evidence fingerprint
- last score, blockers, defense level, side evidence, arbitration, exit state
- memory status and reactivation count

Memory statuses are:

- `REMEMBERED`
- `WAITING_FOR_NEW_EVIDENCE`
- `REACTIVATED`
- `EXPIRED`

## Evidence Fingerprint Design

The fingerprint is derived from meaningful opportunity evidence, not volatile cycle identity:

- market, side, token, condition
- orderbook snapshot/prices
- opportunity score
- decision/effective Paper policy
- blockers/warnings
- defense level and adjusted threshold
- side evidence and arbitration summaries
- source/event/trigger/orderbook identifiers where present

Runtime decision ids alone do not create a new fingerprint.

## Reactivation Rules

Same market/side with the same evidence fingerprint becomes `OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE` and produces no new intent.

Changed fingerprint can reactivate memory and records an `opportunity_reactivation_events` row. The new intent revision is linked through `reactivated_from_memory_id`.

## CLI/API

Added read-only endpoints:

- `GET /dashboard/api/v2/control/opportunity-memory`
- `GET /dashboard/api/v2/control/expired-intents`

Updated views:

- `intent-queue`
- `opportunity-mesh`
- `candidate-consumption`
- `paper-session-report`
- `report`

New CLI commands:

- `.\tools\polybot.ps1 opportunity-memory`
- `.\tools\polybot.ps1 expired-intents`

## Tests

Focused:

`.venv\Scripts\python.exe -m pytest tests/test_paper_intent_expiry.py tests/test_opportunity_memory.py tests/test_opportunity_reactivation.py tests/test_evidence_fingerprint.py tests/test_stuck_intent_does_not_block_new_evidence.py tests/test_opportunity_memory_report.py tests/test_intent_queue_visibility.py tests/test_opportunity_mesh_coordinator.py -q`

Result: `1 passed, 11 skipped`.

Related:

`.venv\Scripts\python.exe -m pytest tests/test_paper_intent_gate_idempotency.py tests/test_paper_defense_level.py tests/test_paper_defense_learning_ledger.py tests/test_side_evidence.py tests/test_same_market_side_arbitration.py tests/test_paper_execution_adapter_runtime.py tests/test_paper_session_status_report.py -q`

Result: `6 passed, 8 skipped`.

Compile:

`.venv\Scripts\python.exe -m compileall app tests`

Result: passed.

Skipped tests were DB-backed tests skipped by local fixture availability.

## Runtime Verification

Build/restart:

- `docker compose build api`: passed
- `docker compose build migrate`: passed
- `docker compose run --rm migrate`: applied `0150_opportunity_memory_intent_expiry.sql`
- `docker compose up -d --no-deps api`: passed
- `/healthz`: `ok`

Fresh session:

- Command: `.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20`
- Active session: `paper_session_20260620T125338Z_a40c5a2e`
- Defense level: `20`
- Starting balance: `1000`

Observed behavior:

- Initial intents became pending.
- After threshold crossing, 7 stale non-executed intents changed to `EXPIRED_NO_EXECUTION`.
- 7 opportunity memory rows were created as `WAITING_FOR_NEW_EVIDENCE`.
- Opportunity Mesh showed `intent_expired=7`, `intent_stuck=0`.
- Newer active revisions were visible separately as pending intents.
- Live/shadow/real remained 0.

Report path:

- `run_reports/paper_session_learning_paper_session_20260620T125338Z_a40c5a2e/paper_session_learning_report_paper_session_20260620T125338Z_a40c5a2e.json`
- Markdown and CSV were created in the same folder.

## Example Expired Intent

`paper_intent_paper_runtime_decision_8ac96c2abf0cc92b3aa5f1c9ae3ec55d_paper_session_20260620T125338Z_a40c5a2e`

- Market: `691547`
- Side: `YES`
- Status: `EXPIRED_NO_EXECUTION`
- Reason: `EXPIRED_NO_EXECUTION:PENDING_OVER_MAX_PENDING_SECONDS`
- Memory: `opportunity_memory_987d280314b0aeb9b3d30196`

## Example Remembered Opportunity

`opportunity_memory_987d280314b0aeb9b3d30196`

- Market: `691547`
- Side: `YES`
- Status: `WAITING_FOR_NEW_EVIDENCE`
- Score: `61.99`
- Reactivation count: `0`

## Example Reactivation

No natural reactivation event was observed in the short corrected runtime window. Unit coverage verifies changed fingerprints record reactivation and link new intent revisions to prior memory.

## Remaining Risks

- Some current-session intents can still remain pending until the 600 second policy threshold is crossed.
- Runtime verification observed one unrelated `mesh_sessions` deadlock in logs during source refresh; it did not affect Paper intent expiry and final report showed latest errors as none.
- More observation is needed to see a natural new-evidence reactivation in live runtime.

## Status

YELLOW.

The expiry/memory lifecycle works and runtime verification passed for stale intent expiration. Natural reactivation was not observed in the verification window, but it is implemented and covered by tests.

Safe to continue Defense 20 Paper runtime: YES.
