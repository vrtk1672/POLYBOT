# V2.5 Rules / Wording / Compliance Neuron

## Purpose

V2.5 adds a durable rules-risk layer so POLYBOT does not treat headline-attractive markets as safe when their rules, resolution source, deadline, settlement method, edge cases, or compliance posture are unsafe or unclear.

The Rules Neuron is intelligence-only. It does not trade, create order intents, approve risk, or bypass the Runtime State Governor.

## Architecture

The phase adds `app/rules_neuron/` with deterministic parsers, guards, scorers, optional AI enrichment, and an orchestration service:

- rules ingestion from V2.2 Data Foundation
- resolution source parsing and deterministic verification
- deadline and settlement parsing
- ambiguous term and edge-case detection
- wording risk, dispute risk, and resolution clarity scoring
- jurisdiction and compliance guards
- optional V2.3 AI wording precheck, cache/budget gated
- V2.1 Event Bus publishing
- FastAPI routes under `/rules`

## Rules Ingestion

`RulesIngestion` reads `markets_v2` and `market_rules`, normalizes rules text, computes a stable hash, and emits `rules.ingested`.

Missing rules are represented explicitly and flow through to high risk, review, or no-trade recommendations.

## Parsers And Detectors

- `resolution_source_parser.py` extracts source name, URL, domain, and source type without network verification.
- `deadline_parser.py` detects missing, ambiguous, timezone-unclear, and close-time-conflicting deadlines.
- `settlement_method_parser.py` classifies objective source, platform manual, oracle, subjective, or unknown settlement.
- `ambiguous_terms_detector.py` flags wording such as likely, announced, reported, before, after, confirmed, and end-of-day.
- `edge_case_detector.py` detects cancellation/postponement, announcement versus implementation, boundary ambiguity, multiple sources, manual discretion, and contradictions.

## Scoring

All scores are bounded `0..1`.

- `wording_risk_scorer.py` combines ambiguity, deadline, source, scope, settlement, edge-case, and contradiction risk.
- `dispute_risk_scorer.py` raises risk for subjective/manual settlement, unclear sources, conflicts, deadlines, and dangerous edge cases.
- `resolution_clarity_scorer.py` rewards present rules, explicit sources, clear deadlines, objective settlement, and few edge cases.

## Guards

`source_verification_guard.py` performs deterministic, non-network source verification. Missing or vague sources remain unknown or unverified.

`jurisdiction_guard.py` is a safety classification layer, not legal advice. Unsupported or prohibited configured categories can produce blocking compliance records.

`compliance_guard.py` creates warnings or blocks and produces the final rules recommendation:

- `TRADE_ALLOWED`
- `NO_TRADE`
- `REVIEW_REQUIRED`
- `PENALIZE_HEAVILY`

`TRADE_ALLOWED` means rules/compliance does not block a future candidate. It is not an execution approval.

## AI Wording Analyzer

`ai_wording_analyzer.py` uses the V2.3 Hybrid AI Brain only as optional enrichment. It is local-first, cache-first, budget-gated, cloud-disabled by default, and cannot override hard compliance blocks.

AI unavailability does not block deterministic rules analysis.

## Database Tables

Migration `0043_v2_rules_wording_compliance_neuron.sql` extends `market_rules` when needed and adds:

- `rules_analysis`
- `wording_risk_scores`
- `compliance_blocks`
- `resolution_sources`
- `rules_ai_analysis`

`market_rules` remains the canonical rules store from V2.2.

## API Routes

- `GET /rules/market/{market_id}`
- `GET /rules/analysis/recent`
- `GET /rules/blocks`
- `GET /rules/coverage`
- `POST /rules/analyze`
- `POST /rules/analyze/all`

Read endpoints return DB truth only. Analyze endpoints require a reason and produce no trading side effects.

## Dashboard Truth Fields

The operator dashboard query layer now exposes real DB-backed rules fields:

- rules coverage percent
- markets with rules analysis
- missing rules count
- high wording risk count
- high dispute risk count
- compliance block count
- average resolution clarity
- latest rules analysis timestamp
- top compliance blocks
- top wording-risk markets

## Event Bus Integration

Rules events are redacted and identifier-focused:

- `rules.ingested`
- `rules.analysis.created`
- `rules.wording_risk.scored`
- `rules.dispute_risk.scored`
- `rules.source.verified`
- `rules.compliance.blocked`
- `rules.ai.analyzed`
- `rules.recommendation.created`

No trading events are published by V2.5.

## Integrations

V2.0 State Governor remains authority. DATA_ONLY, PAPER, and SHADOW_LIVE allow rules analysis; KILL blocks new analysis jobs while read endpoints remain available.

V2.2 Data Foundation supplies markets and rules. V2.3 AI Brain is optional. V2.4 News Neuron is unchanged.

## Safety Guarantees

- no orders
- no order intents
- no risk approval
- no live trading enablement
- no legal advice
- no fake source verification
- no fake dashboard data
- missing rules force risk/review/no-trade posture
- compliance blocks override softer signals
- secrets and large raw rules text are not emitted in events

## Known Limitations

Source verification is deterministic and non-networked. AI wording analysis is optional and mocked in tests. Compliance classification is safety metadata, not legal advice.

Future phases can feed these outputs into Opportunity Cortex and Risk Governor V2.
