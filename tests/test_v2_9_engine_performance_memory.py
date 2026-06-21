from app.market_memory.engine_performance_memory_builder import EnginePerformanceMemoryBuilder


def test_engine_performance_memory_improves_after_successful_outcomes():
    memory = EnginePerformanceMemoryBuilder().build(
        "strike",
        "crypto",
        [{"outcome": "WIN", "roi": 0.12, "roi_per_hour": 0.03}, {"outcome": "WIN", "roi": 0.06}],
    )

    assert memory.win_rate == 1.0
    assert memory.engine_score > 0.5
    assert memory.confidence > 0


def test_engine_performance_memory_decreases_after_failed_outcome():
    memory = EnginePerformanceMemoryBuilder().build(
        "convex",
        "sports",
        [{"outcome": "LOSS", "roi": -0.2, "adverse_selection": True}, {"outcome": "NEUTRAL", "roi": 0}],
    )

    assert memory.losses_count == 1
    assert memory.adverse_selection_rate == 0.5
    assert memory.engine_score < 0.5


def test_engine_performance_memory_no_fake_score_without_history():
    memory = EnginePerformanceMemoryBuilder().build("safe", "politics", [])

    assert memory.observations_count == 0
    assert memory.engine_score == 0
    assert memory.confidence == 0
