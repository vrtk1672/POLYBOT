from __future__ import annotations

from typing import Any

SECRET_MARKERS = ("secret", "token", "key", "password", "passphrase", "private")


def redact_dict(value: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in dict(value or {}).items():
        if any(marker in str(key).lower() for marker in SECRET_MARKERS):
            output[key] = "[REDACTED]"
        elif isinstance(item, dict):
            output[key] = redact_dict(item)
        else:
            output[key] = item
    return output
