# POLYBOT Phase 7B - Candidate-Targeted Refresh Before Execution

## 1. Purpose

Phase 7B closes the remaining trusted-price risk after Phase 7: a globally fresh orderbook must not imply that a specific candidate has fresh executable price evidence.

The required truth is candidate-specific:

candidate_id -> market_id -> side -> token_id -> trusted orderbook -> execution TTL -> entry price source -> exit liquidity source -> price readiness.

No Paper Simulation, Shadow, Live, Full Monitor Run, or execution artifacts were activated.

## 2. Current Reality Found

Phase 7 proved that SYSTEM ON can refresh orderbooks through Runtime Supervisor and LiveOrderbookWatcherService. The remaining risk was that default eligible candidates could still point to stale trusted evidence while unrelated or watchlist orderbooks were fresh.

Pre-smoke active server state showed:

- `candidate-price-path`: `freshness_state=STALE`, `readiness_state=PARTIAL`, `truth_state=REFRESH_REQUIRED`
- `candidate_price_ready=0`
- `waiting_for_refresh=50`
- `refresh_available=50`
- `stale_orderbook=50`
- `trusted_fresh_for_candidate=0`
- `trusted_stale_for_candidate=50`
- sample state: `CANDIDATE_STALE_ORDERBOOK`, `TRUSTED_STALE_FOR_CANDIDATE`, refresh `REQUIRED`

## 3. Why Default Eligible Candidates Pointed To Stale Trusted Evidence

Candidate rows carried historical `orderbook_snapshot_id` and trusted evidence links, but Phase 7 refreshes were not guaranteed to refresh the exact candidate market/side/token path. A stale candidate-linked snapshot could remain stale even if other orderbooks were fresh.

The fix resolves candidate token and side first, then checks the latest exact `market_id + token_id` orderbook and verifies that trusted evidence belongs to that candidate path. A wrong-token fresh orderbook cannot satisfy candidate readiness.

## 4. Candidate Token / Side Mapping

Candidate mapping is resolved in this order:

- `paper_eligibility_candidates.market_id`
- `paper_eligibility_candidates.side`
- `paper_eligibility_candidates.expected_token_id`
- fallback to `markets_v2.yes_token_id` or `markets_v2.no_token_id` by side
- evidence JSON only where existing data already carries token evidence

Missing market, side, or token is exposed as candidate-specific blocker state.

## 5. Existing Sources Reused

- `paper_eligibility_candidates`
- `markets_v2`
- `orderbook_snapshots`
- `trusted_orderbook_evidence_links`
- `trusted_orderbook_evidence_runs`
- `paper_intents`
- `runtime_supervisor`
- `StateGovernor`
- `LiveOrderbookWatcherService`
- `TrustedOrderbookEvidenceService`
- existing paper readiness, candidate explanation, and eligible-to-intent bridge services

## 6. Files Inspected

- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/candidate_producer_freshness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/runtime_supervisor.py`
- `app/services/orderbook_snapshots.py`
- `app/services/trusted_orderbook.py`
- `app/services/live_orderbook_watcher.py`
- `app/services/paper_eligibility.py`
- `app/services/paper_intents.py`
- `app/services/paper_execution.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_orderbook_price_readiness.py`
- `tests/test_candidate_producer_freshness.py`
- `tests/test_paper_readiness.py`
- `tests/test_candidate_explanations.py`
- `tests/test_eligible_intent_bridge.py`
- `docs/FRESH_ORDERBOOK_PRICE_PATH_REPORT.md`

## 7. Files Changed

- `app/control_center/orderbook_price_readiness.py`
- `app/control_center/runtime_supervisor.py`
- `app/services/trusted_orderbook.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/candidate_explanations.py`
- `app/control_center/eligible_intent_bridge.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_candidate_price_path.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/CANDIDATE_TARGETED_REFRESH_BEFORE_EXECUTION_REPORT.md`

## 8. APIs Added / Changed

Added:

- `GET /dashboard/api/v2/control/candidate-price-path`
- `GET /dashboard/api/v2/control/candidate-price-path/{candidate_id}`

Extended:

- `GET /dashboard/api/v2/control/paper-readiness`
- `GET /dashboard/api/v2/control/candidate-explanations`
- `GET /dashboard/api/v2/control/eligible-intent-bridge`

## 9. Frontend Changes

The Control Center client now knows and refreshes `candidatePricePath`. The Command Center orderbook panel now includes candidate-specific price truth:

- candidate price-ready count
- candidate refresh state
- candidate trusted orderbook state
- sample candidate token
- sample candidate state
- refresh plan

No mock data was added.

## 10. Candidate Price Path States Added

- `CANDIDATE_PRICE_READY`
- `CANDIDATE_WAITING_FOR_REFRESH`
- `CANDIDATE_REFRESH_AVAILABLE`
- `CANDIDATE_REFRESH_BLOCKED`
- `CANDIDATE_MISSING_MARKET`
- `CANDIDATE_MISSING_SIDE`
- `CANDIDATE_MISSING_TOKEN`
- `CANDIDATE_MISSING_ORDERBOOK`
- `CANDIDATE_STALE_ORDERBOOK`
- `CANDIDATE_UNTRUSTED_ORDERBOOK`
- `CANDIDATE_EXIT_LIQUIDITY_MISSING`
- `UNKNOWN`

Candidate trusted orderbook states:

- `TRUSTED_FRESH_FOR_CANDIDATE`
- `TRUSTED_STALE_FOR_CANDIDATE`
- `TRUSTED_MISSING_FOR_CANDIDATE`
- `UNTRUSTED_FOR_CANDIDATE`
- `TOKEN_MISMATCH`
- `SIDE_MISMATCH`

## 11. Tests Added

Added `tests/test_candidate_price_path.py` covering:

- matching token/side fresh orderbook becomes `CANDIDATE_PRICE_READY`
- wrong-token global orderbook cannot make candidate price-ready
- missing token and missing side
- stale candidate-specific orderbook
- read-only endpoint creates no paper artifacts
- paper readiness includes candidate price-ready counts
- supervisor candidate-targeted module is bounded and safe

## 12. Tests Run And Exact Results

- `.venv\Scripts\python.exe -m pytest tests/test_candidate_price_path.py -q`
  - Result: `1 passed, 6 skipped in 2.48s`
- `.venv\Scripts\python.exe -m pytest tests/test_orderbook_price_readiness.py tests/test_candidate_producer_freshness.py tests/test_paper_readiness.py tests/test_candidate_explanations.py tests/test_eligible_intent_bridge.py tests/test_control_center_read_only_apis.py -q`
  - Result: `5 passed, 59 skipped in 7.12s`
- `.venv\Scripts\python.exe -m pytest tests -q -k "candidate_price or orderbook or price or freshness"`
  - Result: `28 passed, 91 skipped, 1807 deselected in 6.72s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed
