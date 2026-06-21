from __future__ import annotations

import pytest

from app.services.ai_mesh_intelligence import _validate_ai_contract


def test_valid_json_passes_schema() -> None:
    payload, repaired = _validate_ai_contract(
        {
            "summary": "ok",
            "confidence": 0.6,
            "direction_hint": "YES",
            "thesis_type": "PAYOUT_DISCREPANCY",
            "recommended_mesh_action": "BUILD_THESIS",
            "missing_evidence": [],
            "why_not": [],
        },
        task="THESIS",
    )

    assert payload["_schema_valid"] is True
    assert repaired is False


def test_missing_fields_are_repaired_safely() -> None:
    payload, repaired = _validate_ai_contract({"summary": "ok"}, task="THESIS")

    assert repaired is True
    assert payload["confidence"] == 0.0
    assert payload["direction_hint"] == "UNKNOWN"
    assert payload["thesis_type"] == "UNKNOWN"


def test_invalid_critical_field_triggers_schema_invalid() -> None:
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID"):
        _validate_ai_contract({"summary": "bad", "thesis_type": "MAGIC_ALPHA"}, task="THESIS")
