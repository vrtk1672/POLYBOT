# Side-Specific Evidence Arbitration Report

## 1. Purpose

This change upgrades PAPER same-market side arbitration so POLYBOT can distinguish whether evidence supports YES or NO instead of applying generic market evidence equally to both sides.

The goal is not to force trades. The goal is to let the Full Mesh choose one better-supported side when side evidence exists, keep unresolved conflicts visible when evidence is missing, and preserve Paper Defense, PaperIntentGate idempotency, session accounting, and live/shadow/real safety.

## 2. Audit Findings

Same-market arbitration was already running before PaperIntentGate. It grouped YES/NO ENTER-like decisions by market and compared arbitration scores.

The repeated exact ties were caused primarily by a missing normalized side-evidence model:

- Generic market-level evidence was applied symmetrically to YES and NO.
- Many signals and AI records were SIDE_UNKNOWN or WATCH_ONLY.
- Opportunity scores often collapsed to the same baseline, commonly 55.46.
- Thesis, edge, and exit states were mostly side-scoped by decision row but not directional enough to distinguish support.
- Orderbook and token data proved executability, but often did not carry direction.

Primary classification:

- H. MISSING_SIDE_EVIDENCE_MODEL

Secondary classifications:

- A. GENERIC_MARKET_EVIDENCE_APPLIED_TO_BOTH_SIDES
- B. SIDE_UNKNOWN_DOMINATES
- D. SCORE_COLLAPSE_TO_55_46
- E. MISSING_SIDE_THESIS
- F. MISSING_SIDE_EDGE

## 3. Why Ties Happened

The prior arbitrator used opportunity score, thesis/edge/exit state, orderbook freshness, spread/liquidity, blockers, and Defense Level. Those inputs were valid, but many were identical for both sides of the same market.

When both sides had the same opportunity score, same fallback exit status, same blocker shape, and no explicit side direction, the computed YES and NO arbitration scores were identical. Example observed before this work:

- Market 691547
- YES arbitration score: 93.99
- NO arbitration score: 93.99
- Margin: 0
- Required margin at Defense 20: 2
- Outcome: SAME_MARKET_OPPOSING_SIDE_UNRESOLVED

## 4. Side Evidence Model

Added `SideEvidenceScorer` in `app/services/side_evidence.py`.

For each market/side it computes:

- side_evidence_score
- direction_confidence
- evidence_quality: DIRECT, INDIRECT, WEAK, or UNKNOWN
- source_support by news/event/AI/orderbook/liquidity/thesis/edge/exit/memory
- positive_reasons
- negative_reasons
- missing_reasons
- side_unknown_penalty
- already_priced_in_penalty

It uses existing evidence only:

- runtime decision side and token context
- `source_evidence.direction_for_market`
- `side_evidence.direction_for_market`
- `signal_market_links.matched_side`, `side_confidence`, and `side_evidence_json`
- `ai_mesh_insights.direction_hint` and `direction_confidence`
- explicit thesis/edge side fields if present
- side-specific orderbook spread and liquidity fields

SIDE_UNKNOWN evidence is not treated as directional support.

## 5. Scoring Formula

SameMarketSideArbitrator now computes:

```text
side_arbitration_score =
  existing_arbitration_score
  + side_evidence_score
  + direction_confidence bonus
  - side_unknown_penalty
  - missing_side_evidence penalty
```

The side evidence score is additive, but integrity blockers still dominate and cannot be softened by evidence.

## 6. Tie-Break Policy

If both sides are still tied after side evidence:

1. Fresher orderbook.
2. Tighter spread.
3. Better liquidity/depth.
4. Better fallback exit viability.
5. Lower blocker severity.
6. Better recent price movement / repricing potential.
7. Deterministic hash of market_id + paper_session_id.

Defense behavior:

- Defense 100/80: weak exact ties remain unresolved.
- Defense 60: unresolved unless technical tie-break strongly favors one side.
- Defense 40: technical tie-break allowed.
- Defense 20: deterministic tie-break allowed if no integrity blocker exists.
- Defense 0: deterministic tie-break allowed for technically executable exact ties.

Every tie-break is recorded.

## 7. Defense-Level Behavior

Defense 20 still uses the existing adjusted threshold and strategic blocker softening from the Paper Defense Governor. This change does not lower thresholds or weaken integrity checks.

At Defense 20:

