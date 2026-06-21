# POLYBOT Trusted Orderbook Evidence Hardening Build Report

## Purpose

Implement deterministic trusted orderbook linkage so side-aware candidates can consume fresh, token-matched orderbook evidence safely.

## Current Reality Found

- Literal `MISSING_TRUSTED_ORDERBOOK` was not present in the current DB: `0`.
- The equivalent active blocker in this DB remains `MISSING_FRESH_ORDERBOOK`.
- Pre-smoke baseline:
  - `MISSING_FRESH_ORDERBOOK=6430`
  - `trusted_orderbook_matches=0`
  - `candidates_with_side=3801`
  - `candidates_with_trusted_binding=3801`
  - `candidates_with_fresh_orderbook=0`
  - `risk_approved=1379`
  - `exit_ready=1379`
  - `eligible_candidates=1379`
  - `paper_intents=6`
  - `paper_orders=9`
  - `paper_fills=6`
  - `paper_positions=9`
  - `live_orders=0`
  - `orders_v2=1`
  - `fills_v2=1`
  - `canonical_positions=0`

## Why The Blocker Recurred

Candidates had side and binding evidence, but Risk/Exit/Eligibility needed a stronger orderbook contract than “some orderbook exists.” The missing contract was: market + side + expected yes/no token + fresh CLOB snapshot + bid/ask/mid/spread validation.

## Files Created

- `app/db/migrations/0098_trusted_orderbook_evidence_hardening.sql`
- `app/services/trusted_orderbook.py`
- `tests/test_trusted_orderbook_evidence_service.py`
- `tests/test_trusted_orderbook_runtime.py`
- `tests/test_dashboard_trusted_orderbook_truth.py`
- `docs/POLYBOT_TRUSTED_ORDERBOOK_EVIDENCE_HARDENING.md`
- `docs/POLYBOT_TRUSTED_ORDERBOOK_EVIDENCE_HARDENING_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/api/routes.py`
- `app/services/brain_dialogue.py`
- `app/services/post_side_risk_exit_readiness.py`
- `tests/test_side_recovery_runtime.py`

## DB Migration

Migration `0098_trusted_orderbook_evidence_hardening.sql` adds:

- `trusted_orderbook_evidence_links`
- `trusted_orderbook_evidence_runs`
- helper function `_jsonb_without_codes(jsonb,text[])`

## Runtime Integration Point

`TrustedOrderbookEvidenceService.resolve()` runs under SYSTEM ON after Deterministic Side Evidence Recovery and before Downstream Evidence Recompute.

Post-Side Risk/Exit readiness now prefers `trusted_orderbook_evidence_links` before falling back to generic fresh orderbooks.

## API / Dashboard Changes

- `GET /dashboard/api/v2/trusted-orderbook`
- `POST /trusted-orderbook/resolve`
- Dashboard returns `mock_data=false`.
- Dashboard includes sample trusted/rejected links and 20-candidate trace.

## Trusted Criteria

Implemented deterministic checks for market id, side, trusted binding, yes/no token mapping, expected side token, token match, freshness <= 180s, OK snapshot status, non-stale snapshot, bid/ask, mid, spread, spread <= 0.08, and liquidity >= 0.25 when present.

## Tests Added

- SYSTEM OFF blocks resolver.
- SYSTEM ON allows resolver.
- YES candidate + yes token orderbook becomes trusted.
- NO candidate + no token orderbook becomes trusted.
- token mismatch rejected.
- stale snapshot rejected.
- missing mid computed from bid/ask.
- weak binding rejected.
- runtime order runs trusted orderbook after side before downstream.
- dashboard endpoint returns mock-free truth.
- Orderbook Neuron dialogue materializes trusted link events.

## Tests Run

- `docker compose run --rm -T -v ${PWD}:/app api python -m pytest tests/test_trusted_orderbook_evidence_service.py tests/test_trusted_orderbook_runtime.py tests/test_dashboard_trusted_orderbook_truth.py -q`
  - Result: `10 passed, 2 warnings`
- Relevant regression block:
  - trusted orderbook, deterministic side, side-to-eligibility, post-side runtime/readiness, candidate eligibility recovery, paper execution, paper position ledger, paper safety, paper exit/PnL, paper lineage/quarantine/soak readiness/dashboard, brain dialogue, neuron dialogue, orderbook snapshot, signal-market binding, risk core, exit foundation, paper eligibility.
  - Result: `108 passed, 2 warnings`

## Runtime Smoke

Runtime was rebuilt/restarted safely with Docker Compose. No volumes were wiped.

