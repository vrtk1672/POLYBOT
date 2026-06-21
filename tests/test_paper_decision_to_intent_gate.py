from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from test_paper_runtime_execution_chain import _Actionability, _Governor, _Power, _prepare, _seed_policy_review


def test_capital_watch_and_risk_review_can_pass_paper_learning_gate(postgres_test_schema) -> None:
    _prepare()
    _seed_policy_review(market_id="paper-learning-risk-review", risk_state="RISK_REVIEW")

    result = PaperIntentGateService(
        system_power=_Power(),
        governor=_Governor(),
        paper_actionability=_Actionability(),
    ).build_intents(limit=20, write_intents=True, write_no_trade=True)

    assert result["paper_intents_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        intent = conn.execute("SELECT * FROM paper_intents ORDER BY id DESC LIMIT 1").fetchone()
    assert intent["paper_only"] is True
    assert intent["live"] is False
    assert intent["execution_allowed"] is False
    warnings = intent["evidence"]["paper_mode_policy"]["warnings"]
    assert "RISK_REVIEW_ALLOWED_FOR_PAPER_LEARNING" in warnings
    assert "CAPITAL_WATCH_ALLOWED_FOR_PAPER_LEARNING" in warnings


def test_full_paper_certification_not_required_for_runtime_paper_decision(postgres_test_schema) -> None:
    _prepare()
    _seed_policy_review(market_id="paper-learning-full-cert-not-required")

    PaperIntentGateService(
        system_power=_Power(),
        governor=_Governor(),
        paper_actionability=_Actionability(),
    ).build_intents(limit=20, write_intents=True, write_no_trade=True)

    with DatabaseConnectionFactory().connect() as conn:
        intent = conn.execute("SELECT * FROM paper_intents ORDER BY id DESC LIMIT 1").fetchone()
    assert intent["evidence"]["paper_mode_policy"]["full_paper_required"] is False
