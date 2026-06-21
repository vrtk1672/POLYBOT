from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService
from app.services.clob_token_book_verification import ClobTokenBookVerificationService
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


class _FakeGamma:
    def __init__(self, markets: list[dict[str, Any]]) -> None:
        self.markets = markets
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[list[dict[str, Any]], int]:
        self.calls.append({"url": url, "params": dict(params or {})})
        return [{"markets": self.markets}], 5


def _book(*, token: str, condition: str = "condition-1", bid: str = "0.44", ask: str = "0.45", bids: bool = True, asks: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {"market": condition, "asset_id": token}
    if bids:
        payload["bids"] = [{"price": bid, "size": "1500"}]
    else:
        payload["bids"] = []
    if asks:
        payload["asks"] = [{"price": ask, "size": "1600"}]
    else:
        payload["asks"] = []
    return payload


def _gamma_market(suffix: str, *, market_id: str | None = None, accepting_orders: bool = True, closed: bool = False) -> dict[str, Any]:
    market_id = market_id or f"market-{suffix}"
    return {
        "id": market_id,
        "conditionId": f"condition-{suffix}",
        "question": f"Question {suffix}?",
        "slug": f"slug-{suffix}",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": [f"yes-{suffix}", f"no-{suffix}"],
        "closed": closed,
        "archived": False,
        "active": not closed,
        "acceptingOrders": accepting_orders,
    }


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "clob_token_book_verification_traces",
            "clob_token_book_verification_runs",
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
    SystemPowerService().turn_on(actor="test", reason="clob-book-verification-prepare")


def _seed_fresh_candidate(
    suffix: str,
    *,
    side: str = "YES",
    identity_status: str = "FRESH_VERIFIED",
    closed: bool = False,
    accepting_orders: bool = True,
) -> dict[str, str]:
    market_id = f"market-{suffix}"
    condition_id = f"condition-{suffix}"
    yes = f"yes-{suffix}"
    no = f"no-{suffix}"
    expected = yes if side == "YES" else no
    candidate_id = f"eligibility-{suffix}"
    raw = _gamma_market(suffix, market_id=market_id, accepting_orders=accepting_orders, closed=closed)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                accepting_orders, closed, archived, active, raw_market_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)
            """,
            (market_id, condition_id, raw["question"], raw["slug"], yes, no, accepting_orders, closed, not closed, Jsonb(raw)),
        )
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                signal_ids, market_id, side, status, eligibility_score,
                eligibility_blockers, missing_requirements, evidence,
                link_confidence, lineage_trusted, risk_approved, exit_ready,
                not_dry_run, is_runtime_generated, is_dry_run_generated,
                identity_status, identity_verified_at, identity_source,
                expected_token_id
            )
            VALUES (
                %s, %s, %s, %s, '[]'::jsonb, %s, %s, 'BLOCKED', 0,
                %s, %s, '{}'::jsonb, 0.95, true, false, false,
                true, true, false, %s, now(), 'test', %s
            )
            """,
            (
                candidate_id,
                f"thesis-{suffix}",
                f"risk-{suffix}",
                f"exit-{suffix}",
                market_id,
                side,
                Jsonb(["MISSING_FRESH_ORDERBOOK"]),
                Jsonb(["MISSING_FRESH_ORDERBOOK"]),
                identity_status,
                expected,
            ),
        )
    return {"candidate_id": candidate_id, "market_id": market_id, "condition_id": condition_id, "yes": yes, "no": no, "expected": expected}


def _latest_trace(identifier: str) -> dict[str, Any]:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM clob_token_book_verification_traces
            WHERE candidate_id=%s OR seed_id=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (identifier, identifier),
        ).fetchone()
        return dict(row)


def test_only_fresh_verified_candidates_are_sent_to_clob_and_stale_skipped(postgres_test_schema) -> None:
    _prepare()
    fresh = _seed_fresh_candidate("fresh")
    stale = _seed_fresh_candidate("stale", identity_status="STALE_MARKET")
    fake = _FakeCLOB({fresh["expected"]: _book(token=fresh["expected"], condition=fresh["condition_id"])})

    result = ClobTokenBookVerificationService(clob_client=fake, gamma_client=_FakeGamma([])).run_verification(limit=5, seed_threshold=0, seed_limit=0)

    assert result["fresh_verified_candidates"] == 1
    assert fake.calls == [{"url": "https://clob.polymarket.com/book", "params": {"token_id": fresh["expected"]}}]
    assert _latest_trace(stale["candidate_id"])["rejection_reason"] == "STALE_MARKET"


def test_expected_token_id_is_used_and_valid_book_creates_snapshot_and_trusted_link(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_fresh_candidate("valid", side="NO")

    result = ClobTokenBookVerificationService(
        clob_client=_FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])}),
        gamma_client=_FakeGamma([]),
    ).run_verification(limit=1, seed_threshold=0, seed_limit=0)

    trace = _latest_trace(ids["candidate_id"])
    assert result["clob_books_verified"] == 1
    assert result["snapshots_created"] == 1
    assert result["trusted_links_created"] == 1
    assert trace["expected_token_id"] == ids["no"]
    assert trace["snapshot_id"] is not None
    assert trace["trust_link_id"] == f"trusted_orderbook_{ids['candidate_id']}"


