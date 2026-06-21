# Candidate Event Scope + Orderbook Selection Repair Report

## 1. Purpose

Repair or prove the current hard blockers preventing high-scoring candidates from reaching Paper Observation or Full Paper readiness:

- `candidate_event_scope_not_actionable`
- `stale_orderbook`

This pass stayed DATA_ONLY. Paper Simulation, Shadow, Live, and Full Monitor Run were not activated.

## 2. Current Hard Blockers

Before the repair, the Trade Opportunity Score endpoint showed top candidates around `61.19` with:

- decision band: `HARD_BLOCKED`
- hard blockers: `candidate_event_scope_not_actionable`, `missing_candidate_event_link`, `stale_orderbook`
- soft blockers: `risk_review_not_full_paper_ready`, `capital_watch_not_full_paper_ready`, `reward_evidence_weak_or_missing`

## 3. Top Candidates Analyzed

Representative top candidates:

| candidate_id | market_id | side | token_id | score before |
|---|---|---|---|---:|
| `eligibility_exit_risk_thesis_coord_0e52013d10844453958d006d664dd668` | `691547` | `YES` | `34626184950254225208692030156208941308358060420950772251072421141618169142241` | `61.19` |
| `eligibility_exit_risk_thesis_coord_1952a0b87c1c495897eb8be31361da97` | `691547` | `YES` | `34626184950254225208692030156208941308358060420950772251072421141618169142241` | `61.19` |
| `eligibility_exit_risk_thesis_coord_c3363c8cfa4447d18270d37b91ea36f6` | `691547` | `YES` | `34626184950254225208692030156208941308358060420950772251072421141618169142241` | `61.19` |

## 4. Candidate Event Scope Root Cause

The selector found candidate-id event rows, but `CandidateEventCorrelationService` resolved the candidate token only from:

1. `paper_eligibility_candidates.expected_token_id`
2. `paper_eligibility_candidates.evidence.trusted_orderbook`
3. `paper_eligibility_candidates.evidence.candidate_price_path`

For high-score candidates, `expected_token_id` was null and the latest candidate evidence no longer contained the nested trusted orderbook token, while `trusted_orderbook_evidence_links` did contain fresh matching token truth.

Result:

- false `TOKEN_SIDE_MISMATCH`
- false `missing_candidate_event_link`
- candidate scope stayed `NOT_ACTIONABLE`

The remaining candidate-scope blocker after token repair is current when no fresh event_log row exists for that exact candidate. Fresh market/side/token events for other candidates are not used as candidate-actionable evidence.

## 5. Orderbook Freshness Root Cause

`stale_orderbook` was true while SYSTEM was OFF because orderbook execution TTL is 180 seconds. During DATA_ONLY SYSTEM ON verification, source refresh produced fresh exact trusted orderbook evidence for candidate/side/token.

Result after refresh:

- `candidate_trusted_orderbook_state=TRUSTED_FRESH_FOR_CANDIDATE`
- `candidate_price_path_state=CANDIDATE_PRICE_READY`
- `stale_orderbook` cleared for matching candidates

No stale orderbook was marked fresh without matching evidence.

## 6. Fixes Made

Code changes:

- `CandidateEventCorrelationService._candidate_rows()` now joins `markets_v2` and latest `trusted_orderbook_evidence_links`.
- `_candidate_token()` now resolves token identity from:
  1. explicit candidate `expected_token_id`
  2. latest trusted orderbook expected/orderbook token
  3. candidate evidence token
  4. market YES/NO token by side
- Paper Actionability now exposes selected candidate event and selected orderbook snapshot fields.
- Trade Opportunity Score now exposes:
  - `candidate_event_scope`
  - `candidate_event_link_state`
  - `token_side_match`
  - `orderbook_freshness_state`
  - `selected_orderbook_snapshot_id`
  - `selected_candidate_event_id`
- Decision Propagation Trace now exposes selected event/orderbook evidence and cycle consistency.

## 7. Remaining Hard Blockers

After DATA_ONLY verification:

- `Full Paper Certification count = 0`
- `Paper Observation eligible count = 24`
- `Hard Blocked count = 76`

Remaining hard blockers are current and candidate-specific, including missing thesis/exit/dynamic hold-time and capital hard blocks on lower-score rows.