- `npm run typecheck`
  - Result: passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed`, `18 passed`
- `npm run build`
  - Result: passed with existing Vite chunk-size warning

## 13. Deployment / Restart Results

Port 8000 is served by Docker container `polybot_api`.

Deployment action:

- `docker compose build api`
- `docker compose up -d --no-deps api`

The container rebuilt and restarted successfully. Active server served the new endpoint.

## 14. Controlled SYSTEM ON Smoke Procedure

Allowed POST actions used:

- `POST /dashboard/api/v2/control/actions/system-on`
- `POST /dashboard/api/v2/control/actions/system-off`

Forbidden actions were not called:

- Paper Simulation ON
- Full Monitor Run
- Shadow
- Live
- manual trade or execution actions

SYSTEM ON ran in DATA_ONLY. Paper Simulation stayed OFF.

## 15. Before / After Candidate-Specific Orderbook Evidence

Before SYSTEM ON:

- sample candidate: `eligibility_exit_risk_thesis_coord_5def7b952cf540d483b471cd79572e12`
- market: `691547`
- side: `YES`
- token: `34626184950254225208692030156208941308358060420950772251072421141618169142241`
- state: `CANDIDATE_STALE_ORDERBOOK`
- trusted state: `TRUSTED_STALE_FOR_CANDIDATE`
- entry source: `BEST_ASK`
- exit source: `BEST_BID`
- refresh: `REQUIRED`
- refresh plan: available

During SYSTEM ON:

- sample candidate: `eligibility_exit_risk_thesis_coord_6f8ee8250cf84d1abbba6aef86c62104`
- market: `691547`
- side: `YES`
- same token path
- state: `CANDIDATE_PRICE_READY`
- trusted state: `TRUSTED_FRESH_FOR_CANDIDATE`
- exact token match: true
- exact side match: true
- entry source: `BEST_ASK`, price `0.32`
- exit source: `BEST_BID`
- exit liquidity: `EXIT_LIQUIDITY_READY`
- best bid: `0.30`
- best ask: `0.32`
- spread: `0.02`
- latest orderbook: `2026-06-14T18:14:17.814817+00:00`
- age: under execution TTL during smoke
- refresh: `NOT_REQUIRED`

After SYSTEM OFF and elapsed TTL:

- candidate-price-path returned to `STALE` / `REFRESH_REQUIRED`
- this is correct because system power is OFF and execution TTL is short

## 16. Candidate Explanation / Bridge Integration

Candidate explanations now include:

- candidate-specific token
- candidate price path state
- candidate trusted orderbook state
- orderbook age / TTL
- refresh-before-execution state
- entry price source
- exit liquidity state
- candidate-specific required-to-pass

Eligible-to-intent bridge now includes:

- `candidate_price_path_state`
- `candidate_trusted_orderbook_state`
- `refresh_before_execution_state`
- token/side mismatch blockers when applicable

## 17. Paper Readiness Before / During / After

Before smoke:

- `paper_readiness_state=BLOCKED`
- `paper_simulation_state=OFF`
- `candidate_targeted_refresh_state=REFRESH_AVAILABLE`
- `candidate_price_ready_count=0`
- `candidates_waiting_for_price_refresh=100`

During smoke:

- `paper_readiness_state=BLOCKED`
- `paper_simulation_state=OFF`
- `runtime_life_state=ALIVE`
- `candidate_targeted_refresh_state=REFRESH_SUCCEEDED`
- `candidate_price_ready_count=100`
- `candidates_waiting_for_price_refresh=0`

After cleanup:

- `paper_readiness_state=BLOCKED`
- `paper_simulation_state=OFF`
- `system_power_state=OFF`
- `runtime_life_state=STOPPED`
- candidate price path returned to refresh-required after TTL

Paper did not become executable.

## 18. Artifact Safety Counts

Before smoke:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `live_orders=0`
- `positions=0`

During smoke:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `live_orders=0`
- `positions=0`

After cleanup:

- `paper_intents=20`
- `paper_orders=12`
- `paper_fills=9`
- `paper_positions=12`
- `paper_position_closes=9`
- `live_orders=0`
- `positions=0`

Allowed DATA_ONLY freshness movement:

- `orderbook_snapshots` increased from `50760` to `50912`
- `market_snapshots_v2` increased from `115500` to `115520`
- `paper_eligibility_candidates` increased from `20192` to `20222`
- `no_trade_log` increased from `20192` to `20222`
- `trusted_orderbook_evidence_runs` increased from `1018` to `1033`

## 19. Remaining Risks

- Candidate-targeted freshness is still bounded per cycle, so not every historical candidate is refreshed in one pass.
- After SYSTEM OFF, short execution TTL correctly makes candidate price evidence stale again.
- Some historical candidates still lack market/side/token and remain blocked with missing-data explanations.
- The latest exact token orderbook is used when trusted candidate evidence exists for that candidate path; the trusted link may not always point to the newest snapshot id.
- Some bridge rows still show missing token/orderbook for older or incomplete candidates.

## 20. Next Recommended Phase

Paper certification should be the next phase only after explicit approval. It should keep Paper Simulation OFF until a controlled certification run is approved and should require candidate-specific fresh trusted price evidence immediately before any paper execution.

