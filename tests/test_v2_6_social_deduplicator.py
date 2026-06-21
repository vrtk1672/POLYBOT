from __future__ import annotations

from app.social_neuron.contracts import NormalizedSocialEvent
from app.social_neuron.deduplicator import SocialDeduplicator
from app.social_neuron.bot_spam_filter import BotSpamFilter


def test_same_text_deduped_and_duplicate_risk_increases() -> None:
    deduper = SocialDeduplicator()
    first = NormalizedSocialEvent(source_id="manual", text="BTC pumping now", normalized_text="btc pumping now")
    second = NormalizedSocialEvent(source_id="manual", text="BTC pumping now", normalized_text="btc pumping now")
    assert deduper.compute_group_hash(first) == deduper.compute_group_hash(second)
    second.dedup_group_id = deduper.compute_group_hash(second)
    assert BotSpamFilter().compute_duplicate_risk(second) >= 0.6


def test_different_post_not_deduped() -> None:
    deduper = SocialDeduplicator()
    first = NormalizedSocialEvent(source_id="manual", text="BTC pumping now", normalized_text="btc pumping now")
    second = NormalizedSocialEvent(source_id="manual", text="Election debate tonight", normalized_text="election debate tonight")
    assert deduper.compute_group_hash(first) != deduper.compute_group_hash(second)