## 8. Remaining Soft Blockers

Top Paper Observation candidates still carry soft blockers:

- `risk_review_not_full_paper_ready`
- `capital_watch_not_full_paper_ready`
- `reward_evidence_weak_or_missing`

These were preserved as soft blockers and were not converted to approval.

## 9. Score / Actionability / Trace Alignment

After verification:

- Score top candidates show `CANDIDATE_SCOPED`, `LINKED_TO_CANDIDATE`, `token_side_match=true`.
- Score and Paper Actionability show `TRUSTED_FRESH_FOR_CANDIDATE`.
- Decision Trace exposes selected event scope, link state, selected orderbook snapshot, and cycle consistency.

## 10. Tests Run

Focused:

```text
.venv\Scripts\python.exe -m pytest tests/test_candidate_event_scope_orderbook_selection.py tests/test_opportunity_score_hard_blocker_reconciliation.py tests/test_actionability_score_trace_alignment.py -q
13 passed in 2.28s
```

Related:

```text
.venv\Scripts\python.exe -m pytest tests/test_trade_opportunity_scoring.py tests/test_opportunity_decision_bands.py tests/test_paper_observation_eligibility.py tests/test_opportunity_score_actionability_integration.py tests/test_paper_actionability_strict_qualification.py tests/test_phase10_actionability_alignment.py -q
24 passed in 2.90s
```

Broad:

```text
.venv\Scripts\python.exe -m pytest tests -q -k "candidate_event_scope or orderbook_selection or opportunity_score or hard_blocker or paper_observation or paper_actionability or decision_trace"
46 passed, 1 skipped, 2086 deselected in 6.05s
```

Compile:

```text
.venv\Scripts\python.exe -m compileall app tests
Passed
```

## 11. DATA_ONLY Verification

Deployment:

```text
docker compose build api
docker compose up -d --no-deps api
```

Controlled verification:

- POST SYSTEM ON
- waited six source-refresh cycles: `216 -> 222`
- Paper Simulation stayed OFF
- Full Monitor Run was not started
- POST SYSTEM OFF

Post-run score counts:

| Count | Result |
|---|---:|
| Full Paper Certification | 0 |
| Paper Observation eligible | 24 |
| Watch Only | 0 |
| Hard Blocked | 76 |

Top candidate after repair:

- candidate_id: `eligibility_exit_risk_thesis_coord_9f28627279344700a81fb9bbb4ad7aee`
- score: `63.47`
- band: `PAPER_OBSERVATION`
- event scope: `CANDIDATE_SCOPED`
- link state: `LINKED_TO_CANDIDATE`
- orderbook: `TRUSTED_FRESH_FOR_CANDIDATE`
- remaining soft blockers: Risk Review, Capital Watch, weak/missing reward evidence

## 12. Paper Observation Eligibility Result

Paper Observation classification is now working for candidates with clean candidate event scope and fresh trusted orderbook evidence.

This is classification only. No Paper Observation execution mode was implemented or activated.

## 13. Full Paper Readiness Result

Full Paper readiness remains blocked:

- `Full Paper Certification count = 0`
- remaining blockers include current Risk Review, Capital Watch, and reward-evidence weakness

## 14. Safety Result

Forbidden artifacts before verification:

| Table | Before |
|---|---:|
| `paper_intents` | 21 |
| `paper_orders` | 12 |
| `paper_fills` | 9 |
| `paper_positions` | 12 |
| `paper_position_closes` | 9 |
| `live_orders` | 0 |
| `positions` | 0 |
| `shadow_orders` | 0 |

Forbidden artifacts after verification:

| Table | After |
|---|---:|
| `paper_intents` | 21 |
| `paper_orders` | 12 |
| `paper_fills` | 9 |
| `paper_positions` | 12 |
| `paper_position_closes` | 9 |
| `live_orders` | 0 |
| `positions` | 0 |
| `shadow_orders` | 0 |

No paper, live, shadow, or real artifacts were created.

## 15. Recommended Next Step

Extended Paper Runtime is safe to retry only as Paper-only runtime if the operator wants observation of classification behavior. Paper Observation execution remains not implemented and must not execute until explicitly approved as a separate mode.
