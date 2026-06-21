# Source-Backed Edge Integration Report

## Purpose

Implement a source-backed Edge Integration Bridge so candidate-scoped Mesh evidence can produce one auditable Edge Thesis for Risk without faking edge, loosening gates, or activating Paper Simulation.

## Existing Neurons Found

Reused existing evidence surfaces:

- Candidate-scoped trusted orderbook snapshots/events.
- Candidate price path and mesh evidence bundles.
- Liquidity, risk, exit, capital, lifecycle opinions.
- Coordinator decisions.
- `risk_evidence_mesh_evaluations`.
- `neuron_signals`.
- News impact, whale events, market memory, and payout odds where present.
- AI routing/config surfaces through `AIContextRouterService` and `HybridAIBrainService`.

## Evidence Sources Used

Candidate-scoped:

- Trusted orderbook evidence.
- Candidate identity, side, token, correlation, and mesh bundle context.
- Payout/risk evidence where already candidate-linked.

Market-level/supporting only:

- News impact rows.
- Whale/flow rows.
- Market memory rows.
- Generic neuron signals.

Market-level evidence is not treated as candidate-actionable by itself.

## AI Model Usage

AI integration was implemented as a safe contract layer:

- Structured AI review validation is available.
- AI may not invent source IDs.
- AI may not invent fair probability or expected edge.
- Malformed AI output is rejected.
- If AI is unavailable, deterministic fallback is used.

The controlled run used `deterministic_fallback` with `ai_review_status=UNAVAILABLE`.

## Edge Thesis Schema

The canonical Edge Thesis is stored in `risk_evidence_mesh_evaluations.metadata_json.edge_thesis` and exposed through `/dashboard/api/v2/control/source-backed-edge`.

Key fields:

- candidate identity: `candidate_id`, `market_id`, `condition_id`, `side`, `token_id`
- `edge_state`
- `edge_score`
- `source_backed`
- `risk_usable`
- supporting/opposing neurons and sources
- `ai_thesis`
- `ai_counter_thesis`
- `blocker_code`
- `required_to_pass`
- `source_records`

No fair probability or expected edge is fabricated.

## Scoring Logic

Rules implemented:

- Fresh orderbook alone can create `EDGE_WATCH`, not `EDGE_SUPPORTED`.
- Fresh directional non-orderbook evidence is required for `EDGE_SUPPORTED`.
- Conflicting directional evidence reduces score and can produce `SOURCE_CONFLICT`.
- Stale orderbook or stale directional source evidence produces `EDGE_STALE`.
- Stale neutral context remains visible but does not become the risk blocker.
- AI cannot increase the score without cited source evidence.

## Risk Integration

Risk now builds and consumes the Edge Thesis during `risk_evidence_mesh` evaluation.

Mappings:

- `EDGE_SUPPORTED` and `risk_usable=true` -> `SOURCE_BACKED_EDGE_PRESENT`
- `EDGE_WATCH` / `EDGE_WEAK` -> risk review / weak edge
- `NO_SOURCE_BACKED_EDGE` -> `RISK_BLOCKED_NO_SOURCE_BACKED_EDGE`
- `SOURCE_CONFLICT` -> `RISK_BLOCKED_SOURCE_CONFLICT`
- `EDGE_STALE` -> `RISK_BLOCKED_EDGE_STALE`

Risk thresholds and approvals were not loosened.

## Lifecycle / Actionability Integration

Paper actionability now exposes:

- `edge_thesis`
- `edge_state`
- `edge_score`
- `source_backed`
- `risk_usable`
- supporting/opposing neurons

Lifecycle remains the governing blocker where Risk does not provide usable edge.

## Tests Run

```text
.venv\Scripts\python.exe -m pytest tests/test_source_backed_edge_integration.py tests/test_ai_edge_reasoner_contract.py -q
10 passed in 0.37s

.venv\Scripts\python.exe -m pytest tests/test_risk_lineage_candidate_identity.py tests/test_exit_candidate_specific_refresh.py tests/test_pre_paper_blocker_correction.py tests/test_paper_actionability_contract.py tests/test_pre_paper_safety_invariants.py tests/test_candidate_scoped_event_production.py tests/test_lifecycle_capital_event_native_opinions.py tests/test_mesh_evidence_bundle.py tests/test_paper_readiness.py -q
29 passed, 21 skipped in 4.12s

.venv\Scripts\python.exe -m pytest tests -q -k "edge or source_backed or ai_edge or risk or lineage or exit or lifecycle or pre_paper or paper_actionability or candidate_scoped or mesh"
168 passed, 313 skipped, 1512 deselected in 8.53s

.venv\Scripts\python.exe -m compileall app tests
Passed
```

## Deployment

```text
docker compose build api
docker compose up -d --no-deps api
```

Active server verified with:

