from __future__ import annotations

from app.rules_neuron.resolution_source_parser import extract_domain, parse_resolution_source
from app.rules_neuron.source_verification_guard import verify_resolution_source


def test_explicit_source_url_parsed_and_verified() -> None:
    source = parse_resolution_source("Resolved by official source https://www.noaa.gov/storm", {}, market_id="m1")
    verified = verify_resolution_source(source)
    assert extract_domain(source.source_url) == "noaa.gov"
    assert verified.verification_status == "VERIFIED"


def test_vague_or_missing_source_marked_unknown_or_unverified() -> None:
    vague = parse_resolution_source("Resolved according to official source.", {}, market_id="m1")
    missing = verify_resolution_source(parse_resolution_source(None, {}, market_id="m2"))
    assert vague.verification_status == "WARNING"
    assert missing.verification_status == "UNVERIFIED"