def test_asset_condition_and_empty_books_are_rejected(postgres_test_schema) -> None:
    _prepare()
    asset = _seed_fresh_candidate("asset")
    condition = _seed_fresh_candidate("condition")
    empty = _seed_fresh_candidate("empty")

    service = ClobTokenBookVerificationService(
        clob_client=_FakeCLOB({
            asset["expected"]: _book(token="wrong-token", condition=asset["condition_id"]),
            condition["expected"]: _book(token=condition["expected"], condition="other-condition"),
            empty["expected"]: _book(token=empty["expected"], condition=empty["condition_id"], bids=False),
        }),
        gamma_client=_FakeGamma([]),
    )
    service.run_verification(limit=3, seed_threshold=0, seed_limit=0)

    assert _latest_trace(asset["candidate_id"])["rejection_reason"] == "ASSET_ID_MISMATCH"
    assert _latest_trace(condition["candidate_id"])["rejection_reason"] == "CONDITION_ID_MISMATCH"
    assert _latest_trace(empty["candidate_id"])["rejection_reason"] == "EMPTY_BIDS"


def test_token_not_found_and_system_off_block_are_precise(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_fresh_candidate("not-found")
    ClobTokenBookVerificationService(clob_client=_FakeCLOB({}), gamma_client=_FakeGamma([])).run_verification(limit=1, seed_threshold=0, seed_limit=0)
    assert _latest_trace(ids["candidate_id"])["rejection_reason"] == "TOKEN_NOT_FOUND"

    SystemPowerService().turn_off(actor="test", reason="clob-off")
    result = ClobTokenBookVerificationService(clob_client=_FakeCLOB({}), gamma_client=_FakeGamma([])).run_verification(limit=1, seed_threshold=0, seed_limit=0)
    assert result["status"] == "BLOCKED"
    assert result["blocker_counts"] == {"SYSTEM_POWER_OFF": 1}


def test_fresh_current_gamma_seed_stays_out_of_paper_path_and_can_verify_book(postgres_test_schema) -> None:
    _prepare()
    market = _gamma_market("seed")
    yes = "yes-seed"
    no = "no-seed"

    result = ClobTokenBookVerificationService(
        clob_client=_FakeCLOB({
            yes: _book(token=yes, condition="condition-seed"),
            no: _book(token=no, condition="condition-seed", bid="0.55", ask="0.56"),
        }),
        gamma_client=_FakeGamma([market]),
    ).run_verification(limit=1, seed_threshold=5, seed_limit=2, verify_seeds=True)

    with DatabaseConnectionFactory().connect() as conn:
        seeds = conn.execute("SELECT COUNT(*) AS count FROM fresh_candidate_seeds").fetchone()["count"]
        paper_candidates = conn.execute("SELECT COUNT(*) AS count FROM paper_eligibility_candidates").fetchone()["count"]
        paper_intents = conn.execute("SELECT COUNT(*) AS count FROM paper_intents").fetchone()["count"]
    assert result["fresh_seeds_created"] == 2
    assert result["clob_books_verified"] == 2
    assert seeds == 2
    assert paper_candidates == 0
    assert paper_intents == 0


def test_seed_requires_active_open_accepting_market(postgres_test_schema) -> None:
    _prepare()

    result = ClobTokenBookVerificationService(
        clob_client=_FakeCLOB({}),
        gamma_client=_FakeGamma([
            _gamma_market("closed", closed=True),
            _gamma_market("noorders", accepting_orders=False),
            _gamma_market("good"),
        ]),
    ).run_verification(limit=1, seed_threshold=5, seed_limit=10, verify_seeds=False)

    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute("SELECT market_id, side FROM fresh_candidate_seeds ORDER BY market_id, side").fetchall()
    assert result["fresh_seeds_created"] == 2
    assert [(row["market_id"], row["side"]) for row in rows] == [("market-good", "NO"), ("market-good", "YES")]


def test_dashboard_dialogue_and_no_trading_mutation(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_fresh_candidate("dialogue")
    with DatabaseConnectionFactory().connect() as conn:
        before = {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "positions")}

    ClobTokenBookVerificationService(
        clob_client=_FakeCLOB({ids["expected"]: _book(token=ids["expected"], condition=ids["condition_id"])}),
        gamma_client=_FakeGamma([]),
    ).run_verification(cycle_id=f"clob-{uuid4().hex}", limit=1, seed_threshold=0, seed_limit=0)
    BrainDialogueService().materialize_recent(limit_per_source=5)
    dashboard = TestClient(create_app()).get("/dashboard/api/v2/clob-token-book-verification?limit=5").json()

    with DatabaseConnectionFactory().connect() as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "positions")}
        dialogue = conn.execute("SELECT human_message FROM brain_dialogue_events WHERE component='CLOB Token Book Verification' ORDER BY id DESC LIMIT 1").fetchone()
    assert dashboard["mock_data"] is False
    assert dashboard["clob_books_verified"] >= 1
    assert "Verified CLOB book" in dialogue["human_message"]
    assert after == before