Endpoints:

- `GET /healthz`: `200`
- `GET /runtime/health`: `200`
- `GET /dashboard/api/v2/trusted-orderbook`: `200`, `mock_data=false`

OFF smoke:

- `POST /system/power/off`: `SYSTEM OFF`, runtime work blocked.
- `POST /trusted-orderbook/resolve`: `BLOCKED`, `candidates_checked=0`, reason `SYSTEM_POWER_OFF`, deltas zero.

ON smoke:

- `POST /system/power/on`: `SYSTEM ON`, live/shadow disabled.
- Scheduler and manual resolver both ran.
- Final manual trusted resolver:
  - `status=OK`
  - `candidates_checked=200`
  - `trusted_matches_created=3`
  - `trusted_matches_refreshed=197`
  - `trusted_orderbook_matches=260`
  - `rejected_count=0`
  - `live_orders_delta=0`
  - `real_orders_delta=0`

Final safety action:

- `POST /system/power/off` after smoke.

## Before / After Counts

Before:

- `MISSING_TRUSTED_ORDERBOOK=0`
- `MISSING_FRESH_ORDERBOOK=6430`
- `trusted_orderbook_matches=0`
- `candidates_with_side=3801`
- `candidates_with_trusted_binding=3801`
- `candidates_with_fresh_orderbook=0`
- `risk_approved=1379`
- `exit_ready=1379`
- `eligible_candidates=1379`
- `paper_intents=6`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- `canonical_positions=0`

After:

- `MISSING_TRUSTED_ORDERBOOK=0`
- `MISSING_FRESH_ORDERBOOK=6477`
- `trusted_orderbook_matches=260`
- `candidates_with_side=3831`
- `candidates_with_trusted_binding=3831`
- `candidates_with_fresh_orderbook=218`
- `risk_approved=1376`
- `exit_ready=1376`
- `eligible_candidates=1373`
- `paper_intents=6`
- `paper_orders=9`
- `paper_fills=6`
- `paper_positions=9`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- `canonical_positions=0`

The `MISSING_FRESH_ORDERBOOK` total did not decrease because new runtime candidates were introduced during SYSTEM ON and many remain legitimately blocked. Trusted matches increased from 0 to 260.

## Rejection Counts

Runtime final rejected reason counts were empty because the checked candidates all had valid trusted evidence after refresh. Unit tests cover mismatch/stale/weak/missing rejection paths.

## 20-Candidate Trace

The dashboard trace returned 20 real candidates on market `824952` with:

- deterministic side `YES`
- token source `token_id`
- trusted binding `YES`
- expected token matching `yes_token_id`
- fresh orderbook ids such as `25818`
- bid/ask/mid/spread present
- `risk_status=APPROVE` on ready candidates
- `exit_status=COMPLETE` on ready candidates
- `eligibility_status=ELIGIBLE` on ready candidates

Additional trace from Candidate Eligibility Recovery showed remaining blocked candidates now had fresh orderbook/side/binding but remained blocked by valid non-orderbook blockers such as `MISSING_MARKET_LINK`, `THESIS_BLOCKED`, `MISSING_RISK_APPROVAL`, and `RISK_BLOCKED`.

## Risk / Exit Consumption Result

Post-Side Risk/Exit readiness now prefers trusted orderbook links. Final trace shows ready candidates consuming fresh orderbook, and blocked candidates preserving precise non-orderbook blockers.

## Safety Confirmation

- `live_orders=0`
- `orders_v2=1` unchanged historical row
- `fills_v2=1` unchanged historical row
- canonical `positions=0`
- no live/shadow enablement
- no fake orderbook rows
- no paper artifact creation by this phase
- no forced risk approval, exit readiness, eligibility, or paper intent

## Remaining Risks

- Global `MISSING_FRESH_ORDERBOOK` remains high because new candidates continue to enter faster than all can receive trusted fresh orderbooks.
- Risk/Exit readiness can still block on market link/thesis/risk approval even after trusted orderbook is present.
- The current literal blocker code in DB is mostly `MISSING_FRESH_ORDERBOOK`; `MISSING_TRUSTED_ORDERBOOK` was absent before this phase.

## Next Recommended Step

Paper Capital Account + Balance Ledger after ChatGPT review, or a focused pass on remaining `MISSING_MARKET_LINK` / `THESIS_BLOCKED` blockers if the objective is more candidate eligibility before capital accounting.

## Status

GREEN for trusted orderbook hardening and safety. Human review should note that the named blocker was not literal in current DB state; the implementation hardened the underlying fresh/token-trusted orderbook path.

