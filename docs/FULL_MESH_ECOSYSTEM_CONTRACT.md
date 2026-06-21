# Full Mesh Ecosystem Contract

## 1. What Full Mesh Means

The Mesh is the operating system of POLYBOT decision truth.

Every decision-critical component must be queryable as a Mesh organ. A candidate cannot progress toward Paper, Shadow, or Live unless the Mesh can show:

- which organs were asked
- which organs answered
- which organs were unavailable
- which evidence supports the candidate
- which evidence opposes the candidate
- what is stale or missing
- what AI concluded or why AI was unavailable
- what Risk accepted or rejected
- what Lifecycle allowed or blocked
- why the final decision is true

Orderbook freshness alone is not Edge. A candidate alone is not Edge. AI opinion alone is not Edge.

## 2. Universal Mesh Contract

Every Mesh organ response must use this shape:

```json
{
  "neuron_name": "...",
  "neuron_type": "ORDERBOOK | NEWS | WHALE | RISK | EXIT | CAPITAL | AI | MEMORY | CROSS_MARKET | LIQUIDITY | COORDINATOR | LIFECYCLE | CANDIDATE | MARKET | ACTIONABILITY | SAFETY | OTHER",
  "candidate_id": "...",
  "market_id": "...",
  "condition_id": "...",
  "side": "YES | NO",
  "token_id": "...",
  "correlation_id": "...",
  "event_id": "...",
  "response_state": "SUPPORTED | OPPOSED | NEUTRAL | WATCH | BLOCKED | STALE | MISSING | UNAVAILABLE | ERROR",
  "supports_side": "YES | NO | NEUTRAL | CONFLICT | UNKNOWN",
  "confidence": 0.0,
  "strength": 0.0,
  "freshness_seconds": 0,
  "source_backed": true,
  "summary": "...",
  "reason": "...",
  "blocker_code": null,
  "required_to_pass": [],
  "source_records": [],
  "created_at": "..."
}
```

The implementation lives in `app/services/full_mesh_contract.py`.

## 3. Neuron Registry Rules

Every decision-critical organ must either:

1. register as a Mesh organ, or
2. explicitly declare why it is not Mesh-native.

The Full Mesh registry lives in `app/services/full_mesh_registry.py`.

The current registry includes:

- candidate
- candidate event correlation
- trusted orderbook
- candidate price path
- liquidity
- market movement
- news
- whale
- social
- cross market
- market memory
- source-backed edge
- risk
- exit
- capital
- same-market guard
- lifecycle
- coordinator
- AI reasoner
- paper actionability
- pre-paper safety
- runtime supervisor
- state governor

`paper_execution` and `live_execution` are explicitly exempt from pre-paper inquiry because they are forbidden unless a later phase activates the relevant mode.

## 4. Organ Adapter Pattern

Existing services are wrapped; they are not rewritten.

Adapters live in `app/services/mesh_organ_adapters.py` and translate existing truth into the Universal Mesh Contract.

Adapters may be:

- available: returns source-backed response
- passive: registered but currently not candidate-scoped
- unavailable: explicitly recorded as unavailable
- error: adapter failure reported as a Mesh response

Missing organs must not be hidden.

## 5. Mesh Inquiry Orchestrator

The orchestrator lives in `app/services/full_mesh_inquiry.py`.

For a candidate-scoped bundle it:

- builds candidate identity
- requests every pre-paper-safe registered organ
- collects Universal Mesh responses
- records unavailable/passive organs
- builds an inquiry Edge Thesis from responses
- attaches latest canonical Risk Edge Thesis when available
- summarizes Risk, Lifecycle, and Paper Actionability

The read-only Control Center surface is:

`GET /dashboard/api/v2/control/full-mesh-inquiry`

## 6. Source-Backed Edge Requirements

The Source-Backed Edge Engine may consume Mesh inquiry responses through:

`build_edge_thesis_from_mesh_responses(...)`

Rules:

- orderbook-only evidence can produce `EDGE_WATCH`
- strong edge requires independent fresh directional source evidence
- stale directional evidence blocks
- conflicting directional evidence blocks or lowers score
- AI cannot raise score without cited source records
- fair probability and expected edge remain null unless real supported computation exists

## 7. AI Safety Rules

AI output must be structured and validated.

AI may not:

- invent source IDs
- invent probabilities
- invent expected edge
- mark edge source-backed without source records
- override Risk, Exit, Capital, Lifecycle, or State Governor

If AI is unavailable, the deterministic fallback must be explicit.

## 8. Safety Boundaries

Pre-paper Mesh inquiry is DATA_ONLY.

It may write only derived truth/evidence rows when existing safe paths do so. It must not create:

- paper intents
- paper orders
- paper fills
- paper positions
- live orders
- shadow orders

The Mesh must not bypass:

- State Governor
- Risk
- Exit
- Capital
- Lifecycle
- same-market guard
- duplicate guard
- open-position guard

## 9. Future Development Rule

Every new decision-critical feature must be Mesh-native before it can influence Paper, Shadow, or Live.

A new feature must include:

- registry entry
- adapter or explicit exemption
- Universal Mesh response
- tests proving missing/unavailable state is exposed
- tests proving no paper/live/shadow artifact creation

## 10. How To Test New Neurons

New organs must add or update tests that prove:

- the organ is registered or explicitly exempt
- the adapter returns the Universal Mesh Contract
- candidate identity is preserved
- freshness/confidence/source/blockers are explicit
- unavailable state is not hidden
- source-backed evidence contributes to Edge Thesis only when directional and fresh
- no trading artifacts are created
