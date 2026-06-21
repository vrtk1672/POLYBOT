from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.services.decision_autopsy import DecisionAutopsyService
from decision_autopsy_helpers import prepare_autopsy_fixture, seed_runtime_decision, table_exists


def test_thesis_and_exit_blockers_have_missing_requirements(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-missing-thesis",
        market_id="m-thesis",
        side="YES",
        decision="BLOCK",
        score=62,
        thesis_state="THESIS_MISSING",
        exit_state="EXIT_NOT_READY",
        blockers=["THESIS_NOT_SUPPORTED", "EXIT_NOT_READY"],
    )

    item = DecisionAutopsyService().list_autopsies(limit=5)["items"][0]
    blockers = DecisionAutopsyService().top_blockers()["top_blockers"]

    assert "THESIS_NOT_SUPPORTED" in item["blocker_codes"]
    assert "EXIT_NOT_READY" in item["blocker_codes"]
    assert "supported_trade_thesis" in item["missing_requirements"]
    assert "exit_plan" in item["missing_requirements"]
    assert any(row["blocker_code"] == "THESIS_NOT_SUPPORTED" and row["blocking_organ"] == "Trade Thesis Mesh" for row in blockers)


def test_top_blockers_limit_owner_reason_and_unmapped_visibility(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    for idx in range(25):
        code = f"UNMAPPED_BLOCKER_{idx:02d}"
        seed_runtime_decision(
            decision_id=f"decision-{idx}",
            market_id=f"m-{idx}",
            side="YES",
            decision="WATCH",
            score=50 + idx,
            blockers=[code],
        )
    for idx in range(3):
        seed_runtime_decision(
            decision_id=f"decision-score-{idx}",
            market_id="m-score",
            side="NO",
            decision="WATCH",
            score=55.46,
            blockers=["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"],
        )

    app = FastAPI()
    app.include_router(create_router())
    payload = TestClient(app).get("/dashboard/api/v2/control/decision-autopsy/top-blockers?limit=20").json()

    assert payload["status"] == "OK"
    assert payload["limit"] == 20
    assert len(payload["top_blockers"]) == 20
    assert any(row["blocking_organ"] == "UNMAPPED" for row in payload["top_blockers"])
    score_row = next(row for row in payload["top_blockers"] if row["blocker_code"] == "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD")
    assert score_row["blocking_gate"] == "PaperRuntimeDecision"
    assert score_row["plain_english_meaning"]
    assert score_row["required_value_or_missing_requirement"] == "opportunity_score >= 60"
    assert score_row["example"]["market_id"] == "m-score"
    assert score_row["expected_vs_suspicious"] == "EXPECTED"


def test_top_blockers_service_is_read_only_for_live_shadow_real_tables(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-readonly",
        market_id="m-readonly",
        side="YES",
        decision="WATCH",
        score=55.46,
        blockers=["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"],
    )
    before = _safety_counts()

    payload = DecisionAutopsyService().top_blockers(limit=20)

    assert payload["top_blockers"]
    assert _safety_counts() == before


def test_polybot_blockers_cli_supports_limit_and_read_only_endpoint() -> None:
    text = __import__("pathlib").Path("tools/polybot.ps1").read_text(encoding="utf-8")

    assert '"blockers"' in text
    assert 'Get-ArgValue -Args $Rest -Names @("-limit", "--limit")' in text
    assert "/dashboard/api/v2/control/decision-autopsy/top-blockers?limit={0}" in text
    assert "Invoke-PolybotJson -Method \"GET\"" in text
    assert "Run .\\tools\\polybot.ps1 blockers -limit 20 for full blocker breakdown." in text


def _safety_counts() -> dict[str, int]:
    tables = ("live_orders", "shadow_orders", "orders_v2", "fills_v2", "positions")
    with DatabaseConnectionFactory().connect() as conn:
        out = {}
        for table in tables:
            if table_exists(conn, table):
                out[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
        return out
