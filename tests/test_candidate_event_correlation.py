from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.candidate_event_correlation import CandidateEventCorrelationService, _classify_link
from app.control_center.eligible_intent_bridge import EligibleIntentBridgeService
from app.control_center.event_mesh_proof import EventMeshProofService
from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.control_center.paper_readiness import PaperReadinessService
from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.db.connection import DatabaseConnectionFactory
from app.repositories.orderbook_snapshot_repository import OrderbookSnapshotRepository

_ORDERBOOK_TEST_SPEC = spec_from_file_location("_phase7_orderbook_test_helpers", Path(__file__).with_name("test_orderbook_price_readiness.py"))
assert _ORDERBOOK_TEST_SPEC and _ORDERBOOK_TEST_SPEC.loader
_ORDERBOOK_TEST_HELPERS = module_from_spec(_ORDERBOOK_TEST_SPEC)
_ORDERBOOK_TEST_SPEC.loader.exec_module(_ORDERBOOK_TEST_HELPERS)

_prepare_case = _ORDERBOOK_TEST_HELPERS._prepare_case
_artifact_counts = _ORDERBOOK_TEST_HELPERS._artifact_counts
_table_exists = _ORDERBOOK_TEST_HELPERS._table_exists


def test_correlation_classifier_requires_exact_candidate_scope() -> None:
    now = datetime.now(UTC)
    matched, ambiguous, state, confidence, blockers, _required = _classify_link(
        [
            {
                "eligibility_id": "candidate-classifier",
                "market_id": "market-classifier",
                "side": "YES",
                "expected_token_id": "token-yes",
                "status": "ELIGIBLE",
                "created_at": now,
                "updated_at": now,
            }
        ],
        direct_candidate_id=None,
        market_id="market-classifier",
        side="YES",
        token_id="token-yes",
        event_age=1,
        now=now,
    )

    assert state == "LINKED_TO_CANDIDATE"
    assert confidence == "HIGH"
    assert blockers == []
    assert ambiguous == []
    assert matched[0]["candidate_id"] == "candidate-classifier"


def test_correlation_classifier_marks_multiple_exact_matches_ambiguous() -> None:
    now = datetime.now(UTC)
    _matched, ambiguous, state, confidence, blockers, _required = _classify_link(
        [
            {
                "eligibility_id": "candidate-a",
                "market_id": "market-classifier",
                "side": "YES",
                "expected_token_id": "token-yes",
                "status": "ELIGIBLE",
                "created_at": now,
                "updated_at": now,
            },
            {
                "eligibility_id": "candidate-b",
                "market_id": "market-classifier",
                "side": "YES",
                "expected_token_id": "token-yes",
                "status": "ELIGIBLE",
                "created_at": now,
                "updated_at": now,
            },
        ],
        direct_candidate_id=None,
        market_id="market-classifier",
        side="YES",
        token_id="token-yes",
        event_age=1,
        now=now,
    )

    assert state == "AMBIGUOUS_MULTIPLE_CANDIDATES"
    assert confidence == "LOW"
    assert "MULTIPLE_CANDIDATES_MATCH_EVENT" in blockers
    assert {item["candidate_id"] for item in ambiguous} == {"candidate-a", "candidate-b"}


def test_event_matching_one_candidate_is_candidate_scoped(postgres_test_schema) -> None:
    before = _artifact_counts()
    candidate_id = _seed_candidate_event_case("linked", token="token-yes")
    _append_snapshot("market-linked", "token-yes")

    payload = CandidateEventCorrelationService(connection_factory=DatabaseConnectionFactory()).list_correlations(limit=5)
    item = payload["items"][0]

    assert item["candidate_id"] == candidate_id
    assert item["candidate_event_link_state"] == "LINKED_TO_CANDIDATE"
    assert item["candidate_event_actionability_scope"] == "CANDIDATE_SCOPED"
    assert item["correlation_confidence"] == "HIGH"
    assert _artifact_counts() == before