- `/healthz`
- `/runtime/health`
- `/dashboard/api/v2/control/paper-actionability`
- `/dashboard/api/v2/control/pre-paper-safety`
- `/dashboard/api/v2/control/paper-readiness`
- `/dashboard/api/v2/control/paper-certification-plan`
- `/dashboard/api/v2/control/source-backed-edge`

## Controlled SYSTEM ON Decision Run

Action:

- POST `/system/power/on`
- Waited about 4-6 supervisor cycles.
- Did not enable Paper Simulation.
- Did not start Full Monitor Run.
- POST `/system/power/off`

Result:

- Supervisor reached ALIVE/RUNNING.
- Candidate-scoped events appeared.
- Mesh bundles remained complete.
- Edge theses generated.
- Paper Simulation stayed OFF.
- Forbidden artifacts did not increase.

## Decision Run Counts

During run:

- candidate-scoped events: 16 in latest 50 checked
- mesh bundles: 50
- candidate-scoped bundles: 16 during run; final actionability read showed 50 candidate-scoped bundles
- all-five opinions: 50
- source-backed-edge items: 50
- `EDGE_SUPPORTED`: 0
- `EDGE_WATCH`: 50
- `EDGE_STALE`: 0 after stale-neutral correction
- `source_backed`: 0
- `risk_usable`: 0
- `ACTIONABLE_SMALL_PAPER`: 0
- `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`: 0 after enforcing the edge thesis gate
- `BLOCKED_BY_RISK`: 14 after enforcing the edge thesis gate
- `BLOCKED_BY_LIFECYCLE`: 36 after enforcing the edge thesis gate
- pre-paper safety: `PRE_PAPER_NOT_READY`
- paper readiness: `BLOCKED`

## Sample Edge Thesis

Candidate:

- candidate_id: `eligibility_exit_risk_thesis_coord_22ff4b1d2fea49d1968f850394ca3220`
- market_id: `691547`
- side: `YES`
- token_id: `34626184950254225208692030156208941308358060420950772251072421141618169142241`

Edge result:

- edge_state: `EDGE_WATCH`
- edge_score: `0.18`
- source_backed: `false`
- risk_usable: `false`
- primary_edge_type: `ORDERBOOK_LIQUIDITY_SETUP`
- supporting_neurons: `[]`
- blocker_code: `NO_SOURCE_BACKED_EDGE`
- required_to_pass: collect fresh directional source evidence from news, whale, payout, cross-market, or validated neuron signals.

AI summary:

- `Orderbook supports watch-level context only; no independent directional source backs the candidate side.`

## What-If Analysis

1. Current state: `EDGE_WATCH`, not risk-usable; Phase 10 cannot start on source-backed edge criteria.
2. If Paper Simulation were ON only: still not enough; Paper OFF is not the only blocker for source-backed edge.
3. If edge threshold were lower by 10 percent: still no `EDGE_SUPPORTED`; score is 0.18 and lacks directional backing.
4. If AI unavailable: deterministic fallback classifies safely, as observed.
5. If only orderbook evidence exists: classified as `EDGE_WATCH`, not paper-usable edge.
6. If source-backed evidence exists but conflicts: classified as `SOURCE_CONFLICT` or score reduced.
7. If `EDGE_SUPPORTED` and other non-edge blockers clear: candidate can become `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`.

## Artifact Safety Counts

Forbidden artifacts:

- paper_intents: 20 -> 20
- paper_orders: 12 -> 12
- paper_fills: 9 -> 9
- paper_positions: 12 -> 12
- live_orders: 0 -> 0
- positions: 0 -> 0

DATA_ONLY evidence rows changed as expected:

- event_log: +261
- orderbook_snapshots: +164
- risk_decisions: +10
- exit_plans: +13
- lifecycle_governance_decisions: +74
- brain_outputs: +840
- coordinator_decisions: +184
- no_trade_log: +16
- risk_evidence_mesh_evaluations: +74

## READY_FOR_PHASE_10

READY_FOR_PHASE_10 = NO

Exact reason:

The Edge Integration Bridge is implemented and Risk now consumes a canonical Edge Thesis, but no sampled candidate currently has fresh directional source-backed evidence. Current candidates are at `EDGE_WATCH`, not `EDGE_SUPPORTED`; `source_backed=false`; `risk_usable=false`.

The paper actionability surface now enforces this rule: candidates with `EDGE_WATCH` and `risk_usable=false` are blocked by Risk and are not labeled `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`.

## Safety Result

- Paper Simulation was not activated.
- Full Monitor Run was not started.
- Shadow and Live remained disabled.
- No paper/live/shadow artifacts were created.
- Risk, Exit, Lifecycle, Capital, and execution gates were not loosened.
- No DB destructive action was performed.

## Recommended Next Step

Build a source ingestion/freshness pass for directional evidence:

- fresh candidate-linked news impact
- candidate/side-aware whale-flow evidence
- cross-market discrepancy evidence
- validated directional neuron signals

Then rerun the Edge Thesis bridge and require `EDGE_SUPPORTED`, `source_backed=true`, and `risk_usable=true` before Phase 10.
