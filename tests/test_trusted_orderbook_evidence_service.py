from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.system_power import SystemPowerService
from app.services.trusted_orderbook import TrustedOrderbookEvidenceService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "trusted_orderbook_evidence_runs",
            "trusted_orderbook_evidence_links",
            "paper_eligibility_candidates",
            "signal_market_links",
            "orderbook_snapshots",
            "markets_v2",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="trusted_orderbook_prepare")


def _seed_candidate(
    suffix: str,
    *,
    side: str = "YES",
    orderbook_token: str | None = None,
    insert_orderbook: bool = True,
    collected_at: datetime | None = None,
    best_bid: float | None = 0.45,
    best_ask: float | None = 0.49,
    mid_price: float | None = 0.47,
    spread: float | None = 0.04,
    link_confidence: float = 0.95,
    review_required: bool = False,
) -> dict[str, object]:
    market_id = f"market-{suffix}"
    signal_id = f"signal-{suffix}"
    eligibility_id = f"eligibility-{suffix}"
    yes_token = f"yes-{suffix}"
    no_token = f"no-{suffix}"
    expected_token = yes_token if side == "YES" else no_token
    token = orderbook_token if orderbook_token is not None else expected_token
    collected = collected_at or datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, slug, yes_token_id, no_token_id)
            VALUES (%s, 'Trusted orderbook test?', %s, %s, %s)
            """,
            (market_id, market_id, yes_token, no_token),
        )
        conn.execute(
            """
            INSERT INTO neuron_signals (
                signal_id, neuron, event_type, source_name, market_id,
                confidence, strength, evidence_json, status, raw_payload_ref,
                correlation_id, created_at, updated_at
            )
            VALUES (%s, 'market', 'trusted_orderbook_test', 'test', %s, %s, 0.8, %s, 'ACTIVE', %s, %s, now(), now())
            """,
            (
                signal_id,
                market_id,
                link_confidence,
                Jsonb({"details": {"sample_token_id": expected_token}}),
                f"raw-{suffix}",
                f"corr-{suffix}",
            ),
        )
        conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_type, link_status, confidence, reason,
                created_by, link_confidence, link_reason, link_evidence_json,
                link_method, linked_by, is_auto_linked, is_review_required,
                is_runtime_link, source_signal_id, matched_side
            )
            VALUES (
                %s, %s, 'test', 'confirmed', %s, 'test', 'test', %s, 'test',
                %s, 'explicit_market_id', 'test', true, %s, true, %s, %s
            )
            """,
            (
                signal_id,
                market_id,
                link_confidence,
                link_confidence,
                Jsonb({"matched_side": side, "source": "test"}),
                review_required,
                signal_id,
                side,
            ),
        )
        if insert_orderbook:
            conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                    mid_price, spread, liquidity_score, source, snapshot_status, is_stale,
                    collected_at, snapshot_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0.8, 'CLOB', 'OK', false, %s, %s, %s)
                """,
                (
                    f"book-{suffix}",
                    market_id,
                    token,
                    side,
                    best_bid,
                    best_ask,
                    mid_price,
                    spread,
                    collected,
                    collected,
                    collected,
                ),
            )
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                signal_ids, market_id, side, status, eligibility_score,
                eligibility_blockers, missing_requirements, evidence,
                orderbook_snapshot_id, link_confidence, lineage_trusted,
                risk_approved, exit_ready, not_dry_run, is_runtime_generated,
                is_dry_run_generated
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, 'BLOCKED', 0,
                %s, %s, '{}'::jsonb, NULL, %s, true, false, false, true, true, false
            )
            """,
            (
                eligibility_id,
                f"thesis-{suffix}",
                f"risk-{suffix}",
                f"exit-{suffix}",
                Jsonb([signal_id]),
                market_id,
                side,
                Jsonb(["MISSING_TRUSTED_ORDERBOOK", "MISSING_FRESH_ORDERBOOK"]),
                Jsonb(["MISSING_TRUSTED_ORDERBOOK", "MISSING_FRESH_ORDERBOOK"]),
                link_confidence,
            ),
        )
    return {
        "market_id": market_id,
        "signal_id": signal_id,
        "eligibility_id": eligibility_id,
        "expected_token": expected_token,
    }


class _FakeCLOB:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[dict[str, object] | None, int]:
        self.calls.append({"url": url, "params": dict(params or {})})
        if self.payload is None:
            raise RuntimeError("No orderbook exists for the requested token id")
        return self.payload, 12


def _book_payload() -> dict[str, object]:
    return {
        "bids": [{"price": "0.45", "size": "1200"}],
        "asks": [{"price": "0.49", "size": "1300"}],
    }