def test_event_without_candidate_is_unlinked_with_reason(postgres_test_schema) -> None:
    before = _artifact_counts()
    _reset_mesh_tables()
    _insert_orderbook_event("orphan-event", market_id="orphan-market", side="YES", token_id="orphan-token")

    payload = CandidateEventCorrelationService(connection_factory=DatabaseConnectionFactory()).list_correlations(limit=5)
    item = payload["items"][0]

    assert item["candidate_event_link_state"] == "UNLINKED_WITH_REASON"
    assert item["candidate_event_actionability_scope"] == "NOT_ACTIONABLE"
    assert item["correlation_confidence"] == "NONE"
    assert "NO_CANDIDATE_FOR_MARKET" in item["blockers"]
    assert _artifact_counts() == before


def test_multiple_matching_candidates_are_ambiguous(postgres_test_schema) -> None:
    _seed_candidate_event_case("ambiguous", token="token-yes")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _clone_candidate(conn, "eligibility-ambiguous", "eligibility-ambiguous-2")
    _append_snapshot("market-ambiguous", "token-yes")

    payload = CandidateEventCorrelationService(connection_factory=DatabaseConnectionFactory()).list_correlations(limit=5)
    item = payload["items"][0]

    assert item["candidate_event_link_state"] == "AMBIGUOUS_MULTIPLE_CANDIDATES"
    assert item["candidate_event_actionability_scope"] == "AMBIGUOUS"
    assert item["correlation_confidence"] == "LOW"
    assert len(item["ambiguous_candidates"]) >= 2


def test_token_mismatch_is_not_candidate_actionable(postgres_test_schema) -> None:
    _seed_candidate_event_case("mismatch", token="candidate-token")
    _append_snapshot("market-mismatch", "event-token")

    payload = CandidateEventCorrelationService(connection_factory=DatabaseConnectionFactory()).list_correlations(limit=5)
    item = payload["items"][0]

    assert item["candidate_event_link_state"] == "TOKEN_SIDE_MISMATCH"
    assert item["candidate_event_actionability_scope"] == "NOT_ACTIONABLE"
    assert "NO_CANDIDATE_TOKEN_MATCH" in item["blockers"]


def test_market_only_match_is_low_confidence_and_market_scoped(postgres_test_schema) -> None:
    _seed_candidate_event_case("market-only", token=None)
    _append_snapshot("market-market-only", "event-token")

    payload = CandidateEventCorrelationService(connection_factory=DatabaseConnectionFactory()).list_correlations(limit=5)
    item = payload["items"][0]

    assert item["candidate_event_link_state"] == "MARKET_LEVEL_ONLY_WITH_REASON"
    assert item["candidate_event_actionability_scope"] == "MARKET_SCOPED_ONLY"
    assert item["correlation_confidence"] == "LOW"
    assert "MISSING_CANDIDATE_TOKEN" in item["blockers"]


def test_mesh_bundle_and_event_mesh_proof_expose_candidate_link_truth(postgres_test_schema) -> None:
    _seed_candidate_event_case("bundle", token="token-yes")
    _append_snapshot("market-bundle", "token-yes")

    bundle = MeshEvidenceBundleService(connection_factory=DatabaseConnectionFactory()).list_bundles(limit=5)["items"][0]
    proof = EventMeshProofService(connection_factory=DatabaseConnectionFactory()).list_proofs(limit=5)

    assert bundle["candidate_event_link_state"] == "LINKED_TO_CANDIDATE"
    assert bundle["candidate_event_actionability_scope"] == "CANDIDATE_SCOPED"
    assert proof["counts"]["events_linked_to_candidate"] >= 1
    assert proof["counts"]["events_market_level_only"] == 0


def test_eligible_bridge_blocks_market_level_event_actionability(postgres_test_schema) -> None:
    _seed_candidate_event_case("bridge-market", token=None, paper_simulation=False)
    _append_snapshot("market-bridge-market", "event-token")

    payload = EligibleIntentBridgeService(connection_factory=DatabaseConnectionFactory()).list_bridge(limit=5)
    item = next(item for item in payload["items"] if item["candidate_id"] == "eligibility-bridge-market")

    assert item["candidate_event_actionability_scope"] == "MARKET_SCOPED_ONLY"
    assert "MARKET_SCOPED_ONLY_EVENT" in item["blockers"]


