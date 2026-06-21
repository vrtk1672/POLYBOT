from __future__ import annotations

from app.news_neuron.source_reliability import SourceReliabilityScorer


def test_source_scoring_neutral_and_error_penalty() -> None:
    scorer = SourceReliabilityScorer()
    assert scorer.get_source_reliability("unknown") == 0.5
    assert scorer.score_source_event({"source_id": "s", "reliability_score": 0.8, "error_count": 4}) < 0.8
    assert scorer.score_source_event({"source_id": "s", "reliability_score": 0.5, "error_count": 0}, {"linked": True}) > 0.5

