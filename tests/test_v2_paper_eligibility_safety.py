from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.mesh_blockers import MeshBlockersService
from app.services.paper_eligibility import PaperEligibilityService

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain, table_exists


def test_paper_eligibility_creates_no_executable_artifacts(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("safety")

    result = PaperEligibilityService().evaluate_candidates(limit=10)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_eligibility_candidates WHERE execution_allowed = true").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_eligibility_candidates WHERE paper_intent_allowed = true").fetchone()["count"] == 0
        for table in ("paper_orders", "shadow_orders", "live_orders", "positions"):
            if table_exists(conn, table):
                assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == 0
        if table_exists(conn, "order_intents"):
            assert conn.execute("SELECT COUNT(*) AS count FROM order_intents").fetchone()["count"] == 0


def test_mesh_blockers_paper_eligible_resolves_only_with_eligible_candidate(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    blockers = MeshBlockersService().get_mesh_blockers(limit=10)
    assert "NO_PAPER_ELIGIBLE_SIGNALS" in blockers["blocked_by"]

    seed_paper_eligibility_chain("eligible")
    PaperEligibilityService().evaluate_candidates(limit=10)
    blockers = MeshBlockersService().get_mesh_blockers(limit=10)
    assert "NO_PAPER_ELIGIBLE_SIGNALS" not in blockers["blocked_by"]
    assert blockers["paper_ready"] is False
