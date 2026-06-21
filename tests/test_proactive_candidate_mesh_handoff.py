from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.proactive_candidate_generation import MESH_HANDOFF_SKIPPED_REASON, ProactiveCandidateGenerationService
from proactive_candidate_generation_helpers import setup_proactive_seed_source


def test_mesh_handoff_is_skipped_without_safe_data_only_contract(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-mesh", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT mesh_handoff_state, metadata_json FROM proactive_candidate_seeds WHERE market_id='market-stage4-mesh'").fetchone()
    assert row["mesh_handoff_state"] == "SKIPPED"
    assert row["metadata_json"]["mesh_handoff_reason"] == MESH_HANDOFF_SKIPPED_REASON


def test_mesh_handoff_skip_does_not_create_paper_intents(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-no-paper", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")
    with DatabaseConnectionFactory().connect() as conn:
        before = conn.execute("SELECT COUNT(*) AS count FROM paper_intents").fetchone()["count"]

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        after = conn.execute("SELECT COUNT(*) AS count FROM paper_intents").fetchone()["count"]
        seed = conn.execute("SELECT paper_allowed, execution_allowed FROM proactive_candidate_seeds WHERE market_id='market-stage4-no-paper'").fetchone()
    assert after == before
    assert seed["paper_allowed"] is False
    assert seed["execution_allowed"] is False
