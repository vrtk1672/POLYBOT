from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository

_ORDERBOOK_TEST_SPEC = spec_from_file_location("_phase7_orderbook_test_helpers", Path(__file__).with_name("test_orderbook_price_readiness.py"))
assert _ORDERBOOK_TEST_SPEC and _ORDERBOOK_TEST_SPEC.loader
_ORDERBOOK_TEST_HELPERS = module_from_spec(_ORDERBOOK_TEST_SPEC)
_ORDERBOOK_TEST_SPEC.loader.exec_module(_ORDERBOOK_TEST_HELPERS)

_artifact_counts = _ORDERBOOK_TEST_HELPERS._artifact_counts


def _make_snapshot(market_id: str = "bundle-market", token_id: str = "bundle-token", side: str = "YES"):
    return OrderbookSnapshotter().normalize_orderbook(
        {
            "asset_id": token_id,
            "market": "bundle-condition",
            "bids": [{"price": "0.40", "size": "120"}],
            "asks": [{"price": "0.42", "size": "110"}],
        },
        market_id=market_id,
        token_id=token_id,
        side=side,
        source="test_mesh_evidence_bundle",
        correlation_id="mesh-bundle-test",
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
                'ACTIONABLE_SMALL_PAPER', true, true, '[]'::jsonb, 'test bundle lifecycle source', %s)
            """,
            (
                f"mesh-bundle-lifecycle-{market_id}",
                f"mesh-bundle-candidate-{market_id}",
                market_id,
                side,
                token_id,
                now,
            ),
        )


def test_bundle_assembled_for_orderbook_snapshot_trace(postgres_test_schema) -> None:
    before_artifacts = _artifact_counts()
    snapshot = _make_snapshot()
    _seed_five_opinion_sources(snapshot.market_id, snapshot.token_id, snapshot.side)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        OrderbookSnapshotRepository().append_snapshot(conn, snapshot)

    payload = MeshEvidenceBundleService(connection_factory=DatabaseConnectionFactory()).list_bundles(limit=5)

    assert payload["counts"]["bundles"] >= 1
    item = payload["items"][0]
    assert item["event_type"] == "orderbook.snapshot.created"
    assert item["market_id"]
    assert item["side"] == "YES"
    assert item["token_id"]
    assert item["orderbook"]["freshness_state"] == "FRESH"
    assert item["opinion_states"]["liquidity"] == "PRESENT"
    assert item["opinion_states"]["risk"] == "PRESENT"
    assert item["opinion_states"]["exit"] == "PRESENT"
    assert item["opinion_states"]["capital"] == "PRESENT"
    assert item["opinion_states"]["lifecycle"] == "PRESENT"
    assert item["opinions"]["capital"]["event_native_state"] == "EVENT_NATIVE"
    assert item["opinions"]["lifecycle"]["event_native_state"] == "EVENT_NATIVE"
    assert item["coordinator"]["decision_id"]
    assert item["coordinator"]["execution_allowed"] is False
    assert _artifact_counts() == before_artifacts


def test_bundle_endpoint_returns_counts_and_items(postgres_test_schema) -> None:
    snapshot = _make_snapshot(market_id="bundle-api-market", token_id="bundle-api-token")
    _seed_five_opinion_sources(snapshot.market_id, snapshot.token_id, snapshot.side)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        OrderbookSnapshotRepository().append_snapshot(conn, snapshot)

    app = FastAPI()
    app.include_router(create_router())
    response = TestClient(app).get("/dashboard/api/v2/control/mesh-evidence-bundles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["counts"]["bundles"] >= 1
    assert payload["data"]["items"][0]["bundle_id"]


def test_single_bundle_endpoint_returns_full_trace(postgres_test_schema) -> None:
    snapshot = _make_snapshot(market_id="bundle-single-market", token_id="bundle-single-token")
    _seed_five_opinion_sources(snapshot.market_id, snapshot.token_id, snapshot.side)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = OrderbookSnapshotRepository().append_snapshot(conn, snapshot)
    correlation_id = f"{snapshot.correlation_id}:{result.orderbook_snapshot_id}"

    app = FastAPI()
    app.include_router(create_router())
    response = TestClient(app).get(f"/dashboard/api/v2/control/mesh-evidence-bundles/{correlation_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["bundle"]["correlation_id"] == correlation_id
    assert payload["data"]["bundle"]["coordinator"]["decision_id"]


def test_conflicts_are_explicit(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    corr = "mesh-bundle-conflict-corr"
    event_id = "mesh-bundle-conflict-event"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, mode, occurred_at, payload_json, metadata_json
            )
            VALUES (
                %s, 'orderbook.snapshot.created', 'orderbook_snapshot', 'conflict-snapshot',
                'test', %s, 'DATA_ONLY', %s,
                '{"market_id":"conflict-market","side":"YES","token_id":"conflict-token","orderbook_snapshot_id":"missing"}'::jsonb,
                '{}'::jsonb
            )
            """,
            (event_id, corr, now),
        )
        for brain, blockers in (
            ("liquidity", []),
            ("risk", ["PRICE_RISK_SPREAD_TOO_WIDE"]),
            ("exit", ["EXIT_PRICE_MISSING"]),
        ):
            conn.execute(
                """
                INSERT INTO brain_outputs (
                    brain_output_id, brain, output_type, market_id, recommendation,
                    confidence, urgency, risk_flags_json, reasoning_summary, status,
                    ttl_seconds, correlation_id, generated_by, model_name, model_version,
                    raw_payload_ref, metadata_json
                )
                VALUES (%s, %s, 'WATCH', 'conflict-market', 'OBSERVE', 0.5, 0.5, %s,
                        %s, 'ACTIVE', 180, %s, 'minimal_event_mesh_proof',
                        'deterministic_mesh_proof', 'test', %s, %s)
                """,
                (
                    f"bundle_conflict_{brain}",
                    brain,
                    Jsonb(blockers),
                    f"{brain} synthetic opinion",
                    corr,
                    f"event_log:{event_id}",
                    Jsonb({"reaction_state": "REACTED", "blockers": blockers, "event_id": event_id, "token_id": "conflict-token", "side": "YES"}),
                ),
            )
        conn.execute(
            """
            INSERT INTO coordinator_decisions (
                coordinator_decision_id, market_id, final_state, primary_reason,
                confidence, urgency, conflicts_detected, governor_required,
                execution_allowed, approved_actions_json, blocked_actions_json,
                required_reviews_json, risk_flags_json, source_brain_count,
                input_output_count, conflict_count, correlation_id, ttl_seconds,
                status, metadata_json
            )
            VALUES (
                'bundle_conflict_coord', 'conflict-market', 'WATCH', 'synthetic price ready',
                0.5, 0.5, false, true, false, '["WATCH"]'::jsonb,
                '["PAPER_ENTRY","LIVE_ENTRY"]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                3, 3, 0, %s, 180, 'ACTIVE',
                '{"event_type":"orderbook.snapshot.created","decision":"PRICE_READY","coordinator_state":"DECISION_CREATED"}'::jsonb
            )
            """,
            (corr,),
        )

    payload = MeshEvidenceBundleService(connection_factory=DatabaseConnectionFactory()).list_bundles(correlation_id=corr)
    item = payload["items"][0]
    conflict_types = {conflict["conflict_type"] for conflict in item["conflicts"]}

    assert "LIQUIDITY_USABLE_RISK_BLOCKED" in conflict_types
    assert "EXIT_NOT_READY_COORDINATOR_PRICE_READY" in conflict_types
    assert item["bundle_state"] == "CONFLICTED"
