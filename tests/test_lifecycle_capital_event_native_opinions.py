from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from psycopg.types.json import Jsonb

from app.control_center.event_mesh_proof import EventMeshProofService
from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository

_ORDERBOOK_TEST_SPEC = spec_from_file_location("_phase7_orderbook_test_helpers", Path(__file__).with_name("test_orderbook_price_readiness.py"))
assert _ORDERBOOK_TEST_SPEC and _ORDERBOOK_TEST_SPEC.loader
_ORDERBOOK_TEST_HELPERS = module_from_spec(_ORDERBOOK_TEST_SPEC)
_ORDERBOOK_TEST_SPEC.loader.exec_module(_ORDERBOOK_TEST_HELPERS)

_artifact_counts = _ORDERBOOK_TEST_HELPERS._artifact_counts


def _snapshot(market_id: str = "phase9b-market", token_id: str = "phase9b-token", side: str = "YES"):
    return OrderbookSnapshotter().normalize_orderbook(
        {
            "asset_id": token_id,
            "market": "phase9b-condition",
            "bids": [{"price": "0.40", "size": "120"}],
            "asks": [{"price": "0.42", "size": "110"}],
        },
        market_id=market_id,
        token_id=token_id,
        side=side,
        source="test_lifecycle_capital_event_native_opinions",
        correlation_id="phase9b",
        collected_at=datetime.now(UTC),
    )


def _seed_capital_and_lifecycle(*, market_id: str, side: str, token_id: str, allow: bool = True) -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, currency, initial_balance, current_balance,
                available_balance, locked_balance, open_exposure, max_open_positions, status, updated_at
            )
            VALUES ('paper_default', 'Default Paper Account', 'USD', 1000, 1000, 1000, 0, 0, 3, 'ACTIVE', %s)
            ON CONFLICT (account_id) DO UPDATE SET
                available_balance = EXCLUDED.available_balance,
                locked_balance = EXCLUDED.locked_balance,
                open_exposure = EXCLUDED.open_exposure,
                max_open_positions = EXCLUDED.max_open_positions,
                updated_at = EXCLUDED.updated_at
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
                %s, %s, %s, %s, %s, %s)
            """,
            (
                f"phase9b-lifecycle-{market_id}",
                f"phase9b-candidate-{market_id}",
                market_id,
                side,
                token_id,
                "ACTIONABLE_SMALL_PAPER" if allow else "BLOCKED",
                allow,
                allow,
                Jsonb([] if allow else ["PHASE9B_TEST_LIFECYCLE_DENIED"]),
                "phase9b lifecycle fixture",
                now,
            ),
        )


def test_capital_and_lifecycle_are_event_native_for_orderbook_event(postgres_test_schema) -> None:
    before_artifacts = _artifact_counts()
    market_id = "phase9b-all-five-market"
    token_id = "phase9b-all-five-token"
    side = "YES"
    _seed_capital_and_lifecycle(market_id=market_id, side=side, token_id=token_id, allow=True)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = OrderbookSnapshotRepository().append_snapshot(conn, _snapshot(market_id=market_id, token_id=token_id, side=side))

    correlation_id = f"phase9b:{result.orderbook_snapshot_id}"
    proof = EventMeshProofService(connection_factory=DatabaseConnectionFactory()).list_proofs(correlation_id=correlation_id)
    item = proof["items"][0]

    assert proof["mesh_proof_state"] == "PROVEN"
    assert proof["counts"]["events_with_capital_reaction"] == 1
    assert proof["counts"]["events_with_lifecycle_reaction"] == 1
    assert proof["counts"]["events_with_all_five_reactions"] == 1
    assert proof["counts"]["events_with_event_native_capital"] == 1
    assert proof["counts"]["events_with_event_native_lifecycle"] == 1
    assert {reaction["brain"] for reaction in item["brain_reactions"]} >= {"liquidity", "risk", "exit", "capital", "lifecycle"}
    assert item["coordinator"]["decision"] == "PRICE_READY"
    assert item["coordinator"]["mesh_consensus_state"] == "CONSENSUS_READY"
    assert item["coordinator"]["capital_opinion_state"] == "CAPITAL_OK"
    assert item["coordinator"]["lifecycle_opinion_state"] == "LIFECYCLE_ALLOWED"
    assert _artifact_counts() == before_artifacts


def test_mesh_bundle_shows_event_native_capital_lifecycle_and_five_opinions(postgres_test_schema) -> None:
    before_artifacts = _artifact_counts()
    market_id = "phase9b-bundle-market"
    token_id = "phase9b-bundle-token"
    side = "YES"
    _seed_capital_and_lifecycle(market_id=market_id, side=side, token_id=token_id, allow=True)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = OrderbookSnapshotRepository().append_snapshot(conn, _snapshot(market_id=market_id, token_id=token_id, side=side))

    correlation_id = f"phase9b:{result.orderbook_snapshot_id}"
    bundle = MeshEvidenceBundleService(connection_factory=DatabaseConnectionFactory()).list_bundles(correlation_id=correlation_id)
    item = bundle["items"][0]

    assert bundle["counts"]["with_all_five_opinions"] == 1
    assert bundle["counts"]["with_event_native_capital"] == 1
    assert bundle["counts"]["with_event_native_lifecycle"] == 1
    assert item["opinion_states"]["capital"] == "PRESENT"
    assert item["opinion_states"]["lifecycle"] == "PRESENT"
    assert item["opinions"]["capital"]["event_native_state"] == "EVENT_NATIVE"
    assert item["opinions"]["lifecycle"]["event_native_state"] == "EVENT_NATIVE"
    assert item["opinions"]["capital"]["capital_opinion_state"] == "CAPITAL_OK"
    assert item["opinions"]["lifecycle"]["lifecycle_opinion_state"] == "LIFECYCLE_ALLOWED"
    assert item["mesh_consensus_state"] == "CONSENSUS_READY"
    assert item["coordinator"]["execution_allowed"] is False
    assert _artifact_counts() == before_artifacts


def test_coordinator_blocks_when_lifecycle_denies(postgres_test_schema) -> None:
    before_artifacts = _artifact_counts()
    market_id = "phase9b-lifecycle-denied-market"
    token_id = "phase9b-lifecycle-denied-token"
    side = "YES"
    _seed_capital_and_lifecycle(market_id=market_id, side=side, token_id=token_id, allow=False)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        result = OrderbookSnapshotRepository().append_snapshot(conn, _snapshot(market_id=market_id, token_id=token_id, side=side))

    correlation_id = f"phase9b:{result.orderbook_snapshot_id}"
    proof = EventMeshProofService(connection_factory=DatabaseConnectionFactory()).list_proofs(correlation_id=correlation_id)
    item = proof["items"][0]
    bundle = MeshEvidenceBundleService(connection_factory=DatabaseConnectionFactory()).list_bundles(correlation_id=correlation_id)

    assert item["coordinator"]["decision"] == "LIFECYCLE_BLOCKED"
    assert item["coordinator"]["mesh_consensus_state"] == "CONSENSUS_BLOCKED"
    assert item["coordinator"]["lifecycle_opinion_state"] == "LIFECYCLE_DENIED"
    assert bundle["items"][0]["opinions"]["lifecycle"]["event_native_state"] == "EVENT_NATIVE"
    assert bundle["items"][0]["mesh_consensus_state"] == "CONSENSUS_BLOCKED"
    assert _artifact_counts() == before_artifacts
