from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def json_safe(value: Any) -> Any:
    """Return a value that can be serialized by the standard JSON encoder."""
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(json_safe(item) for item in value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "to_api_dict"):
        return json_safe(value.to_api_dict())
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump(mode="json"))
    return value


def json_dumps(value: Any, **kwargs: Any) -> str:
    return json.dumps(json_safe(value), **kwargs)
