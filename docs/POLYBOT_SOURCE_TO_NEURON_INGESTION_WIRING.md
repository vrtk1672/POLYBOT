# POLYBOT V3.9 Source-to-Neuron Ingestion Wiring

## Purpose

V3.9 wires configured external intelligence sources into the correct POLYBOT organs before they enter the nervous system.

Correct flow:

External Source -> Neuron / Brain -> Neural Event -> Mesh Session -> Shared Awareness -> Multi-Brain Consumption -> Mesh Coordinator -> Dialogue / Dashboard.

This phase does not create orders, fills, positions, paper intents, live actions, shadow actions, strategy routing, or opportunity scoring.

## Runtime Entry Points

- `GET /dashboard/api/v2/source-to-neuron-flow`
- `POST /source-to-neuron/run`

The controlled run endpoint respects `SystemPowerService`. When SYSTEM is OFF, ingestion is blocked and no provider calls or event publishing occur.

## Source Mapping

| Source | Organ | Event Type | Storage | Status |
| --- | --- | --- | --- | --- |
| `NEWS_RSS_FEEDS` | News Neuron | `NEWS_DETECTED` | `news_sources`, `news_raw_events`, `news_normalized_events`, `neural_events` | Wired |
| `NEWS_API_KEY` / NewsAPI | News Neuron | `NEWS_DETECTED` | `news_sources`, `news_raw_events`, `news_normalized_events`, `neural_events` | Wired |
| Polymarket Gamma public API | Market Neuron | `MARKET_REPRICING` | `source_status`, `neural_events` | Wired |
| Polymarket CLOB `/book` | Orderbook Neuron | `ORDERBOOK_REFRESHED` | `orderbook_snapshots`, `neural_events` | Wired |
| Polymarket CLOB `/book` spread/depth | Liquidity Neuron | `SPREAD_CHANGED`, `LIQUIDITY_CHANGED` | `orderbook_snapshots`, `neural_events` | Wired |
| Polymarket public trade activity | Whale Neuron | `WHALE_DETECTED` when threshold is met | `whale_events`, `neural_events` | Wired |
| Ollama local generation | AI Context Brain | `AI_CONTEXT_UPDATED` when local generation succeeds | `ai_requests`, `ai_responses`, `neural_events` | Wired, runtime degraded in smoke |
| OpenAI / Anthropic | AI Context Brain | No event by default | Provider status only | Auth-only, no generation |
| Paper PnL truth | PnL Neuron | `PNL_CHANGED` | `paper_trade_ledger`, `neural_events` | Wired |

Missing providers remain out of scope for this phase: CryptoPanic, X/Twitter, Reddit, Telegram, Discord.

## Safety Rules

- No write/order endpoints are called.
- CLOB access is read-only.
- Cloud AI providers are auth/status only by default.
- Real `.env` is not modified.
- Secret values are never returned; error summaries are redacted.
- Trading truth tables are not mutated by ingestion.

## Thresholds

- Whale detection uses `SOURCE_TO_NEURON_WHALE_USD_THRESHOLD`, default `1000`.
- CLOB spread and liquidity events are source-backed from the current bounded orderbook sample.
- One bounded run uses `limit_per_source`, defaulted by endpoint payload.

## Dashboard Truth

The dashboard returns `mock_data=false` and reports:

- Provider status.
- Source and neuron status.
- Events created by type.
- Sessions, awareness records, brain opinions, and mesh coordinator decisions updated.
- Latest source-backed items.
- Missing/degraded providers.
- Redacted errors only.

## Next Phase

Full News Neuron, Whale Neuron, and AI Context expansion can build on this wiring by adding richer source-specific interpretation and operator-selected provider depth.
