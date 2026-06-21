# POLYBOT Neuron Dialogue Coverage

## Purpose

This phase hardens Brain Dialogue Feed coverage for real POLYBOT neurons. It adds independent, source-backed neuron voices without changing trading decisions, paper execution, live execution, Risk, Exit, or Eligibility behavior.

## Contract

- Neuron dialogue is observational only.
- Every normal neuron dialogue event must cite a real source table and source record id.
- SYSTEM OFF blocks normal neuron dialogue materialization.
- SYSTEM ON allows neuron dialogue materialization from existing DB/runtime source records.
- Dashboard reads do not create dialogue rows.
- Silent neurons are reported through System Life neuron coverage with exact reasons.
- Silent/missing/disabled neurons are not counted active.
- Decorative `service_health` rows do not make neurons active.

## Supported Neuron Voices

- News Neuron: `news_normalized_events`, `news_raw_events`, `news_market_links`.
- Social / Hype Neuron: `social_normalized_events`, `social_raw_events`, `social_market_links`.
- Whale Neuron: `whale_events`, `whale_scan_runs`, `whale_market_scores`.
- Market Neuron: `market_snapshots`, `markets_v2`.
- Orderbook Neuron: `orderbook_snapshots`.
- Liquidity Neuron: `liquidity_snapshots`, `liquidity_signals`.
- Time Neuron: `market_snapshots`, `market_lifecycle_events`.
- Rules / Wording Neuron: `rules_analysis`, `market_rules`, `wording_risk_scores`.
- Fees / Rewards Neuron: `fee_snapshots`, `fee_reward_signals`.
- AI / Context Neuron: `ai_decision_logs`, `ai_responses`, `brain_outputs`.
- Capital Neuron: `capital_state_v2`, `capital_brain_outputs`.
- Position Neuron: `paper_positions`, `paper_trade_ledger`.

## API

- `GET /dashboard/api/v2/brain-dialogue?component_type=neuron`
- `GET /dashboard/api/v2/brain-dialogue?component_type=neuron&component=Orderbook%20Neuron`
- `GET /dashboard/api/v2/neuron-dialogue`
- `GET /dashboard/api/v2/system-life`

`/dashboard/api/v2/system-life` now includes `neuron_coverage` with total, speaking, silent, missing, disabled, last neuron dialogue timestamp, and per-neuron state.

## Safety

This feature only writes `brain_dialogue_events`. It does not create paper intents, paper orders, fills, paper positions, real orders, live orders, Risk approvals, Exit readiness, or Eligibility decisions.
