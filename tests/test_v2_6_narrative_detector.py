from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.contracts import NormalizedSocialEvent
from app.social_neuron.narrative_detector import NarrativeDetector


def test_repeated_topic_creates_stronger_narrative_and_fades(postgres_test_schema) -> None:
    run_migrations()
    detector = NarrativeDetector(connection_factory=DatabaseConnectionFactory())
    first = NormalizedSocialEvent(source_id="manual", text="BTC breakout #BTC", normalized_text="btc breakout #btc", topics=["btc"], hashtags=["btc"], author_handle="a")
    second = NormalizedSocialEvent(source_id="manual", text="BTC breakout continues #BTC", normalized_text="btc breakout continues #btc", topics=["btc"], hashtags=["btc"], author_handle="b")
    n1 = detector.update_narrative(first, [])
    n2 = detector.update_narrative(second, [])
    assert n1.narrative_key == n2.narrative_key
    assert n2.event_count >= 2
    assert n2.narrative_strength >= n1.narrative_strength
    with DatabaseConnectionFactory().connect() as conn:
        conn.execute("UPDATE social_narratives SET last_seen_at = %s", (datetime.now(UTC) - timedelta(days=2),))
        conn.commit()
    assert detector.mark_faded_narratives(older_than_seconds=60) >= 1
