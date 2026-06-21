# Full Mesh Inquiry Orchestrator Report

## 1. Purpose

Implement the Full Mesh Ecosystem layer so candidate-scoped evidence can be queried through one Universal Mesh Contract and exposed through a read-only inquiry endpoint.

## 2. What Full Mesh Means

Full Mesh means each decision-critical organ can register, answer structured questions, expose freshness/confidence/source/blockers, and participate in candidate inquiry before Risk/Lifecycle/Paper actionability.

## 3. Existing Organs Found

Found and reused:

- candidate producer / paper eligibility
- candidate event correlation
- trusted orderbook
- candidate price path
- mesh evidence bundle
- liquidity/risk/exit/capital/lifecycle brain opinions
- coordinator decision
- source-backed edge engine
- risk evidence mesh
- exit foundation
- capital and same-market guard
- paper actionability and pre-paper safety
- runtime supervisor and state governor
- news, whale, social, market memory, signal infrastructure
- AI edge reasoner contract/fallback

## 4. Registered Organs

The Full Mesh registry registers:

- candidate
- candidate_event_correlation
- trusted_orderbook
- candidate_price_path
- liquidity
- market_movement
- news
- whale
- social
- cross_market
- market_memory
- source_backed_edge
- risk
- exit
- capital
- same_market_guard
- lifecycle
- coordinator
- ai_reasoner
- paper_actionability
- pre_paper_safety
- runtime_supervisor
- state_governor

## 5. Exempt Organs

- paper_execution: forbidden until controlled Paper activation.
- live_execution: forbidden for this phase.

## 6. Available Organs

Candidate-scoped available organs include:

- candidate
- candidate_event_correlation
- trusted_orderbook
- candidate_price_path
- liquidity
- source_backed_edge
- risk
- exit
- capital
- lifecycle
- coordinator
- paper_actionability
- pre_paper_safety

## 7. Unavailable / Passive Organs

Registered but passive or unavailable:

- news
- whale
- social
- market_movement
- market_memory
- cross_market
- ai_reasoner when configured model review is unavailable

These are not hidden. They appear in inquiry `missing_neurons` or unavailable responses.

## 8. Universal Mesh Contract

Implemented in:

- `app/services/full_mesh_contract.py`

Every organ response has candidate identity, response state, directional support, confidence, strength, freshness, source records, blockers, and required-to-pass fields.

## 9. Neuron Registry Design

Implemented in:

- `app/services/full_mesh_registry.py`

The registry declares organ type, service module, questions, scope, directional capability, DATA_ONLY write safety, availability, and adapter name.

## 10. Mesh Inquiry Orchestrator Design

Implemented in:

- `app/services/full_mesh_inquiry.py`
- `app/control_center/full_mesh_inquiry.py`

The orchestrator assembles inquiry sessions from existing Mesh Evidence Bundles, Source-Backed Edge Thesis rows, and Paper Actionability truth.

No new execution path is introduced.

## 11. Organ Adapters Implemented

Implemented in:

- `app/services/mesh_organ_adapters.py`

Adapters wrap existing truth for candidate identity, orderbook, liquidity, risk, exit, capital, lifecycle, coordinator, source-backed edge, AI fallback, and paper actionability. Passive/unavailable adapters return explicit unavailable responses.

## 12. AI Integration Result

AI remains safe:

- structured validation exists
- deterministic fallback is explicit
- unavailable AI is reported
- no source IDs or probabilities are invented

## 13. Edge Integration Result

`app/services/source_backed_edge_engine.py` now supports:

`build_edge_thesis_from_mesh_responses(...)`

Orderbook-only Mesh responses create `EDGE_WATCH`. Fresh directional source responses can create `EDGE_SUPPORTED`.

## 14. Risk / Lifecycle / Actionability Integration

Risk continues to consume the canonical Edge Thesis from `risk_evidence_mesh_evaluations`.

Paper Actionability now exposes:

- `full_mesh_inquiry_state`
- `full_mesh_edge_state`
- `full_mesh_required_to_pass`

Non-risk-usable edge remains blocked.

## 15. Control Center Endpoints

Added:

`GET /dashboard/api/v2/control/full-mesh-inquiry`

It exposes sessions, requested/responded/unavailable organs, missing neurons, edge state, risk result, lifecycle result, paper actionability result, final blocker, and required-to-pass.

## 16. Tests Run

Focused tests:

```text
.venv\Scripts\python.exe -m pytest tests/test_full_mesh_ecosystem_contract.py tests/test_mesh_inquiry_orchestrator.py tests/test_neuron_registry.py tests/test_mesh_organ_adapters.py -q
14 passed in 0.75s
```

Related pre-paper regression slice:

