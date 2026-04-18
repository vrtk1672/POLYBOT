# POLYBOT

POLYBOT is a modular Polymarket intelligence system. This repository now includes:

- **Stage 1: Eyes** - market visibility
- **Stage 2: Brain** - Claude-assisted signal analysis
- **Stage 3: Memory + Paper Trading**
- **Stage 4: Guarded Live Execution Foundation**

Stage 1 does four things:
- fetches active Polymarket markets from the public Gamma API,
- normalizes the market payloads into internal models,
- computes a deterministic opportunity score for monitoring,
- exposes the current top opportunities in both the terminal and a local API.

Stage 4 is intentionally constrained. It supports authenticated connectivity, dry-run validation, and one explicitly armed micro-order path. It does **not** enable unattended autonomous live trading.

---

## Quick Start

```powershell
# 1. Install dependencies
python -m uv sync --extra dev

# 2. Run a live scan — top 10 markets, 500 events
.venv\Scripts\python gamma_crawler.py

# 3. Watch mode — rescan every 5 minutes, show only new entries
.venv\Scripts\python gamma_crawler.py --watch
```

---

## gamma_crawler.py

Standalone CLI that fetches, scores, and displays live Polymarket opportunities.
No server needed — runs once and exits (or loops with `--watch`).

### Usage

```
.venv\Scripts\python gamma_crawler.py [OPTIONS]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--top N` | 10 | Number of markets to display in the table |
| `--pages N` | 5 | API pages to fetch (100 events per page, so 5 = 500 events) |
| `--watch` | off | Repeat scan on an interval; shows only NEW markets each cycle |
| `--interval SEC` | 300 | Seconds between scans in `--watch` mode |

### Examples

```powershell
# Single scan, top 10 (default)
.venv\Scripts\python gamma_crawler.py

# Fetch more data, show more results
.venv\Scripts\python gamma_crawler.py --pages 10 --top 20

# Watch mode, rescan every 2 minutes
.venv\Scripts\python gamma_crawler.py --watch --interval 120 --top 15
```

### What it prints

Each run checks the Polymarket geoblock API first. If your IP is blocked, the
crawler exits with an error message before making any other requests.

The output table shows one row per market:

| Column | Meaning |
|--------|---------|
| `#` | Rank (1 = highest score) |
| `Question` | Market question |
| `YES` | Current YES price (0–1) |
| `NO` | Current NO price (0–1) |
| `Edge` | Profit in cents if cheap side wins (e.g. `75c` = 75 cents per $1 of shares) |
| `Hours` | Time remaining until market resolves |
| `24h Vol` | Trading volume in the last 24 hours |
| `Bucket` | Liquidity tier: `whale` / `high` / `safe` |
| `Score` | Opportunity score 0–100 |
| `Signal` | Human-readable reason for the score |

**Edge** is `(1 - cheap_side_price) * 100`. If YES=0.25 and NO=0.75, the cheap
side is YES at 25¢. If YES resolves, you profit 75¢ per share → edge = 75c.

**Bucket** guides position sizing:

| Bucket | Liquidity threshold | Meaning |
|--------|---------------------|---------|
| `whale` | liq ≥ $100k or 24h vol ≥ $200k | Deep — absorbs large positions |
| `high` | liq ≥ $10k or 24h vol ≥ $30k | Medium depth |
| `safe` | below high thresholds | Shallow — small positions only |

### Scan logs

Every run saves a timestamped JSON file:

```
logs/scan_YYYY-MM-DD_HH-MM.json
```

Each file contains:
- `scanned_at` — UTC timestamp
- `duration_ms` — total fetch + score time
- `total_events`, `total_markets`, `total_scored`
- `top_markets` — top 20 markets with all fields including breakdown, edge, bucket

---

## Scoring Model

Stage 1 uses a deterministic `0–100` score for **monitoring opportunity**, not trade execution.

```
Score = price_attractiveness (35%)
      + time_to_close        (25%)
      + liquidity_volume     (20%)
      + market_activity      (20%)
```

