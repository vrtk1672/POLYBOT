from __future__ import annotations

from app.services.source_event_memory import SourceEventMemoryService


def _event(**overrides):
    event = {
        "source_event_id": "event-guardrail",
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
        "market_memory_id": "memory-guardrail",
        "market_id": "guardrail-market",
        "condition_id": "guardrail-condition",
        "slug": "guardrail-market",
        "title": "Will a crypto ETF be approved?",
        "question": "Will a crypto ETF be approved?",
        "category": "crypto",
        "entities_json": [],
        "tags_json": ["crypto"],
        "keywords_json": ["crypto", "etf", "approval"],
        "yes_token_id": "guardrail-yes",
        "no_token_id": "guardrail-no",
    }
    market.update(overrides)
    return market


def test_low_confidence_remains_not_revalidation_eligible() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="Broad market update", keywords_json=["market"]),
        [_market()],
    )

    assert links[0]["link_type"] in {"NO_LINK", "CONTEXT_ONLY", "WEAK_LINK"}
    assert links[0]["eligible_for_targeted_revalidation"] is False
    assert links[0]["candidate_actionability_hint"] in {"NOT_RELEVANT", "CONTEXT_ONLY", "BLOCKED_BY_LOW_CONFIDENCE"}


def test_weak_and_context_links_are_not_revalidation_eligible() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(headline="Crypto regulation policy chatter", topics_json=["crypto"], keywords_json=["crypto", "regulation", "policy"]),
        [
            _market(
                title="Will a crypto regulation bill pass?",
                question="Will a crypto regulation bill pass?",
                keywords_json=["crypto", "regulation", "bill"],
            )
        ],
    )

    assert links[0]["link_type"] in {"WEAK_LINK", "CONTEXT_ONLY"}
    assert links[0]["eligible_for_targeted_revalidation"] is False
    assert links[0]["candidate_actionability_hint"] == "CONTEXT_ONLY"


def test_token_side_unknown_creates_watch_only_hint() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(
            headline="SEC ETF approval deadline approaches",
            summary="Crypto ETF decision is expected soon.",
            topics_json=["crypto", "ETF"],
            keywords_json=["sec", "etf", "approval", "deadline"],
            direction="UNKNOWN",
        ),
        [_market()],
    )

    assert links[0]["link_type"] in {"DIRECT_LINK", "LIKELY_LINK"}
    assert links[0]["token_side_resolution_state"] in {"MARKET_LEVEL_ONLY", "TOKEN_SIDE_UNKNOWN"}
    assert links[0]["candidate_actionability_hint"] == "WATCH_ONLY"
    assert links[0]["guardrail_reason"] == "TOKEN_SIDE_OR_DIRECTION_NOT_CANDIDATE_ACTIONABLE"


def test_high_confidence_directional_link_is_revalidation_eligible() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(
            headline="SEC approves Bitcoin ETF",
            summary="The decision supports ETF approval markets.",
            entities_json=["SEC", "Bitcoin"],
            topics_json=["crypto", "ETF"],
            keywords_json=["sec", "bitcoin", "etf", "approval"],
            direction="YES",
        ),
        [_market(entities_json=["SEC", "Bitcoin"], keywords_json=["sec", "bitcoin", "etf", "approval"])],
    )

    assert links[0]["link_type"] == "DIRECT_LINK"
    assert links[0]["eligible_for_targeted_revalidation"] is True
    assert links[0]["candidate_actionability_hint"] in {"REVALIDATION_ELIGIBLE", "WATCH_ONLY"}


def test_token_side_conflict_is_blocked_by_conflict() -> None:
    links = SourceEventMemoryService()._build_links(
        _event(token_id="guardrail-yes", direction="NO", headline="Conflicting side update"),
        [_market()],
    )

    assert links[0]["link_type"] == "DIRECT_LINK"
    assert links[0]["token_side_resolution_state"] == "TOKEN_SIDE_CONFLICT"
    assert links[0]["candidate_actionability_hint"] == "BLOCKED_BY_CONFLICT"
    assert links[0]["eligible_for_targeted_revalidation"] is False
