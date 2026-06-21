"""
app/stage2/ws_listener.py — Polymarket CLOB WebSocket listener.

Subscribes to real-time price-change events for a set of markets and:
  - Logs every event to logs/ws_events.jsonl
  - Maintains an in-memory dict of latest prices per token_id
  - Exposes an asyncio.Event that fires whenever any price changes

WebSocket endpoint: wss://ws-subscriptions-clob.polymarket.com/ws/market
Subscription message:  {"assets_ids": [...token_ids...], "type": "market"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import websockets
from websockets.exceptions import ConnectionClosed

from app.models.market import NormalizedMarket

CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
LOGS_DIR = Path("logs")
WS_LOG_FILE = LOGS_DIR / "ws_events.jsonl"

logger = logging.getLogger(__name__)


def extract_token_ids(market: NormalizedMarket) -> list[str]:
    """Return the clobTokenIds for this market (YES + NO token IDs as decimal strings)."""
    raw = market.raw_market
    clob_ids = raw.get("clobTokenIds")
    if not clob_ids:
        return []
    if isinstance(clob_ids, str):
        try:
            clob_ids = json.loads(clob_ids)
        except json.JSONDecodeError:
            return []
    if isinstance(clob_ids, list):
        return [str(tid) for tid in clob_ids if tid]
    return []


class PriceUpdate:
    __slots__ = ("token_id", "price", "side", "size", "timestamp", "raw")

    def __init__(self, token_id: str, price: float, side: str, size: float,
                 timestamp: str, raw: dict):
        self.token_id = token_id
        self.price = price
        self.side = side
        self.size = size
        self.timestamp = timestamp
        self.raw = raw

    def __repr__(self) -> str:
        return f"PriceUpdate(token={self.token_id[:12]}... price={self.price} {self.side})"


class WSListener:
    """
    Connects to the Polymarket CLOB WebSocket and subscribes to a set of markets.

    Usage:
        listener = WSListener(token_id_to_market_name)
        await listener.start()       # non-blocking, runs in background
        await listener.stop()
    """

    def __init__(
        self,
        token_id_to_name: dict[str, str],
        on_price_update: Callable[[PriceUpdate], None] | None = None,
    ):
        self._token_ids: list[str] = list(token_id_to_name.keys())
        self._id_to_name: dict[str, str] = token_id_to_name
        self._on_update = on_price_update
        self._latest_prices: dict[str, float] = {}
        self._change_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False
        self._event_count = 0

        LOGS_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the listener as a background asyncio task."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="ws_listener")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def latest_prices(self) -> dict[str, float]:
        return dict(self._latest_prices)

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def change_event(self) -> asyncio.Event:
        return self._change_event

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Reconnect loop — retries on any connection error."""
        backoff = 2
        while self._running:
            try:
                await self._connect_and_listen()
                backoff = 2  # reset on clean exit
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("ws_reconnect error=%s backoff=%ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect_and_listen(self) -> None:
        if not self._token_ids:
            logger.warning("ws_listener: no token IDs — skipping WS connection")
            return

        logger.info("ws_connecting url=%s tokens=%s", CLOB_WS_URL, len(self._token_ids))
        async with websockets.connect(
            CLOB_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            # Subscribe to all token IDs
            sub_msg = json.dumps({"assets_ids": self._token_ids, "type": "market"})
            await ws.send(sub_msg)
            logger.info("ws_subscribed tokens=%s", len(self._token_ids))

            async for raw_msg in ws:
                if not self._running:
                    break
                try:
                    self._handle_message(raw_msg)
                except Exception as exc:
                    logger.debug("ws_parse_error err=%s msg=%s", exc, raw_msg[:120])

    def _handle_message(self, raw_msg: str) -> None:
        # Messages can be a single dict or a list of dicts
        try:
            payload = json.loads(raw_msg)
        except json.JSONDecodeError:
            return

        events = payload if isinstance(payload, list) else [payload]
        for ev in events:
            if not isinstance(ev, dict):
                continue
            self._process_event(ev)

    def _process_event(self, ev: dict) -> None:
        event_type = ev.get("event_type") or ev.get("type") or "unknown"
        asset_id = ev.get("asset_id", "")
        price_str = ev.get("price") or ev.get("outcome_price")

        if not asset_id or price_str is None:
            return

        try:
            price = float(price_str)
        except (TypeError, ValueError):
            return

        side = ev.get("side", "")
        size_str = ev.get("size") or ev.get("amount") or "0"
        try:
            size = float(size_str)
        except (TypeError, ValueError):
            size = 0.0

        ts = ev.get("timestamp") or datetime.now(UTC).isoformat()

        update = PriceUpdate(
            token_id=asset_id,
            price=price,
            side=side,
            size=size,
            timestamp=str(ts),
            raw=ev,
        )

        # Update in-memory price
        self._latest_prices[asset_id] = price
        self._event_count += 1
        self._change_event.set()
        self._change_event.clear()

        # Log to JSONL
        self._write_log(event_type, asset_id, price, side, size, ts)

        # Callback
        if self._on_update:
            try:
                self._on_update(update)
            except Exception as exc:
                logger.debug("ws_callback_error err=%s", exc)

    def _write_log(self, event_type: str, asset_id: str, price: float,
                   side: str, size: float, timestamp: str) -> None:
        name = self._id_to_name.get(asset_id, asset_id[:16] + "...")
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "asset_id": asset_id,
            "market_name": name,
            "price": price,
            "side": side,
            "size": size,
            "timestamp": timestamp,
        }
        try:
            with open(WS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass
