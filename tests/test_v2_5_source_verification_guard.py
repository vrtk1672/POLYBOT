from __future__ import annotations

from app.rules_neuron.contracts import ResolutionSourceStatus
from app.rules_neuron.source_verification_guard import source_warning_or_block, verify_resolution_source


def test_source_verification_status_affects_warning() -> None:
    verified = verify_resolution_source(ResolutionSourceStatus(market_id="m1", source_url="https://sec.gov/filing", source_domain="sec.gov"))
    missing = verify_resolution_source(ResolutionSourceStatus(market_id="m2"))
    assert verified.verification_status == "VERIFIED"
    assert missing.verification_status == "UNVERIFIED"
    assert source_warning_or_block(missing)[0] == "UNVERIFIED_SOURCE"

