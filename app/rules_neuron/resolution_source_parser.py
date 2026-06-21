from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.rules_neuron.contracts import ResolutionSourceStatus, RulesStatus, bounded


URL_PATTERN = re.compile(r"https?://[^\s),]+", re.I)
SOURCE_SENTENCE_PATTERN = re.compile(
    r"(?P<sentence>(?:the\s+)?(?:primary\s+)?resolution source for this market will be [^.]+)",
    re.I,
)
RESOLVE_BASED_ON_PATTERN = re.compile(
    r"(?P<sentence>(?:resolved?|resolves?) (?:according to|based on|by) [^.]+)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ResolutionSourceExtraction:
    status: str
    source_type: str
    source_name: str | None = None
    source_url: str | None = None
    evidence: str | None = None
    confidence: float = 0.0
    penalty: float = 0.45
    hard_block: bool = False

    @property
    def source_present(self) -> bool:
        return self.status in {"EXPLICIT", "RULES_DERIVED", "FAMILY_DERIVED", "AMBIGUOUS"}


def parse_resolution_source(rules_text: str | None, raw_market_json: dict[str, Any] | None = None, *, market_id: str = "") -> ResolutionSourceStatus:
    extraction = extract_resolution_source_truth(
        rules_text,
        raw_market_json,
        market_family=str((raw_market_json or {}).get("market_family") or ""),
    )
    raw = raw_market_json or {}
    source_name = extraction.source_name
    source_url = extraction.source_url
    domain = extract_domain(source_url)
    status = RulesStatus.UNKNOWN
    reason = extraction.evidence or "source missing or vague"
    reliability = extraction.confidence or 0.5
    if source_url and domain:
        status = RulesStatus.VERIFIED if _plausible_domain(domain) else RulesStatus.UNVERIFIED
        reason = extraction.evidence or ("explicit source url present" if status == RulesStatus.VERIFIED else "unsupported or implausible source domain")
        reliability = 0.8 if status == RulesStatus.VERIFIED else 0.35
    elif extraction.status in {"RULES_DERIVED", "FAMILY_DERIVED"}:
        status = RulesStatus.WARNING
        reliability = max(reliability, 0.55)
    elif extraction.status == "AMBIGUOUS":
        status = RulesStatus.WARNING
        reliability = max(reliability, 0.45)
    elif source_name:
        status = RulesStatus.WARNING
        reliability = max(reliability, 0.55)
    return ResolutionSourceStatus(
        market_id=market_id or str(raw.get("market_id") or raw.get("id") or ""),
        source_name=source_name,
        source_url=source_url,
        source_domain=domain,
        verification_status=status,
        verification_reason=reason,
        reliability_score=bounded(reliability, 0.5),
    )


def extract_resolution_source_truth(
    rules_text: str | None,
    raw_market_json: dict[str, Any] | None = None,
    *,
    market_family: str | None = None,
    question: str | None = None,
    category: str | None = None,
) -> ResolutionSourceExtraction:
    raw = raw_market_json or {}
    preserved = _preserved_extraction(raw)
    if preserved:
        return preserved

    explicit_url = extract_source_url(None, raw)
    explicit_name = _first_text(
        raw.get("resolution_source"),
        raw.get("resolutionSource"),
        raw.get("resolution_source_name"),
        raw.get("source"),
    )
    if explicit_url or explicit_name:
        return ResolutionSourceExtraction(
            status="EXPLICIT",
            source_type="EXPLICIT",
            source_name=explicit_name or extract_domain(explicit_url) or explicit_url,
            source_url=explicit_url,
            evidence="resolution source field present in market metadata",
            confidence=0.9 if explicit_url else 0.75,
            penalty=0.0 if explicit_url else 0.1,
        )

    text = _normalize_text(rules_text)
    if not text:
        return ResolutionSourceExtraction(
            status="MISSING",
            source_type="MISSING",
            evidence="rules text missing; no resolution source evidence",
            confidence=0.0,
            penalty=0.85,
            hard_block=True,
        )

    url = extract_source_url(text, {})
    if url:
        sentence = _sentence_containing(text, url) or f"rules text contains source URL {url}"
        return ResolutionSourceExtraction(
            status="RULES_DERIVED",
            source_type="RULES_DERIVED",
            source_name=extract_domain(url) or url,
            source_url=url,
            evidence=_trim(sentence),
            confidence=0.85,
            penalty=0.05,
        )

    source_sentence = _source_sentence(text)
    if source_sentence:
        name = _source_name_from_sentence(source_sentence)
        ambiguous = _is_ambiguous_source_sentence(source_sentence)
        return ResolutionSourceExtraction(
            status="AMBIGUOUS" if ambiguous else "RULES_DERIVED",
            source_type="AMBIGUOUS" if ambiguous else "RULES_DERIVED",
            source_name=name,
            source_url=None,
            evidence=_trim(source_sentence),
            confidence=0.55 if ambiguous else 0.68,
            penalty=0.35 if ambiguous else 0.18,
            hard_block=False,
        )

    family_source = _family_source(market_family=market_family, question=question, category=category, rules_text=text)
    if family_source:
        return family_source

    return ResolutionSourceExtraction(
        status="MISSING",
        source_type="MISSING",
        evidence="no explicit, rules-derived, or high-confidence family source found",
        confidence=0.0,
        penalty=0.45,
        hard_block=False,
    )


def extract_source_name(rules_text: str | None, raw_market_json: dict[str, Any] | None = None) -> str | None:
    raw = raw_market_json or {}
    source = raw.get("resolution_source") or raw.get("resolutionSource") or raw.get("source")
    if source:
        return str(source)
    extracted = extract_resolution_source_truth(rules_text, raw)
    if extracted.source_name:
        return extracted.source_name
    lower = (rules_text or "").lower()
    for marker in ("according to", "official source", "resolved based on", "source:"):
        if marker in lower:
            return marker
    return None


def extract_source_url(rules_text: str | None, raw_market_json: dict[str, Any] | None = None) -> str | None:
    raw = raw_market_json or {}
    url = raw.get("resolution_source_url") or raw.get("resolutionSourceUrl") or raw.get("source_url")
    if url:
        return str(url)
    match = URL_PATTERN.search(rules_text or "")
    return match.group(0) if match else None


def extract_domain(source_url: str | None) -> str | None:
    if not source_url:
        return None
    try:
        return urlparse(source_url).netloc.lower().removeprefix("www.")
    except Exception:
        return None


def classify_source_type(source_status: ResolutionSourceStatus) -> str:
    domain = source_status.source_domain or ""
    name = (source_status.source_name or "").lower()
    if any(term in domain for term in ("gov", "senate", "house", "court")) or "government" in name:
        return "government"
    if any(term in domain for term in ("nba", "nfl", "fifa", "mlb", "espn")):
        return "sports league"
    if "weather" in domain or "noaa" in domain:
        return "weather"
    if "polymarket" in domain:
        return "exchange/platform"
    if source_status.source_url:
        return "official"
    return "unknown"


def _plausible_domain(domain: str) -> bool:
    return "." in domain and not domain.endswith(".test") and " " not in domain


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _preserved_extraction(raw: dict[str, Any]) -> ResolutionSourceExtraction | None:
    status = _first_text(raw.get("resolution_source_status"), raw.get("resolutionSourceStatus"))
    if not status:
        return None
    status = status.upper()
    if status not in {"EXPLICIT", "RULES_DERIVED", "FAMILY_DERIVED", "AMBIGUOUS", "MISSING"}:
        return None
    source_type = (_first_text(raw.get("resolution_source_type"), raw.get("resolutionSourceType")) or status).upper()
    name = _first_text(raw.get("resolution_source"), raw.get("resolutionSource"), raw.get("resolution_source_name"))
    url = extract_source_url(None, raw)
    evidence = _first_text(raw.get("resolution_source_evidence"), raw.get("resolutionSourceEvidence"))
    confidence = _safe_float(raw.get("resolution_source_confidence"), default=0.0)
    penalty = _safe_float(raw.get("resolution_source_penalty"), default=0.45 if status == "MISSING" else 0.0)
    hard_block = bool(raw.get("resolution_source_hard_block") or raw.get("resolutionSourceHardBlock") or False)
    if status == "MISSING" and not evidence:
        evidence = "no explicit, rules-derived, or high-confidence family source found"
    return ResolutionSourceExtraction(
        status=status,
        source_type=source_type,
        source_name=name,
        source_url=url,
        evidence=evidence,
        confidence=confidence,
        penalty=penalty,
        hard_block=hard_block,
    )


def _safe_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _source_sentence(text: str) -> str | None:
    for pattern in (SOURCE_SENTENCE_PATTERN, RESOLVE_BASED_ON_PATTERN):
        match = pattern.search(text)
        if match:
            sentence = match.group("sentence")
            if _is_generic_resolution_phrase(_source_name_from_sentence(sentence)):
                continue
            return sentence
    return None


def _source_name_from_sentence(sentence: str) -> str:
    cleaned = re.sub(r"^(the\s+)?(primary\s+)?resolution source for this market will be\s+", "", sentence, flags=re.I)
    cleaned = re.sub(r"^(this market )?(will )?resolves?\s+(according to|based on|by)\s+", "", cleaned, flags=re.I)
    cleaned = re.split(r"\s+however\s+|\s+but\s+|\s+or\s+a consensus|\s+and\s+a consensus", cleaned, flags=re.I)[0]
    return _trim(cleaned.strip(" .,:;")) or "rules-derived source"


def _is_ambiguous_source_sentence(sentence: str) -> bool:
    lower = sentence.lower()
    ambiguous_markers = (
        "however",
        "consensus of credible reporting",
        "credible reporting",
        "also suffice",
        "also be used",
        "and/or",
        "may",
    )
    return any(marker in lower for marker in ambiguous_markers) or re.search(r"\bor\b", lower) is not None


def _is_generic_resolution_phrase(source_name: str | None) -> bool:
    lower = (source_name or "").lower().strip()
    generic_phrases = (
        "final official certification",
        "official certification",
        "final certification",
        "certification",
    )
    return any(lower == phrase or lower.startswith(f"{phrase} ") for phrase in generic_phrases)


def _sentence_containing(text: str, needle: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if needle in sentence:
            return sentence
    return None


def _family_source(
    *,
    market_family: str | None,
    question: str | None,
    category: str | None,
    rules_text: str,
) -> ResolutionSourceExtraction | None:
    combined = " ".join(str(value or "").lower() for value in (market_family, question, category, rules_text))
    if _is_generic_resolution_phrase(_source_name_from_sentence(rules_text)):
        return None
    if any(term in combined for term in ("nba", "nfl", "mlb", "fifa", "uefa", "sports")) and "official" in combined:
        return ResolutionSourceExtraction(
            status="FAMILY_DERIVED",
            source_type="FAMILY_DERIVED",
            source_name="official sports league or event source",
            evidence="sports family/rules mention official source but no explicit URL",
            confidence=0.48,
            penalty=0.3,
        )
    if any(term in combined for term in ("politics", "election", "government", "macro", "fed", "senate", "congress")) and "official" in combined:
        return ResolutionSourceExtraction(
            status="FAMILY_DERIVED",
            source_type="FAMILY_DERIVED",
            source_name="official government or macro source",
            evidence="politics/macro family/rules mention official source but no explicit URL",
            confidence=0.48,
            penalty=0.3,
        )
    return None


def _trim(value: str, limit: int = 360) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
