from __future__ import annotations

from app.services.source_event_memory import SourceEventMemoryService


def _event(**overrides):
    event = {
        "source_event_id": "source-event-1",
        "source_record_id": "event-1",
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
        "market_memory_id": "memory-market-1",
        "market_id": "market-1",
        "condition_id": "condition-1",
        "slug": "bitcoin-etf-approval",
        "title": "Will a Bitcoin ETF be approved by the SEC?",
        "question": "Will a Bitcoin ETF be approved by the SEC?",
        "category": "crypto",
        "entities_json": ["Bitcoin", "SEC"],
        "tags_json": ["crypto", "ETF"],
        "keywords_json": ["bitcoin", "etf", "approval", "sec"],
        "yes_token_id": "token-yes",
        "no_token_id": "token-no",
    }
    market.update(overrides)
    return market


def test_exact_condition_id_creates_direct_link() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(condition_id="condition-1", headline="Condition-specific update"),
        [_market()],
    )

    assert links[0]["link_type"] == "DIRECT_LINK"
    assert links[0]["confidence_components_json"]["identifier_score"] >= 0.95
    assert "condition_id" in links[0]["matched_fields_json"]


def test_exact_token_id_creates_direct_link_with_side_state() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(token_id="token-yes", direction="YES", headline="YES token update"),
        [_market()],
    )

    assert links[0]["link_type"] == "DIRECT_LINK"
    assert links[0]["token_side_resolution_state"] == "TOKEN_SIDE_DIRECT"
    assert links[0]["candidate_actionability_hint"] == "REVALIDATION_ELIGIBLE"
    assert "token_id" in links[0]["matched_fields_json"]


def test_strong_entity_and_topic_creates_direct_link() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(
            headline="SEC approves Ethereum ETF",
            summary="Spot ETF decision affects crypto regulation.",
            entities_json=["SEC", "Ethereum"],
            topics_json=["crypto", "ETF"],
            keywords_json=["sec", "ethereum", "etf", "approval"],
            direction="YES",
        ),
        [
            _market(
                market_memory_id="memory-eth",
                market_id="eth-market",
                condition_id="eth-condition",
                slug="ethereum-etf-approval",
                title="Will an Ethereum ETF be approved by the SEC?",
                question="Will an Ethereum ETF be approved by the SEC?",
                entities_json=["Ethereum", "SEC"],
                keywords_json=["ethereum", "etf", "approval", "sec"],
                yes_token_id="eth-yes",
                no_token_id="eth-no",
            )
        ],
    )

    assert links[0]["link_type"] == "DIRECT_LINK"
    assert links[0]["link_confidence"] >= 0.85
    assert "sec" in links[0]["matched_aliases_json"]
    assert "ethereum" in links[0]["matched_aliases_json"]
    assert "entities" in links[0]["matched_fields_json"]
    assert "topics" in links[0]["matched_fields_json"]


def test_entity_only_broad_match_is_not_direct() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="Trump comments at rally", entities_json=["Trump"], keywords_json=["trump"]),
        [
            _market(
                market_memory_id="memory-trump",
                market_id="trump-market",
                condition_id="trump-condition",
                slug="trump-market",
                title="Will Donald Trump win a policy dispute?",
                question="Will Donald Trump win a policy dispute?",
                category="politics",
                entities_json=["Donald Trump"],
                tags_json=["politics"],
                keywords_json=["donald", "trump", "policy"],
                yes_token_id="trump-yes",
                no_token_id="trump-no",
            )
        ],
    )

    assert links[0]["link_type"] in {"LIKELY_LINK", "WEAK_LINK"}


def test_topic_only_broad_match_is_context_or_weak() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="Crypto regulation debate continues", topics_json=["crypto"], keywords_json=["crypto", "regulation"]),
        [
            _market(
                market_memory_id="memory-topic",
                market_id="topic-market",
                condition_id="topic-condition",
                slug="crypto-market",
                title="Will a broad crypto bill pass?",
                question="Will a broad crypto bill pass?",
                category="crypto",
                entities_json=[],
                tags_json=["crypto"],
                keywords_json=["crypto", "bill"],
                yes_token_id="topic-yes",
                no_token_id="topic-no",
            )
        ],
    )

    assert links[0]["link_type"] in {"WEAK_LINK", "CONTEXT_ONLY"}
    assert links[0]["link_type"] != "DIRECT_LINK"
