from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.brain_dialogue import BrainDialogueService
from app.services.live_orderbook_watcher import LiveOrderbookWatcherService
from app.services.system_power import SystemPowerService


class _FakeCLOB:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[dict[str, object], int]:
        token_id = str((params or {}).get("token_id"))
        self.calls.append({"url": url, "params": dict(params or {})})
        payload = self.payloads.get(token_id)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise RuntimeError("token not found")
        return payload, 5


def _book(
    *,
    token: str,
    condition: str,
    bid: str = "0.44",
    ask: str = "0.45",
    bid_size: str = "1200",
    ask_size: str = "1300",
    bids: bool = True,
    asks: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {"market": condition, "asset_id": token}
    payload["bids"] = [{"price": bid, "size": bid_size}] if bids else []
    payload["asks"] = [{"price": ask, "size": ask_size}] if asks else []
    return payload


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "live_orderbook_watcher_traces",
            "live_orderbook_watcher_runs",
            "live_orderbook_watchlist",
            "fresh_candidate_seeds",
            "trusted_orderbook_evidence_links",
            "paper_eligibility_candidates",
            "orderbook_snapshots",
            "market_snapshots_v2",
            "markets_v2",
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "live_orders",
            "orders_v2",
            "fills_v2",
            "positions",
            "brain_dialogue_events",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="live-orderbook-watcher-prepare")


def _seed_market_seed(
    suffix: str,
    *,
    side: str = "YES",
    status: str = "BOOK_VERIFIED",
    closed: bool = False,
    active: bool = True,
    accepting_orders: bool = True,
    expected_token: str | None = None,
) -> dict[str, str]:
    market_id = f"market-{suffix}"
    condition_id = f"condition-{suffix}"
    base = abs(hash(suffix)) % 10_000_000
    yes = f"100000000000000000000000000000000000000000000000000000000000{base:07d}"
    no = f"200000000000000000000000000000000000000000000000000000000000{base:07d}"
    expected = expected_token if expected_token is not None else (yes if side == "YES" else no)
    seed_id = f"seed-{suffix}"
    raw = {
        "id": market_id,
        "conditionId": condition_id,
        "question": f"Question {suffix}?",
        "slug": f"slug-{suffix}",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": [yes, no],
        "closed": closed,
        "archived": False,
        "active": active,
        "acceptingOrders": accepting_orders,
    }
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                accepting_orders, closed, archived, active, raw_market_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)
            """,
            (market_id, condition_id, raw["question"], raw["slug"], yes, no, accepting_orders, closed, active, Jsonb(raw)),
        )
        conn.execute(
            """
            INSERT INTO fresh_candidate_seeds (
                seed_id, market_id, condition_id, slug, question, side,
                expected_token_id, yes_token_id, no_token_id, source, status,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'test', %s, '{}'::jsonb)
            """,
            (seed_id, market_id, condition_id, raw["slug"], raw["question"], side, expected, yes, no, status),
        )
    return {
        "seed_id": seed_id,
        "market_id": market_id,
        "condition_id": condition_id,
        "side": side,
        "yes": yes,
        "no": no,
        "expected": expected,
    }


def _insert_watch(ids: dict[str, str], *, last_spread: float | None = None, last_liquidity: float | None = None) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO live_orderbook_watchlist (
                watch_id, market_id, condition_id, side, token_id, source_type,
                source_id, priority, status, last_best_bid, last_best_ask,
                last_spread, last_liquidity_score, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, 'test', %s, 1, 'ACTIVE', 0.44, 0.45, %s, %s, '{}'::jsonb)
            """,
            (
                f"live_watch_{ids['market_id']}_{ids['side']}_{ids['expected']}",
                ids["market_id"],
                ids["condition_id"],
                ids["side"],
                ids["expected"],
                ids["seed_id"],
                last_spread,
                last_liquidity,
            ),
        )


def _count(table: str, where: str = "true") -> int:
    with DatabaseConnectionFactory().connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def _latest_event(event_type: str) -> dict[str, Any]:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM neural_events
            WHERE source_component='Live Token / Orderbook Watcher'
              AND event_type=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (event_type,),
        ).fetchone()
        return dict(row)


def test_watchlist_created_from_book_verified_seed_and_uses_expected_token(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("verified")
    fake = _FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])})

    result = LiveOrderbookWatcherService(clob_client=fake).run(limit=5, max_seconds=10)

    assert result["watch_items_checked"] == 1
    assert _count("live_orderbook_watchlist") == 1
    assert fake.calls == [{"url": "https://clob.polymarket.com/book", "params": {"token_id": ids["expected"]}}]


