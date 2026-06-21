from __future__ import annotations

from app.data_foundation.market_family_classifier import MarketFamilyClassifier


def test_btc_5m_market_classified_crypto_short_window() -> None:
    result = MarketFamilyClassifier().classify({"question": "Bitcoin up or down in next 5m?", "slug": "btc-5m"})
    assert result["market_family"] == "crypto-short-window"


def test_election_market_classified() -> None:
    result = MarketFamilyClassifier().classify({"question": "Who will win the 2028 presidential election?"})
    assert result["market_family"] == "politics-election"


def test_sports_market_classified() -> None:
    result = MarketFamilyClassifier().classify({"question": "Will Arsenal win the game vs Chelsea?"})
    assert result["market_family"] == "sports-pre-match"


def test_unknown_market_generic_low_confidence() -> None:
    result = MarketFamilyClassifier().classify({"question": "Will an unspecified thing happen?"})
    assert result["market_family"] == "generic"
    assert result["confidence"] < 0.5
