from app.brains.context_brain import ContextBrain
from app.brains.contracts import ContextBrainInput


def test_context_can_say_no_real_shift():
    output = ContextBrain().analyze(ContextBrainInput(market_id="m1", technical_signals=[{"technical_score": 0.05}], data_completeness_score=1.0))

    assert output.context_shift is False
    assert output.direction in {"NONE", "UNKNOWN"}


def test_context_detects_real_shift_from_supported_inputs():
    output = ContextBrain().analyze(
        ContextBrainInput(
            market_id="m1",
            news_signals=[{"strength": 0.9, "confidence": 0.8, "direction": "YES", "already_priced_in": 0.1, "urgency": 0.7}],
            whale_signals=[{"follow_value": 0.8, "side": "YES"}],
            technical_signals=[{"technical_score": 0.7, "data_completeness_score": 1.0}],
            memory_snapshot={"confidence": 0.8, "whale_memory": {"whale_score": 0.8, "confidence": 0.8}},
            data_completeness_score=1.0,
        )
    )

    assert output.context_shift is True
    assert output.direction == "YES"
    assert output.strength > 0.25


def test_context_marks_insufficient_data_when_inputs_missing():
    output = ContextBrain().analyze(ContextBrainInput(market_id="m1"))

    assert output.insufficient_data is True
    assert "missing_context_signals" in output.insufficient_data_reasons


def test_context_reduces_confidence_when_already_priced_in_high():
    output = ContextBrain().analyze(
        ContextBrainInput(
            market_id="m1",
            news_signals=[{"strength": 1.0, "confidence": 1.0, "direction": "YES", "already_priced_in": 0.95}],
            data_completeness_score=1.0,
        )
    )

    assert output.context_shift is False
    assert output.already_priced_in_score == 0.95


def test_context_exposes_rules_wording_risk_and_ai_cannot_override():
    output = ContextBrain().analyze(
        ContextBrainInput(
            market_id="m1",
            news_signals=[{"strength": 0.9, "confidence": 0.9, "direction": "YES"}],
            memory_snapshot={"confidence": 0.8, "rules_risk_memory": [{"rules_risk_score": 0.9}]},
            ai_analysis={"summary": "Looks great"},
            data_completeness_score=1.0,
        )
    )

    assert "high_wording_risk" in output.risks
    assert "ai_cannot_override_risk" in output.risks


def test_context_weighs_whale_by_memory_not_size_alone_and_penalizes_social_noise():
    output = ContextBrain().analyze(
        ContextBrainInput(
            market_id="m1",
            whale_signals=[{"follow_value": 1.0, "size_usd": 1_000_000, "side": "YES"}],
            social_signals=[{"hype_pressure": 1.0, "bot_risk": 0.9, "spam_ratio": 0.8, "confidence": 1.0}],
            memory_snapshot={"confidence": 0.2, "whale_memory": {"whale_score": 0.0, "confidence": 0.0}},
            data_completeness_score=1.0,
        )
    )

    assert "noisy_social_signal" in output.risks
    assert output.strength < 0.25
