# POLYBOT Active Truth & Historical Memory Layer

## Purpose

The Active Truth layer separates current decision truth from historical memory.

Core rule:

* Fresh data can decide.
* Historical data can explain.
* Stale data can only block or request refresh.

This prevents old same-market guard, risk, lifecycle, orderbook, or paper intent records from authorizing new Paper activity while preserving them for forensics, memory, and learning.

## Truth States

| Truth state | Meaning |
| --- | --- |
| `ACTIVE_FRESH` | Source is within policy TTL or is an active non-TTL source. |
| `LAST_KNOWN` | Source is stale but still useful as context. It cannot authorize. |
| `HISTORICAL_ONLY` | Source is accounting/history/memory only. It cannot authorize. |
| `REFRESH_REQUIRED` | Source is stale/expired and must refresh before Paper authorization. |
| `UNKNOWN` | Source freshness or authority cannot be determined. |
| `EXPIRED` | Reserved for future explicit expiry policies. |

## Decision Permissions

| Permission | Meaning |
| --- | --- |
| `CAN_AUTHORIZE` | May support Paper authorization when other gates also pass. |
| `CAN_INFORM_ONLY` | May inform Mesh, dashboard, and forensics only. |
| `CAN_TEACH_ONLY` | Historical memory only. |
| `MUST_REFRESH` | Blocks authorization until refreshed. |
| `MUST_BLOCK` | Blocks authorization because required truth is missing/invalid. |
| `UNKNOWN_PERMISSION` | Not enough evidence to authorize. |

## Source Policy

Critical sources use strict TTL and become `REFRESH_REQUIRED` when stale:

* market/token identity
* orderbook and executable price
* risk decisions
* exit plans
* capital evaluations
* lifecycle plans
* lifecycle governance
* same-market guard decisions
* paper intents/candidates

Context sources are informational when stale:

* payout/odds
* exit/hold
* capital efficiency
* mesh coordinator context

Historical sources cannot authorize:

* closed positions
* close rows
* capital release / realized PnL rows
* generic capital account events

Capital lock truth is only `CAN_AUTHORIZE` for actual active lock events such as `CAPITAL_LOCKED_ON_FILL` or audited lock backfills. Generic account initialization or PnL accounting rows are historical/accounting memory.

## Same-Market Truth Handling

Same-market opposing-side guard decisions are critical only while fresh. A stale same-market guard result is no longer treated as active opposing exposure truth. It becomes:

* truth state: `REFRESH_REQUIRED`
* permission: `MUST_REFRESH`
* lifecycle blocker: `STALE_SAME_MARKET_GUARD`

Fresh guard rows may still hard-block on active opposite exposure or active opposite intent. Historical closed exposure can explain prior behavior but cannot authorize or hard-block new Paper action by itself.

## Governance Integration

`LifecycleGovernanceGateService` now evaluates same-market guard authority through `TruthStateService` before converting a same-market plan into a hard blocker. For Paper intent/execution actions, missing or stale same-market truth requires refresh. For observe-only bounded audits, stale guard evidence is reported as stale instead of being promoted to current opposing exposure truth.

`FreshnessGovernanceService` now uses truth-state classification. Stale payout/odds, exit/hold, and capital-efficiency records are informational; stale critical sources still block.

## Dashboard And Forensics

Added:

* `GET /dashboard/api/v2/truth-state`
* `GET /dashboard/api/v2/truth-state/{truth_id}`
* `GET /dashboard/api/v2/truth-state/subject/{subject_id}`
* `POST /truth-state/audit`

Paper trade forensics now includes subject-linked truth-state records and a compact truth summary.

Brain dialogue now has a `Truth State` component that explains whether a source can authorize, must refresh, or is historical memory.

## Safety

The layer writes derived truth/governance rows only. It does not create Paper intents, Paper orders, fills, positions, closes, live orders, real orders, capital ledger rows, or balance changes.

## Runtime Use

Before any future Paper intent or Paper execution authorization, critical source truth must be fresh. Old intents and old lifecycle decisions remain preserved, but they must refresh before they can authorize Paper.
