from __future__ import annotations

from typing import Any


SECRET_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "passphrase",
    "private",
    "credential",
    "api_key",
    "api_secret",
    "authorization",
    "bearer",
    "key",
)


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_dict(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


def redact_dict(value: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key).lower()
        if any(marker in key_text for marker in SECRET_KEY_MARKERS):
            output[key] = "<redacted>"
        else:
            output[key] = redact_value(item)
    return output


def redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = str(value)
    for marker in SECRET_KEY_MARKERS:
        if marker in redacted.lower():
            return "<redacted>"
    return redacted
