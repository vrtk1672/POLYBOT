from app.market_memory.whale_memory_builder import WhaleMemoryBuilder


def test_whale_memory_penalizes_noisy_whale():
    memory = WhaleMemoryBuilder().build(
        "w1",
        [{"follow_value": 0.4, "noise_penalty": 0.9, "timing_quality": 0.2}],
        market_family="crypto",
    )

    assert memory.noise_score_avg == 0.9
    assert memory.whale_score < 0.4


def test_whale_memory_does_not_treat_size_alone_as_intelligence():
    memory = WhaleMemoryBuilder().build("big", [{"size_usd": 1_000_000}], market_family="sports")

    assert memory.avg_size_usd == 1_000_000
    assert memory.follow_value_avg == 0
    assert memory.whale_score <= 0.2
    assert memory.summary["size_alone_is_not_intelligence"] is True