- direct or indirect side evidence can select a side when it creates a meaningful advantage;
- deterministic tie-break can choose a side for learning only when no integrity blocker exists;
- unresolved evidence remains visible.

## 8. Learning Ledger Fields

The same-market arbitration ledger now records side evidence details:

- yes_side_evidence_score
- no_side_evidence_score
- yes_evidence_quality
- no_evidence_quality
- side_unknown_count
- missing_side_evidence_json

These are added by migration `0149_same_market_side_evidence_fields.sql` and are also included in runtime arbitration evidence attached to decisions.

## 9. API / CLI Changes

Added:

- `GET /dashboard/api/v2/control/side-evidence`
- `.\tools\polybot.ps1 side-evidence [-limit 20]`

Updated:

- `GET /dashboard/api/v2/control/arbitration-autopsy` output includes side evidence fields through the arbitration records.
- `.\tools\polybot.ps1 arbitration-autopsy` displays side evidence scores and qualities.
- `.\tools\polybot.ps1 report` includes a Side Evidence section.

## 10. Tests Run

Focused:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_side_evidence.py tests/test_side_evidence_arbitration.py tests/test_side_unknown_arbitration.py tests/test_defense_tie_break_arbitration.py tests/test_arbitration_learning_ledger.py tests/test_arbitration_autopsy.py tests/test_paper_defense_level.py -q
10 passed, 3 skipped in 2.91s
```

Related:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_same_market_side_arbitration.py tests/test_defense_aware_arbitration.py tests/test_paper_intent_gate_idempotency.py tests/test_paper_defense_learning_ledger.py tests/test_paper_execution_adapter_runtime.py -q
5 passed, 4 skipped in 2.38s
```

Compile:

```text
.\.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 11. Runtime Verification

Deployment:

```text
docker compose build api
docker compose build migrate
docker compose run --rm migrate
docker compose up -d --no-deps api
```

Runtime:

```text
.\tools\polybot.ps1 restart-paper-session -balance 1000 -defense 20
Start-Sleep -Seconds 1200
```

Active session:

- `paper_session_20260620T013129Z_bdc4229c`
- Defense level: 20
- Starting balance: 1000

After the 20-minute observation:

- Runtime continuity: CONTINUOUS
- Hunting verdict: BROAD_HUNTING
- Trade lifecycle: ENTER_OK_EXIT_UNKNOWN
- Total conflicts: 18
- Resolved conflicts: 18
- Unresolved conflicts: 0
- Tie-broken conflicts: 5
- Paper intents: 14
- Paper orders: 0
- Paper fills: 0
- Paper positions: 0
- Open positions: 0
- Live orders: 0
- Shadow orders: 0
- Real orders: 0

System cleanup:

```text
.\tools\polybot.ps1 off
```

Final cleanup state:

- System power: OFF
- Runtime state: DATA_ONLY
- Paper adapter: DISABLED
- Live adapter: BLOCKED

## 12. Examples

Resolved conflict:

- Market: 597964
- Defense: 20
- YES arbitration score: 100.16
- NO arbitration score: 102.052
- Selected side: NO
- Rejected side: YES
- Outcome: ARBITRATION_SELECTED_BY_SIDE_EVIDENCE
- Reason: NO selected by stronger side-specific evidence under Defense 20

Tie-broken conflict:

- Market: 610236
- YES arbitration score: 98.16
- NO arbitration score: 98.16
- Selected side: YES
- Outcome: TIE_BROKEN_FOR_LEARNING
- Tie breaker: deterministic_hash_market_session

## 13. Remaining Risks

- The verification run created current-session Paper intents but no orders/fills/positions. That is downstream of side arbitration and should be investigated separately in Paper execution adapter / intent execution scheduling.
- Some side evidence remains indirect because thesis and edge records are not always explicitly directional.
- Supervisor reporting briefly showed a source-refresh mutation diagnostic, but `supervisor-autopsy` reported `RUNNING_OR_IDLE` and `blocks paper entries: False`.

## 14. Status

Status: YELLOW

Side-specific arbitration is working and reduced unresolved same-market conflicts in this run. The remaining YELLOW reason is that the 20-minute verification produced intents but no paper orders/fills/positions, so the trade execution continuation deserves a separate follow-up audit.

Safe to continue Defense 20 PAPER runtime: YES, with the noted downstream execution follow-up.
