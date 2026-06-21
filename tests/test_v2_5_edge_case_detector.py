from __future__ import annotations

from app.rules_neuron.edge_case_detector import detect_contradictions, detect_dangerous_edge_cases, detect_edge_cases


def test_edge_cases_and_contradictions_detected() -> None:
    text = "If the event is postponed or cancelled, and announced before deadline but implemented after, will resolve yes and will resolve no."
    cases = detect_edge_cases(text)
    dangerous = detect_dangerous_edge_cases(cases)
    contradictions = detect_contradictions(text)
    assert "postponed/cancelled event" in cases
    assert "announced vs implemented" in cases
    assert dangerous
    assert contradictions