```text
.venv\Scripts\python.exe -m pytest tests/test_source_backed_edge_integration.py tests/test_ai_edge_reasoner_contract.py tests/test_risk_lineage_candidate_identity.py tests/test_exit_candidate_specific_refresh.py tests/test_pre_paper_blocker_correction.py tests/test_paper_actionability_contract.py tests/test_candidate_scoped_event_production.py tests/test_mesh_evidence_bundle.py tests/test_paper_readiness.py -q
37 passed, 18 skipped in 3.58s
```

Broad slice:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "mesh or neuron or inquiry or edge or source_backed or risk or exit or lifecycle or paper_actionability or candidate_scoped"
176 passed, 338 skipped, 1493 deselected in 8.21s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 17. Controlled SYSTEM ON Run

Deployment:

```text
docker compose build api
docker compose up -d --no-deps api
```

Active server verification:

- `/healthz`: `status=ok`, `ready=true`
- `/runtime/health`: active API reachable
- `/dashboard/api/v2/control/full-mesh-inquiry`: `status=REAL`
- `/dashboard/api/v2/control/source-backed-edge`: `status=REAL`
- `/dashboard/api/v2/control/paper-actionability`: `status=REAL`
- `/dashboard/api/v2/control/pre-paper-safety`: `PRE_PAPER_NOT_READY`
- `/dashboard/api/v2/control/paper-readiness`: `BLOCKED`
- `/dashboard/api/v2/control/paper-certification-plan`: `status=REAL`

Controlled run:

- `POST /dashboard/api/v2/control/actions/system-on`
- Waited through 8 supervisor cycles.
- Paper Simulation remained OFF.
- Full Monitor Run was not started.
- `POST /dashboard/api/v2/control/actions/system-off`

Run results:

- Runtime Supervisor reached `ALIVE` / `RUNNING`.
- Candidate producer reached `RUNNING`.
- Candidates updated since SYSTEM ON: 249.
- Raw durable orderbook events since SYSTEM ON: 228.
- Raw candidate-scoped orderbook events since SYSTEM ON: 121.
- Raw market-scoped orderbook events since SYSTEM ON: 107.
- Latest endpoint pages became token/side-mismatch heavy by the final poll, so candidate-scoped counts on the final `limit=200` page were 0 even though raw run evidence shows candidate-scoped events were produced.
- Full Mesh inquiry final `limit=200`: 200 sessions, 200 blocked, 0 errors, 4,600 organ requests, 2,400 responses, 2,200 unavailable/passive responses.
- Source-backed edge final `limit=50`: `EDGE_SUPPORTED=0`, `EDGE_WATCH=35`, `EDGE_STALE=15`, `risk_usable=0`, `source_backed=0`.
- Paper actionability final `limit=200`: `ACTIONABLE_SMALL_PAPER=0`, `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED=0`, `blocked_by_lifecycle=160`, `blocked_by_risk=40`.

## 18. FULL_MESH_STATE

`FULL_MESH_STATE = FULL_MESH_PARTIAL`

Reason:

- Universal contract, registry, orchestrator, adapters, and endpoint are active.
- Available organs respond through the shared Mesh contract.
- Passive/unavailable organs are visible rather than hidden.
- Current evidence does not produce source-backed, risk-usable edge.
- Latest event pages are dominated by token/side mismatch and missing candidate-event links, which keeps inquiry sessions blocked.

## 19. READY_FOR_PHASE_10

`READY_FOR_PHASE_10 = NO`

No candidate reached `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`.

## 20. Exact Reason If NO

Current minimum blockers:

- no `EDGE_SUPPORTED` candidate
- no `risk_usable` Edge Thesis
- no fresh directional source-backed evidence from news, whale, cross-market, payout, or validated directional neuron signals
- `MISSING_CANDIDATE_EVENT_LINK` / token-side mismatch dominates latest event pages
- `PAPER_SIMULATION_OFF` remains an expected operational blocker

## 21. Safety Result

Implementation is read-only over existing truth surfaces. No Paper, Shadow, Live, order, fill, position, or capital mutation path was added.

Forbidden artifact counts:

| Table | Before | After |
| --- | ---: | ---: |
| paper_intents | 20 | 20 |
| paper_orders | 12 | 12 |
| paper_fills | 9 | 9 |
| paper_positions | 12 | 12 |
| paper_position_closes | 9 | 9 |
| live_orders | 0 | 0 |
| positions | 0 | 0 |

DATA_ONLY evidence rows changed as expected:

- `event_log`: 556125 -> 556474
- `orderbook_snapshots`: 52975 -> 53219
- `risk_decisions`: 20442 -> 20462
- `exit_plans`: 20504 -> 20539
- `lifecycle_governance_decisions`: 11298 -> 11428
- `brain_outputs`: 30907 -> 32147
- `coordinator_decisions`: 22811 -> 23075
- `no_trade_log`: 20477 -> 20515
- `risk_evidence_mesh_evaluations`: 1995 -> 2125

## 22. Future Development Governance Rule

Every future decision-critical POLYBOT feature must register as a Mesh organ or declare an explicit exemption before it can influence Paper, Shadow, or Live.
