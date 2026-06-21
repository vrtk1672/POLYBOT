from __future__ import annotations

from app.news_neuron.contracts import NewsDirection, NormalizedNewsEvent
from app.news_neuron.market_linker import NewsMarketLinker


def test_news_linked_to_matching_market_and_direction_unknown() -> None:
    event = NormalizedNewsEvent(source_id="manual", title="BTC price jumps", normalized_title="btc price jumps", category="crypto", entities=["BTC"], topics=["crypto"])
    market = {"market_id": "m1", "question": "Will BTC close above 100k?", "category": "crypto", "market_family": "crypto-daily", "closed": False, "active": True}
    link = NewsMarketLinker().score_market_link(event, market)
    assert link.link_score >= 0.2
    assert link.direction == NewsDirection.UNKNOWN


def test_irrelevant_or_closed_market_penalized() -> None:
    event = NormalizedNewsEvent(source_id="manual", title="BTC price jumps", normalized_title="btc price jumps", category="crypto", entities=["BTC"], topics=["crypto"])
    irrelevant = {"market_id": "m2", "question": "Will the Lakers win?", "category": "sports", "closed": False, "active": True}
    closed = {"market_id": "m3", "question": "Will BTC close above 100k?", "category": "crypto", "closed": True, "active": False}
    linker = NewsMarketLinker()
    assert linker.score_market_link(event, irrelevant).link_score < 0.2
    assert linker.score_market_link(event, closed).confidence < linker.score_market_link(event, {**closed, "closed": False, "active": True}).confidence

