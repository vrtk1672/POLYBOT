from __future__ import annotations

from app.news_neuron.contracts import RawNewsEvent
from app.news_neuron.normalizer import NewsNormalizer, extract_basic_entities, infer_topics, normalize_title


def test_raw_event_normalized_with_bounded_scores() -> None:
    raw = RawNewsEvent(source_id="manual", title="Breaking: BTC moves after Fed decision", summary="Bitcoin and Fed news.")
    event = NewsNormalizer().normalize_raw_event(raw)
    assert event.normalized_title == "breaking btc moves after fed decision"
    assert "crypto" in event.topics
    assert event.category == "crypto"
    assert 0 <= event.importance_score <= 1
    assert 0 <= event.urgency_score <= 1


def test_helpers_handle_empty_optional_fields() -> None:
    assert normalize_title("  Hello, WORLD!!! ") == "hello world"
    assert "BTC" in {item.upper() for item in extract_basic_entities("BTC and Ethereum rally")}
    assert infer_topics("court ruling in election case")

