from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.event_mesh_proof import EventMeshProofService
from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository

_ORDERBOOK_TEST_SPEC = spec_from_file_location("_phase7_orderbook_test_helpers", Path(__file__).with_name("test_orderbook_price_readiness.py"))
assert _ORDERBOOK_TEST_SPEC and _ORDERBOOK_TEST_SPEC.loader
_ORDERBOOK_TEST_HELPERS = module_from_spec(_ORDERBOOK_TEST_SPEC)
_ORDERBOOK_TEST_SPEC.loader.exec_module(_ORDERBOOK_TEST_HELPERS)

_artifact_counts = _ORDERBOOK_TEST_HELPERS._artifact_counts


def _make_snapshot(market_id: str = "mesh-market", token_id: str = "mesh-token", side: str = "YES"):
    return OrderbookSnapshotter().normalize_orderbook(
        {
            "asset_id": token_id,
            "market": "mesh-condition",
            "bids": [{"price": "0.40", "size": "120"}],
            "asks": [{"price": "0.42", "size": "110"}],
        },
        market_id=market_id,
        token_id=token_id,
        side=side,
        source="test_event_mesh_proof",
        correlation_id="mesh-proof-test",
        collected_at=datetime.now(UTC),
    )


def _seed_five_opinion_sources(market_id: str, token_id: str, side: str = "YES") -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, currency, initial_balance, current_balance,
                available_balance, locked_balance, open_exposure, max_open_positions, status, updated_at
            )
            VALUES ('paper_default', 'Default Paper Account', 'USD', 1000, 1000, 1000, 0, 0, 3, 'ACTIVE', %s)
            ON CONFLICT (account_id) DO UPDATE SET available_balance = 1000, updated_at = EXCLUDED.updated_at
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO lifecycle_governance_decisions (
                decision_id, subject_type, subject_id, market_id, side, token_id,
                actionability_class, allow_paper_intent, allow_paper_execution,
                critical_blockers_json, reason, created_at
            )
            VALUES (%s, 'PAPER_CANDIDATE', %s, %s, %s, %s,
                'ACTIONABLE_SMALL_PAPER', true, true, %s, 'test event mesh lifecycle source', %s)
            """,
            (
                f"mesh-proof-lifecycle-{market_id}",
                f"mesh-proof-candidate-{market_id}",
                market_id,
                side,
                token_id,
                Jsonb([]),
                now,
            ),
        )


def test_orderbook_snapshot_created_event_wakes_multiple_brains(postgres_test_schema) -> None:
    before_artifacts = _artifact_counts()
    snapshot = _make_snapshot()
    _seed_five_opinion_sources(snapshot.market_id, snapshot.token_id, snapshot.side)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        OrderbookSnapshotRepository().append_snapshot(conn, snapshot)

    payload = EventMeshProofService(connection_factory=DatabaseConnectionFactory()).list_proofs(limit=5)

    assert payload["mesh_proof_state"] == "PROVEN"
    assert payload["counts"]["events_seen"] >= 1
    assert payload["counts"]["events_with_liquidity_reaction"] >= 1
    assert payload["counts"]["events_with_risk_reaction"] >= 1
    assert payload["counts"]["events_with_exit_reaction"] >= 1
    assert payload["counts"]["events_with_capital_reaction"] >= 1
    assert payload["counts"]["events_with_lifecycle_reaction"] >= 1
    assert payload["counts"]["events_with_all_five_reactions"] >= 1
    assert payload["counts"]["events_with_coordinator_trace"] >= 1
    assert payload["counts"]["fully_proven_events"] >= 1

    item = payload["items"][0]
    assert item["event_type"] == "orderbook.snapshot.created"
    assert item["event_delivery_state"] == "DELIVERED"
    assert {reaction["brain"] for reaction in item["brain_reactions"]} >= {"liquidity", "risk", "exit", "capital", "lifecycle"}
    assert item["coordinator"]["state"] == "DECISION_CREATED"
    assert item["coordinator"]["decision"] == "PRICE_READY"
    assert _artifact_counts() == before_artifacts


def test_event_mesh_proof_endpoint_returns_trace(postgres_test_schema) -> None:
    snapshot = _make_snapshot(market_id="mesh-api-market", token_id="mesh-api-token")
    _seed_five_opinion_sources(snapshot.market_id, snapshot.token_id, snapshot.side)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        OrderbookSnapshotRepository().append_snapshot(conn, snapshot)

    app = FastAPI()
    app.include_router(create_router())
    response = TestClient(app).get("/dashboard/api/v2/control/event-mesh-proof")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["mesh_proof_state"] == "PROVEN"
    assert payload["data"]["counts"]["fully_proven_events"] >= 1
    assert payload["data"]["items"][0]["correlation_id"]


def test_missing_consumer_is_not_fake_proof(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, mode, occurred_at, payload_json, metadata_json
            )
            VALUES (
                'mesh-proof-missing-event', 'orderbook.snapshot.created',
                'orderbook_snapshot', 'missing-snapshot', 'test',
                'mesh-proof-missing-corr', 'DATA_ONLY', %s,
                '{"market_id":"missing-market"}'::jsonb, '{}'::jsonb
            )
            """,
            (now,),
        )

    payload = EventMeshProofService(connection_factory=DatabaseConnectionFactory()).list_proofs(
        correlation_id="mesh-proof-missing-corr",
    )

    assert payload["mesh_proof_state"] == "MISSING"
    assert payload["items"][0]["event_delivery_state"] == "NO_CONSUMERS"
    assert "NO_CONSUMERS" in payload["items"][0]["blockers"]


def test_failed_consumer_is_recorded(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, mode, occurred_at, payload_json, metadata_json
            )
            VALUES (
                'mesh-proof-failed-event', 'orderbook.snapshot.created',
                'orderbook_snapshot', 'failed-snapshot', 'test',
                'mesh-proof-failed-corr', 'DATA_ONLY', %s,
                '{"market_id":"failed-market"}'::jsonb, '{}'::jsonb
            )
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO event_delivery_attempts (
                event_id, consumer_name, attempt_number, status, error_message, finished_at, metadata_json
            )
            VALUES ('mesh-proof-failed-event', 'mesh_proof_liquidity_brain', 1, 'FAILED', 'synthetic failure', now(), '{}'::jsonb)
            """
        )

    payload = EventMeshProofService(connection_factory=DatabaseConnectionFactory()).list_proofs(
        correlation_id="mesh-proof-failed-corr",
    )

    assert payload["mesh_proof_state"] == "BLOCKED"
    assert payload["items"][0]["event_delivery_state"] == "CONSUMER_FAILED"
    assert "CONSUMER_FAILED" in payload["items"][0]["blockers"]