def test_paper_readiness_includes_correlation_counts(postgres_test_schema) -> None:
    _seed_candidate_event_case("paper-readiness-corr", token="token-yes", paper_simulation=False)
    _append_snapshot("market-paper-readiness-corr", "token-yes")

    payload = PaperReadinessService(connection_factory=DatabaseConnectionFactory()).get_readiness()

    assert payload["counts"]["candidate_scoped_event_count"] >= 1
    assert payload["candidate_event_correlation_state"] in {"CANDIDATE_SCOPED", "MARKET_SCOPED_ONLY", "UNLINKED", "MISSING", "UNKNOWN"}


def test_candidate_event_correlation_endpoint_is_read_only(postgres_test_schema) -> None:
    _seed_candidate_event_case("api", token="token-yes")
    _append_snapshot("market-api", "token-yes")
    before = _artifact_counts()
    app = FastAPI()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/candidate-event-correlation")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["counts"]["events_checked"] >= 1
    assert payload["items"][0]["candidate_event_link_state"]
    assert _artifact_counts() == before


def _seed_candidate_event_case(suffix: str, *, token: str | None, paper_simulation: bool = True) -> str:
    candidate_id = _prepare_case(
        suffix,
        seed_orderbook=False,
        expected_token=token,
        market_tokens=token is not None,
        paper_simulation=paper_simulation,
        reset=True,
    )
    _reset_mesh_tables()
    return candidate_id


def _append_snapshot(market_id: str, token_id: str, side: str = "YES") -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook(
        {
            "asset_id": token_id,
            "market": f"condition-{market_id}",
            "bids": [{"price": "0.40", "size": "120"}],
            "asks": [{"price": "0.42", "size": "110"}],
        },
        market_id=market_id,
        token_id=token_id,
        side=side,
        source="test_candidate_event_correlation",
        correlation_id=f"candidate-event-{market_id}",
        collected_at=datetime.now(UTC),
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        OrderbookSnapshotRepository().append_snapshot(conn, snapshot)


def _insert_orderbook_event(event_id: str, *, market_id: str, side: str, token_id: str) -> None:
    now = datetime.now(UTC)
    payload = {
        "event_id": event_id,
        "correlation_id": f"corr-{event_id}",
        "market_id": market_id,
        "side": side,
        "token_id": token_id,
        "orderbook_snapshot_id": f"book-{event_id}",
        "best_bid": 0.4,
        "best_ask": 0.42,
        "spread": 0.02,
    }
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, mode, occurred_at, payload_json, metadata_json
            )
            VALUES (%s, 'orderbook.snapshot.created', 'orderbook_snapshot', %s,
                'test_candidate_event_correlation', %s, 'DATA_ONLY', %s, %s, '{}'::jsonb)
            """,
            (event_id, payload["orderbook_snapshot_id"], payload["correlation_id"], now, Jsonb(payload)),
        )


def _clone_candidate(conn: Any, existing_id: str, new_id: str) -> None:
    conn.execute(
        """
        INSERT INTO paper_eligibility_candidates (
            eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
            market_id, side, status, eligibility_score, eligibility_blockers,
            missing_requirements, evidence, orderbook_snapshot_id, link_confidence,
            lineage_trusted, risk_approved, exit_ready, not_dry_run,
            paper_intent_allowed, execution_allowed, generated_by, producer_name,
            is_runtime_generated, is_dry_run_generated, expected_token_id, created_at, updated_at
        )
        SELECT %s, thesis_id, risk_decision_id, exit_plan_id,
            market_id, side, status, eligibility_score, eligibility_blockers,
            missing_requirements, evidence, orderbook_snapshot_id, link_confidence,
            lineage_trusted, risk_approved, exit_ready, not_dry_run,
            paper_intent_allowed, execution_allowed, generated_by, producer_name,
            is_runtime_generated, is_dry_run_generated, expected_token_id, created_at, updated_at
        FROM paper_eligibility_candidates
        WHERE eligibility_id = %s
        """,
        (new_id, existing_id),
    )


def _reset_mesh_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_outputs",
            "brain_dialogue_events",
            "mesh_sessions",
            "event_delivery_attempts",
            "neural_event_delivery",
            "neural_events",
            "event_consumers",
            "event_log",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
