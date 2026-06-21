# POLYBOT Lifecycle Governance Risk Evidence Integration

Date: 2026-06-05

Security governance: `YELLOW_ACCEPTED_BY_OPERATOR`

## Purpose

Lifecycle Governance now treats fresh Risk Evidence Mesh as the preferred current risk source.

The rule is:

`Fresh Risk Evidence beats stale legacy Risk summary.`

This does not weaken critical gates. A fresh `RISK_BLOCK` still hard-blocks. Non-risk critical blockers such as stale exit plans, stale orderbooks, capital blocks, same-market active conflicts, paper lineage red, and capital reconciliation red still hard-block.

## Risk Source Priority

Risk source order:

1. Fresh `risk_evidence_mesh_evaluations` within the Risk Evidence TTL
2. Fresh current-run `risk_decisions`
3. Last-known risk decisions for context
4. Historical risk decisions for forensics only

When Risk Evidence exists:

* `RISK_BLOCK` adds `RISK_BLOCKED` plus its precise subtype.
* `RISK_REVIEW`, `RISK_WATCH`, and `RISK_SUPPORT` remove stale or legacy risk blockers such as `RISK_BLOCKED`, `RISK_BLOCKED_LINEAGE`, `RISK_BLOCKED_NO_EDGE`, and `STALE_RISK_DECISION`.
* Stale Risk Evidence is context only. If no fresh legacy risk source is available, Lifecycle Governance blocks with `STALE_RISK_SOURCE_REFRESH_REQUIRED`.
* Optional context remains optional.
* Non-risk critical blockers are preserved.

## Actionability Mapping

* Fresh `RISK_BLOCK` with critical blockers -> `HARD_BLOCK`
* Fresh `RISK_REVIEW` with only legacy/stale risk blockers -> `WATCH_FOR_CONFIRMATION`
* Fresh `RISK_REVIEW` with non-risk critical blockers -> `HARD_BLOCK`
* Fresh `RISK_SUPPORT` with all critical gates clear -> can allow Paper according to existing Paper gate rules

No fake edge, fair probability, confidence, or actionability is created.

## Governance Trace

Lifecycle Governance metadata now records:

* selected risk source
* selected risk evidence evaluation id
* legacy risk decision id
* ignored legacy risk blockers
* ignored reason
* final risk interpretation
* blockers by priority

Dashboard summary exposes:

* `risk_evidence_used_count`
* `legacy_risk_ignored_count`
* `stale_legacy_risk_block_ignored_count`
* `risk_review_promoted_to_watch_count`
* `risk_review_kept_blocked_count`
* `risk_review_actionable_count`
* `risk_source_selection_summary`
* `latest_risk_review_traces`

Paper forensics exposes the selected risk source trace directly.

## Runtime Smoke Result

Bounded SYSTEM OFF smoke re-evaluated the 24 latest `RISK_REVIEW` subjects.

Result:

* fresh Risk Evidence was selected
* stale legacy risk was ignored
* `STALE_RISK_DECISION` was removed as the deciding blocker
* all 24 remained blocked by non-risk critical gates, mainly stale exit/capital/orderbook/lifecycle sources
* no Paper/live/capital mutation occurred

This is correct: the phase fixes risk-source priority, not stale exit/orderbook refresh.
