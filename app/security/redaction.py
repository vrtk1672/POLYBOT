from __future__ import annotations

import re
from collections.abc import Iterable


SECRET_KEYWORDS = (
    "api_key",
    "apikey",
    "secret",
    "passphrase",
    "password",
    "private_key",
    "bearer",
    "token",
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=\-]{16,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----[\s\S]+?-----END\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----"),
)

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<key>[A-Z0-9_]*(?:API_KEY|SECRET|PASSPHRASE|PASSWORD|PRIVATE_KEY|BEARER_TOKEN|CLIENT_SECRET|API_HASH)[A-Z0-9_]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>['\"]?)"
    r"(?P<value>[^\s,'\"}]+)"
    r"(?P=quote)",
    re.IGNORECASE,
)

LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-+/=]{32,}\b")
HASH_LABEL_RE = re.compile(r"(?:hash|fingerprint|digest|checksum|sha256|sha1|md5)", re.IGNORECASE)


def mask_secret(value: object, *, visible: int = 4) -> str:
    text = "" if value is None else str(value)
    if not text:
        return "MISSING"
    if len(text) <= visible * 2:
        return "*" * len(text)
    return f"{text[:visible]}...{text[-visible:]}"


def redact_secrets(text: object, *, known_secret_values: Iterable[str] | None = None) -> str:
    redacted = "" if text is None else str(text)
    for secret in known_secret_values or ():
        if secret:
            redacted = redacted.replace(str(secret), mask_secret(secret))
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)

    def replace_assignment(match: re.Match[str]) -> str:
        return f"{match.group('key')}{match.group('sep')}[REDACTED_SECRET]"

    redacted = SECRET_ASSIGNMENT_RE.sub(replace_assignment, redacted)
    return redacted


def contains_secret_like_value(text: object) -> bool:
    value = "" if text is None else str(text)
    if not value:
        return False
    if "risk-" in value.lower() and not any(keyword in value.lower() for keyword in SECRET_KEYWORDS):
        return False
    if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
        return True
    if SECRET_ASSIGNMENT_RE.search(value):
        return True
    for match in LONG_TOKEN_RE.finditer(value):
        candidate = match.group(0)
        if "_" in candidate and candidate.upper() == candidate:
            continue
        start = max(0, match.start() - 32)
        context = value[start : match.end() + 32]
        if HASH_LABEL_RE.search(context):
            continue
        if any(keyword in context.lower() for keyword in SECRET_KEYWORDS):
            return True
    return False


def value_status(value: object) -> str:
    return "PRESENT" if value not in (None, "") else "MISSING"
