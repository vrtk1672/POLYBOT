from app.market_memory.source_reliability_memory_builder import SourceReliabilityMemoryBuilder


def test_source_reliability_memory_improves_after_supported_signal():
    memory = SourceReliabilityMemoryBuilder().build(
        "news",
        "wire",
        [{"supported": True, "latency_seconds": 10}, {"supported": True, "latency_seconds": 20}],
    )

    assert memory.true_positive_count == 2
    assert memory.false_positive_count == 0
    assert memory.reliability_score > 0.5
    assert memory.usefulness_score > 0


def test_source_reliability_memory_decreases_after_false_stale_noisy_signal():
    memory = SourceReliabilityMemoryBuilder().build(
        "social",
        "trend_feed",
        [{"supported": False, "stale": True}, {"supported": False, "duplicate": True}],
    )

    assert memory.false_positive_count == 2
    assert memory.reliability_score < 0.5
    assert memory.summary["stale_count"] == 1
    assert memory.summary["duplicate_count"] == 1


def test_source_reliability_memory_low_confidence_without_outcome_evidence():
    memory = SourceReliabilityMemoryBuilder().build("technical", "v2.8", [{"supported": None}])

    assert memory.observations_count == 1
    assert memory.confidence < 0.2