### Component breakdown

**Price Attractiveness (0–35 pts)**
Prefers markets priced in a tradable band rather than near-0 or near-1.
- Full points at balanced price (YES ≈ 0.50)
- Bonus for cheap-side near 0.20 (high upside)
- Near zero at extreme prices (0.01 or 0.99)

**Time to Close (0–25 pts)**
Prefers markets approaching resolution but not effectively over.

| Time remaining | Points |
|----------------|--------|
| ≤ 6 hours | 6.25 (very close, less predictable) |
| 6–24 hours | 13.75 |
| 1–7 days | **25** (peak window) |
| 7–30 days | 17.5 |
| 30–90 days | 11.25 |
| > 90 days | 5 |
| Unknown | 10 |

**Liquidity / Volume (0–20 pts)**
Log-scaled combination of total liquidity and total volume.
Floor $1k/$5k → ceiling $250k/$2M.

**Market Activity (0–20 pts)**
Combination of recent 24h volume, comment count, and how recently the market
was updated. A market updated in the last hour gets full recency credit; one
not touched in 3+ days gets minimal.

---

## Stack

| Package | Purpose |
|---------|---------|
| Python 3.11 | Runtime |
| `httpx` | Async HTTP with timeout/retry |
| `pydantic` | Strict data models and validation |
| `pydantic-settings` | Environment-based config |
| `fastapi` + `uvicorn` | Local REST API (server mode) |
| `rich` | Terminal tables and logging |
| `pytest` + `pytest-asyncio` | Test suite |
| `ruff` | Linting and formatting |
| `uv` | Dependency management |

---

## Install

1. Ensure Python 3.11+ is available.
2. Copy the environment file:

```powershell
Copy-Item .env.example .env
```

3. Install dependencies:

```powershell
python -m uv sync --extra dev
```

---

## Server Mode (FastAPI)

Run the full server with a background refresh loop and REST API:

```powershell
python -m uv run polybot
```

API starts on `http://127.0.0.1:8000`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service status + last error |
| GET | `/markets/top` | Top N scored markets |
| GET | `/markets/raw-count` | Event / market / score counts |
| GET | `/markets/last-refresh` | Last refresh timestamp + duration |

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/markets/top
```

---

## Tests

```powershell
python -m uv run pytest          # all 22 tests
python -m uv run pytest -v       # verbose
```

Test coverage:
- `test_gamma_client.py` — HTTP retry behavior, non-retryable errors
- `test_market_service.py` — normalization, ranking, error resilience
- `test_scoring.py` — OpportunityScorer with strong vs weak markets
- `test_scorer.py` — edge_cents, liquidity_bucket, hours_remaining, score ordering

---

## Stage 4: Guarded Live Foundation

Stage 4 uses Polymarket's official `py-clob-client` and keeps live execution heavily constrained.

Supported now:
- L1/L2 auth validation
- adaptive eligible-universe filtering and deterministic candidate ranking
- balance and allowance checks
- orderbook-backed order validation
- dry-run order construction
- one explicitly armed micro-order attempt
- hard safety guards: optional whitelist subset mode, kill switch, max notional cap

Not supported yet:
- unattended live loops
- autonomous bucket deployment
- true settlement-aware live trading

### Stage 4 commands

```powershell
# Auth + connectivity self-check
.venv\Scripts\python brain.py --live-auth-check

# Build and validate one guarded live order without sending it
.venv\Scripts\python brain.py --minutes 2 --top 5 --pages 1 --live-dry-run

