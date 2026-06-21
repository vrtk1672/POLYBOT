from app.whale_neuron.category_engine import WhaleCategoryEngine
from app.whale_neuron.contracts import WhaleProfile


def test_category_engine_requires_sample_and_assigns_categories():
    engine = WhaleCategoryEngine()
    assert engine.compute_category_scores(WhaleProfile(whale_id="new", sample_size=1))[0].category == "unknown"
    cats = engine.compute_category_scores(WhaleProfile(whale_id="smart", sample_size=10, timing_quality=0.9, hit_rate=0.8, noise_score=0.1, follow_value=0.8, copy_worthy_score=0.8, market_specialties=["sports"], confidence=0.9))
    names = {cat.category for cat in cats}
    assert {"smart_whale", "copy_worthy_whale", "sports_specialist"}.issubset(names)
    assert engine.compute_category_scores(WhaleProfile(whale_id="noisy", sample_size=10, noise_score=0.9))[0].category == "noisy_whale"

