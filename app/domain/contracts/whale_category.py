from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WhaleCategoryContract:
    id: str
    wallet_address: str
    whale_profile_id: str
    whale_category_run_id: str
    primary_category: str
    secondary_categories_json: list[str] = field(default_factory=list)
    category_confidence: float = 0.0
    specialization_context_json: dict[str, object] = field(default_factory=dict)
    category_reason_codes_json: list[str] = field(default_factory=list)
    category_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    categorizer_version: str = ""
