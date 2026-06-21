from __future__ import annotations

from app.social_neuron.bot_spam_filter import BotSpamFilter
from app.social_neuron.contracts import NormalizedSocialEvent


def test_spam_bot_and_normal_text_scores() -> None:
    filt = BotSpamFilter()
    spam = NormalizedSocialEvent(source_id="manual", text="100x guaranteed click #a #b #c #d $BTC", normalized_text="100x guaranteed click #a #b #c #d $btc", hashtags=["a", "b", "c", "d"], cashtags=["BTC"], author_handle="new1234")
    normal = NormalizedSocialEvent(source_id="manual", text="BTC volume is rising", normalized_text="btc volume is rising")
    assert filt.compute_spam_score(spam) > filt.compute_spam_score(normal)
    assert filt.compute_bot_risk(spam) > filt.compute_bot_risk(normal)
    assert filt.compute_noise_score(spam).noise_score > filt.compute_noise_score(normal).noise_score
