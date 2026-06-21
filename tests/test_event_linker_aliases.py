from __future__ import annotations

from app.services.source_event_memory import SourceEventMemoryService


def _event(**overrides):
    event = {
        "source_event_id": "event-alias",
        "headline": "",
        "summary": "",
        "entities_json": [],
        "topics_json": [],
        "keywords_json": [],
        "direction": "UNKNOWN",
        "direction_confidence": 0.0,
    }
    event.update(overrides)
    return event


def _market(**overrides):
    market = {
        "market_memory_id": "memory-alias",
        "market_id": "alias-market",
        "condition_id": "alias-condition",
        "slug": "alias-market",
        "title": "Will Bitcoin ETF approval happen?",
        "question": "Will Bitcoin ETF approval happen?",
        "category": "crypto",
        "entities_json": ["Bitcoin"],
        "tags_json": ["crypto", "ETF"],
        "keywords_json": ["bitcoin", "etf", "approval"],
        "yes_token_id": "alias-yes",
        "no_token_id": "alias-no",
    }
    market.update(overrides)
    return market


def test_btc_alias_links_to_bitcoin_market() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="BTC ETF approval odds rise", keywords_json=["btc", "etf", "approval"], direction="YES"),
        [_market()],
    )

    assert links[0]["link_type"] in {"DIRECT_LINK", "LIKELY_LINK"}
    assert "bitcoin" in links[0]["matched_aliases_json"]
    assert links[0]["confidence_components_json"]["alias_score"] > 0


def test_eth_alias_links_to_ethereum_market() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="ETH ETF approval decision nears", keywords_json=["eth", "etf", "approval"], direction="YES"),
        [
            _market(
                market_memory_id="memory-eth",
                market_id="eth-market",
                condition_id="eth-condition",
                slug="ethereum-etf",
                title="Will an Ethereum ETF be approved?",
                question="Will an Ethereum ETF be approved?",
                entities_json=["Ethereum"],
                keywords_json=["ethereum", "etf", "approval"],
                yes_token_id="eth-yes",
                no_token_id="eth-no",
            )
        ],
    )

    assert links[0]["link_type"] in {"DIRECT_LINK", "LIKELY_LINK"}
    assert "ethereum" in links[0]["matched_aliases_json"]
    assert links[0]["confidence_components_json"]["alias_score"] > 0


def test_sec_etf_event_recalls_etf_and_regulation_market() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(
            headline="SEC ETF approval decision expected",
            summary="Crypto regulation watchers expect a spot ETF ruling.",
            keywords_json=["sec", "etf", "approval", "crypto", "regulation"],
            topics_json=["crypto", "ETF"],
        ),
        [
            _market(
                market_memory_id="memory-reg",
                market_id="reg-market",
                condition_id="reg-condition",
                slug="crypto-etf-regulation",
                title="Will the SEC approve a spot crypto ETF?",
                question="Will the SEC approve a spot crypto ETF?",
                entities_json=["SEC"],
                tags_json=["crypto", "regulation"],
                keywords_json=["sec", "spot", "crypto", "etf", "approval"],
                yes_token_id="reg-yes",
                no_token_id="reg-no",
            )
        ],
    )

    assert links[0]["link_type"] in {"DIRECT_LINK", "LIKELY_LINK"}
    assert {"sec", "etf"}.issubset(set(links[0]["matched_aliases_json"]))
    assert links[0]["link_confidence"] >= 0.65


def test_ai_does_not_invent_aliases_or_links_for_unrelated_event() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="Local weather update", summary="Rain expected downtown.", keywords_json=["weather", "rain"]),
        [_market()],
    )

    assert links[0]["link_type"] == "NO_LINK"
    assert links[0]["matched_aliases_json"] == []
    assert links[0]["candidate_actionability_hint"] == "NOT_RELEVANT"
