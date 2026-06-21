import json
import time
from pathlib import Path
from typing import Any

import urllib.request


GAMMA_URL = (
    "https://gamma-api.polymarket.com/events"
    "?active=true&closed=false&limit=5&order=volume_24hr&ascending=false"
)

CLOB_BOOK_URL = "https://clob.polymarket.com/book?token_id={token_id}"

OUT_DIR = Path("run_reports")
OUT_DIR.mkdir(exist_ok=True)

OUT_FILE = OUT_DIR / "polymarket_orderbook_smoke.json"


def fetch_json(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "POLYBOT-orderbook-smoke/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read().decode("utf-8")
        return json.loads(raw)


def parse_clob_token_ids(raw: Any) -> list[str]:
    if not raw:
        return []

    if isinstance(raw, list):
        return [str(x) for x in raw if x]

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except json.JSONDecodeError:
            return []

    return []


def best_bid_ask(book: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []

    if not bids or not asks:
        return None, None

    best_bid = max(bids, key=lambda x: float(x["price"]))
    best_ask = min(asks, key=lambda x: float(x["price"]))

    return best_bid, best_ask


def main() -> int:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    print("=== POLYMARKET ORDERBOOK SMOKE ===")
    print(f"Fetching Gamma events: {GAMMA_URL}")

    events = fetch_json(GAMMA_URL)

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for event in events:
        event_title = event.get("title", "")

        for market in event.get("markets", []) or []:
            if not (
                market.get("active") is True
                and market.get("closed") is False
                and market.get("acceptingOrders") is True
                and market.get("enableOrderBook") is True
                and market.get("clobTokenIds")
            ):
                continue

            tokens = parse_clob_token_ids(market.get("clobTokenIds"))

            for token_id in tokens:
                if len(rows) >= 10:
                    break

                try:
                    book = fetch_json(CLOB_BOOK_URL.format(token_id=token_id))
                    bids = book.get("bids") or []
                    asks = book.get("asks") or []

                    best_bid, best_ask = best_bid_ask(book)

                    if not best_bid or not best_ask:
                        continue

                    best_bid_price = float(best_bid["price"])
                    best_ask_price = float(best_ask["price"])
                    spread = best_ask_price - best_bid_price

                    row = {
                        "event_title": event_title,
                        "market_question": market.get("question"),
                        "condition_id": market.get("conditionId"),
                        "token_id": token_id,
                        "asset_id": book.get("asset_id"),
                        "book_market": book.get("market"),
                        "best_bid": best_bid_price,
                        "best_bid_size": float(best_bid["size"]),
                        "best_ask": best_ask_price,
                        "best_ask_size": float(best_ask["size"]),
                        "spread": spread,
                        "bids_count": len(bids),
                        "asks_count": len(asks),
                        "min_order_size": float(book.get("min_order_size", 0)),
                        "tick_size": float(book.get("tick_size", 0)),
                        "last_trade_price": float(book.get("last_trade_price", 0)),
                    }

                    rows.append(row)

                    print(
                        "OK:",
                        row["market_question"],
                        "| bid:",
                        row["best_bid"],
                        "| ask:",
                        row["best_ask"],
                        "| spread:",
                        row["spread"],
                    )

                except Exception as exc:
                    errors.append(
                        {
                            "token_id": token_id,
                            "error": str(exc),
                        }
                    )

            if len(rows) >= 10:
                break

        if len(rows) >= 10:
            break

    result = {
        "status": "GREEN" if rows else "RED",
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rows_count": len(rows),
        "errors_count": len(errors),
        "rows": rows,
        "errors": errors,
    }

    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Saved: {OUT_FILE}")
    print(f"Rows: {len(rows)}")
    print(f"Errors: {len(errors)}")

    if not rows:
        print("RED: No usable orderbooks found.")
        return 1

    print("GREEN: Polymarket Gamma → CLOB /book smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
