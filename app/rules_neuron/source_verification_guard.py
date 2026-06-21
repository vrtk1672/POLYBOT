from __future__ import annotations

from app.rules_neuron.contracts import ResolutionSourceStatus, RulesStatus


def verify_resolution_source(source_status: ResolutionSourceStatus) -> ResolutionSourceStatus:
    domain = source_status.source_domain
    if domain:
        reliability = classify_domain_reliability(domain)
        status = RulesStatus.VERIFIED if reliability >= 0.65 else RulesStatus.UNVERIFIED
        return source_status.model_copy(update={"verification_status": status, "verification_reason": "deterministic domain check", "reliability_score": reliability})
    if source_status.source_name:
        return source_status.model_copy(update={"verification_status": RulesStatus.WARNING, "verification_reason": "source named but no URL"})
    return source_status.model_copy(update={"verification_status": RulesStatus.UNVERIFIED, "verification_reason": "resolution source missing"})


def classify_domain_reliability(domain: str | None) -> float:
    if not domain:
        return 0.25
    domain = domain.lower()
    if any(part in domain for part in ("gov", "court", "nba.com", "nfl.com", "mlb.com", "fifa.com", "noaa.gov", "sec.gov")):
        return 0.9
    if any(part in domain for part in ("polymarket.com", "reuters.com", "apnews.com", "espn.com")):
        return 0.75
    if "." in domain and "example" not in domain:
        return 0.6
    return 0.3


def source_warning_or_block(source_status: ResolutionSourceStatus) -> tuple[str, str] | None:
    if source_status.verification_status in {RulesStatus.UNVERIFIED, RulesStatus.BROKEN}:
        return ("UNVERIFIED_SOURCE", source_status.verification_reason or "source is unverified")
    if source_status.verification_status in {RulesStatus.UNKNOWN, RulesStatus.WARNING}:
        return ("UNCLEAR_RESOLUTION", source_status.verification_reason or "source requires review")
    return None