def test_stale_or_closed_market_and_missing_token_are_not_added(postgres_test_schema) -> None:
    _prepare()
    _seed_market_seed("closed", closed=True, active=False)
    _seed_market_seed("missing-token", expected_token="")

    result = LiveOrderbookWatcherService(clob_client=_FakeCLOB({})).run(limit=5, max_seconds=10)

    assert result["watch_items_checked"] == 0
    assert _count("live_orderbook_watchlist") == 0


def test_system_off_blocks_watcher_run(postgres_test_schema) -> None:
    _prepare()
    _seed_market_seed("off")
    SystemPowerService().turn_off(actor="test", reason="watcher-off")

    result = LiveOrderbookWatcherService(clob_client=_FakeCLOB({})).run(limit=1)

    assert result["status"] == "BLOCKED"
    assert result["blocker_counts"] == {"SYSTEM_POWER_OFF": 1}
    assert _count("live_orderbook_watchlist") == 0


def test_valid_book_creates_snapshot_orderbook_refreshed_event_mesh_and_awareness(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("refresh")
    service = LiveOrderbookWatcherService(clob_client=_FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])}))

    result = service.run(limit=1, max_seconds=10)

    event = _latest_event("ORDERBOOK_REFRESHED")
    assert result["orderbooks_refreshed"] == 1
    assert result["snapshots_created"] == 1
    assert _count("orderbook_snapshots", "source='live_orderbook_watcher'") == 1
    assert event["payload_json"]["market_id"] == ids["market_id"]
    assert event["payload_json"]["condition_id"] == ids["condition_id"]
    assert event["payload_json"]["token_id"] == ids["expected"]
    assert event["payload_json"]["side"] == ids["side"]
    assert event["payload_json"]["snapshot_id"] is not None
    assert _count("mesh_session_events", "source_component='Live Token / Orderbook Watcher'") >= 1
    assert _count("mesh_awareness_sources", "source_component='Live Token / Orderbook Watcher' AND source_domain='ORDERBOOK'") >= 1


def test_spread_and_liquidity_change_events_publish_when_threshold_crossed(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("changed")
    _insert_watch(ids, last_spread=0.001, last_liquidity=0.1)
    payload = _book(
        token=ids["expected"],
        condition=ids["condition_id"],
        bid="0.40",
        ask="0.46",
        bid_size="2500",
        ask_size="2500",
    )

    result = LiveOrderbookWatcherService(clob_client=_FakeCLOB({ids["expected"]: payload})).run(limit=1, max_seconds=10)

    assert result["spread_changed_count"] == 1
    assert result["liquidity_changed_count"] == 1
    assert _latest_event("SPREAD_CHANGED")["payload_json"]["spread_delta"] is not None
    assert _latest_event("LIQUIDITY_CHANGED")["payload_json"]["liquidity_delta"] is not None


def test_token_book_unavailable_after_prior_valid_book_fails(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("unavailable")
    _insert_watch(ids, last_spread=0.01, last_liquidity=0.8)

    result = LiveOrderbookWatcherService(clob_client=_FakeCLOB({})).run(limit=1, max_seconds=10)

    event = _latest_event("TOKEN_BOOK_UNAVAILABLE")
    assert result["token_unavailable_count"] == 1
    assert event["payload_json"]["reason"] == "TOKEN_NOT_FOUND"
    assert _count("live_orderbook_watchlist", "status='TOKEN_UNAVAILABLE'") == 1


def test_market_resolved_event_when_market_no_longer_tradable(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("resolved", closed=True, active=False)
    _insert_watch(ids)

    result = LiveOrderbookWatcherService(clob_client=_FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])})).run(limit=1)

    assert result["market_resolved_count"] == 1
    assert _latest_event("MARKET_RESOLVED")["payload_json"]["reason"] == "MARKET_RESOLVED"


def test_dashboard_route_returns_truth_and_dialogue_materializes(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("dashboard")
    LiveOrderbookWatcherService(clob_client=_FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])})).run(limit=1)

    payload = LiveOrderbookWatcherService().get_dashboard_summary(limit=5)
    dialogue = BrainDialogueService().materialize_recent(limit_per_source=10)
    feed = BrainDialogueService().list_events(limit=10, component="Live Orderbook Watcher")

    assert payload["mock_data"] is False
    assert payload["watchlist_count"] == 1
    assert dialogue["status"] == "OK"
    assert feed["events"]


def test_no_trading_mutation_from_watcher(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_market_seed("safety")
    before = {
        "paper_intents": _count("paper_intents"),
        "paper_orders": _count("paper_orders"),
        "paper_fills": _count("paper_fills"),
        "paper_positions": _count("paper_positions"),
        "live_orders": _count("live_orders"),
        "orders_v2": _count("orders_v2"),
        "fills_v2": _count("fills_v2"),
        "positions": _count("positions"),
    }

    LiveOrderbookWatcherService(clob_client=_FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])})).run(limit=1)

    after = {key: _count(key if key != "positions" else "positions") for key in before}
    assert after == before
