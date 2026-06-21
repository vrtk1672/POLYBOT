from __future__ import annotations

from app.services.full_mesh_registry import full_mesh_registry, registry_by_name


def test_full_mesh_registry_includes_current_core_organs() -> None:
    names = registry_by_name()

    for required in (
        "candidate",
        "candidate_event_correlation",
        "trusted_orderbook",
        "candidate_price_path",
        "liquidity",
        "source_backed_edge",
        "risk",
        "exit",
        "capital",
        "lifecycle",
        "coordinator",
        "paper_actionability",
        "pre_paper_safety",
    ):
        assert required in names
        assert names[required].safe_for_pre_paper_inquiry is True


def test_source_organs_are_registered_or_explicitly_unavailable() -> None:
    names = registry_by_name()

    assert names["cross_market"].availability == "UNAVAILABLE"
    assert names["news"].availability == "AVAILABLE"
    assert names["news"].passive_only is False
    assert names["whale"].availability == "AVAILABLE"
    assert names["whale"].passive_only is False
    assert names["signal_quality"].availability == "AVAILABLE"
    assert names["payout"].availability == "AVAILABLE"
    assert names["ai_reasoner"].availability == "PASSIVE"


def test_registry_entries_declare_questions_and_scope() -> None:
    for organ in full_mesh_registry():
        payload = organ.to_api_dict()
        assert payload["neuron_name"]
        assert payload["questions"]
        assert "candidate_scoped" in payload
        assert "directional_evidence" in payload