def _link_for(candidate_id: str) -> dict[str, object]:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(conn.execute(
            "SELECT * FROM trusted_orderbook_evidence_links WHERE candidate_id = %s",
            (candidate_id,),
        ).fetchone())


def test_system_off_blocks_trusted_orderbook_resolver(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("off")
    SystemPowerService().turn_off(actor="test", reason="trusted_orderbook_off")

    result = TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-off", limit=10)

    assert result["status"] == "BLOCKED"
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM trusted_orderbook_evidence_links").fetchone()["count"] == 0


def test_yes_candidate_with_yes_token_orderbook_becomes_trusted(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("yes", side="YES")

    result = TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-yes", limit=10)

    assert result["status"] == "OK"
    assert result["trusted_matches_created"] == 1
    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is True
    assert link["expected_token_id"] == ids["expected_token"]
    assert link["trust_status"] == "TRUSTED"


def test_candidate_without_snapshot_fetches_real_clob_book_and_becomes_trusted(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("fetch", side="YES", insert_orderbook=False)
    clob = _FakeCLOB(_book_payload())

    result = TrustedOrderbookEvidenceService(http_client=clob).resolve(
        cycle_id="trusted-fetch",
        limit=10,
        refresh_orderbooks=True,
    )

    assert result["status"] == "OK"
    assert result["trusted_matches_created"] == 1
    assert result["orderbook_snapshots_created"] == 1
    assert clob.calls[0]["params"]["token_id"] == ids["expected_token"]
    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is True
    assert link["orderbook_token_id"] == ids["expected_token"]


def test_no_candidate_with_no_token_orderbook_becomes_trusted(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("no", side="NO")

    TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-no", limit=10)

    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is True
    assert link["expected_token_id"] == ids["expected_token"]


def test_token_mismatch_is_rejected(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("mismatch", side="YES", orderbook_token="wrong-token")

    result = TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-mismatch", limit=10)

    assert result["trusted_matches_created"] == 0
    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is False
    assert link["trust_reason"] == "TOKEN_SIDE_MISMATCH"


def test_stale_snapshot_is_rejected(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("stale", collected_at=datetime.now(UTC) - timedelta(minutes=20))

    TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-stale", limit=10)

    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is False
    assert link["trust_reason"] == "ORDERBOOK_STALE"


def test_stale_snapshot_triggers_clob_refresh_when_enabled(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("stale-refresh", collected_at=datetime.now(UTC) - timedelta(minutes=20))
    clob = _FakeCLOB(_book_payload())

    result = TrustedOrderbookEvidenceService(http_client=clob).resolve(
        cycle_id="trusted-stale-refresh",
        limit=10,
        refresh_orderbooks=True,
    )

    assert result["trusted_matches_created"] == 1
    assert result["orderbook_snapshots_created"] == 1
    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is True
    assert link["trust_reason"] == "TRUSTED_ORDERBOOK"


def test_clob_no_book_is_recorded_precisely_without_fake_snapshot(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("clob-empty", side="YES", insert_orderbook=False)
    clob = _FakeCLOB(None)

    result = TrustedOrderbookEvidenceService(http_client=clob).resolve(
        cycle_id="trusted-clob-empty",
        limit=10,
        refresh_orderbooks=True,
    )

    assert result["trusted_matches_created"] == 0
    assert result["missing_orderbook_count"] == 1
    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is False
    assert link["trust_reason"] == "CLOB_NO_BOOK"
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots").fetchone()["count"]
    assert count == 0


def test_stale_snapshot_refresh_failure_records_clob_no_book(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate(
        "stale-clob-empty",
        collected_at=datetime.now(UTC) - timedelta(minutes=20),
    )
    clob = _FakeCLOB(None)

    result = TrustedOrderbookEvidenceService(http_client=clob).resolve(
        cycle_id="trusted-stale-clob-empty",
        limit=10,
        refresh_orderbooks=True,
    )

    assert result["trusted_matches_created"] == 0
    assert result["missing_orderbook_count"] == 1
    assert result["stale_count"] == 0
    assert result["orderbook_snapshots_created"] == 0
    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is False
    assert link["trust_reason"] == "CLOB_NO_BOOK"
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots").fetchone()["count"]
    assert count == 1


def test_missing_mid_price_is_computed_from_bid_ask(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("mid", mid_price=None)

    TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-mid", limit=10)

    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is True
    assert float(link["mid_price"]) == 0.47


def test_weak_binding_is_rejected(postgres_test_schema) -> None:
    _prepare()
    ids = _seed_candidate("weak", link_confidence=0.4)

    TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-weak", limit=10)

    link = _link_for(str(ids["eligibility_id"]))
    assert link["trusted"] is False
    assert link["trust_reason"] == "WEAK_BINDING"