# Attempt one real micro-order only if all guards pass
.venv\Scripts\python brain.py --minutes 2 --top 5 --pages 1 --live --armed
```

### Stage 4 environment variables

| Variable | Purpose |
|----------|---------|
| `POLY_CLOB_HOST` | CLOB API host, default `https://clob.polymarket.com` |
| `POLY_CHAIN_ID` | Polygon chain id, default `137` |
| `POLY_PRIVATE_KEY` | Wallet private key used by the official SDK |
| `POLY_API_KEY` | Polymarket L2 API key |
| `POLY_API_SECRET` | Polymarket L2 API secret |
| `POLY_API_PASSPHRASE` | Polymarket L2 API passphrase |
| `POLY_FUNDER` | Funder/proxy wallet address |
| `POLY_SIGNATURE_TYPE` | `0` EOA, `1` POLY_PROXY, `2` GNOSIS_SAFE |
| `LIVE_TRADING_ENABLED` | Must be `true` before any live submission is allowed |
| `LIVE_MAX_ORDER_USD` | Hard max live order notional, default `2` |
| `LIVE_MARKET_WHITELIST` | Optional comma-separated subset of allowed market ids |
| `LIVE_USE_ADAPTIVE_SELECTOR` | Use adaptive Stage 4 universe filtering and ranking |
| `LIVE_ALLOWED_UNIVERSE_TOP_N` | Max number of analyzed markets considered by the adaptive selector |
| `LIVE_MIN_TOTAL_RANK` | Minimum adaptive rank score required before execution policy allows a trade |
| `LIVE_MIN_CONFIDENCE` | Minimum Claude confidence required for live consideration |
| `LIVE_MAX_OPEN_POSITIONS` | Maximum open live orders/positions allowed at once |
| `LIVE_MAX_SAME_MARKET_EXPOSURE` | Maximum same-market live exposure allowed |
| `LIVE_COOLDOWN_SECONDS` | Minimum delay between live submissions |
| `LIVE_REQUIRE_ORDERBOOK` | Require usable orderbook metadata before live consideration |
| `LIVE_REQUIRE_TRADABLE_MARKET` | Require `accepting_orders` markets only |
| `LIVE_OPTIONAL_WHITELIST_MODE` | `subset` to narrow the adaptive universe when a whitelist is present |
| `LIVE_KILL_SWITCH` | Immediate hard block for all live submissions |

---

## Development Commands

```powershell
python -m uv run ruff check .
python -m uv run ruff format .
python -m uv run pytest
```

---

## Configuration (server mode)

Key environment variables from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `POLYBOT_GAMMA_API_BASE_URL` | `https://gamma-api.polymarket.com` | Gamma API base |
| `POLYBOT_GAMMA_EVENTS_PATH` | `/events` | Events endpoint path |
| `POLYBOT_REFRESH_INTERVAL_SECONDS` | `60` | Server refresh loop interval |
| `POLYBOT_TOP_N` | `10` | Markets shown in server mode |
| `POLYBOT_REQUEST_TIMEOUT_SECONDS` | `20.0` | Per-request timeout |
| `POLYBOT_REQUEST_MAX_RETRIES` | `3` | Retry attempts on 5xx / 429 |
| `POLYBOT_GAMMA_PAGE_LIMIT` | `100` | Events per API page |
| `POLYBOT_GAMMA_MAX_PAGES` | `25` | Max pages per refresh |
| `POLYBOT_LOG_LEVEL` | `INFO` | Log verbosity |
| `POLYBOT_API_HOST` | `127.0.0.1` | Server bind address |
| `POLYBOT_API_PORT` | `8000` | Server port |

---

## Project Layout

```
polybot/
  app/
    api/          REST endpoints
    ingestion/    Gamma API client + normalization
    models/       Pydantic schemas
    scoring/      OpportunityScorer
    utils/        terminal, safe_math, time_utils
  logs/           Timestamped JSON scan results (auto-created)
  tests/          22 pytest tests
  gamma_crawler.py   Standalone live scanner CLI
  .env.example
  Makefile
  pyproject.toml
  README.md
```

---

## Next Planned Stage

**Stage 2: Brain**

Adds richer market interpretation — LLM-assisted analysis, news context, and
a smarter signal layer — while still deferring order execution to the
intentionally separate Hands stage.
#   P O L Y B O T  
 