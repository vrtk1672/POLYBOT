from __future__ import annotations

from app.services.ai_mesh_intelligence import _candidate_prompt, _event_prompt


def test_compressed_candidate_prompt_stays_below_configured_size() -> None:
    prompt = _candidate_prompt(
        {
            "market_id": "m1",
            "side": "YES",
            "token_id": "t1",
            "trigger_type": "PAYOUT_DISCREPANCY",
            "edge_state": "EDGE_SUPPORTED",
            "thesis_state": "THESIS_MISSING",
            "exit_state": "EXIT_NOT_READY",
            "policy_blockers": ["missing_trade_thesis", "exit_not_ready"] * 20,
            "required_to_pass": ["Build thesis", "Define exit"] * 20,
        },
        reasoning=True,
        max_chars=700,
    )

    assert len(prompt) <= 700
    assert "Return compact JSON only" in prompt
    assert "chain-of-thought" not in prompt.lower()


def test_compressed_event_prompt_stays_below_configured_size() -> None:
    prompt = _event_prompt({"summary": "x" * 3000, "source_type": "NEWS"}, max_chars=600)

    assert len(prompt) <= 600
    assert "Do not invent market ids" in prompt
